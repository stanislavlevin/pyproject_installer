from collections.abc import MutableMapping
from io import StringIO
from pathlib import Path
from tempfile import mkdtemp
from zipfile import ZipFile
import csv
import shutil
import textwrap

import pytest

from pyproject_installer.lib.wheel import digest_for_record


class WheelContents(MutableMapping):
    def __init__(self, distr="foo", version="1.0", purelib=True):
        self.distinfo = f"{distr}-{version}.dist-info"
        self.record_key = f"{self.distinfo}/RECORD"
        self._contents = {
            f"{distr}/__init__.py": textwrap.dedent(
                """\
                    def main():
                        print("Hello, World!")
                """
            ),
            f"{self.distinfo}/METADATA": textwrap.dedent(
                f"""\
                    Metadata-Version: 2.1
                    Name: {distr}
                    Version: {version}
                    Platform: linux
                    Summary: Test project
                    Author-email: somebody@example.com
                    Classifier: License :: OSI Approved :: MIT License
                """
            ),
            f"{self.distinfo}/WHEEL": textwrap.dedent(
                f"""\
                    Wheel-Version: 1.0
                    Generator: bdist_wheel
                    Root-Is-Purelib: {str(purelib).lower()}
                    Tag: py3-none-any
                """
            ),
        }
        self.update_record()

    @property
    def record(self):
        return self._contents[self.record_key]

    @record.setter
    def record(self, value):
        self._contents[self.record_key] = value

    def update_record(self):
        with StringIO(newline="") as ws:
            writer = csv.writer(ws, lineterminator="\n")
            records = [
                (
                    f,
                    "sha256={}".format(
                        digest_for_record("sha256", v.encode("utf8"))
                    ),
                    0,
                )
                for f, v in self._contents.items()
                if f != self.record_key
            ]
            records.append((self.record_key, "", 0))
            writer.writerows(records)
            self.record = ws.getvalue()

    def drop_from_record(self, file):
        with StringIO(self.record, newline="") as rs, StringIO(
            newline=""
        ) as ws:
            reader = csv.reader(rs)
            writer = csv.writer(ws, lineterminator="\n")
            for row in reader:
                if row[0] != file:
                    writer.writerow(row)

            self.record = ws.getvalue()

    def __getitem__(self, key):
        return self._contents[key]

    def __setitem__(self, key, value):
        self._contents[key] = value
        if key != self.record_key:
            self.update_record()

    def __delitem__(self, key):
        del self._contents[key]
        if key != self.record_key:
            self.update_record()

    def __iter__(self):
        return iter(self._contents)

    def __len__(self):
        return len(self._contents)


@pytest.fixture
def tmpdir(tmp_path):
    yield tmp_path
    # Solaris: rmtree can't remove current working directory
    assert Path.cwd() != tmp_path
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


@pytest.fixture
def wheel_contents():
    def _wheel_contents(*args, **kwargs):
        return WheelContents(*args, **kwargs)

    return _wheel_contents


@pytest.fixture
def wheel(tmpdir):
    """Prepares wheel file"""

    def _wheel(name="foo-1.0-py3-none-any.whl", contents={}):
        # make it possible to rebuild wheel during a test
        wheeldir = Path(mkdtemp(dir=tmpdir))
        wheel = wheeldir / name

        with ZipFile(wheel, "w") as z:
            for file, content in contents.items():
                z.writestr(file, content)

        return wheel

    return _wheel


@pytest.fixture
def pyproject_with_backend(pyproject, monkeypatch):
    """Generates pyproject with self-hosted build backend"""

    def _build_backend_src(be_content):
        be_module = "be"
        pyproject_toml_content = textwrap.dedent(
            f"""\
            [build-system]
            requires=[]
            build-backend="{be_module}"
            backend-path=["."]
            """
        )
        pyproject_path = pyproject(pyproject_toml_content)

        backend_path = pyproject_path / be_module
        backend_path.mkdir()
        (backend_path / "__init__.py").write_text(be_content)

        monkeypatch.chdir(pyproject_path)
        return pyproject_path

    return _build_backend_src


@pytest.fixture
def pyproject_metadata(pyproject_with_backend):
    """Build backend with prepare_metadata_for_build_wheel"""
    default_content_fields = [
        "Metadata-Version: 2.1",
        "Name: foo",
        "Version: 1.0",
    ]

    def _core_metadata(headers=default_content_fields, reqs=[]):
        content_fields = list(headers)
        for req in reqs:
            content_fields.append(f"Requires-Dist: {req}")

        be_content = textwrap.dedent(
            """\
            def prepare_metadata_for_build_wheel(
                metadata_directory, config_settings=None
            ):
                from pathlib import Path

                distinfo = "foo-1.0.dist-info"
                distinfo_path = Path(metadata_directory) / distinfo
                distinfo_path.mkdir()
                metadata_path = distinfo_path / "METADATA"
                content = "{content}"

                metadata_path.write_text(content, encoding="utf-8")

                return distinfo

            def build_wheel(
                wheel_directory, config_settings=None, metadata_directory=None
            ):
                # prepare_metadata_for_build_wheel is preferred over build_wheel
                assert False
            """
        ).format(content="\\n".join(content_fields) + "\\n")
        return pyproject_with_backend(be_content)

    return _core_metadata


@pytest.fixture
def pyproject_metadata_wheel(pyproject_with_backend, wheel_contents, wheel):
    """Build backend with build_wheel only"""
    default_content_fields = [
        "Metadata-Version: 2.1",
        "Name: foo",
        "Version: 1.0",
    ]

    def _core_metadata(headers=default_content_fields, reqs=[]):
        contents = wheel_contents()
        content_fields = list(headers)
        content_fields.extend((f"Requires-Dist: {x}" for x in reqs))
        metadata_content = "\n".join(content_fields) + "\n"
        contents["foo-1.0.dist-info/METADATA"] = metadata_content
        wheel_path = wheel(contents=contents)

        be_content = textwrap.dedent(
            f"""\
            from pathlib import Path


            def build_wheel(
                wheel_directory, config_settings=None, metadata_directory=None
            ):
                target_path = Path(wheel_directory) / "{wheel_path.name}"
                Path("{wheel_path}").rename(target_path)
                return "{wheel_path.name}"
            """
        )
        return pyproject_with_backend(be_content)

    return _core_metadata
