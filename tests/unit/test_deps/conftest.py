import pytest


@pytest.fixture
def depsconfig_path(tmpdir, monkeypatch):
    depsconfig_path = tmpdir / "foo.json"
    monkeypatch.chdir(tmpdir)
    return depsconfig_path


@pytest.fixture
def depsconfig(depsconfig_path):
    """Create deps config"""
    default_content = '{"sources": {"foo": {"srctype": "metadata"}}}'

    def _gen_depsconfig(content=default_content):
        depsconfig_path.write_text(content, encoding="utf-8")
        return depsconfig_path

    return _gen_depsconfig
