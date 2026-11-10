"""A single thread that owns EDSDK.

On Windows, EDSDK delivers events (e.g. an image ready for download)
via Windows messages, so the thread that initializes the SDK must run
with COM in STA mode and regularly process the message queue. All calls
to the SDK are therefore sent here via `call()` and wait for the result.
"""

from __future__ import annotations

import ctypes
import queue
import sys
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable

COINIT_APARTMENTTHREADED = 0x2
PM_REMOVE = 0x0001


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint32),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
        ("lPrivate", ctypes.c_uint32),
    ]


def _make_pump() -> Callable[[], None]:
    """Processes pending Windows messages; does nothing outside Windows."""
    if sys.platform != "win32":
        return lambda: None
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    msg = _MSG()
    pmsg = ctypes.byref(msg)

    def pump() -> None:
        while user32.PeekMessageW(pmsg, None, 0, 0, PM_REMOVE):
            user32.TranslateMessage(pmsg)
            user32.DispatchMessageW(pmsg)

    return pump


class EdsdkWorker:
    """Thread with a task queue, message pump and periodic tasks."""

    def __init__(self, name: str = "edsdk", poll_interval: float = 0.01) -> None:
        self._tasks: queue.Queue[tuple[Callable[[], Any], Future] | None] = queue.Queue()
        self._periodic: list[tuple[float, float, Callable[[], None]]] = []
        self._poll = poll_interval
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._started = threading.Event()
        self._pump: Callable[[], None] = lambda: None
        self._thread.start()
        self._started.wait()

    # --- public API (callable from any thread) ---
    def call(self, fn: Callable[..., Any], *args: Any, timeout: float | None = 30.0, **kwargs: Any) -> Any:
        if threading.current_thread() is self._thread:
            return fn(*args, **kwargs)
        fut: Future = Future()
        self._tasks.put((lambda: fn(*args, **kwargs), fut))
        return fut.result(timeout=timeout)

    def every(self, interval: float, fn: Callable[[], None]) -> None:
        """Runs `fn` on the SDK thread every `interval` seconds (register on the SDK thread)."""
        self._periodic.append((interval, time.monotonic() + interval, fn))

    def wait_until(self, predicate: Callable[[], bool], timeout: float) -> bool:
        """On the SDK thread: waits for a condition while processing Windows messages."""
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                return False
            self._pump()
            time.sleep(self._poll)
        return True

    def stop(self) -> None:
        self._tasks.put(None)
        self._thread.join(timeout=5)

    @property
    def thread(self) -> threading.Thread:
        return self._thread

    # --- thread ---
    def _run(self) -> None:
        if sys.platform == "win32":
            ctypes.windll.ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)  # type: ignore[attr-defined]
        self._pump = _make_pump()
        self._started.set()
        try:
            while True:
                self._pump()
                self._run_periodic()
                try:
                    item = self._tasks.get(timeout=self._poll)
                except queue.Empty:
                    continue
                if item is None:
                    break
                fn, fut = item
                if not fut.set_running_or_notify_cancel():
                    continue
                try:
                    fut.set_result(fn())
                except BaseException as exc:  # noqa: BLE001 - passed on to the caller
                    fut.set_exception(exc)
        finally:
            if sys.platform == "win32":
                ctypes.windll.ole32.CoUninitialize()  # type: ignore[attr-defined]

    def _run_periodic(self) -> None:
        now = time.monotonic()
        for i, (interval, due, fn) in enumerate(self._periodic):
            if now >= due:
                self._periodic[i] = (interval, now + interval, fn)
                try:
                    fn()
                except Exception:  # noqa: BLE001 - a periodic task must not crash the thread
                    pass
