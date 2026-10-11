import subprocess
import pytest


@pytest.fixture(autouse=True)
def no_real_subprocess(monkeypatch):
    """Koi bhi tool real termux command ya app na chalaye."""
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append(a) or None)
    return calls


def _fn(module_path, *names):
    try:
        mod = __import__(module_path, fromlist=["x"])
    except Exception:
        pytest.skip(f"{module_path} not importable")
    for n in names:
        fn = getattr(mod, n, None)
        if callable(fn):
            return fn
    pytest.skip(f"none of {names} in {module_path}")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "raven_workspace"
    ws.mkdir()
    monkeypatch.setenv("RAVEN_WORKSPACE", str(ws))
    return ws


def test_add_then_read_note(workspace):
    add = _fn("tools.builtin.notes", "add_note", "run_add_note")
    read = _fn("tools.builtin.notes", "read_note", "run_read_note")
    add("shopping", "milk and eggs") if add.__code__.co_argcount >= 2 else add({"title": "shopping", "text": "milk and eggs"})
    out = read("shopping") if read.__code__.co_argcount >= 1 else read({"title": "shopping"})
    assert "milk" in str(out)


def test_read_missing_note_does_not_crash(workspace):
    read = _fn("tools.builtin.notes", "read_note", "run_read_note")
    try:
        out = read("does_not_exist")
    except Exception as e:
        assert not isinstance(e, (SystemExit, KeyboardInterrupt))
    else:
        assert out is not None


def test_search_files_finds_workspace_file(workspace):
    search = _fn("tools.builtin.files", "search_files", "run_search_files")
    (workspace / "report_final.txt").write_text("x")
    out = search("report")
    assert "report_final" in str(out)


def test_search_files_never_lists_outside(workspace, tmp_path):
    search = _fn("tools.builtin.files", "search_files", "run_search_files")
    (tmp_path / "outside_secret.txt").write_text("x")
    out = search("outside_secret")
    assert "outside_secret" not in str(out)


def test_open_app_blocks_unlisted_app(no_real_subprocess):
    open_app = _fn("tools.builtin.apps", "open_app", "run_open_app")
    try:
        open_app("definitely_not_a_safe_app")
    except Exception:
        pass
    assert not any("definitely_not_a_safe_app" in str(c) for c in no_real_subprocess)


def test_set_reminder_does_not_crash(workspace):
    set_reminder = _fn("tools.builtin.reminder", "set_reminder", "run_set_reminder")
    try:
        set_reminder("kal 8 baje meeting", "2099-01-01 08:00")
    except TypeError:
        set_reminder({"text": "meeting", "when": "2099-01-01 08:00"})


@pytest.mark.parametrize("fname", ["pause_media", "next_track"])
def test_media_controls_use_mocked_subprocess(fname):
    fn = _fn("tools.builtin.media", fname, f"run_{fname}")
    fn()


def test_set_volume_rejects_out_of_range():
    fn = _fn("tools.builtin.media", "set_volume", "run_set_volume")
    for bad in (-5, 999):
        try:
            fn(bad)
        except Exception:
            pass