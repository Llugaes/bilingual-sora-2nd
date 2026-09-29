"""Give bundled CPython hosts identifiable names without changing their executable code."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import struct
import tempfile


def _block(key, value=b"", children=(), *, text=False):
    data = bytearray(struct.pack("<HHH", 0, len(value) // 2 if text else len(value), int(text)))
    data += (key + "\0").encode("utf-16le")
    data += b"\0" * (-len(data) % 4)
    data += value
    for child in children:
        data += b"\0" * (-len(data) % 4)
        data += child
    struct.pack_into("<H", data, 0, len(data))
    return bytes(data)


def _version(name, description):
    strings = {
        "FileDescription": description,
        "ProductName": "Bilingual Sora 2nd",
        "InternalName": name,
        "OriginalFilename": name,
        "FileVersion": "1.0.0.0",
        "ProductVersion": "1.0.0.0",
    }
    table = _block(
        "040904b0",
        children=[
            _block(key, (value + "\0").encode("utf-16le"), text=True)
            for key, value in strings.items()
        ],
        text=True,
    )
    fixed = struct.pack(
        "<13I", 0xFEEF04BD, 0x10000, 0x10000, 0, 0x10000, 0, 0x3F, 0, 0x40004, 1, 0, 0, 0
    )
    return _block(
        "VS_VERSION_INFO",
        fixed,
        [
            _block("StringFileInfo", children=[table], text=True),
            _block(
                "VarFileInfo",
                children=[_block("Translation", struct.pack("<HH", 0x409, 1200))],
                text=True,
            ),
        ],
    )


def branded_hosts(files):
    """Build-time resource editing only; imports, entry point and CPython DLL stay intact."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    kernel.BeginUpdateResourceW.restype = wintypes.HANDLE
    kernel.UpdateResourceW.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.WORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    result = {}
    with tempfile.TemporaryDirectory() as temporary:
        for role, source in [
            ("UI", "pythonw.exe"),
            ("Backend", "pythonw.exe"),
            ("Worker", "python.exe"),
        ]:
            name = f"BilingualSora2nd.{role}.exe"
            path = Path(temporary) / name
            path.write_bytes(files[source])
            handle = kernel.BeginUpdateResourceW(str(path), False)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            data = _version(name, f"Bilingual Sora 2nd ({role})")
            try:
                if not kernel.UpdateResourceW(handle, 16, 1, 0x409, data, len(data)):
                    raise ctypes.WinError(ctypes.get_last_error())
            except Exception:
                kernel.EndUpdateResourceW(handle, True)
                raise
            if not kernel.EndUpdateResourceW(handle, False):
                raise ctypes.WinError(ctypes.get_last_error())
            result[name] = path.read_bytes()
    return result
