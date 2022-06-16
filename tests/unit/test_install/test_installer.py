from collections.abc import MutableMapping
from zipfile import ZipFile
from pathlib import Path
from io import StringIO
import csv
import os
import logging
import sys
import subprocess
import sysconfig
import textwrap

import pytest

from pyproject_installer.install_cmd import install_wheel
from pyproject_installer.install_cmd._install import (
    digest_for_record,
    get_installation_scheme,
    SCRIPT_TEMPLATE,
    ALLOW_DIST_INFO_LIST,
    DENY_DIST_INFO_LIST,
)


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
                    Name: Test project
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


class InstalledWheel:
    def __init__(self, destdir, distr="foo", version="1.0", purelib=True):
        self.destdir = destdir
        self.sitedir = Path(
            str(destdir)
            + sysconfig.get_path("purelib" if purelib else "platlib")
        )
        self.distinfo = self.sitedir / f"{distr}-{version}.dist-info"
        self.data = self.sitedir / f"{distr}-{version}.data"
        self.scripts = Path(str(destdir) + sysconfig.get_path("scripts"))

    def filelist(self):
        actual_filelist = set()
        for root, dirs, files in os.walk(self.destdir):
            # add empty dirs
            if not dirs and not files:
                actual_filelist.add(Path(root))
                continue

            for f in files:
                actual_filelist.add(Path(root) / f)

        return actual_filelist


@pytest.fixture
def wheel_contents():
    def _wheel_contents(*args, **kwargs):
        return WheelContents(*args, **kwargs)

    return _wheel_contents


@pytest.fixture
def installed_wheel(tmpdir):
    def _installed_wheel(*args, **kwargs):
        destdir = tmpdir / "destdir"
        destdir.mkdir()
        return InstalledWheel(destdir, *args, **kwargs)

    return _installed_wheel


@pytest.fixture
def wheel(tmpdir):
    """Prepares wheel file"""

    def _wheel(name="foo-1.0-py3-none-any.whl", contents={}):
        wheeldir = tmpdir / "wheeldir"
        wheeldir.mkdir()
        wheel = wheeldir / name

        with ZipFile(wheel, "w") as z:
            for file, content in contents.items():
                z.writestr(file, content)

        return wheel

    return _wheel


@pytest.fixture
def sub_execs(tmpdir, request):
    """Makes named executables and format shebang for them"""
    sys_execs = tmpdir / "sys_execs"
    sys_execs.mkdir()
    sys_exec, expected_shebang = request.param
    sys_exec_path = sys_execs / sys_exec
    sys_exec_path.symlink_to(sys.executable)
    return str(sys_exec_path), expected_shebang.format(sys_execs=sys_execs)


def test_nonexistent_wheel(installed_wheel):
    with pytest.raises(ValueError, match="Unable to resolve path for wheel"):
        install_wheel(
            Path("/nonexistent/wheel.file"), destdir=installed_wheel().destdir
        )


@pytest.mark.skipif(os.geteuid() == 0, reason="Requires unprivileged user")
def test_unaccessible_destdir(wheel):
    with pytest.raises(ValueError, match="Unable to create path for destdir"):
        install_wheel(wheel(), destdir=Path("/unaccessible/dest/dir"))


@pytest.mark.parametrize(
    "wheel_name",
    (
        "distr",
        "distr.whl",
        "distr.zip",
        "-1.0-py3-none-any.whl",
        "distr--py3-none-any.whl",
        "distr-1.0.whl",
        "distr-1.0-build.whl",
        "distr-1.0-build-py3.whl",
        "distr-1.0-build-py3-none-any-extra.whl",
    ),
)
def test_invalid_wheel_name(wheel_name, wheel, installed_wheel):
    with pytest.raises(ValueError, match="Invalid wheel filename"):
        install_wheel(wheel(wheel_name), destdir=installed_wheel().destdir)


def test_missing_dist_info(wheel, installed_wheel):
    with pytest.raises(
        ValueError, match="Missing mandatory dist-info directory"
    ):
        install_wheel(wheel(), destdir=installed_wheel().destdir)


@pytest.mark.parametrize("missing_file", ("METADATA", "WHEEL", "RECORD"))
def test_missing_files_in_dist_info(
    missing_file, wheel_contents, wheel, installed_wheel
):
    contents = wheel_contents()
    del contents[f"foo-1.0.dist-info/{missing_file}"]

    with pytest.raises(
        ValueError,
        match=f"Missing mandatory {missing_file} in dist-info directory",
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_missing_wheel_version(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.dist-info/WHEEL"] = ""

    with pytest.raises(
        ValueError, match="Missing version number of Wheel spec"
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_unparseable_wheel_version(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.dist-info/WHEEL"] = "Wheel-Version: foo"
    with pytest.raises(
        ValueError, match="Invalid version number of Wheel spec: foo"
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_incompatible_wheel_version(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.dist-info/WHEEL"] = "Wheel-Version: 2.0"
    with pytest.raises(
        ValueError,
        match="Incompatible version of Wheel spec: 2.0, supported: 1.0",
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_greater_wheel_version(wheel_contents, wheel, installed_wheel, caplog):
    contents = wheel_contents()
    contents["foo-1.0.dist-info/WHEEL"] = "Wheel-Version: 1.1"
    logger = "pyproject_installer.install_cmd._install"
    caplog.set_level(logging.WARNING, logger=logger)

    install_wheel(wheel(contents=contents), destdir=installed_wheel().destdir)
    # assume only our warning emitted
    assert caplog.record_tuples == [
        (
            logger,
            logging.WARNING,
            (
                "Installing wheel having Wheel spec version: 1.1 newer than "
                "supported: 1.0"
            ),
        )
    ]


def test_empty_record(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents.record = ""
    with pytest.raises(ValueError, match="Empty RECORD file"):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_invalid_number_record(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents.record = ",,,"
    with pytest.raises(
        ValueError, match="Invalid number of fields in RECORD row:"
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


@pytest.mark.parametrize("hash_value", ("", "sha256="))
def test_invalid_hash_record(
    hash_value, wheel_contents, wheel, installed_wheel
):
    contents = wheel_contents()
    contents.record = f"foo-1.0.dist-info/METADATA,{hash_value},0"
    with pytest.raises(ValueError, match="Invalid hash record"):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_recorded_twice(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    metadata = "foo-1.0.dist-info/METADATA"
    contents.record += f"{metadata},sha256=123456,0"
    with pytest.raises(ValueError, match=f"Multiple records for: {metadata}"):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


@pytest.mark.parametrize(
    "hashes",
    (
        ("md5", "1B2M2Y8AsgTpgAmY7PhCfg"),
        ("sha1", "2jmj7l5rSw0yVb_vlWAYkK_YBwk"),
    ),
    ids=("md5", "sha1"),
)
def test_weak_hash_record(hashes, wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    extra_content = "extra_content.py"
    contents[extra_content] = ""
    # drop proper record for extra_content.py
    contents.drop_from_record(extra_content)
    hash_name, hash_value = hashes
    contents.record += f"{extra_content},{hash_name}={hash_value},0"

    with pytest.raises(
        ValueError,
        match=f"Too weak hash algorithm for records: {hash_name}",
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_incorrect_hash_record(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    extra_content = "extra_content.py"
    contents[extra_content] = ""
    # drop proper record for extra_content.py
    contents.drop_from_record(extra_content)
    contents.record += f"{extra_content},sha256=123456,0"

    with pytest.raises(
        ValueError,
        match=f"Incorrect hash for recorded file: {extra_content}",
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_not_recorded_files(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    extra_content = "extra_content.py"
    contents[extra_content] = ""
    # drop proper record for extra_content.py
    contents.drop_from_record(extra_content)

    with pytest.raises(
        ValueError,
        match=f"Extra packaged files not recorded in RECORD: {extra_content}",
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_extra_recorded_files(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    non_content = "non_content.py"
    contents.record += f"{non_content},sha256=123456,0\n"

    with pytest.raises(
        ValueError,
        match=f"Not packaged file but recorded in RECORD: {non_content}",
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_data_is_not_dir(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.data"] = ""
    with pytest.raises(
        ValueError, match="Optional .data should be a directory"
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_data_contains_files(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.data/bar"] = ""
    with pytest.raises(
        ValueError, match="Optional .data cannot contain files: bar"
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


def test_data_invalid_scheme_key(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.data/key/bar"] = ""
    with pytest.raises(
        ValueError,
        match="Optional .data contains unsupported scheme keys: key",
    ):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


@pytest.mark.parametrize("ep_spec", ("foo", "foo.bar"))
def test_invalid_entry_points(ep_spec, wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents[
        "foo-1.0.dist-info/entry_points.txt"
    ] = f"[console_scripts]\nbar = {ep_spec}\n"
    with pytest.raises(ValueError, match="Invalid entry_points specification"):
        install_wheel(
            wheel(contents=contents), destdir=installed_wheel().destdir
        )


@pytest.mark.parametrize("purelib", (True, False), ids=("purelib", "platlib"))
def test_extraction_root(purelib, wheel_contents, wheel, installed_wheel):
    contents = wheel_contents(purelib=purelib)
    dest_wheel = installed_wheel(purelib=purelib)
    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)

    assert dest_wheel.sitedir.exists()
    assert dest_wheel.sitedir.is_dir()


@pytest.mark.parametrize(
    "strip_dist_info", (None, True, False), ids=("default", "strip", "no_strip")
)
def test_record_not_installed(
    strip_dist_info, wheel_contents, wheel, installed_wheel
):
    """Check RECORD is not installed"""
    contents = wheel_contents()
    dest_wheel = installed_wheel()
    kwargs = {"destdir": dest_wheel.destdir}
    if strip_dist_info is not None:
        kwargs["strip_dist_info"] = strip_dist_info

    install_wheel(wheel(contents=contents), **kwargs)

    assert not (dest_wheel.distinfo / "RECORD").exists()


def test_installer_tool_default(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    dest_wheel = installed_wheel()
    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)

    assert not (dest_wheel.distinfo / "INSTALLER").exists()


def test_installer_tool_custom(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    dest_wheel = installed_wheel()
    install_wheel(
        wheel(contents=contents), destdir=dest_wheel.destdir, installer="rpm"
    )

    assert (dest_wheel.distinfo / "INSTALLER").read_text() == "rpm\n"


def test_data_removed(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.data/purelib/bar"] = "content\n"
    dest_wheel = installed_wheel()
    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)
    assert (
        Path(
            str(dest_wheel.destdir) + get_installation_scheme("foo")["purelib"]
        )
        / "bar"
    ).exists()
    assert not dest_wheel.data.exists()


@pytest.mark.parametrize(
    "strip_dist_info", (None, True, False), ids=("default", "strip", "no_strip")
)
def test_installation_filelist(
    strip_dist_info, wheel_contents, wheel, installed_wheel
):
    contents = wheel_contents()
    contents[
        "foo-1.0.dist-info/entry_points.txt"
    ] = "[console_scripts]\nbar = foo:main\n"

    dest_wheel = installed_wheel()
    kwargs = {"destdir": dest_wheel.destdir}
    if strip_dist_info is not None:
        kwargs["strip_dist_info"] = strip_dist_info

    install_wheel(wheel(contents=contents), **kwargs)

    expected_filelist = set()
    allowed_files = {
        str(Path(contents.distinfo) / x) for x in ALLOW_DIST_INFO_LIST
    }
    deny_files = {str(Path(contents.distinfo) / x) for x in DENY_DIST_INFO_LIST}

    for f in contents.keys():
        if (
            strip_dist_info is not False
            and f.startswith(contents.distinfo)
            and f not in allowed_files
        ):
            continue

        # unconditionally stripped by installer
        if f in deny_files:
            continue

        expected_filelist.add(dest_wheel.sitedir / f)

    # console script
    expected_filelist.add(dest_wheel.scripts / "bar")
    assert dest_wheel.filelist() == expected_filelist


@pytest.mark.parametrize(
    "scheme_key",
    ("purelib", "platlib", "headers", "scripts", "data"),
)
def test_data_scheme_keys(scheme_key, wheel_contents, wheel, installed_wheel):
    data_subpath_name = "foo/bar"
    data_name = f"foo-1.0.data/{scheme_key}/{data_subpath_name}"
    contents = wheel_contents()
    contents[data_name] = "content\n"

    dest_wheel = installed_wheel()

    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)

    expected_filelist = set()
    allowed_files = {
        str(Path(contents.distinfo) / x) for x in ALLOW_DIST_INFO_LIST
    }
    deny_files = {str(Path(contents.distinfo) / x) for x in DENY_DIST_INFO_LIST}

    for f in contents.keys():
        if f == data_name:
            expected_filelist.add(
                Path(
                    str(dest_wheel.destdir)
                    + get_installation_scheme("foo")[scheme_key]
                )
                / data_subpath_name
            )
            continue

        if f.startswith(contents.distinfo) and f not in allowed_files:
            continue

        # unconditionally stripped by installer
        if f in deny_files:
            continue

        expected_filelist.add(dest_wheel.sitedir / f)

    assert dest_wheel.filelist() == expected_filelist


@pytest.mark.parametrize(
    "sub_execs",
    (
        ("mypython", "#!{sys_execs}/mypython"),
        (
            f"{'very_' * 24}_long_mypython",
            f"#!/bin/sh\n'''exec' {{sys_execs}}/{'very_' * 24}_long_mypython"
            ' "$0" "$@"\n' + "' '''",
        ),
    ),
    indirect=True,
    ids=["regular_shebang", "long_shebang"],
)
def test_data_scripts(
    mocker, sub_execs, wheel_contents, wheel, installed_wheel
):
    sys_exec, expected_shebang = sub_execs
    mocker.patch(
        "pyproject_installer.install_cmd._install.sys.executable", sys_exec
    )
    contents = wheel_contents()
    contents["foo-1.0.data/scripts/bar"] = "#!python\nprint('Hello, World!')\n"

    dest_wheel = installed_wheel()

    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)
    script = dest_wheel.scripts / "bar"

    expected_content = f"{expected_shebang}\nprint('Hello, World!')\n"
    assert script.read_text() == expected_content

    result = subprocess.run([script], capture_output=True)
    assert result.returncode == 0
    assert result.stdout == b"Hello, World!\n"
    assert result.stderr == b""


@pytest.mark.parametrize(
    "sub_execs",
    (
        ("mypython", "#!{sys_execs}/mypython"),
        (
            f"{'very_' * 24}_long_mypython",
            f"#!/bin/sh\n'''exec' {{sys_execs}}/{'very_' * 24}_long_mypython"
            ' "$0" "$@"\n' + "' '''",
        ),
    ),
    indirect=True,
    ids=["regular_shebang", "long_shebang"],
)
def test_entry_points_scripts(
    mocker, sub_execs, wheel_contents, wheel, installed_wheel
):
    sys_exec, expected_shebang = sub_execs
    mocker.patch(
        "pyproject_installer.install_cmd._install.sys.executable", sys_exec
    )
    contents = wheel_contents()
    contents[
        "foo-1.0.dist-info/entry_points.txt"
    ] = "[console_scripts]\nbar = foo:main\n"

    dest_wheel = installed_wheel()

    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)
    script = dest_wheel.scripts / "bar"

    expected_content = SCRIPT_TEMPLATE.format(
        shebang=expected_shebang, module="foo", attr="main", main="main"
    )
    assert script.read_text() == expected_content

    new_env = os.environ.copy()
    new_env["PYTHONPATH"] = (
        str(dest_wheel.sitedir) + os.pathsep + new_env.get("PYTHONPATH", "")
    )
    result = subprocess.run([script], capture_output=True, env=new_env)
    assert result.returncode == 0
    assert result.stdout == b"Hello, World!\n"
    assert result.stderr == b""
