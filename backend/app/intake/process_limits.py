"""Operating-system resource limits for short-lived native OCR workers."""

import sys
from threading import Lock

MAX_OCR_MEMORY_BYTES = 384 * 1024 * 1024
MAX_OCR_CPU_SECONDS = 40


def limit_linux_worker():
    if sys.platform != "linux":
        return
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (MAX_OCR_CPU_SECONDS, MAX_OCR_CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MAX_OCR_MEMORY_BYTES, MAX_OCR_MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def limit_windows_worker(process):
    """Assign before sending any uploaded bytes; return the job's close callback."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimit),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise OSError("OCR resource limits unavailable")
    try:
        limits = ExtendedLimit()
        # CPU time, one process, committed memory and termination on job close.
        limits.BasicLimitInformation.LimitFlags = 0x2 | 0x8 | 0x100 | 0x2000
        limits.BasicLimitInformation.PerProcessUserTimeLimit = MAX_OCR_CPU_SECONDS * 10_000_000
        limits.BasicLimitInformation.ActiveProcessLimit = 1
        limits.ProcessMemoryLimit = MAX_OCR_MEMORY_BYTES
        if not kernel.SetInformationJobObject(
            handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            raise OSError("OCR resource limits unavailable")
        if not kernel.AssignProcessToJobObject(handle, int(process._handle)):
            raise OSError("OCR resource limits unavailable")
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    lock = Lock()

    def close():
        nonlocal handle
        with lock:
            if handle:
                kernel.CloseHandle(handle)
                handle = None

    return close
