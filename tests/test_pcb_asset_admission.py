"""Pure stdlib asset boundary tests: no torch, API, DB, Redis, .env or real weights."""
from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest

from scripts import verify_pcb_assets as admission


def entry(name="source/model.py", *, size=6, compressed=6, mode=stat.S_IFREG | 0o644):
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = mode << 16
    info.file_size = size
    info.compress_size = compressed
    return info


@pytest.mark.parametrize("name", [
    "../outside", "folder/../../outside", "/absolute", "//server/share", "C:/drive",
    "folder\\model.py", "folder//file", "./file", "folder/./file", "folder/",
    "folder/trailing.", "folder/trailing ", "NUL", "CON.txt", "aux.py", "PRN",
    "folder/LPT1.txt", "COM9", "COM¹.txt", "CONIN$", "file:stream", "file\x00suffix",
    "file\nname", 'a"b', "a?b", "a*b", "a<b", "a>b", "a|b",
])
def test_rejects_unsafe_windows_paths(name):
    with pytest.raises(admission.AdmissionError):
        admission.scan_members([entry(name)])


@pytest.mark.parametrize("names", [
    ["source/a.py", "source/a.py"], ["source/a.py", "SOURCE/A.PY"],
    ["source", "source/a.py"], ["SOURce", "source/a.py"],
    ["cafe\u0301.txt", "caf\u00e9.txt"],
])
def test_rejects_duplicate_and_prefix_collisions(names):
    with pytest.raises(admission.AdmissionError):
        admission.scan_members([entry(name) for name in names])


@pytest.mark.parametrize("mode", [stat.S_IFLNK | 0o777, stat.S_IFDIR | 0o755,
                                   stat.S_IFIFO | 0o600, stat.S_IFCHR | 0o600, 0])
def test_rejects_symlink_directory_and_special_file(mode):
    with pytest.raises(admission.AdmissionError, match="regular file"):
        admission.scan_members([entry(mode=mode)])


@pytest.mark.parametrize("flag", [1, 64, 65])
def test_rejects_encryption(flag):
    info = entry()
    info.flag_bits = flag
    with pytest.raises(admission.AdmissionError, match="encrypted"):
        admission.scan_members([info])


@pytest.mark.parametrize("size,compressed", [(70_000_001, 70_000_001), (2_000_001, 1), (-1, 1), (5, -1)])
def test_rejects_oversized_and_bomb_members(size, compressed):
    with pytest.raises(admission.AdmissionError):
        admission.scan_members([entry(size=size, compressed=compressed)])


def test_checks_aggregate_bytes_and_member_count():
    with pytest.raises(admission.AdmissionError, match="expanded archive"):
        admission.scan_members([entry(str(i), size=60_000_000, compressed=60_000_000) for i in range(3)])
    with pytest.raises(admission.AdmissionError, match="count"):
        admission.scan_members([entry(str(i)) for i in range(53)])
    with pytest.raises(admission.AdmissionError, match="count"):
        admission.scan_members([])


def test_checks_allowlist_and_expected_total():
    with pytest.raises(admission.AdmissionError, match="allowlist"):
        admission.scan_members([entry("images.zip")], expected_names=frozenset({"weights.pth"}))
    with pytest.raises(admission.AdmissionError, match="byte total"):
        admission.scan_members([entry()], expected_total=5)
    assert set(admission.scan_members([entry()], expected_names=frozenset({"source/model.py"}), expected_total=6)) == {"source/model.py"}


def test_rejects_unsupported_compression():
    info = entry()
    info.compress_type = zipfile.ZIP_BZIP2
    with pytest.raises(admission.AdmissionError, match="compression"):
        admission.scan_members([info])


def test_small_compressible_reference_is_allowed_with_fixed_size_budget():
    info = entry("expected_black.npy", size=786560, compressed=867)
    assert admission.scan_members([info])[info.filename] is info


@pytest.mark.parametrize("sums", [
    "malformed", "0" * 64 + "  source/model.py\n" + "0" * 64 + "  source/model.py",
    "0" * 64 + "  ../outside", "0" * 64 + "  unlisted.file", "",
])
def test_hash_manifest_is_complete_unique_and_path_safe(sums):
    with pytest.raises(admission.AdmissionError):
        admission.parse_sums(sums, {"source/model.py", "SHA256SUMS.txt"})


def test_valid_hash_manifest():
    digest = hashlib.sha256(b"model").hexdigest()
    assert admission.parse_sums(f"{digest}  source/model.py\n", {"source/model.py", "SHA256SUMS.txt"}) == {"source/model.py": digest}


def test_bounded_stream_reader():
    with pytest.raises(admission.AdmissionError, match="declared size"):
        admission.stream_hash(io.BytesIO(b"123456"), limit=5)


def test_duplicate_json_keys_are_rejected():
    with pytest.raises(admission.AdmissionError, match="JSON key"):
        json.loads('{"models": [], "models": ["surprise"]}', object_pairs_hook=admission.json_object)


def test_private_destination_rejects_outside_and_existing(tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    target = private / "new"
    assert admission.check_private_destination(target, private) == target
    for invalid in [tmp_path / "public/new", private]:
        with pytest.raises(admission.AdmissionError, match="outside"):
            admission.check_private_destination(invalid, private)
    target.mkdir()
    with pytest.raises(admission.AdmissionError, match="already exists"):
        admission.check_private_destination(target, private)


def test_rejects_linked_staging_without_requiring_os_symlink_privileges(tmp_path, monkeypatch):
    private = tmp_path / "private"
    monkeypatch.setattr(Path, "is_symlink", lambda p: p == private)
    with pytest.raises(admission.AdmissionError, match="symlink/junction"):
        admission.check_private_destination(private / "new", private)


def test_real_zip_extract_checks_on_disk_hash_and_refuses_overwrite(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(entry("source/test.py"), b"# data only, not executed\n")
    buffer.seek(0)
    digest = hashlib.sha256(b"# data only, not executed\n").hexdigest()
    private = tmp_path / "private"
    target = private / "release"
    with zipfile.ZipFile(buffer) as z:
        names = admission.scan_members(z.infolist())
        admission.extract_verified(z, names, {"source/test.py": digest}, target, private)
        assert (target / "source/test.py").read_bytes() == b"# data only, not executed\n"
        with pytest.raises(admission.AdmissionError, match="already exists"):
            admission.extract_verified(z, names, {"source/test.py": digest}, target, private)


def test_extract_rejects_hash_mismatch(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(entry("data.json"), b"{}")
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as z:
        with pytest.raises(admission.AdmissionError, match="hash mismatch"):
            admission.extract_verified(z, admission.scan_members(z.infolist()), {"data.json": "0" * 64},
                                       tmp_path / "private/release", tmp_path / "private")


def test_fixed_release_sidecar_and_outer_digest_checked_before_zip(tmp_path):
    archive = tmp_path / f"{admission.RELEASE}.zip"
    archive.write_bytes(b"not the frozen archive")
    sidecar = archive.with_suffix(".zip.sha256")
    with pytest.raises(admission.AdmissionError, match="sidecar"):
        admission.verify_release(archive)
    sidecar.write_text("0" * 64 + "  malicious.zip", encoding="utf-8")
    with pytest.raises(admission.AdmissionError, match="sidecar"):
        admission.verify_release(archive)
    sidecar.write_text(f"{admission.ZIP_SHA256}  {admission.RELEASE}.zip", encoding="utf-8")
    with pytest.raises(admission.AdmissionError, match="SHA256/size"):
        admission.verify_release(archive)


def test_frozen_file_allowlist_contains_only_three_models_and_no_private_dataset():
    assert len(admission.ALLOWLIST) == 52
    assert {n.split("/")[1] for n in admission.ALLOWLIST if n.startswith("models/")} == set(admission.MODEL_IDENTITIES)
    assert not any(n.lower().endswith((".png", ".jpg", ".jpeg", ".env", ".pt", ".zip")) for n in admission.ALLOWLIST)
    assert "predictions.csv" not in admission.ALLOWLIST and "evaluation.json" not in admission.ALLOWLIST
