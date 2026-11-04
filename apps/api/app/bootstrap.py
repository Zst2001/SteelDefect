from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

def _restore_windows_cpu_identity() -> None:
    """Recover missing platform identifiers from this Windows host before model admission."""
    if sys.platform != "win32" or (platform.machine() and platform.processor()):
        return
    import winreg

    changed = False
    system_env = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, system_env) as key:
            for name in ("PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER"):
                if os.environ.get(name):
                    continue
                try:
                    value, kind = winreg.QueryValueEx(key, name)
                except OSError:
                    continue
                if kind == winreg.REG_SZ and value:
                    os.environ[name] = value
                    changed = True
    except OSError:
        return
    if changed:
        # Earlier imports can already have cached an empty uname. Python
        # versions without platform.invalidate_caches() use this module cache.
        invalidate = getattr(platform, "invalidate_caches", None)
        if invalidate is not None:
            invalidate()
        else:
            platform._uname_cache = None


_restore_windows_cpu_identity()

ROOT = Path(__file__).resolve().parents[3]
for candidate in (ROOT, ROOT / "packages", ROOT / "third_party", ROOT / "apps" / "api"):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)
