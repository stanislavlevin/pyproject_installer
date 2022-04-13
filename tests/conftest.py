import shutil
import textwrap

import pytest


@pytest.fixture
def tmpdir(tmp_path):
    yield tmp_path
    shutil.rmtree(tmp_path)


@pytest.fixture
def wheeldir(tmpdir):
    wheeldir = tmpdir / "dist"
    wheeldir.mkdir()
    return wheeldir


@pytest.fixture
def destdir(tmpdir):
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    return destdir


@pytest.fixture
def pyproject(tmpdir):
    def _pyproject(toml_text=None):
        if toml_text is None:
            toml_text = textwrap.dedent(
                """\
                [build-system]
                requires=[]
                build-backend="be"
                """
            )
        project_path = tmpdir / "srcroot"
        project_path.mkdir()
        pyproject_toml = project_path / "pyproject.toml"
        pyproject_toml.write_text(toml_text)
        return project_path

    return _pyproject
