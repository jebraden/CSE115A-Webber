"""
Platform Support for Linux

This file contains code specific to Linux.
"""

import ctypes
from typing import Optional
import os
import signal
import logging

logger = logging.getLogger(__name__)

_libc = ctypes.CDLL(None, use_errno=True)


def _check_libc_syscall_rval(
    rval: ctypes.c_int, func: ctypes._CFuncPtr, args: tuple
) -> None:
    errno = ctypes.get_errno()
    if rval < 0:
        raise OSError(errno, os.strerror(errno))
    return None


_prctl: _libc._FuncPtr = _libc.prctl
_prctl.restype = ctypes.c_int
_prctl.argtypes = (ctypes.c_int,)
_prctl.errcheck = _check_libc_syscall_rval

# from <linux/prctl.h>
_PR_SET_PDEATHSIG = 1


def die_with_parent(signum: int, ppid: Optional[int] = None):
    _prctl(_PR_SET_PDEATHSIG, signum)
    logger.info("Ran prctl(PR_SET_PDEATHSIG, %d)", signum)
    if ppid is not None:
        cur_ppid = os.getppid()
        if cur_ppid != ppid:
            logger.info(
                "Current PPID %d differes from original of %d, exiting...",
                cur_ppid,
                ppid,
            )
            signal.raise_signal(signum)
