"""The benchmark that ships with the package: memory is really measured, missing samples are reported."""

from gelcam import bench


def test_peak_memory_is_measured():
    assert bench.rss_mb() > 10  # a Python process with numpy imported is never below 10 MB


def test_real_pipeline_reports_missing_frames(tmp_path, capsys):
    bench.bench_real_pipeline(tmp_path)
    assert "skipped" in capsys.readouterr().out


def test_real_pipeline_on_a_case_insensitive_disk_does_not_see_frames_twice(tmp_path, capsys):
    for name in ("lights", "darks"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "a.CR2").write_bytes(b"x")  # not a valid frame: the run fails, but only after listing
    try:
        bench.bench_real_pipeline(tmp_path)
    except Exception:  # noqa: BLE001 - the fake frames cannot be read
        pass
    assert "Real pipeline: 1 lights, 1 darks" in capsys.readouterr().out
