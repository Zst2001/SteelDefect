"""Offline negative admission tests on a disposable COPY, never original assets."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"packages"),str(ROOT/"scripts")]
platform.uname()
from infer.pcb_classification import catalog
from verify_pcb_assets import AdmissionError, safe_name, scan_members


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--report",type=Path,required=True)
    path=parser.parse_args().report
    if path.exists():raise RuntimeError("Fresh evidence required")
    checks=[]
    def denied(call,label):
        try:call()
        except (ValueError,OSError):checks.append(label);return
        raise AssertionError("Expected denial: "+label)
    for name in ("../a","/a","C:/a","a\\b","con.txt","LPT1.txt","a./b","a /b","a//b","a/../b","a:b","a\x00b"):
        denied(lambda:safe_name(name),"unsafe archive path "+repr(name))
    def info(name,mode=stat.S_IFREG|0o644,size=1,compressed=1):
        row=zipfile.ZipInfo(name);row.external_attr=mode<<16;row.file_size=size;row.compress_size=compressed;return row
    for members in ([info("A"),info("a")],[info("a"),info("a")],[info("a",stat.S_IFLNK|0o777)],
                    [info("a"),info("a/b")],[info("a",size=70000001)],[info("a",size=100000,compressed=1)]):
        denied(lambda:scan_members(members),"unsafe ZIP member structure")
    original=ROOT/"assets/pcb_classification/deeppcb_roi_v0_formal_v1"
    before={n:catalog.digest(original/n) for n in catalog.FILES|{catalog.RECEIPT}}
    with tempfile.TemporaryDirectory(prefix="steel-roi-admission-") as temp:
        copied=Path(temp)/"copy";shutil.copytree(original,copied)
        receipt=copied/catalog.RECEIPT;data=receipt.read_bytes()
        # Even a matching new receipt cannot rebind modules already imported.
        assert catalog._loaded_source == catalog.source_hash()
        obj=json.loads(data);obj["source_hash"]="changed-before-first-request"
        receipt.write_text(json.dumps(obj),encoding="utf-8")
        with patch.object(catalog,"source_hash",return_value=obj["source_hash"]):
            denied(lambda:catalog.admitted(copied),"code changed before first admission fails closed")
        receipt.write_bytes(data)
        obj=json.loads(data);obj["runtime"]={"changed":"before-first-request"}
        receipt.write_text(json.dumps(obj),encoding="utf-8")
        with patch.object(catalog,"runtime_identity",return_value=obj["runtime"]):
            denied(lambda:catalog.admitted(copied),"runtime changed with matching new receipt requires restart")
        receipt.write_bytes(data)
        catalog.admitted(copied);checks.append("valid private copy admitted")
        original_configs=catalog.verify_release(copied)["configs"]
        changed=catalog.verify_release(copied)
        changed["configs"]["preprocess"]["mean"]=-999
        changed["configs"]["classes"]["classes"][0]["label_en"]="mutated"
        proof=catalog.admitted(copied)
        assert proof["configs"]==original_configs
        proof["configs"]["preprocess"]["std"]=-1
        assert catalog.admitted(copied)["configs"]==original_configs
        checks.append("verified and admitted configs cannot mutate cached identity")
        with patch.object(catalog,"digest",wraps=catalog.digest) as hashes:
            catalog.admitted(copied);catalog.admitted(copied)
            assert hashes.call_count==0;checks.append("unchanged files avoid repeated full-file hashes")
        for name in ("models/efficientnet_b0.pth","models/mobilenet_v3_small.pth","config/classes.json",
                     "config/preprocess.json","config/model_spec.json","MANIFEST.json","runtime/inference.py"):
            target=copied/name;data=target.read_bytes();target.write_bytes(data+b"tamper")
            denied(lambda:catalog.admitted(copied),"changed payload invalidates "+name)
            target.write_bytes(data);catalog.admitted(copied)
        receipt=copied/catalog.RECEIPT;data=receipt.read_bytes()
        for field,value in (("status","FAIL"),("source_hash","changed"),("runtime",{}),("models",{}),("tolerance",{"atol":1,"rtol":1})):
            obj=json.loads(data);obj[field]=value;receipt.write_text(json.dumps(obj),encoding="utf-8")
            denied(lambda:catalog.admitted(copied),"receipt identity invalidates "+field)
            receipt.write_bytes(data)
        malformed=[None,[],"PASS",1,{"models":None},{"models":[]}]
        for value in (None,[],"PASS",1):
            obj=json.loads(data);obj["models"][catalog.DEFAULT]=value;malformed.append(obj)
        for field,value in (("passed","false"),("passed",1),("strict",False),("weights_only",False),
                            ("missing_keys",1),("unexpected_keys",1),("parameters",1),("missing_keys",False)):
            obj=json.loads(data);obj["models"][catalog.DEFAULT][field]=value;malformed.append(obj)
        for index,obj in enumerate(malformed):
            receipt.write_text(json.dumps(obj),encoding="utf-8")
            denied(lambda:catalog.admitted(copied),f"malformed receipt rejected {index}")
            assert all(not row["available"] for row in catalog.catalog(copied))
            checks.append(f"malformed receipt catalog gracefully unavailable {index}")
        receipt.write_bytes(data)
        # A config replacement during parsing must not enter the hash cache.
        target=copied/"config/preprocess.json";config_bytes=target.read_bytes()
        read_text=Path.read_text
        def replace_during_read(path,*args,**kwargs):
            value=read_text(path,*args,**kwargs)
            if path==target:target.write_bytes(config_bytes+b" ")
            return value
        catalog._verified.pop(str(copied.absolute()),None)
        with patch.object(Path,"read_text",replace_during_read):
            denied(lambda:catalog.verify_release(copied),"config mutation during parsing is rejected")
        target.write_bytes(config_bytes);catalog.admitted(copied)
        spec=importlib.util.spec_from_file_location("pcb_catalog_missing_runtime",catalog.__file__)
        missing_runtime=importlib.util.module_from_spec(spec)
        with patch.object(catalog.importlib.metadata,"version",side_effect=catalog.importlib.metadata.PackageNotFoundError("torch")):
            spec.loader.exec_module(missing_runtime)
            assert all(not row["available"] for row in missing_runtime.catalog(copied))
        assert missing_runtime._loaded_runtime is None
        denied(lambda:missing_runtime.admitted(copied),"installing libraries into a running API still requires restart")
        checks.append("missing optional ML libraries do not break lightweight catalog import")
        with patch.object(catalog,"source_hash",return_value="changed-code"):
            denied(lambda:catalog.admitted(copied),"deployment code changed fails closed")
        with patch.object(catalog,"runtime_identity",return_value={}):
            denied(lambda:catalog.admitted(copied),"runtime libraries or CPU settings changed fails closed")
        receipt.unlink();denied(lambda:catalog.admitted(copied),"missing receipt fails closed")
        for flag in ("-O","-OO"):
            report=Path(temp)/(flag.lstrip("-")+".json")
            result=subprocess.run([sys.executable,flag,"-B",str(ROOT/"scripts/admit_pcb_classification_cpu.py"),
                                   "--report",str(report)],capture_output=True,text=True,timeout=30)
            assert result.returncode!=0 and "Admission requires assertions enabled" in result.stderr and not report.exists()
            checks.append(flag+" admission aborts before loading models or writing receipt")
    assert before=={n:catalog.digest(original/n) for n in before};checks.append("all original extracted assets and private receipt unchanged")
    with path.open("x",encoding="utf-8") as out:json.dump({"status":"PASS","checks":len(checks),"assertions":checks},out,ensure_ascii=False,indent=2)
    print(f"PASS: {len(checks)} safe extraction/cache/admission checks on copied assets")


if __name__=="__main__":main()
