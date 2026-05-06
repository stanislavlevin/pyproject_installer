import csv
import shutil
import textwrap
from collections.abc import Callable, Iterator, MutableMapping
from io import StringIO
from pathlib import Path
from tempfile import mkdtemp
from typing import Any
from zipfile import ZipFile

import pytest

from pyproject_installer.lib.wheel import digest_for_record

default_content_fields = [
    "Metadata-Version: 2.1",
    "Name: foo",
    "Version: 1.0",
]


class WheelContents(MutableMapping[str, "str | bytes"]):

    def __init__(
        self,
        *,
        distr: str = "foo",
        version: str = "1.0",
        purelib: bool = True,
        create_init: bool = True,
    ) -> None:
        self.distinfo = f"{distr}-{version}.dist-info"
        self.record_key = f"{self.distinfo}/RECORD"
        self._contents: dict[str, str | bytes] = {
            **(
                {
                    f"{distr}/__init__.py": textwrap.dedent(
                        """\
                            def main():
                                print("Hello, World!")
                        """,
                    ),
                }
                if create_init
                else {}
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
                """,
            ),
            f"{self.distinfo}/WHEEL": textwrap.dedent(
                f"""\
                    Wheel-Version: 1.0
                    Generator: bdist_wheel
                    Root-Is-Purelib: {str(purelib).lower()}
                    Tag: py3-none-any
                """,
            ),
        }
        self.update_record()

    @property
    def record(self) -> str:
        return str(self._contents[self.record_key])

    @record.setter
    def record(self, value: str) -> None:
        self._contents[self.record_key] = value

    def update_record(self) -> None:
        with StringIO(newline="") as ws:
            writer = csv.writer(ws, lineterminator="\n")
            records = [
                (
                    f,
                    "sha256={}".format(
                        digest_for_record(
                            "sha256",
                            v if isinstance(v, bytes) else v.encode("utf8"),
                        ),
                    ),
                    0,
                )
                for f, v in self._contents.items()
                if f != self.record_key
            ]
            records.append((self.record_key, "", 0))
            writer.writerows(records)
            self.record = ws.getvalue()

    def drop_from_record(self, file: str) -> None:
        with (
            StringIO(self.record, newline="") as rs,
            StringIO(newline="") as ws,
        ):
            reader = csv.reader(rs)
            writer = csv.writer(ws, lineterminator="\n")
            for row in reader:
                if row[0] != file:
                    writer.writerow(row)

            self.record = ws.getvalue()

    def __getitem__(self, key: str) -> str | bytes:
        return self._contents[key]

    def __setitem__(self, key: str, value: str | bytes) -> None:
        self._contents[key] = value
        if key != self.record_key:
            self.update_record()

    def __delitem__(self, key: str) -> None:
        del self._contents[key]
        if key != self.record_key:
            self.update_record()

    def __iter__(self) -> Iterator[str]:
        return iter(self._contents)

    def __len__(self) -> int:
        return len(self._contents)


@pytest.fixture
def tmpdir(tmp_path: Path) -> Iterator[Path]:
    yield tmp_path
    # Solaris: rmtree can't remove current working directory
    assert Path.cwd() != tmp_path
    shutil.rmtree(tmp_path)


@pytest.fixture
def wheeldir(tmpdir: Path) -> Path:
    wheeldir = tmpdir / "dist"
    wheeldir.mkdir()
    return wheeldir


@pytest.fixture
def destdir(tmpdir: Path) -> Path:
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    return destdir


@pytest.fixture
def pyproject(tmpdir: Path) -> Callable[..., Path]:
    def _pyproject(toml_text: str | None = None) -> Path:
        if toml_text is None:
            toml_text = textwrap.dedent(
                """\
                [build-system]
                requires=[]
                build-backend="be"
                """,
            )
        project_path = tmpdir / "srcroot"
        project_path.mkdir()
        pyproject_toml = project_path / "pyproject.toml"
        pyproject_toml.write_text(toml_text)
        return project_path

    return _pyproject


@pytest.fixture
def pyproject_toml(
    pyproject: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[str], Path]:
    """Create pyproject.toml and cd to its directory"""

    def _pyproject_toml(content: str) -> Path:
        pyproject_path = pyproject(content)
        monkeypatch.chdir(pyproject_path)
        return pyproject_path

    return _pyproject_toml


@pytest.fixture
def wheel_contents() -> Callable[..., WheelContents]:
    def _wheel_contents(**kwargs: Any) -> WheelContents:
        return WheelContents(**kwargs)

    return _wheel_contents


@pytest.fixture
def wheel(tmpdir: Path) -> Callable[..., Path]:
    """Prepares wheel file"""

    def _wheel(
        name: str = "foo-1.0-py3-none-any.whl",
        contents: dict[str, str | bytes] | None = None,
    ) -> Path:
        if contents is None:
            contents = {}
        # make it possible to rebuild wheel during a test
        wheeldir = Path(mkdtemp(dir=tmpdir))
        wheel = wheeldir / name

        with ZipFile(wheel, "w") as z:
            for file, content in contents.items():
                z.writestr(file, content)

        return wheel

    return _wheel


@pytest.fixture
def pyproject_with_backend(
    pyproject: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[str], Path]:
    """Generates pyproject with self-hosted build backend"""

    def _build_backend_src(be_content: str) -> Path:
        be_module = "be"
        pyproject_toml_content = textwrap.dedent(
            f"""\
            [build-system]
            requires=[]
            build-backend="{be_module}"
            backend-path=["."]
            """,
        )
        pyproject_path = pyproject(pyproject_toml_content)

        backend_path = pyproject_path / be_module
        backend_path.mkdir()
        (backend_path / "__init__.py").write_text(be_content)

        monkeypatch.chdir(pyproject_path)
        return pyproject_path

    return _build_backend_src


@pytest.fixture
def pyproject_metadata(
    pyproject_with_backend: Callable[[str], Path],
) -> Callable[..., Path]:
    """Build backend with prepare_metadata_for_build_wheel"""

    def _core_metadata(
        headers: list[str] = default_content_fields,
        reqs: tuple[str, ...] = (),
    ) -> Path:
        content_fields = [
            *headers,
            *(f"Requires-Dist: {req}" for req in reqs),
        ]

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
            """,
        ).format(content="\\n".join(content_fields) + "\\n")
        return pyproject_with_backend(be_content)

    return _core_metadata


@pytest.fixture
def pyproject_metadata_wheel(
    pyproject_with_backend: Callable[[str], Path],
    wheel_contents: Callable[..., WheelContents],
    wheel: Callable[..., Path],
) -> Callable[..., Path]:
    """Build backend with build_wheel only"""

    def _core_metadata(
        headers: list[str] = default_content_fields,
        reqs: tuple[str, ...] = (),
    ) -> Path:
        contents = wheel_contents()
        content_fields = list(headers)
        content_fields.extend(f"Requires-Dist: {x}" for x in reqs)
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
            """,
        )
        return pyproject_with_backend(be_content)

    return _core_metadata
