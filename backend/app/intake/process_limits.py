"""Resource limits and Linux isolation for short-lived native OCR workers."""

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


def isolate_linux_worker():
    """Read-only public runtime/assets; no sockets, exec or peer/process access."""
    if sys.platform != "linux":
        return None
    import ctypes
    import errno
    import os
    import platform
    import sysconfig
    from pathlib import Path

    # Install before native initialization can create threads. Future threads
    # inherit both policies; ordinary fork/clone and clone3 are unavailable.
    if len(list(Path("/proc/self/task").iterdir())) != 1:
        raise OSError("OCR process restrictions unavailable")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    libc.prctl.argtypes = [ctypes.c_int, *([ctypes.c_ulong] * 4)]

    def checked(value):
        if value < 0:
            raise OSError(ctypes.get_errno(), "OCR process restrictions unavailable")
        return value

    # Landlock ABI3 includes rename/refer and truncate controls. No fallback to
    # unrestricted decoding on unsupported/disabled kernels.
    abi = checked(libc.syscall(444, 0, 0, 1))
    if abi < 3:
        raise OSError("OCR process restrictions unavailable")
    checked(libc.prctl(38, 1, 0, 0, 0))  # PR_SET_NO_NEW_PRIVS
    attributes = (ctypes.c_uint64 * 3)((1 << 15) - 1, 0, 3 if abi >= 6 else 0)
    rules = checked(libc.syscall(444, ctypes.byref(attributes), ctypes.sizeof(attributes), 0))

    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

    paths = {
        Path(sysconfig.get_path(name)).resolve() for name in ("stdlib", "purelib", "platlib")
    } | {
        Path(__file__).resolve().parents[1] / "assets",
        *[Path(name) for name in ("/lib", "/usr/lib", "/usr/share/fonts", "/etc/fonts",
            "/var/cache/fontconfig", "/etc/ld.so.cache")],
    }
    try:
        for path in sorted(paths):
            if not path.exists():
                continue
            descriptor = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(12 if path.is_dir() else 4, descriptor)
                checked(libc.syscall(445, rules, 1, ctypes.byref(rule), 0))
            finally:
                os.close(descriptor)
        checked(libc.syscall(446, rules, 0))
    finally:
        os.close(rules)

    # Kernel syscall tables: x86 syscall_64.tbl and asm-generic/unistd.h.
    # Landlock covers filesystem access; seccomp also blocks socket creation,
    # io_uring, execution, new processes and interaction with other processes.
    policies = {
        "x86_64": (0xC000003E, 56,
            (41, 53, 57, 58, 59, 62, 101, 129, 200, 234, 297, 310, 311, 322)),
        "aarch64": (0xC00000B7, 220,
            (117, 129, 130, 131, 138, 198, 199, 221, 240, 270, 271, 281)),
    }
    if platform.machine() not in policies:
        raise OSError("OCR process restrictions unavailable")
    architecture, clone, denied = policies[platform.machine()]

    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
            ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32)]

    class Program(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]

    # Reject other ABIs and x32 syscall numbers rather than letting them evade
    # the native-architecture numbers. clone is allowed only for CLONE_THREAD.
    instructions = [Filter(0x20, 0, 0, 4), Filter(0x15, 1, 0, architecture),
        Filter(0x06, 0, 0, 0x80000000), Filter(0x20, 0, 0, 0),
        Filter(0x35, 0, 1, 0x40000000), Filter(0x06, 0, 0, 0x80000000)]
    for number in (*denied, 424, 425, 426, 427, 435, 438):
        instructions.extend([Filter(0x15, 0, 1, number),
            Filter(0x06, 0, 0, 0x50000 | (errno.ENOSYS if number == 435 else errno.EACCES))])
    instructions.extend([Filter(0x15, 0, 4, clone), Filter(0x20, 0, 0, 16),
        Filter(0x45, 1, 0, 0x10000), Filter(0x06, 0, 0, 0x50000 | errno.EACCES),
        Filter(0x06, 0, 0, 0x7FFF0000), Filter(0x06, 0, 0, 0x7FFF0000)])
    filters = (Filter * len(instructions))(*instructions)
    program = Program(len(filters), filters)
    checked(libc.prctl(22, 2, ctypes.addressof(program), 0, 0))  # PR_SET_SECCOMP/FILTER
    return abi


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
