from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def depsconfig_path(
    tmpdir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    depsconfig_path = tmpdir / "foo.json"
    monkeypatch.chdir(tmpdir)
    return depsconfig_path


@pytest.fixture
def depsconfig(depsconfig_path: Path) -> Callable[..., Path]:
    """Create deps config"""
    default_content = '{"sources": {"foo": {"srctype": "metadata"}}}'

    def _gen_depsconfig(content: str = default_content) -> Path:
        depsconfig_path.write_text(content, encoding="utf-8")
        return depsconfig_path

    return _gen_depsconfig
