"""Persistent PCB batch coordinator; each image retains an isolated legacy version.

The parent stores only identities. Existing single-task permissions, file guards,
reruns and atomic publication remain authoritative for each image/model result.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import warnings

import numpy as np
from PIL import Image

from app.config import get_settings
from app.db.models import AuditLog, Dataset, DatasetVersion, Sample, Task, TaskModel
from app.errors import AppError
from app.services import pcb_segmentation as single
from app.services.dispatch import Delivery, apply_task_delivery
from app.services.input_freeze import lock_version, manifest_path
from app.services.submission import lock_user, request_id
from app.util_time import new_id
from infer.pcb.tiling import limits, plan, source_hash

MAX_FILE_BYTES = limits()['max_image_bytes']
logger = logging.getLogger(__name__)


def bad(message, code="PCB_BAD_BATCH", status=400):
    return AppError(message, code=code, stage="file", status_code=status)


def _binary_gt(image):
    """Use visible pixel values, never palette indices or a luminance threshold."""
    if image.mode == 'P' and image.getpalette() is None:
        raise ValueError('missing PNG palette')
    # This also resolves palette/tRNS alpha. Unused transparent palette entries
    # are harmless, but no actually used pixel may have an ambiguous opacity.
    rgba = np.asarray(image.convert('RGBA'))
    if np.any(rgba[..., 3] != 255):
        raise ValueError('transparent GT pixels')
    rgb = rgba[..., :3]
    if np.any(rgb[..., 0] != rgb[..., 1]) or np.any(rgb[..., 0] != rgb[..., 2]):
        raise ValueError('colored GT pixels')
    gray = rgb[..., 0]
    values = set(np.unique(gray).tolist())
    if not (values <= {0, 1} or values <= {0, 255}):
        raise ValueError('nonbinary GT pixels')
    return (gray > 0).astype(np.uint8)


def decode_image(name, content, *, gt=False, expected_size=None, mime=None):
    """Decode bounded original bytes; only lossless binary GT is normalized."""
    if not isinstance(name, str) or not name or any(c in name for c in '/\\:\x00') or name[-1] in '. ':
        raise bad("文件名无效，请使用普通 PNG/JPEG 文件名")
    if not content or len(content) > limits()["max_image_bytes"]:
        raise bad("单文件须为 1 字节至 10 MiB", "PCB_IMAGE_SIZE")
    try:
        suffix = name.rsplit('.', 1)[-1].lower()
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                fmt = image.format
                width, height = image.size
                mode = image.mode
                expected_format = 'PNG' if suffix == 'png' else 'JPEG' if suffix in {'jpg','jpeg'} else None
                if fmt != expected_format or (gt and fmt != 'PNG'):
                    raise ValueError('format')
                if mime not in (None, '', 'application/octet-stream', 'image/png' if fmt == 'PNG' else 'image/jpeg'):
                    raise ValueError('MIME')
                if mode not in ({'1','L','P','RGB'} if gt else {'RGB','L'}) or getattr(image,'n_frames',1) != 1:
                    raise ValueError('channels or frames')
                geometry = plan(width,height,'L' if gt else mode)
                if expected_size is not None and (width,height) != tuple(expected_size):
                    raise ValueError('paired size')
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                if image.getexif().get(274,1) != 1:
                    raise ValueError('EXIF')
                image.load()
                output = content
                if gt:
                    stream=io.BytesIO()
                    Image.fromarray(_binary_gt(image)).save(stream,format='PNG')
                    output=stream.getvalue()
        metadata={'width':width,'height':height,'mode':'L' if gt else mode,'bytes':len(output),
                  'sha256':hashlib.sha256(output).hexdigest()}
        if gt:
            metadata.update(source_mode=mode,source_sha256=hashlib.sha256(content).hexdigest(),
                            source_bytes=len(content),normalization='binary_png_0_1')
        else:metadata['input_plan']=geometry
        return output, 'png' if fmt=='PNG' else 'jpg', metadata
    except (OSError,ValueError,SyntaxError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise bad("GT 须为与原图同尺寸的不透明二值 PNG；支持黑白调色板、1 位、灰度及三通道一致的 RGB，像素须为 0/1 或 0/255" if gt else
                  "图片须为 8-bit RGB/灰度单帧 PNG/JPEG，最长边不超过 2048，EXIF 方向为 1 或缺省",
                  "PCB_BAD_GT" if gt else "PCB_BAD_IMAGE") from exc


def validate_manifest(value):
    if not isinstance(value,dict) or set(value)!={'files'} or not isinstance(value['files'],list):
        raise bad('manifest 须为 files 数组')
    entries=value['files']
    if not 1<=len(entries)<=limits()['max_images']:raise bad('每批须选择 1–10 张原图')
    ids=set(); fields=set()
    for row in entries:
        if not isinstance(row,dict) or set(row)-{'client_file_id','file_field','gt_field'} or not {'client_file_id','file_field'}<=set(row):
            raise bad('图片映射字段无效')
        ident=row['client_file_id']
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',ident) or ident in ids:
            raise bad('图片 client_file_id 必须唯一')
        ids.add(ident)
        for field in [row['file_field']]+([row['gt_field']] if row.get('gt_field') is not None else []):
            if not isinstance(field,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',field) or field=='manifest' or field in fields:
                raise bad('上传字段必须唯一且不得重用 GT')
            fields.add(field)
    return entries,fields


def create_group(db,user,manifest,files,settings=None):
    settings=settings or get_settings()
    single.require_enabled(settings)
    entries,fields=validate_manifest(manifest)
    if set(files)!=fields:raise bad('上传文件与 manifest 不一致')
    if sum(len(row[1]) for row in files.values())>limits()['max_batch_bytes']:
        raise bad('每批原图及 GT 合计不得超过 50 MiB','PCB_BATCH_SIZE')
    validated=[]
    for row in entries:
        name,data,mime=files[row['file_field']]
        original,suffix,facts=decode_image(name,data,mime=mime)
        mask=None; gt_facts=None
        if row.get('gt_field'):
            gt_name,gt_bytes,gt_mime=files[row['gt_field']]
            mask,_,gt_facts=decode_image(gt_name,gt_bytes,gt=True,expected_size=(facts['width'],facts['height']),mime=gt_mime)
        validated.append((row,name,original,suffix,facts,mask,gt_facts))
    if sum(row[4]['input_plan']['window_count'] for row in validated)>limits()['max_window_model_budget']:
        raise bad('单模型总窗口已超预算，请减少图片或尺寸','PCB_WINDOW_BUDGET')
    item=single.asset('unet',settings)
    written=[]; folders=[]
    try:
        lock_user(db,user)
        spec=single._protocol(db,item)
        dataset=Dataset(id=new_id(),owner_id=user.id,name='PCB 多图分割批次',visibility='private')
        db.add(dataset);db.flush()
        parent=DatasetVersion(id=new_id(),dataset_id=dataset.id,kind='pcb_batch',preprocess_id=spec.id,
                              class_map_json={},is_fixed_test=False,forbid_student_gt_download=False)
        db.add(parent);db.flush()
        children=[]
        for row,name,original,suffix,facts,mask,gt_facts in validated:
            meta={'scene':'pcb','task_kind':'segmentation','protocol_hash':item['protocol_hash'],
                  'classes':single.CLASSES,'filename':name[:128],'gt_encoding':'0/1' if mask is not None else None,
                  'batch_extension':1,'parent_batch_id':parent.id,'client_file_id':row['client_file_id'],
                  'input_plan':facts['input_plan'],'extension_hash':source_hash(),'image_facts':facts,'gt_facts':gt_facts}
            version=DatasetVersion(id=new_id(),dataset_id=dataset.id,kind='pcb_batch',preprocess_id=spec.id,
                                   class_map_json=meta,is_fixed_test=False,forbid_student_gt_download=False)
            db.add(version);db.flush()
            folder=settings.storage_path/'pcb'/version.id
            folder.mkdir(parents=True,exist_ok=False);folders.append(folder)
            original_path=folder/f'image.{suffix}'
            # This attempt owns the freshly-created directory. Track each fixed
            # path before writing so a partial write is also removed on rollback.
            written.append(original_path)
            with original_path.open('xb') as stream:stream.write(original)
            if mask is not None:
                mask_path=folder/'gt.png'
                written.append(mask_path)
                with mask_path.open('xb') as stream:stream.write(mask)
            sample=Sample(id=new_id(),version_id=version.id,sample_key='image',
                          origin_uri=f'data:pcb/{version.id}/image.{suffix}',mask_uri=f'data:pcb/{version.id}/gt.png' if mask is not None else None,
                          width=facts['width'],height=facts['height'],sha256=facts['sha256'])
            db.add(sample);db.flush()
            children.append({'version_id':version.id,'sample_id':sample.id,'client_file_id':row['client_file_id']})
        parent.class_map_json={'scene':'pcb','task_kind':'segmentation','batch_group':1,'children':children,
                               'extension_hash':source_hash(),'protocol_hash':item['protocol_hash']}
        db.add(AuditLog(id=new_id(),actor_id=user.id,action='pcb.batch_upload',target_type='dataset_version',target_id=parent.id,
                        reason=f'整批校验通过并保存 {len(children)} 张原图及配对 GT'))
        db.commit()
    except Exception:
        db.rollback()
        for path in reversed(written):
            try:path.unlink(missing_ok=True)
            except OSError:logger.warning('PCB batch upload file cleanup incomplete')
        for folder in reversed(folders):
            try:folder.rmdir()
            except OSError:logger.warning('PCB batch upload directory cleanup incomplete')
        raise
    return get_group(db,user,parent.id,settings=settings)


def _parent(db,batch_id,*,locked=False):
    parent=lock_version(db,batch_id) if locked else db.get(DatasetVersion,batch_id)
    if not parent or parent.kind!='pcb_batch' or (parent.class_map_json or {}).get('batch_group')!=1:
        raise bad('批次不存在','NOT_FOUND',404)
    dataset=db.get(Dataset,parent.dataset_id)
    if not dataset or dataset.visibility!='private':raise bad('批次不可用','NOT_FOUND',404)
    return parent,dataset


def _children(db,parent):
    result=[]
    for row in parent.class_map_json['children']:
        version=db.get(DatasetVersion,row['version_id']);sample=db.get(Sample,row['sample_id'])
        if (not version or version.kind!='pcb_batch' or version.dataset_id!=parent.dataset_id
            or (version.class_map_json or {}).get('parent_batch_id')!=parent.id or not sample or sample.version_id!=version.id
            or version.class_map_json.get('client_file_id')!=row['client_file_id']):
            raise bad('批次图片身份已改变','PCB_PROTOCOL_CHANGED',409)
        result.append((row,version,sample))
    if not 1<=len(result)<=limits()['max_images']:raise bad('批次图片数量无效','PCB_PROTOCOL_CHANGED',409)
    return result


def submit_group(db,user,*,batch_id,model_ids,include_cam=False,accept_unsupported_cam=False,idempotency_key,settings=None):
    settings=settings or get_settings();single.require_enabled(settings)
    if (not isinstance(model_ids,list) or not model_ids or len(model_ids)>3 or len(set(model_ids))!=len(model_ids)
        or any(m not in single.MODELS for m in model_ids) or type(include_cam) is not bool or type(accept_unsupported_cam) is not bool):
        raise bad('请选择 1–3 个不同的准入模型及合法选项')
    models=sorted(model_ids)
    marker_id=request_id('pcb_batch_submit',user.id,idempotency_key)
    tasks=[]; manifest_paths=[]
    try:
        lock_user(db,user)
        parent,dataset=_parent(db,batch_id,locked=True)
        if dataset.owner_id!=user.id:raise bad('批次不存在','NOT_FOUND',404)
        children=_children(db,parent)
        if parent.class_map_json.get('extension_hash')!=source_hash():raise bad('批次适配器已更新，请重新上传','PCB_PROTOCOL_CHANGED',409)
        windows=sum(version.class_map_json['input_plan']['window_count'] for _,version,_ in children)*len(models)
        if windows>limits()['max_window_model_budget']:raise bad('窗口×模型总数超过 500，请减少图片或模型','PCB_WINDOW_BUDGET')
        if include_cam and any(not v.class_map_json['input_plan']['cam_supported'] for _,v,_ in children) and not accept_unsupported_cam:
            raise bad('仅原生 220×220 RGB 图片支持 CAM，请明确确认其他图片不生成 CAM','PCB_CAM_ACK_REQUIRED')
        options={'batch_id':parent.id,'model_ids':models,'include_cam':include_cam,'accept_unsupported_cam':accept_unsupported_cam}
        # A current read is required after waiting for the user/version locks;
        # ordinary get() can retain an earlier MySQL REPEATABLE READ snapshot.
        marker=db.query(AuditLog).filter_by(id=marker_id).populate_existing().with_for_update().one_or_none()
        if marker:
            if marker.action!='pcb.batch_submit' or marker.actor_id!=user.id or marker.reason!=json.dumps(options,sort_keys=True):
                raise bad('同一幂等键不能修改批次、模型或选项','IDEMPOTENCY_CONFLICT',409)
            db.rollback()
            return get_group(db,user,batch_id,settings=settings)
        for _,version,_ in children:
            for model in models:
                key=marker_id+':'+version.id+':'+model
                ident=request_id(single.TYPE,user.id,key)
                frozen_path=manifest_path(settings,ident)
                if not frozen_path.exists():manifest_paths.append(frozen_path)
                task=single.create_pcb_task(db,user,batch_id=version.id,model_id=model,include_cam=include_cam,
                                           idempotency_key=key,settings=settings,_defer_delivery=True,_allow_extended=True)
                # Before actual enqueue, a process crash must not leave untouched siblings falsely queued.
                task.status='failed';task.error_summary='QUEUE_NOT_SENT: 批次已保存，尚未投递，请通过再跑恢复'
                for link in task.models:
                    link.status='failed';link.fail_stage='queue';link.fail_message=task.error_summary
                tasks.append(task)
        db.add(AuditLog(id=marker_id,actor_id=user.id,action='pcb.batch_submit',target_type='dataset_version',target_id=parent.id,
                        reason=json.dumps(options,sort_keys=True)))
        db.commit()
    except Exception:
        db.rollback()
        for path in manifest_paths:
            try:
                path.unlink(missing_ok=True)
                path.parent.rmdir()
            except OSError:logger.warning('PCB rolled back batch manifest cleanup incomplete')
        raise
    from app.services.pcb_delivery import CALLBACK
    for task in tasks:
        current=db.query(Task).filter_by(id=task.id).populate_existing().with_for_update().one()
        current.status='queued';current.error_summary='QUEUE_PENDING: 等待确认投递'
        for link in current.models:link.status='queued';link.fail_stage=None;link.fail_message=None
        db.commit()
        try:
            delivery=single.enqueue(settings,'apps.worker.jobs.run_pcb_segmentation',task.id,settings.pcb_job_timeout_sec,
                                    job_id='task-'+task.id,on_failure=CALLBACK)
        except Exception:
            delivery=Delivery('unknown','task-'+task.id)
        apply_task_delivery(db,task,delivery)
        single.invalidate_after_write(task.id,user.id)
    return get_group(db,user,batch_id,settings=settings)


def get_group(db,user,batch_id,*,page=1,page_size=50,settings=None):
    settings=settings or get_settings()
    parent,dataset=_parent(db,batch_id)
    children=_children(db,parent)
    owner=dataset.owner_id==user.id
    query=db.query(Task).filter(Task.dataset_version_id.in_([v.id for _,v,_ in children]),Task.type==single.TYPE,Task.creator_id==dataset.owner_id)
    if not owner:
        if user.role!='advisor':raise bad('批次不存在','NOT_FOUND',404)
        query=query.filter(Task.submitted_to_advisor_at.is_not(None))
    counts={status:query.filter(Task.status==status).count() for status in ('success','failed','queued','running')}
    counts['total']=sum(counts.values())
    if not owner and not counts['total']:raise bad('批次不存在','NOT_FOUND',404)
    tasks=query.order_by(Task.created_at.desc(),Task.id).offset((page-1)*page_size).limit(page_size).all()
    grouped={};selected=set();cam=False
    for task in tasks:
        payload=single.serialize_pcb_task(db,task,settings)
        grouped.setdefault(task.dataset_version_id,[]).append(payload)
        if payload['model']:selected.add(payload['model']['id'])
        cam=cam or payload['include_cam']
    samples=[]
    for row,version,sample in children:
        entries=grouped.get(version.id,[])
        if not entries and (not owner or counts['total']):continue
        meta=version.class_map_json
        samples.append({'sample_id':sample.id,'client_file_id':row['client_file_id'],'filename':meta['filename'],
                        'width':sample.width,'height':sample.height,'has_gt':bool(sample.mask_uri),
                        'input_plan':meta['input_plan'],'windows':meta['input_plan']['window_count'],'tasks':entries})
    status=('uploaded' if not counts['total'] else 'running' if counts['running'] else 'queued' if counts['queued'] else
            'partial_failed' if counts['failed'] and counts['success'] else 'failed' if counts['failed'] else 'success')
    return {'batch_id':parent.id,'status':status,'counts':counts,'samples':samples,'image_count':len(samples),
            'selected_model_ids':sorted(selected),'include_cam':cam,
            'total_windows':sum(s['windows']*max(1,len(s['tasks'])) for s in samples),
            'pagination':{'page':page,'page_size':page_size,'total':counts['total'],'has_more':page*page_size<counts['total']},
            'open_path':f'/inspect/pcb/batches/{parent.id}'}
