"""Diagnostics for "DLL load failed" in the packaged Windows app, written into crash.log.

Windows only says that *some* dependency of a compiled module is missing. This reads the module's import table
(which DLLs it needs), tries to load each one the same way Python does, and lists the DLLs in the bundle, so the
log names the culprit. Pure Python, so it also works when the failure is in a native library.
"""
from __future__ import annotations

import glob
import os
import struct
import sys


def pe_imports(path: str) -> list[str]:
    """Names of the DLLs a Windows PE file (.dll / .pyd / .exe) imports."""
    with open(path, "rb") as fh:
        data = fh.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    sections_count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    directories = optional + (112 if magic == 0x20B else 96)
    import_rva = struct.unpack_from("<I", data, directories + 8)[0]
    table = optional + optional_size
    sections = [struct.unpack_from("<8sIIII", data, table + 40 * i) for i in range(sections_count)]

    def offset(rva: int) -> int:
        for _name, vsize, vaddr, rsize, rptr in sections:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return rva - vaddr + rptr
        raise ValueError(f"RVA {rva:#x} outside sections")

    names, entry = [], offset(import_rva)
    while True:
        name_rva = struct.unpack_from("<I", data, entry + 12)[0]
        if not name_rva:
            return names
        start = offset(name_rva)
        names.append(data[start:data.index(b"\0", start)].decode("ascii", "replace"))
        entry += 20


def report(message: str) -> str:
    """Explain a "DLL load failed while importing X" error: which dependency of X cannot be loaded."""
    import ctypes

    bundle = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    module = message.split("importing ")[-1].split(":")[0].strip() if "importing " in message else ""
    lines = [f"Python {sys.version}", f"Bundle: {bundle}",
             "Top-level DLLs: " + ", ".join(sorted(os.path.basename(p) for p in glob.glob(os.path.join(bundle, "*.dll"))))]
    candidates = glob.glob(os.path.join(bundle, "**", f"{module}*.pyd"), recursive=True) if module else []
    for pyd in candidates:
        lines.append(f"Module file: {pyd}")
        try:
            for dll in pe_imports(pyd):
                local = os.path.join(bundle, dll)
                try:
                    ctypes.WinDLL(dll)
                    state = "loads"
                except OSError as exc:
                    state = f"FAILS ({exc})"
                lines.append(f"  needs {dll}: {state}; in bundle: {os.path.exists(local)}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  could not read imports: {exc}")
        try:
            ctypes.WinDLL(pyd)
            lines.append("  loading the module file directly: OK")
        except OSError as exc:
            lines.append(f"  loading the module file directly: FAILS ({exc})")
    return "\n".join(lines)
