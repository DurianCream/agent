"""Trusted, nondumpable PID-1 gate inside the approved sandbox rootfs.

EOF never authorizes candidate execution. A separate lifeline remains watched
after authorization; PID-1 exit causes the kernel to kill namespace descendants.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import selectors
import signal
import subprocess
import sys
import time

SECCOMP_POLICY = "amd64-af-unix-only-v1"


def payload_filter_instructions():
    # Linux AMD64 ABI: reject other architectures/x32, then bypass-capable and
    # credential/debug syscalls, then permit only Unix-domain socket creation.
    program = [(0x20, 0, 0, 4), (0x15, 1, 0, 0xC000003E), (0x06, 0, 0, 0x80000000),
               (0x20, 0, 0, 0), (0x35, 0, 1, 0x40000000), (0x06, 0, 0, 0x80000000)]
    for number in (101, 248, 249, 250, 310, 311, 321, 425, 426, 427, 438):
        program.extend([(0x15, 0, 1, number), (0x06, 0, 0, 0x00050001)])
    program.extend([(0x15, 1, 0, 41), (0x15, 0, 3, 53), (0x20, 0, 0, 16),
                    (0x15, 1, 0, 1), (0x06, 0, 0, 0x00050001), (0x06, 0, 0, 0x7FFF0000)])
    return program


def install_payload_filter():
    if sys.platform != "linux" or platform.machine() != "x86_64":
        return False
    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte), ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32)]
    class Program(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]
    instructions = payload_filter_instructions()
    array = (Filter * len(instructions))(*(Filter(*row) for row in instructions))
    program = Program(len(instructions), array)
    libc = ctypes.CDLL(None, use_errno=True)
    return libc.prctl(38, 1, 0, 0, 0) == 0 and libc.prctl(22, 2, ctypes.byref(program), 0, 0) == 0


def supervise(argv, grant_fd, life_fd, ack_fd, token, *, timeout_seconds=10, fixture=False):
    if sys.platform != "linux" or (not fixture and os.getpid() != 1) or len(token) != 32 or not argv or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
        return 125
    if len({grant_fd, life_fd, ack_fd}) != 3 or min(grant_fd, life_fd, ack_fd) < 3:
        return 125
    if not fixture:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(4, 0, 0, 0, 0) != 0 or libc.prctl(38, 1, 0, 0, 0) != 0:
            return 125
        if not install_payload_filter(): return 125
    keep = {0, 1, 2, grant_fd, life_fd, ack_fd}
    for name in os.listdir("/proc/self/fd"):
        descriptor = int(name)
        if descriptor not in keep:
            try: os.close(descriptor)
            except OSError: pass
    os.set_blocking(grant_fd, False); os.set_blocking(life_fd, False)
    process = None; started = False; termination = {"reason": "gate_error", "exit_code": 125}
    def finish(code, reason):
        termination.update(reason=reason, exit_code=code)
        return code
    selector = selectors.DefaultSelector()
    selector.register(life_fd, selectors.EVENT_READ, "life")
    selector.register(grant_fd, selectors.EVENT_READ, "grant")
    received = bytearray(); deadline = time.monotonic() + 20
    try:
        while len(received) < len(token):
            if time.monotonic() >= deadline: return finish(125, "admission_timeout")
            events = selector.select(0.1)
            # A dead supervisor wins even when authorization bytes were queued.
            if any(key.data == "life" for key, _ in events): return finish(125, "lifeline_closed")
            for key, _ in events:
                if key.data == "grant":
                    chunk = os.read(grant_fd, 33 - len(received))
                    if not chunk: return finish(125, "grant_eof")
                    received.extend(chunk)
                    if len(received) > 32: return finish(125, "invalid_grant")
        if bytes(received) != token: return finish(125, "invalid_grant")
        try:
            if os.read(life_fd, 1) == b"": return finish(125, "lifeline_closed")
            return finish(125, "invalid_lifeline")
        except BlockingIOError:
            pass
        selector.unregister(grant_fd); os.close(grant_fd); grant_fd = -1
        # No control descriptor or privileged descriptor is inherited by code.
        process = subprocess.Popen(argv, close_fds=True, stdin=None, stdout=None, stderr=None,
                                   env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8"}, cwd="/output" if not fixture else None)
        started = True
        ack = {"started": True, "token_digest": hashlib.sha256(token).hexdigest(), "child_pid": process.pid,
               "seccomp_policy": "fixture-no-seccomp" if fixture else SECCOMP_POLICY}
        os.write(ack_fd, json.dumps(ack).encode() + b"\n")
        wall_deadline = time.monotonic() + timeout_seconds
        while True:
            if selector.select(0.05): return finish(125, "lifeline_closed")
            if time.monotonic() >= wall_deadline: return finish(125, "wall_budget")
            code = process.poll()
            if code is not None:
                return finish(code if code >= 0 else min(255, 128 - code), "exited")
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            try: process.wait(timeout=1)
            except subprocess.TimeoutExpired: pass
        if started and ack_fd >= 0:
            try: os.write(ack_fd, json.dumps({"finished": True, "token_digest": hashlib.sha256(token).hexdigest(), **termination}).encode() + b"\n")
            except OSError: pass
        selector.close()
        for descriptor in (grant_fd, life_fd, ack_fd):
            if descriptor >= 0:
                try: os.close(descriptor)
                except OSError: pass
        # Production main uses os._exit; PID1 exit kills every descendant,
        # including a candidate that forked or changed sessions.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grant-fd", type=int, required=True)
    parser.add_argument("--lifeline-fd", type=int, required=True)
    parser.add_argument("--ack-fd", type=int, required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try: return supervise(command, args.grant_fd, args.lifeline_fd, args.ack_fd, bytes.fromhex(args.token), timeout_seconds=args.timeout_seconds)
    except (OSError, ValueError): return 125


if __name__ == "__main__":
    os._exit(main())
