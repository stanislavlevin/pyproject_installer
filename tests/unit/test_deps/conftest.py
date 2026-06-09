from collections.abc import Callable
from pathlib import Path

import pytest

from pyproject_installer.deps_cmd.collectors.collector import Collector


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


@pytest.fixture
def pep735_deps(
    pyproject_toml: Callable[[str], Path],
) -> Callable[[dict[str, list[str]]], Path]:
    """Fill pyproject.toml with Dependency Groups dependencies (PEP735)"""

    def _pep735_deps(groups_data: dict[str, list[str]]) -> Path:
        contents = ["[dependency-groups]"]
        for group, deps in groups_data.items():
            contents.append(f"{group} = [{', '.join(deps)}]")

        return pyproject_toml("\n".join(contents) + "\n")

    return _pep735_deps


@pytest.fixture
def pip_reqfile(
    tmpdir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[str], Path]:
    """pip's requirements.txt file"""

    def _pip_reqfile(content: str) -> Path:
        reqfile_path = tmpdir / "requirements.txt"
        reqfile_path.write_text(content, encoding="utf-8")
        monkeypatch.chdir(tmpdir)
        return reqfile_path

    return _pip_reqfile


@pytest.fixture
def mock_collector(mocker):
    """Mock collector"""

    def _collector(reqs):
        class MockCollector(Collector):
            name = "mock_collector"

            def collect(self):
                yield from reqs

        mocker.patch(
            "pyproject_installer.deps_cmd.collectors.SUPPORTED_COLLECTORS",
            {"mock_collector": MockCollector},
        )

    return _collector
