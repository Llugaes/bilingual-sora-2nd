"""Read-only foreground/process identity helpers."""

import ctypes
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD


def process_identity(pid):
    """Creation time of a running process, even if an exited PID still has handles."""
    handle = kernel32.OpenProcess(0x1000 | 0x100000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        state = kernel32.WaitForSingleObject(handle, 0)
        if state == 0:
            raise ProcessLookupError(f"Process {pid} has exited")
        if state != 0x102:
            raise ctypes.WinError(ctypes.get_last_error())
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        kernel32.CloseHandle(handle)


def process_path(pid):
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        raise OSError("无法读取游戏进程路径")
    try:
        size = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return Path(path.value)
    finally:
        kernel32.CloseHandle(handle)


def foreground_rect(pid):
    hwnd = user32.GetForegroundWindow()
    owner = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    if owner.value != pid:
        return None
    rect, point = wintypes.RECT(), wintypes.POINT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        return None
    return point.x, point.y, rect.right, rect.bottom
