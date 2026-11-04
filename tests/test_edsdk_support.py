"""Testy částí vrstvy EDSDK, které jdou spustit bez Windows a bez SDK."""

import importlib.util
import threading
import time
from pathlib import Path

import pytest

from gelcam.camera.edsdk import constants as C
from gelcam.camera.edsdk.binding import diritem_size_is_64bit
from gelcam.camera.edsdk.worker import EdsdkWorker

ROOT = Path(__file__).resolve().parents[1]


def _load_checker():
    spec = importlib.util.spec_from_file_location("checker", ROOT / "tools" / "check_edsdk_constants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_worker_runs_in_own_thread():
    w = EdsdkWorker()
    try:
        assert w.call(lambda: threading.current_thread()) is w.thread
        assert w.call(lambda a, b: a + b, 2, 3) == 5
    finally:
        w.stop()


def test_worker_propagates_exceptions():
    w = EdsdkWorker()
    try:
        with pytest.raises(ValueError):
            w.call(lambda: (_ for _ in ()).throw(ValueError("x")))
    finally:
        w.stop()


def test_worker_nested_call_runs_inline():
    w = EdsdkWorker()
    try:
        assert w.call(lambda: w.call(lambda: 42)) == 42
    finally:
        w.stop()


def test_worker_periodic_and_wait():
    w = EdsdkWorker()
    hits = []
    try:
        w.call(lambda: w.every(0.02, lambda: hits.append(1)))
        time.sleep(0.15)
        assert len(hits) >= 3
        assert w.call(lambda: w.wait_until(lambda: False, timeout=0.05)) is False
    finally:
        w.stop()


def test_checker_detects_mismatch(tmp_path):
    checker = _load_checker()
    (tmp_path / "EDSDKTypes.h").write_text(
        "#define kEdsPropID_ISOSpeed  0x00000402\n"
        "typedef enum {\n  kEdsCameraCommand_DoEvfAf = 0x00000999,\n} EdsCameraCommand;\n",
        encoding="latin-1",
    )
    (tmp_path / "EDSDKErrors.h").write_text("#define EDS_ERR_OK  0x00000000UL\n", encoding="latin-1")
    found = checker.parse_headers(tmp_path)
    assert found["kEdsPropID_ISOSpeed"] == 0x402
    assert found["EDS_ERR_OK"] == 0
    mismatched, missing = checker.compare(C.CHECKED, found)
    assert any(m.startswith("kEdsCameraCommand_DoEvfAf") for m in mismatched)
    assert "kEdsPropID_Tv" in missing


def test_diritem_size_detection(tmp_path):
    assert diritem_size_is_64bit(None) is True
    h = tmp_path / "EDSDKTypes.h"
    h.write_text("typedef struct tagEdsDirectoryItemInfo\n{\n    EdsUInt32 size;\n    EdsBool isFolder;\n} X;\n")
    assert diritem_size_is_64bit(tmp_path) is False
    h.write_text("typedef struct tagEdsDirectoryItemInfo\n{\n    EdsUInt64 size;\n    EdsBool isFolder;\n} X;\n")
    assert diritem_size_is_64bit(tmp_path) is True


def test_checked_constants_are_unique_names():
    assert "kEdsPropID_ISOSpeed" in C.CHECKED and "EDS_ERR_OK" in C.CHECKED
    assert "AE_MODE_MANUAL" not in C.CHECKED
