"""Flat library: storage, the rules for when a flat applies, the UV cross-check and flat measurement."""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from gelcam.acquisition import flat as flat_acq
from gelcam.storage import flat_library as lib
from gelcam.testing.synthetic import SIM_BLACK, SyntheticGel, expose

NOW = datetime(2026, 11, 18, 12, 0)


def _frames(folder: Path, n: int, level: float, *, seed: int, vignetting: float = 0.3, white: int = 15000) -> None:
    """n synthetic flat mosaics (.npy) with a known vignetting: level = photons at the centre."""
    rng = np.random.default_rng(seed)
    gel = SyntheticGel(height=240, width=320, vignetting=vignetting)
    signal = gel.flat_field()
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        np.save(folder / f"f_{i:02d}.npy", expose(signal, rng, photons=level, read_noise=4.0, white_level=white))


def _set(tmp_path: Path, light="uv70", seconds=4.0, n=8, level=4000.0, when=NOW, **kw) -> lib.FlatSet:
    folder = lib.new_flat_dir(tmp_path, light, when)
    _frames(folder / "flat", n, level, seed=1)
    _frames(folder / "dark", n, 0.0, seed=2)
    return flat_acq.build_flat_set(folder, light=light, channel="R", iso=100, seconds=seconds, aperture=8.0,
                                   target="blank gel", zoom_marked=True, lens="EF-S18-55", created=when, **kw)


def test_set_round_trip_and_listing(tmp_path):
    a = _set(tmp_path, "uv70", when=NOW - timedelta(days=3))
    b = _set(tmp_path, "uv100", when=NOW)
    (tmp_path / "junk").mkdir()
    (tmp_path / "half").mkdir()
    (tmp_path / "half" / "flat.json").write_text("{not json", encoding="utf-8")
    found = lib.list_flats(tmp_path)
    assert [f.id for f in found] == [b.id, a.id]  # newest first; broken folders ignored
    assert found[0].light == "uv100" and found[1].path == a.path
    assert len(found[0].flat_paths) == 8 and all(p.exists() for p in found[0].dark_paths)
    assert lib.list_flats(tmp_path / "missing") == []


def test_new_flat_dir_never_reuses_a_folder(tmp_path):
    first = lib.new_flat_dir(tmp_path, "uv70", NOW)
    second = lib.new_flat_dir(tmp_path, "uv70", NOW)
    assert first != second and second.name.endswith("_2")
    with pytest.raises(ValueError):
        lib.new_flat_dir(tmp_path, "red", NOW)


def test_measured_statistics_match_the_known_vignetting(tmp_path):
    s = _set(tmp_path, level=4000.0)
    gel = SyntheticGel(height=240, width=320, vignetting=0.3)
    f = gel.flat_field()
    h, w = f.shape
    true_ratio = f[int(0.04 * h):int(0.04 * h) + int(0.06 * h), :int(0.06 * w) + int(0.04 * w)].mean() / f[
        int(0.4 * h):int(0.6 * h), int(0.4 * w):int(0.6 * w)].mean()
    assert 0.6 < s.corner_ratio < 0.95 and s.corner_ratio == pytest.approx(true_ratio, abs=0.12)
    assert s.centre_adu > 1000 and s.saturated_fraction == 0.0
    assert s.centre_rate == pytest.approx(s.centre_adu / 4.0)


def test_exposure_advice_and_proposal():
    ok = flat_acq.FlatStats(7000, 0.6, 0.7, 0.0)
    assert flat_acq.advice(ok) is None
    assert flat_acq.advice(flat_acq.FlatStats(2000, 0.2, 0.7, 0.0)) == "dark"
    assert flat_acq.advice(flat_acq.FlatStats(11000, 0.9, 0.7, 0.0)) == "bright"
    assert flat_acq.advice(flat_acq.FlatStats(7000, 0.6, 0.7, 0.01)) == "saturated"
    assert flat_acq.propose_flat_seconds(4.0, 0.2) == pytest.approx(4.0 * 0.65 / 0.2)
    assert flat_acq.propose_flat_seconds(20.0, 0.1) == 30.0  # never beyond 30 s


def test_assess_rules(tmp_path):
    f = _set(tmp_path, "uv70", when=NOW)
    arr = lib.Arrangement("uv70", 8.0, "EF-S18-55")
    a = lib.assess(f, arr, NOW)
    assert a.status == "ok" and a.reasons == () and a.usable

    assert lib.assess(f, lib.Arrangement("uv100", 8.0, "EF-S18-55"), NOW).reasons == ("light",)
    assert "aperture" in lib.assess(f, lib.Arrangement("uv70", 5.6, "EF-S18-55"), NOW).reasons
    assert "lens" in lib.assess(f, lib.Arrangement("uv70", 8.0, "EF 50mm"), NOW).reasons
    assert lib.assess(f, lib.Arrangement("uv70", 8.0, None), NOW).status == "ok"  # unknown lens: no objection

    old = lib.assess(f, arr, NOW + timedelta(days=31))
    assert old.status == "warn" and old.reasons == ("old",) and old.age_days == 31 and old.usable
    assert lib.assess(f, arr, NOW + timedelta(days=30)).status == "ok"  # 30 days is still fine


def test_assess_warnings_and_incomplete_sets(tmp_path):
    f = _set(tmp_path, "uv70", when=NOW)
    arr = lib.Arrangement("uv70", 8.0)
    unconfirmed = lib.FlatSet(**{**f.__dict__, "zoom_marked": False})
    assert lib.assess(unconfirmed, arr, NOW).reasons == ("zoom_unconfirmed",)
    saturated = lib.FlatSet(**{**f.__dict__, "saturated_fraction": 0.05})
    assert lib.assess(saturated, arr, NOW).reasons == ("saturated",)
    few = lib.FlatSet(**{**f.__dict__, "flats": f.flats[:3]})
    assert lib.assess(few, arr, NOW).reasons == ("incomplete",)
    f.flat_paths[0].unlink()  # a frame deleted from the library
    a = lib.assess(f, arr, NOW)
    assert a.status == "mismatch" and a.reasons == ("files_missing",) and not a.usable


def test_ranking_prefers_matching_then_newest(tmp_path):
    old70 = _set(tmp_path, "uv70", when=NOW - timedelta(days=40))
    new70 = _set(tmp_path, "uv70", when=NOW - timedelta(days=2))
    new100 = _set(tmp_path, "uv100", when=NOW)
    order = [f.id for f, _a in lib.ranked([old70, new100, new70], lib.Arrangement("uv70", 8.0), NOW)]
    assert order == [new70.id, old70.id, new100.id]  # ok, then warn (old), then mismatch (other UV level)


def test_uv_cross_check_catches_gross_errors_only(tmp_path):
    f70 = _set(tmp_path, "uv70", seconds=4.0, when=NOW)  # rate = centre_adu / 4
    f100 = lib.FlatSet(**{**_set(tmp_path, "uv100", seconds=4.0, when=NOW).__dict__})
    rate70, rate100 = f70.centre_rate, f100.centre_rate
    flats = [f70, f100]

    ok = lib.check_uv_level(flats, "uv70", rate70 * 0.9)
    assert ok.status == "ok" and ok.suggests is None
    assert lib.check_uv_level(flats, "uv100", rate70 * 1.2).status == "ok"  # 70 vs 100 % cannot be told apart

    dark = lib.check_uv_level([f70], "uv70", rate70 * 0.1)  # lamp off / far too dim
    assert dark.status == "warn" and dark.suggests is None and dark.ratio == pytest.approx(0.1)
    bright = lib.check_uv_level([f70], "uv70", rate70 * 5)
    assert bright.status == "warn"

    unknown = lib.check_uv_level([f70], "uv100", rate70)  # no flat of the declared level
    assert unknown.status == "unknown" and unknown.ratio is None
    assert lib.check_uv_level(flats, "uv70", 0.0).status == "unknown"

    dim = [lib.FlatSet(**{**f70.__dict__, "centre_adu": f70.centre_adu * 0.1}), f100]
    hint = lib.check_uv_level(dim, "uv70", rate100)  # looks 10x brighter than the declared flat, fits the other
    assert hint.status == "warn" and hint.suggests == "uv100"


def test_register_existing_copies_and_never_leaves_half_a_set(tmp_path):
    src = tmp_path / "src"
    _frames(src / "f", 8, 4000.0, seed=3)
    _frames(src / "d", 8, 0.0, seed=4)
    flats, darks = sorted((src / "f").glob("*.npy")), sorted((src / "d").glob("*.npy"))
    root = tmp_path / "lib"
    s = flat_acq.register_existing(root, flats, darks, light="white", channel="R", iso=100, seconds=8.0,
                                   aperture=8.0, target="white paper", created=NOW)
    assert s.light == "white" and len(s.flats) == 8 and (s.path / "flat" / "flat_01.NPY").exists()
    assert len(list((src / "f").glob("*.npy"))) == 8  # originals untouched
    with pytest.raises(FileNotFoundError):
        flat_acq.register_existing(root, [tmp_path / "nope.npy"], darks, light="white", channel="R", iso=100,
                                   seconds=8.0, aperture=8.0, target="x", created=NOW)
    assert [f.id for f in lib.list_flats(root)] == [s.id]
    assert len([d for d in root.iterdir() if d.is_dir()]) == 1  # the failed attempt left nothing behind


def test_black_level_is_removed_before_measuring(tmp_path):
    s = _set(tmp_path, level=100.0)
    assert 0 < s.centre_adu < 600 < SIM_BLACK  # centre brightness is above black, not an absolute value
