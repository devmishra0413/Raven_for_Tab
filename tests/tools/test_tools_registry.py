import pytest

registry = pytest.importorskip("tools.registry")

EXPECTED_TOOLS = [
    "set_reminder", "add_note", "read_note", "search_files",
    "play_song", "pause_media", "next_track", "set_volume", "open_app",
]


def _get_registry():
    for name in ("registry", "REGISTRY", "ToolRegistry", "get_registry"):
        obj = getattr(registry, name, None)
        if obj is None:
            continue
        if callable(obj):
            try:
                return obj()
            except TypeError:
                continue
        return obj
    pytest.skip("No registry object found in tools.registry")


def _names(reg):
    for attr in ("names", "list_tools", "list", "all"):
        fn = getattr(reg, attr, None)
        if callable(fn):
            out = fn()
            return [getattr(t, "name", t) for t in out]
    for attr in ("tools", "_tools"):
        d = getattr(reg, attr, None)
        if isinstance(d, dict):
            return list(d.keys())
    pytest.skip("Cannot list tools from registry")


def test_registry_not_empty():
    assert len(_names(_get_registry())) > 0


@pytest.mark.parametrize("tool", EXPECTED_TOOLS)
def test_expected_tool_registered(tool):
    assert tool in _names(_get_registry())


def test_tool_names_unique():
    names = _names(_get_registry())
    assert len(names) == len(set(names))


def test_unknown_tool_not_registered():
    assert "rm_rf_everything" not in _names(_get_registry())