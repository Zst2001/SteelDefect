"""Offline batch orchestration: private SQLite, synthetic pixels, fake CPU/queue."""
import io
import hashlib
import json
import sys
from unittest.mock import Mock
from pathlib import Path

if 'app.config' not in sys.modules or sys.modules['app.config'].Settings.__name__!='OfflineSettings':
    raise RuntimeError('Use the isolated phase-A runner')

import numpy as np
import pytest
from PIL import Image
from app.db.models import Artifact,AuditLog,DatasetVersion,MetricSet,Task,TaskModel,Sample,User
from app.errors import AppError
from app.services import pcb_batch as batch,pcb_segmentation as single
from app.services.dispatch import Delivery
from app.services.records import submit_to_advisor,withdraw_from_advisor,rerun_record
from app.services.input_freeze import verify_inputs
from apps.worker import jobs,pcb_segmentation as worker
from app.routers import pcb_segmentation as router
from test_pcb_backend import pcb,file
from test_phase_a_authorization import lab,client


@pytest.fixture
def group(pcb,monkeypatch):
    monkeypatch.setattr(batch,'get_settings',lambda:pcb.lab.settings)
    def compute(slug,image,cam,root,plan):
        h,w=image.shape[:2]; pred=np.zeros((h,w),np.uint8);pred[:h//2,:w//2]=1
        layers={'pred_mask':pred,'probability':pred.astype(np.float32),'probability_heatmap':image,
                'overlay':image,'boundary':image}
        status='not_requested'
        if cam:
            status='ok' if plan['cam_supported'] else 'not_supported_for_size'
            if status=='ok':layers['cam']=image
        return layers,{'status':status}
    monkeypatch.setattr(worker,'compute_adapted',compute)
    return pcb


def upload(group,count=2,*,gt=True,size=(512,384)):
    manifest={'files':[]};files={}
    for i in range(count):
        dims=(220,220) if i==0 else size
        name,data=file(size=dims,name=f'image-{i}.png')
        row={'client_file_id':f'client-{i}','file_field':f'image_{i}'}
        files[row['file_field']]=(name,data,'image/png')
        if i==0 and gt:
            name,data=file(mode='L',value=255,name='image-0_gt.png')
            row['gt_field']='gt_0';files['gt_0']=(name,data,'image/png')
        manifest['files'].append(row)
    result=batch.create_group(group.lab.db,group.lab.owner,manifest,files,group.lab.settings)
    return result,manifest,files


def submit(group,parent,**options):
    return batch.submit_group(group.lab.db,group.lab.owner,batch_id=parent['batch_id'],
                              model_ids=options.pop('model_ids',list(single.MODELS)),idempotency_key=options.pop('key','key'),
                              settings=group.lab.settings,**options)


def tasks(result):return [t for s in result['samples'] for t in s['tasks']]


def test_2_images_3_models_private_publication_and_rerun(group):
    lab=group.lab;parent,_,_=upload(group)
    result=submit(group,parent,include_cam=True,accept_unsupported_cam=True)
    assert result['counts']=={'total':6,'queued':6,'running':0,'success':0,'failed':0}
    assert group.queue.call_count==6
    for row in tasks(result):jobs.run_pcb_segmentation(row['id'])
    lab.db.expire_all();result=batch.get_group(lab.db,lab.owner,parent['batch_id'],settings=lab.settings)
    assert result['status']=='success' and result['counts']['success']==6
    assert lab.db.query(MetricSet).count()==3
    for sample in result['samples']:
        for row in sample['tasks']:
            assert row['metrics']['available']==sample['has_gt']
            assert row['cam']['status']==('ok' if sample['has_gt'] else 'not_supported_for_size')
            with client(lab,lab.owner) as http:
                for a in row['artifacts']:
                    response=http.get(a['url']);assert response.status_code==200
                    if a['url'].endswith('.png'):
                        assert Image.open(io.BytesIO(response.content)).size==(sample['width'],sample['height'])
    first=tasks(result)[0]
    for user in (lab.peer,lab.advisor):
        with pytest.raises(AppError):batch.get_group(lab.db,user,parent['batch_id'],settings=lab.settings)
    submit_to_advisor(lab.db,lab.owner,first['id'])
    visible=batch.get_group(lab.db,lab.advisor,parent['batch_id'],settings=lab.settings)
    assert visible['counts']['total']==1 and len(visible['samples'])==1
    assert [t['id'] for t in tasks(visible)]==[first['id']]
    withdraw_from_advisor(lab.db,lab.owner,first['id'])
    with pytest.raises(AppError):batch.get_group(lab.db,lab.advisor,parent['batch_id'],settings=lab.settings)
    new=rerun_record(lab.db,lab.owner,first['id']);jobs.run_pcb_segmentation(new.id)
    assert new.id!=first['id']
    assert batch.get_group(lab.db,lab.owner,parent['batch_id'],settings=lab.settings)['counts']['total']==7


def test_10_by_3_atomic_idempotency_and_pagination(group):
    parent,_,_=upload(group,count=10,gt=False,size=(220,220))
    result=submit(group,parent)
    assert len(tasks(result))==30 and group.queue.call_count==30
    assert group.lab.db.query(Task).count()==group.lab.db.query(TaskModel).count()==30
    again=submit(group,parent)
    assert {r['id'] for r in tasks(again)}=={r['id'] for r in tasks(result)} and group.queue.call_count==30
    page=batch.get_group(group.lab.db,group.lab.owner,parent['batch_id'],page_size=7,settings=group.lab.settings)
    assert len(tasks(page))==7 and page['counts']['total']==30 and page['pagination']['has_more']
    for options in ({'model_ids':['unet']},{'include_cam':True},{'accept_unsupported_cam':True}):
        with pytest.raises(AppError) as exc:submit(group,parent,**options)
        assert exc.value.code=='IDEMPOTENCY_CONFLICT'


def test_key_conflict_across_batch_and_new_key_is_new_submission(group):
    one,_,_=upload(group,count=1);two,_,_=upload(group,count=1)
    result=submit(group,one,model_ids=['unet'])
    with pytest.raises(AppError) as exc:submit(group,two,model_ids=['unet'])
    assert exc.value.code=='IDEMPOTENCY_CONFLICT'
    result=submit(group,one,model_ids=['unet_resnet18'],key='new-key')
    assert result['counts']['total']==2 and group.queue.call_count==2


@pytest.mark.parametrize('state',['rejected','unknown','exception'])
def test_one_delivery_failure_preserves_siblings(group,monkeypatch,state):
    parent,_,_=upload(group,count=1,gt=False)
    def send(_s,_f,ident,_t,**kw):
        if send.calls==0:
            send.calls+=1
            if state=='exception':raise OSError('synthetic transport ambiguity')
            return Delivery(state,'task-'+ident)
        return Delivery('confirmed','task-'+ident)
    send.calls=0;monkeypatch.setattr(single,'enqueue',send)
    result=submit(group,parent)
    bad=[t for t in tasks(result) if t['error_summary']]
    assert len(bad)==1
    for row in tasks(result):
        if not row['error_summary']:jobs.run_pcb_segmentation(row['id'])
    group.lab.db.expire_all();result=batch.get_group(group.lab.db,group.lab.owner,parent['batch_id'],settings=group.lab.settings)
    assert result['counts']['success']==2
    if state=='rejected':assert result['status']=='partial_failed'
    else:assert result['status']=='queued' and 'QUEUE_UNKNOWN' in bad[0]['error_summary']


def test_full_validation_before_persistence(group):
    _,manifest,files=upload(group,count=2)
    before=group.lab.db.query(DatasetVersion).count()
    files['image_1']=('broken.png',b'broken','image/png')
    with pytest.raises(AppError):batch.create_group(group.lab.db,group.lab.owner,manifest,files,group.lab.settings)
    assert group.lab.db.query(DatasetVersion).count()==before
    assert group.lab.db.query(Task).count()==0


@pytest.mark.parametrize('value',[{}, {'files':[]},{'files':[{}]}, {'files':[{'client_file_id':'x','file_field':'manifest'}]},
    {'files':[{'client_file_id':'x','file_field':'a'},{'client_file_id':'x','file_field':'b'}]},
    {'files':[{'client_file_id':'x','file_field':'a','gt_field':'a'}]},
    {'files':[{'client_file_id':'x','file_field':'a','unknown':1}]},
    {'files':[{'client_file_id':'x','file_field':'a'}]*11}])
def test_invalid_manifests(value):
    with pytest.raises(AppError):batch.validate_manifest(value)


@pytest.mark.parametrize('mode,size,fmt,name,mime',[
    ('RGBA',(220,220),'PNG','a.png','image/png'),('I;16',(220,220),'PNG','a.png','image/png'),
    ('CMYK',(220,220),'JPEG','a.jpg','image/jpeg'),('RGB',(2049,5),'PNG','a.png','image/png'),
    ('RGB',(220,220),'PNG','a.jpg','image/jpeg'),('RGB',(220,220),'PNG','../a.png','image/png'),
    ('RGB',(220,220),'PNG','a.png','image/jpeg'),('RGB',(220,220),'BMP','a.bmp','image/bmp')])
def test_invalid_extended_images(mode,size,fmt,name,mime):
    _,content=file(mode=mode,size=size,fmt=fmt)
    with pytest.raises(AppError):batch.decode_image(name,content,mime=mime)


@pytest.mark.parametrize('size',[(110,110),(220,220),(221,300),(512,384),(1024,1024),(2048,1)])
def test_gray_and_sizes_preserve_upload_bytes(size):
    name,content=file(mode='L',size=size)
    actual,_,meta=batch.decode_image(name,content,mime='image/png')
    assert actual==content and meta['input_plan']['gray_to_rgb'] and not meta['input_plan']['cam_supported']
    assert (meta['width'],meta['height'])==size


def test_gt_exact_size_binary_and_cam_ack(group):
    parent,_,_=upload(group)
    with pytest.raises(AppError) as exc:submit(group,parent,include_cam=True)
    assert exc.value.code=='PCB_CAM_ACK_REQUIRED' and group.lab.db.query(Task).count()==0
    for dims,value in [((221,220),255),((220,220),2)]:
        name,content=file(mode='L',size=dims,value=value)
        with pytest.raises(AppError):batch.decode_image(name,content,gt=True,expected_size=(220,220))


def _gt_png(mode='P', *, invert=False, colors=None, transparency=None):
    """Synthetic palette resembles the reported files, including non-label indices."""
    truth=np.zeros((220,220),np.uint8);truth[:110,:110]=1
    image=Image.fromarray(truth*255)
    if mode=='P':
        indices=np.where(truth==1,0 if invert else 215,215 if invert else 0).astype(np.uint8)
        image=Image.fromarray(indices).convert('P')
        palette=[0]*768
        palette[3*215:3*215+3]=[0,0,0] if invert else [255,255,255]
        palette[:3]=[255,255,255] if invert else [0,0,0]
        palette[3*100:3*100+3]=[255,0,0]  # Unused color is not a pixel class.
        if colors:
            for index,color in colors.items():palette[3*index:3*index+3]=color
        image.putpalette(palette)
    else:image=image.convert(mode)
    stream=io.BytesIO();options={} if transparency is None else {'transparency':transparency}
    image.save(stream,format='PNG',**options)
    return stream.getvalue(),truth


@pytest.mark.parametrize('mode,invert',[('1',False),('L',False),('RGB',False),('P',False),('P',True)])
def test_lossless_binary_gt_encodings_preserve_pixels(mode,invert):
    original,truth=_gt_png(mode,invert=invert)
    actual,extension,meta=batch.decode_image('any-unrelated-name.png',original,gt=True,expected_size=(220,220))
    with Image.open(io.BytesIO(actual)) as image:
        assert image.mode=='L' and image.size==(220,220)
        np.testing.assert_array_equal(np.asarray(image),truth)
    assert extension=='png' and meta['mode']=='L' and meta['source_mode']==mode
    assert meta['sha256']==hashlib.sha256(actual).hexdigest()
    assert meta['source_sha256']==hashlib.sha256(original).hexdigest()
    assert meta['source_bytes']==len(original) and meta['bytes']==len(actual)
    repeated,_,_=batch.decode_image('gt.png',actual,gt=True,expected_size=(220,220))
    assert repeated==actual  # Worker revalidation remains idempotent.


@pytest.mark.parametrize('colors,transparency',[
    ({215:[255,0,0]},None),({215:[127,127,127]},None),
    (None,215),(None,bytes([255]*215+[128])),
])
def test_palette_gt_rejects_ambiguous_used_colors_or_alpha(colors,transparency):
    original,_=_gt_png(colors=colors,transparency=transparency)
    with pytest.raises(AppError) as exc:batch.decode_image('mask.png',original,gt=True)
    assert exc.value.code=='PCB_BAD_GT'


def test_palette_gt_allows_unused_transparency_but_not_palette_original():
    original,truth=_gt_png(transparency=100)
    actual,_,_=batch.decode_image('mask.png',original,gt=True)
    with Image.open(io.BytesIO(actual)) as image:np.testing.assert_array_equal(np.asarray(image),truth)
    with pytest.raises(AppError) as exc:batch.decode_image('original.png',original)
    assert exc.value.code=='PCB_BAD_IMAGE'


@pytest.mark.parametrize('mode,value,options',[
    ('RGB',(255,0,0),{}),('RGB',(42,42,42),{}),('RGB',(255,255,255),{'transparency':(255,255,255)}),
    ('L',255,{'transparency':255}),('RGBA',(255,255,255,255),{}),('LA',(255,255),{}),
    ('I;16',255,{}),
])
def test_gt_rejects_colored_multilevel_transparent_or_unsupported_pixels(mode,value,options):
    stream=io.BytesIO();Image.new(mode,(220,220),value).save(stream,format='PNG',**options)
    with pytest.raises(AppError) as exc:batch.decode_image('mask.png',stream.getvalue(),gt=True)
    assert exc.value.code=='PCB_BAD_GT'


def test_palette_gt_http_manifest_freeze_and_metrics(group):
    lab=group.lab;_,original=file();mask,truth=_gt_png(invert=True)
    manifest={'files':[{'client_file_id':'user-order-first','file_field':'photo','gt_field':'label'}]}
    with client(lab,lab.owner) as http:
        http.app.include_router(router.router,prefix='/api')
        uploaded=http.post('/api/scenes/pcb/segmentation/uploads/batch',data={'manifest':json.dumps(manifest)},files={
            'photo':('photo-A.png',original,'image/png'),
            'label':('different-name-mask.png',mask,'image/png')})
        assert uploaded.status_code==200,uploaded.text
        result=submit(group,uploaded.json(),model_ids=['unet'])
        ident=tasks(result)[0]['id'];jobs.run_pcb_segmentation(ident)
        lab.db.expire_all();payload=http.get('/api/tasks/'+ident).json()
        assert payload['status']=='success' and payload['metrics']['available']
        assert payload['metrics']['tp']==int(truth.sum())
        assert payload['metrics']['fp']==payload['metrics']['fn']==0
        gt=next(a for a in payload['artifacts'] if a['kind']=='gt')
        with Image.open(io.BytesIO(http.get(gt['url']).content)) as image:
            assert image.mode=='L';np.testing.assert_array_equal(np.asarray(image),truth)
        task=lab.db.get(Task,ident);meta=lab.db.get(DatasetVersion,task.dataset_version_id).class_map_json
        assert meta['gt_facts']['source_mode']=='P' and meta['gt_facts']['mode']=='L'
        assert lab.db.query(MetricSet).filter_by(task_id=ident).count()==1


def test_window_budget_and_disabled_creation(group):
    parent,_,_=upload(group,count=3,gt=False,size=(2048,2048))
    with pytest.raises(AppError) as exc:submit(group,parent)
    assert exc.value.code=='PCB_WINDOW_BUDGET' and group.lab.db.query(Task).count()==0
    object.__setattr__(group.lab.settings,'pcb_segmentation_enabled',False)
    with pytest.raises(AppError) as exc:submit(group,parent,model_ids=['unet'])
    assert exc.value.code=='PCB_DISABLED'
    assert batch.get_group(group.lab.db,group.lab.owner,parent['batch_id'],settings=group.lab.settings)['status']=='uploaded'


@pytest.mark.parametrize('when',['queued','publishing'])
@pytest.mark.parametrize('change',['extension','origin','gt','actor','flag'])
def test_frozen_extension_and_publishing_revocation(group,monkeypatch,when,change):
    parent,_,_=upload(group,count=1,gt=True)
    task=tasks(submit(group,parent,model_ids=['unet']))[0]
    model=group.lab.db.get(Task,task['id'])
    version=group.lab.db.get(DatasetVersion,model.dataset_version_id)
    def revoke():
        if change=='extension':version.class_map_json={**version.class_map_json,'extension_hash':'tampered'}
        elif change in {'origin','gt'}:
            from app.services.storage import resolve_uri
            sample=group.lab.db.query(Sample).filter_by(version_id=version.id).one()
            resolve_uri(sample.origin_uri if change=='origin' else sample.mask_uri,group.lab.settings).write_bytes(b'changed')
        elif change=='actor':group.lab.db.get(User,group.lab.owner.id).status='disabled'
        else:object.__setattr__(group.lab.settings,'pcb_segmentation_enabled',False)
        group.lab.db.commit()
    if when=='queued':revoke()
    else:
        compute=worker.compute_adapted
        def replace(*args):
            result=compute(*args);revoke();return result
        monkeypatch.setattr(worker,'compute_adapted',replace)
    with pytest.raises(AppError):jobs.run_pcb_segmentation(model.id)
    group.lab.db.expire_all()
    assert group.lab.db.get(Task,model.id).status=='failed'
    assert group.lab.db.query(Artifact).filter_by(task_id=model.id).count()==0


def test_http_manifest_and_batch_contract(group):
    lab=group.lab
    name,content=file()
    manifest={'files':[{'client_file_id':'one','file_field':'img'}]}
    with client(lab,lab.owner) as http:
        http.app.include_router(router.router,prefix='/api')
        response=http.post('/api/scenes/pcb/segmentation/uploads/batch',data={'manifest':json.dumps(manifest)},files={'img':(name,content,'image/png')})
        assert response.status_code==200,response.text
        ident=response.json()['batch_id']
        body={'batch_id':ident,'model_ids':['unet']}
        assert http.post('/api/scenes/pcb/segmentation/tasks/batch',json=body).status_code==422
        response=http.post('/api/scenes/pcb/segmentation/tasks/batch',json=body,headers={'Idempotency-Key':'http-key'})
        assert response.status_code==200,response.text
        assert http.get(f'/api/scenes/pcb/segmentation/batches/{ident}').json()['counts']['total']==1
        assert http.get(f'/api/scenes/pcb/segmentation/batches/{ident}?page_size=1000').status_code==422
        for extra in ({'unknown':'x'},{'img':'not-upload'}):
            assert http.post('/api/scenes/pcb/segmentation/uploads/batch',data={'manifest':json.dumps(manifest),**extra},files={'img':(name,content,'image/png')}).status_code==400


def test_extended_gt_metrics_and_legacy_endpoint_cannot_bypass(group):
    lab=group.lab
    manifest={'files':[{'client_file_id':'big','file_field':'origin','gt_field':'gt'}]}
    files={key:(name,data,'image/png') for key,(name,data) in {
        'origin':file(size=(512,384)), 'gt':file(mode='L',size=(512,384),value=255,name='gt.png')}.items()}
    parent=batch.create_group(lab.db,lab.owner,manifest,files,lab.settings)
    child=lab.db.get(DatasetVersion,parent['batch_id']).class_map_json['children'][0]['version_id']
    with client(lab,lab.owner) as http:
        http.app.include_router(router.router,prefix='/api')
        response=http.post('/api/scenes/pcb/segmentation/tasks',json={'batch_id':child,'model_id':'unet','include_cam':True})
        assert response.status_code==409 and response.json()['code']=='PCB_BATCH_ENDPOINT_REQUIRED'
    result=submit(group,parent,model_ids=['unet'],include_cam=True,accept_unsupported_cam=True)
    ident=tasks(result)[0]['id'];jobs.run_pcb_segmentation(ident);lab.db.expire_all()
    task=lab.db.get(Task,ident)
    assert task.status=='success' and task.metric_set.scope=='pcb_uploaded_pair'
    result=batch.get_group(lab.db,lab.owner,parent['batch_id'],settings=lab.settings)
    assert tasks(result)[0]['metrics']['available']
    with client(lab,lab.owner) as http:
        for artifact in tasks(result)[0]['artifacts']:
            if artifact['kind'] in {'gt','error'}:
                assert Image.open(io.BytesIO(http.get(artifact['url']).content)).size==(512,384)


def test_multipart_declared_and_chunked_wire_budget(group,monkeypatch):
    lab=group.lab;original_limits=batch.limits
    monkeypatch.setattr(batch,'limits',lambda:{**original_limits(),'max_batch_bytes':1024})
    with client(lab,lab.owner) as http:
        http.app.include_router(router.router,prefix='/api')
        url='/api/scenes/pcb/segmentation/uploads/batch'
        response=http.post(url,content=b'',headers={'Content-Length':str(2*1024*1024),'Content-Type':'multipart/form-data; boundary=x'})
        assert response.status_code==413
        boundary=b'--x\r\nContent-Disposition: form-data; name="img"; filename="large.png"\r\nContent-Type: image/png\r\n\r\n'
        chunks=iter([boundary,b'x'*700000,b'x'*700000,b'\r\n--x--\r\n'])
        response=http.post(url,content=chunks,headers={'Content-Type':'multipart/form-data; boundary=x'})
        assert response.status_code==400 and 'exceeds batch byte limit' in response.text
        assert lab.db.query(Task).count()==0


@pytest.mark.parametrize('width,height,mode,include_cam',[(220,220,'RGB',True),(221,300,'RGB',True),(220,220,'L',True),(512,384,'RGB',False)])
def test_adapter_dispatch_preserves_native_cam(monkeypatch,width,height,mode,include_cam):
    from infer.pcb import tiling
    original=Mock(return_value=({'native':True},{'status':'ok'}))
    adapted=Mock(return_value=({'adapted':True},{}))
    monkeypatch.setattr(worker,'compute',original);monkeypatch.setattr(tiling,'predict_tiled',adapted)
    result,cam=worker.compute_adapted('unet',np.zeros((height,width,3),np.uint8),include_cam,None,tiling.plan(width,height,mode))
    native=mode=='RGB' and (width,height)==(220,220)
    assert original.call_count==int(native) and adapted.call_count==int(not native)
    assert cam['status']==('ok' if native else 'not_supported_for_size' if include_cam else 'not_requested')


def test_adapter_timeout_and_postcheck_propagate(monkeypatch):
    from infer.pcb import tiling
    from rq.timeouts import JobTimeoutException
    p=tiling.plan(220,220,'RGB');image=np.zeros((220,220,3),np.uint8)
    monkeypatch.setattr(worker,'compute',Mock(side_effect=JobTimeoutException('deadline')))
    with pytest.raises(JobTimeoutException):worker.compute_adapted('unet',image,True,None,p)
    monkeypatch.setattr(worker,'compute',Mock(return_value=({},{})))
    monkeypatch.setattr(tiling,'assert_current_source',Mock(side_effect=[None,ValueError('changed')]))
    with pytest.raises(ValueError):worker.compute_adapted('unet',image,False,None,p)


@pytest.mark.parametrize('failed_file',['image.png','gt.png'])
def test_partial_upload_write_rolls_back_rows_and_removes_owned_files(group,monkeypatch,failed_file):
    lab=group.lab
    before_versions=lab.db.query(DatasetVersion).count()
    before_audits=lab.db.query(AuditLog).count()
    actual_open=Path.open
    touched=[]
    class BrokenWrite:
        def __init__(self,path,args,kwargs):self.handle=actual_open(path,*args,**kwargs)
        def __enter__(self):return self
        def __exit__(self,*_):self.handle.close()
        def write(self,data):
            self.handle.write(data[:17])
            self.handle.flush()
            raise OSError('synthetic disk-full after partial write')
    def open_file(path,*args,**kwargs):
        if args and args[0]=='xb' and path.name==failed_file and path.is_relative_to(lab.settings.storage_path/'pcb'):
            touched.append(path)
            return BrokenWrite(path,args,kwargs)
        return actual_open(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',open_file)
    with pytest.raises(OSError,match='synthetic disk-full'):
        upload(group,count=1,gt=True)
    assert len(touched)==1 and not touched[0].exists() and not touched[0].parent.exists()
    assert list((lab.settings.storage_path/'pcb').iterdir())==[]
    assert lab.db.query(DatasetVersion).count()==before_versions
    assert lab.db.query(AuditLog).count()==before_audits
    assert lab.db.query(Task).count()==lab.db.query(TaskModel).count()==0
    group.queue.assert_not_called()
