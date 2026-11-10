import hashlib
import resource
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pytest

from gelcam.camera import MockCamera
from gelcam.processing.framestack import FrameStack, build_stack
from gelcam.processing.stack import sigma_clip_mean
from gelcam.testing.synthetic import SyntheticGel, expose

CALIB = Path(__file__).resolve().parents[1] / "testdata" / "calib"
SCENE = CALIB / "2026-11-04_scene_4s_iso100_uv100"


def synth_frames(n: int, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    sig = SyntheticGel().signal()
    return np.stack([expose(sig, rng).astype(np.float32) for _ in range(n)])


def test_noise_drops_with_sqrt_n():
    frames = synth_frames(16)
    mean, _ = sigma_clip_mean(frames)
    bg = (slice(5, 60), slice(5, 60))  # corner without lanes or bands
    ratio = mean[bg].std() / frames[0][bg].std()
    assert 0.2 < ratio < 0.3


def test_cosmic_ray_rejected():
    frames = synth_frames(16)
    clean, _ = sigma_clip_mean(frames)
    frames[7, 100:103, 50:52] += 5000
    mean, rejected = sigma_clip_mean(frames)
    assert rejected >= 6
    assert np.abs(mean[100:103, 50:52] - clean[100:103, 50:52]).max() < 20


def test_tiles_and_memmap_identical(tmp_path):
    frames = synth_frames(6)
    a, ra = sigma_clip_mean(frames, tile_rows=5)
    b, rb = sigma_clip_mean(frames, tile_rows=10000)
    assert a.dtype == np.float32 and np.array_equal(a, b) and ra == rb
    mm = np.memmap(tmp_path / "s.dat", np.float32, "w+", shape=frames.shape)
    mm[:] = frames
    c, _ = sigma_clip_mean(mm, tile_rows=7)
    assert np.array_equal(a, c)


def test_small_n_plain_mean():
    frames = synth_frames(2)
    mean, rejected = sigma_clip_mean(frames)
    assert rejected == 0 and np.allclose(mean, frames.mean(axis=0))


def _capture(tmp_path, n):
    cam = MockCamera(seed=3)
    cam.connect()
    return [cam.capture(tmp_path / "raw") for _ in range(n)]


def test_build_stack_from_mock_frames_and_discard(tmp_path):
    paths = _capture(tmp_path, 4)
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    st = build_stack(paths, "R", tmp_path / "work" / "stack.dat")
    assert isinstance(st, FrameStack)
    assert st.array.shape[0] == 4 and st.array.dtype == np.float32
    assert st.saturated.dtype == bool and st.saturated.shape == st.array.shape[1:]
    assert len(st.saturated_per_frame) == 4 and st.file.exists()
    st.discard()
    assert not st.file.exists()
    assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]


def test_build_stack_shape_mismatch_names_file(tmp_path):
    paths = _capture(tmp_path, 2)
    odd = tmp_path / "odd.npy"
    np.save(odd, np.zeros((100, 100), np.uint16))
    with pytest.raises(ValueError, match="odd.npy"):
        build_stack([*paths, odd], "R", tmp_path / "s.dat")
    assert not (tmp_path / "s.dat").exists()


def test_sigma_clip_memory_below_one_float32_stack(tmp_path):
    st = build_stack(_capture(tmp_path, 8), "R", tmp_path / "s.dat")
    full = st.array.size * 4
    tracemalloc.start()
    try:
        mean, _ = sigma_clip_mean(st.array, tile_rows=8)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert mean.dtype == np.float32 and peak < full
    st.discard()


@pytest.mark.skipif(not SCENE.exists(), reason="testdata/calib scene missing")
def test_real_data_noise_ratio(tmp_path):
    paths = sorted(SCENE.glob("*.CR2"))[:8]
    t0 = time.perf_counter()
    st = build_stack(paths, "R", tmp_path / "real.dat")
    mean, rej = sigma_clip_mean(st.array)
    dt = time.perf_counter() - t0
    h, w = mean.shape
    # flattest 64x64 block: lowest local mean-of-stack gradient proxy = smallest std of the stack mean
    best = None
    for y in range(0, h - 64, 64):
        for x in range(0, w - 64, 64):
            blk = (slice(y, y + 64), slice(x, x + 64))
            if st.saturated[blk].any():
                continue
            s = mean[blk].std()
            if best is None or s < best[0]:
                best = (s, blk)
    assert best is not None
    ratio = best[0] / st.array[0][best[1]].std()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(f"\nreal: ratio={ratio:.3f} rejected={rej} time={dt:.1f}s maxrss={rss}")
    assert 0.30 < ratio < 0.45
    st.discard()


def test_ten_sigma_spike_rejected_and_gaussian_rarely_rejected():
    rng = np.random.default_rng(5)
    frames = rng.normal(1000, 7, (8, 200, 200)).astype(np.float32)
    _, rej_clean = sigma_clip_mean(frames)
    assert rej_clean < 0.01 * frames.size
    clean, _ = sigma_clip_mean(frames)
    frames[3, 50:53, 60:63] += 70  # 10 sigma
    mean, rej = sigma_clip_mean(frames)
    assert rej >= rej_clean + 9 - 5  # spike samples rejected (clean rejections may overlap)
    assert np.abs(mean[50:53, 60:63] - clean[50:53, 60:63]).max() < 7
