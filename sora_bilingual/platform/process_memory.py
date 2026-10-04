"""Bounded external reads. Never inject, suspend, write, or call game code."""

import ctypes
from ctypes import wintypes
from pathlib import Path


class ReadOnlyProcess:
    def __init__(self, pid, executable):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.ReadProcessMemory.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.kernel.ReadProcessMemory.restype = wintypes.BOOL
        self.psapi.EnumProcessModulesEx.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.HMODULE),
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.DWORD,
        ]
        self.psapi.GetModuleFileNameExW.argtypes = [
            wintypes.HANDLE,
            wintypes.HMODULE,
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]
        self.handle = self.kernel.OpenProcess(0x1000 | 0x10, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            modules = (wintypes.HMODULE * 1024)()
            needed = wintypes.DWORD()
            if not self.psapi.EnumProcessModulesEx(
                self.handle, modules, ctypes.sizeof(modules), ctypes.byref(needed), 3
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if needed.value > ctypes.sizeof(modules):
                raise ValueError("process module list exceeds read bound")
            expected = str(Path(executable).resolve()).casefold()
            for module in modules[: needed.value // ctypes.sizeof(wintypes.HMODULE)]:
                name = ctypes.create_unicode_buffer(32768)
                if self.psapi.GetModuleFileNameExW(self.handle, module, name, len(name)):
                    if str(Path(name.value).resolve()).casefold() == expected:
                        self.base = int(module)
                        break
            else:
                raise ProcessLookupError("verified executable is not loaded in this process")
        except BaseException:
            self.close()
            raise

    def read(self, address, size):
        if not self.handle or address <= 0 or not 0 < size <= 1024 * 1024:
            raise ValueError("invalid bounded process read")
        data = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        if (
            not self.kernel.ReadProcessMemory(self.handle, address, data, size, ctypes.byref(count))
            or count.value != size
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return data.raw

    def text(self, address, limit):
        result = bytearray()
        while len(result) < limit:
            current = address + len(result)
            # Do not cross into an unreadable page after an otherwise valid NUL.
            block = self.read(current, min(128, limit - len(result), 4096 - current % 4096))
            end = block.find(b"\0")
            if end >= 0:
                return (result + block[:end]).decode("utf-8")
            result.extend(block)
        raise ValueError("process string exceeds read bound")

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
