"""Fixed ZIP audit, optionally extracting to a new private directory. Never execute it."""
import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
from infer.pcb_classification.catalog import (FILES, MANIFEST_SHA, RELEASE, ZIP_BYTES, ZIP_SHA, digest, verify_release)
from verify_pcb_assets import check_private_destination, extract_verified, require, scan_members, stream_hash


def verify(archive, destination=None):
    sidecar = archive.with_suffix(".zip.sha256")
    require(archive.is_file() and not archive.is_symlink() and not sidecar.is_symlink(), "missing/linked release")
    require(archive.stat().st_size == ZIP_BYTES and digest(archive) == ZIP_SHA, "fixed ZIP identity failed")
    require(sidecar.stat().st_size <= 512 and sidecar.read_text(encoding="utf-8").strip().split()[0] == ZIP_SHA, "sidecar mismatch")
    hashes, members = {}, {}
    with zipfile.ZipFile(archive) as z:
        names = scan_members(z.infolist(), expected_names=frozenset(RELEASE + "/" + n for n in FILES))
        require(sum(x.file_size for x in names.values()) < 24_000_000, "expanded size exceeded")
        for name, info in names.items():
            with z.open(info) as stream:
                sha, size = stream_hash(stream, limit=info.file_size)
            require(size == info.file_size, "expanded size mismatch")
            hashes[name] = sha
            members[name.removeprefix(RELEASE + "/")] = {"sha256": sha, "bytes": size}
        require(members["MANIFEST.json"]["sha256"] == MANIFEST_SHA, "fixed manifest mismatch")
        manifest = json.loads(z.read(RELEASE + "/MANIFEST.json"))
        require(len(manifest["files"]) == 13 and {r["path"] for r in manifest["files"]} == FILES - {"MANIFEST.json"}, "manifest coverage")
        for row in manifest["files"]:
            require(members[row["path"]] == {"sha256": row["sha256"], "bytes": row["bytes"]}, "manifest member mismatch")
        if destination:
            # Strip the single frozen archive root, maintaining helper checks.
            root = ROOT / "assets/pcb_classification"
            target = check_private_destination(destination, root)
            target.mkdir(parents=True, exist_ok=False)
            for name in sorted(FILES):
                path = target / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as out:
                    out.write(z.read(RELEASE + "/" + name))
            verify_release(target)
    return {"status": "PASS", "zip_sha256": ZIP_SHA, "bytes": ZIP_BYTES, "files": members,
            "regular_files": 14, "manifest_checks": 13, "source_executed": False,
            "destination": str(destination) if destination else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = verify(ROOT / "assets/PCB_fenlei" / (RELEASE + ".zip"),
                    ROOT / "assets/pcb_classification/deeppcb_roi_v0_formal_v1" if args.extract else None)
    with args.report.open("x", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print("PASS: fixed ZIP, CRC, 14 regular members and 13 manifest hashes")
