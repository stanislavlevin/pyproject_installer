import logging
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import textwrap
from importlib.util import cache_from_source
from pathlib import Path
from zipfile import ZipFile

import pytest

from pyproject_installer.errors import WheelFileError
from pyproject_installer.install_cmd import install_wheel
from pyproject_installer.install_cmd._install import (
    get_installation_scheme,
)
from pyproject_installer.lib.scripts import SCRIPT_TEMPLATE
from pyproject_installer.lib.wheel import WheelFile


def expected_pyc_lines(path):
    return (cache_from_source(path, optimization=opt) for opt in ("", "1", "2"))


class InstalledWheel:
    def __init__(self, destdir, *, distr="foo", version="1.0", purelib=True):
        self.destdir = destdir
        self.sitedir = Path(
            str(destdir)
            + sysconfig.get_path("purelib" if purelib else "platlib"),
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
def compiled_binary(tmpdir):
    gcc_exe = shutil.which("gcc")
    if gcc_exe is None:
        pytest.skip("Requires gcc to compile a test binary")

    def _compiled_binary(exec_name, content):
        output_bin = tmpdir / exec_name
        source_c = tmpdir / f"{exec_name}.c"
        source_c.write_text(content)
        gcc_cmd = [gcc_exe, "-o", output_bin, source_c]
        subprocess.check_call(gcc_cmd)
        return output_bin

    return _compiled_binary


@pytest.fixture
def installed_wheel(tmpdir):
    def _installed_wheel(*args, **kwargs):
        destdir = tmpdir / "destdir"
        destdir.mkdir()
        return InstalledWheel(destdir, *args, **kwargs)

    return _installed_wheel


@pytest.fixture
def sub_execs(tmpdir, request):
    """Makes named executables and format shebang for them"""
    sys_execs = tmpdir / "sys_execs"
    sys_execs.mkdir()
    sys_exec, expected_shebang = request.param
    sys_exec_path = sys_execs / sys_exec
    sys_exec_path.symlink_to(sys.executable)
    return str(sys_exec_path), expected_shebang.format(sys_execs=sys_execs)


@pytest.fixture
def wheel_dir(tmpdir):
    """
    Compat make dir in wheel:
    https://docs.python.org/3/library/zipfile.html#zipfile.ZipFile.mkdir
    """

    def _wheel_dir(whl, dirname):
        with ZipFile(whl, "a") as z:
            if sys.version_info >= (3, 11):
                # pylint: disable-next=no-member,useless-suppression
                z.mkdir(dirname)
            else:
                (dir_path := tmpdir / dirname).mkdir()
                z.write(dir_path, dirname)

    return _wheel_dir


def test_nonexistent_wheel(installed_wheel):
    with pytest.raises(ValueError, match="Unable to resolve path for wheel"):
        install_wheel(
            Path("/nonexistent/wheel.file"),
            destdir=installed_wheel().destdir,
        )


def test_bad_wheel(tmpdir, destdir):
    bad_whl = tmpdir / "wheel.whl"
    bad_whl.touch(exist_ok=False)
    with pytest.raises(
        WheelFileError,
        match=f"Error reading wheel {bad_whl}: ",
    ):
        install_wheel(bad_whl, destdir=destdir)


def test_extract_raises_when_zipfile_uninitialized(
    wheel,
    wheel_contents,
    tmpdir,
):
    """WheelFile.extract rejects use when _zipfile ended up unset."""
    wf = WheelFile(wheel(contents=wheel_contents()))
    wf._zipfile = None  # noqa: SLF001  # simulate post-init corruption
    with pytest.raises(WheelFileError, match="Wheel was not initialized"):
        wf.extract(tmpdir / "extract_target")


def test_extract_default_members_uses_memberlist(
    wheel,
    wheel_contents,
    installed_wheel,
):
    """extract() without a members argument extracts the full memberlist."""
    dest_wheel = installed_wheel()
    wf = WheelFile(wheel(contents=wheel_contents()))
    wf.extract(dest_wheel.destdir)  # no members= -> default-members branch
    expected_filelist = {
        dest_wheel.destdir / f
        for f in (
            "foo/__init__.py",
            "foo-1.0.dist-info/METADATA",
            "foo-1.0.dist-info/WHEEL",
            "foo-1.0.dist-info/RECORD",
        )
    }
    assert dest_wheel.filelist() == expected_filelist


@pytest.mark.skipif(
    # pylint: disable-next=use-implicit-booleaness-not-comparison-to-zero
    os.geteuid() == 0,
    reason="Requires unprivileged user",
)
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
        ValueError,
        match="Missing mandatory dist-info directory",
    ):
        install_wheel(wheel(), destdir=installed_wheel().destdir)


@pytest.mark.parametrize("missing_file", ("METADATA", "WHEEL", "RECORD"))
def test_missing_files_in_dist_info(
    missing_file,
    wheel_contents,
    wheel,
    installed_wheel,
):
    contents = wheel_contents()
    del contents[f"foo-1.0.dist-info/{missing_file}"]

    with pytest.raises(
        ValueError,
        match=f"Missing mandatory {missing_file} in dist-info directory",
    ):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


def test_missing_wheel_version(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.dist-info/WHEEL"] = ""

    with pytest.raises(
        ValueError,
        match="Missing version number of Wheel spec",
    ):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


def test_unparseable_wheel_version(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.dist-info/WHEEL"] = "Wheel-Version: foo"
    with pytest.raises(
        ValueError,
        match="Invalid version number of Wheel spec: foo",
    ):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


def test_incompatible_wheel_version(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.dist-info/WHEEL"] = "Wheel-Version: 2.0"
    with pytest.raises(
        ValueError,
        match=re.escape(
            "Incompatible version of Wheel spec: 2.0, supported: 1.0",
        ),
    ):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


def test_greater_wheel_version(wheel_contents, wheel, installed_wheel, caplog):
    contents = wheel_contents()
    contents["foo-1.0.dist-info/WHEEL"] = "Wheel-Version: 1.1"
    logger = "pyproject_installer.lib.wheel"
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
        ),
    ]


def test_empty_record(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents.record = ""
    with pytest.raises(ValueError, match="Empty RECORD file"):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


def test_invalid_number_record(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents.record = ",,,"
    with pytest.raises(
        ValueError,
        match="Invalid number of fields in RECORD row:",
    ):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


@pytest.mark.parametrize("hash_value", ("", "sha256="))
def test_invalid_hash_record(
    hash_value,
    wheel_contents,
    wheel,
    installed_wheel,
):
    contents = wheel_contents()
    contents.record = f"foo-1.0.dist-info/METADATA,{hash_value},0"
    with pytest.raises(ValueError, match="Invalid hash record"):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


def test_recorded_twice(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    metadata = "foo-1.0.dist-info/METADATA"
    contents.record += f"{metadata},sha256=123456,0"
    with pytest.raises(ValueError, match=f"Multiple records for: {metadata}"):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
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
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
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
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
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
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


def test_non_empty_wheel_dirs(
    wheel_contents,
    wheel_dir,
    wheel,
    installed_wheel,
):
    """Non empty wheel dirs are ignored (not verified and not installed)"""
    contents = wheel_contents()
    parent_dir = "parentdir"
    extra_content = f"{parent_dir}/__init__.py"
    contents[extra_content] = ""
    whl = wheel(contents=contents)
    wheel_dir(whl, parent_dir)
    dest_wheel = installed_wheel()
    install_wheel(whl, destdir=dest_wheel.destdir)

    expected_filelist = {
        dest_wheel.sitedir / f
        for f in (
            "foo-1.0.dist-info/METADATA",
            "foo/__init__.py",
            extra_content,
        )
    }

    assert dest_wheel.filelist() == expected_filelist


def test_empty_wheel_dirs(
    wheel_contents,
    wheel_dir,
    wheel,
    installed_wheel,
):
    """Empty wheel dirs are ignored (not verified and not installed)"""
    contents = wheel_contents()
    whl = wheel(contents=contents)
    wheel_dir(whl, "empty_dir")
    dest_wheel = installed_wheel()
    install_wheel(whl, destdir=dest_wheel.destdir)

    expected_filelist = {
        dest_wheel.sitedir / f
        for f in (
            "foo-1.0.dist-info/METADATA",
            "foo/__init__.py",
        )
    }
    assert dest_wheel.filelist() == expected_filelist


def test_extra_recorded_files(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    non_content = "non_content.py"
    contents.record += f"{non_content},sha256=123456,0\n"

    with pytest.raises(
        ValueError,
        match=f"Not packaged file but recorded in RECORD: {non_content}",
    ):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


def test_data_is_not_dir(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.data"] = ""
    with pytest.raises(
        ValueError,
        match=re.escape("Optional .data should be a directory"),
    ):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


def test_data_contains_files(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.data/bar"] = ""
    with pytest.raises(
        ValueError,
        match=re.escape("Optional .data cannot contain files: bar"),
    ):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


def test_data_invalid_scheme_key(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.data/key/bar"] = ""
    with pytest.raises(
        ValueError,
        match=re.escape("Optional .data contains unsupported scheme keys: key"),
    ):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


@pytest.mark.parametrize("ep_spec", ("foo", "foo.bar"))
def test_invalid_entry_points(ep_spec, wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.dist-info/entry_points.txt"] = (
        f"[console_scripts]\nbar = {ep_spec}\n"
    )
    with pytest.raises(ValueError, match="Invalid entry_points specification"):
        install_wheel(
            wheel(contents=contents),
            destdir=installed_wheel().destdir,
        )


@pytest.mark.parametrize("purelib", (True, False), ids=("purelib", "platlib"))
def test_extraction_root(purelib, wheel_contents, wheel, installed_wheel):
    contents = wheel_contents(purelib=purelib)
    dest_wheel = installed_wheel(purelib=purelib)
    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)

    assert dest_wheel.sitedir.exists()
    assert dest_wheel.sitedir.is_dir()


@pytest.mark.parametrize(
    "strip_dist_info",
    (None, True, False),
    ids=("default", "strip", "no_strip"),
)
def test_record_not_installed(
    strip_dist_info,
    wheel_contents,
    wheel,
    installed_wheel,
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
        wheel(contents=contents),
        destdir=dest_wheel.destdir,
        installer="rpm",
    )

    assert (dest_wheel.distinfo / "INSTALLER").read_text() == "rpm\n"


def test_data_removed(wheel_contents, wheel, installed_wheel):
    contents = wheel_contents()
    contents["foo-1.0.data/purelib/bar"] = "content\n"
    dest_wheel = installed_wheel()
    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)
    assert (
        Path(
            str(dest_wheel.destdir) + get_installation_scheme("foo")["purelib"],
        )
        / "bar"
    ).exists()
    assert not dest_wheel.data.exists()


@pytest.mark.parametrize(
    "strip_dist_info",
    (None, True, False),
    ids=("default", "strip", "no_strip"),
)
def test_installation_filelist(
    strip_dist_info,
    wheel_contents,
    wheel,
    installed_wheel,
):
    contents = wheel_contents()
    contents["foo-1.0.dist-info/entry_points.txt"] = (
        "[console_scripts]\nbar = foo:main\n"
    )

    dest_wheel = installed_wheel()
    kwargs = {"destdir": dest_wheel.destdir}
    if strip_dist_info is not None:
        kwargs["strip_dist_info"] = strip_dist_info

    install_wheel(wheel(contents=contents), **kwargs)

    expected_filelist = {
        dest_wheel.sitedir / f
        for f in (
            "foo-1.0.dist-info/METADATA",
            "foo-1.0.dist-info/entry_points.txt",
            "foo/__init__.py",
            *(("foo-1.0.dist-info/WHEEL",) if strip_dist_info is False else ()),
        )
    }
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

    expected_filelist = {
        *{
            dest_wheel.sitedir / f
            for f in (
                "foo-1.0.dist-info/METADATA",
                "foo/__init__.py",
            )
        },
        Path(
            str(dest_wheel.destdir)
            + get_installation_scheme("foo")[scheme_key],
        )
        / data_subpath_name,
    }

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
    mocker,
    sub_execs,
    wheel_contents,
    wheel,
    installed_wheel,
):
    sys_exec, expected_shebang = sub_execs
    mocker.patch(
        "pyproject_installer.install_cmd._install.sys.executable",
        sys_exec,
    )
    contents = wheel_contents()
    contents["foo-1.0.data/scripts/bar"] = "#!python\nprint('Hello, World!')\n"

    dest_wheel = installed_wheel()

    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)
    script = dest_wheel.scripts / "bar"

    expected_content = f"{expected_shebang}\nprint('Hello, World!')\n"
    assert script.read_text() == expected_content

    result = subprocess.run([script], capture_output=True, check=True)
    assert result.stdout == b"Hello, World!\n"
    assert result.stderr == b""


def test_data_binary_scripts(
    compiled_binary,
    wheel_contents,
    wheel,
    installed_wheel,
):
    """
    Test that compiled binary can be executed on installation
    """
    binary_name = "foo_binary"
    binary_path = compiled_binary(
        binary_name,
        textwrap.dedent(
            """\
            #include <stdio.h>
            int main() {
               printf("Hello, World!\\n");
            }
            """,
        ),
    )

    contents = wheel_contents()
    contents[f"foo-1.0.data/scripts/{binary_name}"] = binary_path.read_bytes()

    dest_wheel = installed_wheel()

    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)
    script = dest_wheel.scripts / binary_name

    result = subprocess.run([script], capture_output=True, check=True)
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
    mocker,
    sub_execs,
    wheel_contents,
    wheel,
    installed_wheel,
):
    sys_exec, expected_shebang = sub_execs
    mocker.patch(
        "pyproject_installer.install_cmd._install.sys.executable",
        sys_exec,
    )
    contents = wheel_contents()
    contents["foo-1.0.dist-info/entry_points.txt"] = (
        "[console_scripts]\nbar = foo:main\n"
    )

    dest_wheel = installed_wheel()

    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)
    script = dest_wheel.scripts / "bar"

    expected_content = SCRIPT_TEMPLATE.format(
        shebang=expected_shebang,
        module="foo",
        attr="main",
        main="main",
    )
    assert script.read_text() == expected_content

    new_env = os.environ.copy()
    new_env["PYTHONPATH"] = (
        str(dest_wheel.sitedir) + os.pathsep + new_env.get("PYTHONPATH", "")
    )
    result = subprocess.run(
        [script],
        capture_output=True,
        env=new_env,
        check=True,
    )
    assert result.stdout == b"Hello, World!\n"
    assert result.stderr == b""


def test_rpm_filelist_empty(wheel_contents, wheel, tmpdir):
    """
    Check rpm filelist for empty wheel.
    """
    contents = wheel_contents(create_init=False)
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    filelist = tmpdir / "foo.files"

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        rpm_filelist=filelist,
    )

    recorded_files = filelist.read_text(encoding="utf-8").splitlines()
    purelib = get_installation_scheme("foo")["purelib"]
    expected_files = sorted(
        (
            f"%dir {purelib}/foo-1.0.dist-info",
            f"{purelib}/foo-1.0.dist-info/METADATA",
        ),
    )
    assert recorded_files == expected_files


def test_rpm_filelist_entrypoints_scripts(wheel_contents, wheel, tmpdir):
    """
    Check if console script is recorded in rpm filelist.
    """
    contents = wheel_contents(create_init=False)
    contents["foo-1.0.dist-info/entry_points.txt"] = (
        "[console_scripts]\nbar = foo:main\n"
    )
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    filelist = tmpdir / "foo.files"

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        rpm_filelist=filelist,
    )
    recorded_files = filelist.read_text(encoding="utf-8").splitlines()
    script_name = str(
        Path(get_installation_scheme("foo")["scripts"]) / "bar",
    )
    purelib = get_installation_scheme("foo")["purelib"]
    expected_files = sorted(
        (
            f"%dir {purelib}/foo-1.0.dist-info",
            f"{purelib}/foo-1.0.dist-info/METADATA",
            f"{purelib}/foo-1.0.dist-info/entry_points.txt",
            script_name,
        ),
    )
    assert recorded_files == expected_files


def test_rpm_filelist_data(wheel_contents, wheel, tmpdir):
    """
    Check if data entries are recorded in rpm filelist.
    """
    contents = wheel_contents(create_init=False)
    contents["foo-1.0.data/data/share/foo/asset.dat"] = ""
    contents["foo-1.0.data/purelib/foo/purelib.foo.py"] = ""
    contents["foo-1.0.data/platlib/foo/platlib.foo.py"] = ""
    contents["foo-1.0.data/purelib/purelib.bar.py"] = ""
    contents["foo-1.0.data/platlib/platlib.bar.py"] = ""
    contents["foo-1.0.data/headers/foo.h"] = ""
    contents["foo-1.0.data/headers/foo/bar.h"] = ""
    contents["foo-1.0.data/scripts/foo"] = ""
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    filelist = tmpdir / "foo.files"

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        rpm_filelist=filelist,
    )

    recorded_files = filelist.read_text(encoding="utf-8").splitlines()
    purelib, platlib, headers, scripts, data = (
        get_installation_scheme("foo")[name]
        for name in ("purelib", "platlib", "headers", "scripts", "data")
    )
    expected_files = sorted(
        (
            f"%dir {headers}",
            f"{headers}/foo.h",
            f"%dir {headers}/foo",
            f"{headers}/foo/bar.h",
            f"%dir {purelib}/foo",
            f"{purelib}/foo/purelib.foo.py",
            f"%dir {purelib}/foo/__pycache__",
            *expected_pyc_lines(f"{purelib}/foo/purelib.foo.py"),
            f"{platlib}/foo/platlib.foo.py",
            *expected_pyc_lines(f"{platlib}/foo/platlib.foo.py"),
            f"{purelib}/purelib.bar.py",
            *expected_pyc_lines(f"{purelib}/purelib.bar.py"),
            f"{platlib}/platlib.bar.py",
            *expected_pyc_lines(f"{platlib}/platlib.bar.py"),
            f"%dir {purelib}/foo-1.0.dist-info",
            f"{purelib}/foo-1.0.dist-info/METADATA",
            f"{scripts}/foo",
            f"{data}/share/foo/asset.dat",
            *(
                (f"%dir {platlib}/foo", f"%dir {platlib}/foo/__pycache__")
                if purelib != platlib
                else ()
            ),
        ),
    )
    assert recorded_files == expected_files


def test_rpm_filelist_site(wheel_contents, wheel, tmpdir):
    """
    Check if site (purelib/platlib) entries are recorded in rpm filelist.
    """
    contents = wheel_contents()
    contents["site_foo.py"] = ""
    contents["foo/bar/__init__.py"] = ""
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    filelist = tmpdir / "foo.files"

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        rpm_filelist=filelist,
    )

    recorded_files = filelist.read_text(encoding="utf-8").splitlines()
    purelib = get_installation_scheme("foo")["purelib"]
    expected_files = sorted(
        (
            f"%dir {purelib}/foo",
            f"{purelib}/foo/__init__.py",
            f"%dir {purelib}/foo/__pycache__",
            *expected_pyc_lines(f"{purelib}/foo/__init__.py"),
            f"%dir {purelib}/foo/bar",
            f"{purelib}/foo/bar/__init__.py",
            f"%dir {purelib}/foo/bar/__pycache__",
            *expected_pyc_lines(f"{purelib}/foo/bar/__init__.py"),
            f"{purelib}/site_foo.py",
            *expected_pyc_lines(f"{purelib}/site_foo.py"),
            f"%dir {purelib}/foo-1.0.dist-info",
            f"{purelib}/foo-1.0.dist-info/METADATA",
        ),
    )
    assert recorded_files == expected_files


def test_rpm_filelist_not_used(wheel_contents, wheel, tmpdir):
    """
    Check if rpm filelist is not generated if was not asked
    """
    contents = wheel_contents()
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    filelist = tmpdir / "foo.files"

    install_wheel(wheel(contents=contents), destdir=destdir)

    assert not filelist.exists()


def test_rpm_filelist_installer(wheel_contents, wheel, tmpdir):
    """
    Check if INSTALLER in rpm filelist if used
    """
    contents = wheel_contents(create_init=False)
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    filelist = tmpdir / "foo.files"

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        installer="test_installer",
        rpm_filelist=filelist,
    )

    recorded_files = filelist.read_text(encoding="utf-8").splitlines()
    purelib = get_installation_scheme("foo")["purelib"]
    expected_files = sorted(
        (
            f"%dir {purelib}/foo-1.0.dist-info",
            f"{purelib}/foo-1.0.dist-info/METADATA",
            f"{purelib}/foo-1.0.dist-info/INSTALLER",
        ),
    )
    assert recorded_files == expected_files


def test_rpm_filelist_no_strip_dist_info(wheel_contents, wheel, tmpdir):
    """
    Check if PEP 639 licenses/ in rpm filelist with --no-strip-dist-info
    """
    contents = wheel_contents(create_init=False)
    contents["foo-1.0.dist-info/licenses/LICENSE.txt"] = "MIT\n"
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    filelist = tmpdir / "foo.files"

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        rpm_filelist=filelist,
        strip_dist_info=False,
    )

    recorded_files = filelist.read_text(encoding="utf-8").splitlines()
    purelib = get_installation_scheme("foo")["purelib"]
    expected_files = sorted(
        (
            f"%dir {purelib}/foo-1.0.dist-info",
            f"{purelib}/foo-1.0.dist-info/METADATA",
            f"{purelib}/foo-1.0.dist-info/WHEEL",
            f"%dir {purelib}/foo-1.0.dist-info/licenses",
            f"{purelib}/foo-1.0.dist-info/licenses/LICENSE.txt",
        ),
    )
    assert recorded_files == expected_files


def test_rpm_filelist_man_page_globbing(wheel_contents, wheel, tmpdir):
    """
    Check man page globbing in rpm flielist.
    """
    contents = wheel_contents(create_init=False)
    contents["foo-1.0.data/data/share/man/man1/aaa.1"] = ""
    contents["foo-1.0.data/data/share/man/man1/bbb.1.gz"] = ""
    contents["foo-1.0.data/data/share/man/man1/ccc.1.bz2"] = ""
    contents["foo-1.0.data/data/share/man/man1/ddd.1.Z"] = ""
    contents["foo-1.0.data/data/share/man/man1/eee.1.xz"] = ""
    contents["foo-1.0.data/data/share/man/man1/fff.1.zst"] = ""
    contents["foo-1.0.data/data/share/man/man3/Baz.3pm"] = ""
    contents["foo-1.0.data/data/share/man/man3/Qux.3pm.gz"] = ""
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    filelist = tmpdir / "foo.files"

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        rpm_filelist=filelist,
    )

    recorded_files = filelist.read_text(encoding="utf-8").splitlines()
    purelib = get_installation_scheme("foo")["purelib"]
    data = get_installation_scheme("foo")["data"]
    expected_files = sorted(
        (
            f"%dir {purelib}/foo-1.0.dist-info",
            f"{purelib}/foo-1.0.dist-info/METADATA",
            f"{data}/share/man/man1/aaa.1*",
            f"{data}/share/man/man1/bbb.1*",
            f"{data}/share/man/man1/ccc.1*",
            f"{data}/share/man/man1/ddd.1*",
            f"{data}/share/man/man1/eee.1.xz*",
            f"{data}/share/man/man1/fff.1.zst*",
            f"{data}/share/man/man3/Baz.3pm*",
            f"{data}/share/man/man3/Qux.3pm*",
        ),
    )
    assert recorded_files == expected_files


def test_rpm_filelist_sys_pycache_prefix(
    wheel_contents,
    wheel,
    tmpdir,
    mocker,
):
    """
    Check the error if sys.pycache_prefix is set
    """
    contents = wheel_contents(create_init=False)
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    filelist = tmpdir / "foo.files"

    mocker.patch(
        "pyproject_installer.install_cmd._install.sys.pycache_prefix",
        "/new_prefix",
    )
    error_pattern = "rpm-filelist requires sys.pycache_prefix to be at its"
    with pytest.raises(ValueError, match=error_pattern):
        install_wheel(
            wheel(contents=contents),
            destdir=destdir,
            rpm_filelist=filelist,
        )
    assert not filelist.exists()


@pytest.mark.parametrize(
    "wheel_purelib",
    (True, False),
    ids=("purelib", "platlib"),
)
@pytest.mark.parametrize(
    "force_site",
    ("purelib", "platlib"),
    ids=("force_purelib", "force_platlib"),
)
def test_extraction_root_force_site(
    wheel_purelib,
    force_site,
    wheel_contents,
    wheel,
    tmpdir,
):
    """
    Check force_site overrides Root-Is-Purelib for root extraction.
    """
    contents = wheel_contents(purelib=wheel_purelib)
    destdir = tmpdir / "destdir"
    destdir.mkdir()

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        force_site=force_site,
    )

    scheme = get_installation_scheme("foo")
    chosen_sitedir = Path(str(destdir) + scheme[force_site])
    other_site = "platlib" if force_site == "purelib" else "purelib"
    other_sitedir = Path(str(destdir) + scheme[other_site])

    # /usr/lib and /usr/lib64 may collapse to the same path on
    # non-multilib distros; only assert the negative when the two
    # paths actually differ.
    assert (chosen_sitedir / "foo" / "__init__.py").exists()
    if chosen_sitedir != other_sitedir:
        assert not (other_sitedir / "foo" / "__init__.py").exists()


@pytest.mark.parametrize(
    "force_site,other_site",
    (
        ("platlib", "purelib"),
        ("purelib", "platlib"),
    ),
    ids=("force_platlib", "force_purelib"),
)
def test_force_site_redirects_data_subdir(
    force_site,
    other_site,
    wheel_contents,
    wheel,
    tmpdir,
):
    """
    Check .data/<other-site> content follows force_site to chosen site.
    """
    contents = wheel_contents()
    contents[f"foo-1.0.data/{other_site}/extra.txt"] = "content\n"
    destdir = tmpdir / "destdir"
    destdir.mkdir()

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        force_site=force_site,
    )

    scheme = get_installation_scheme("foo")
    chosen_sitedir = Path(str(destdir) + scheme[force_site])
    other_sitedir = Path(str(destdir) + scheme[other_site])

    assert (chosen_sitedir / "extra.txt").exists()
    if chosen_sitedir != other_sitedir:
        assert not (other_sitedir / "extra.txt").exists()


@pytest.mark.parametrize(
    "force_site,wheel_purelib,other_site",
    (
        ("platlib", False, "purelib"),
        ("purelib", True, "platlib"),
    ),
    ids=("force_platlib", "force_purelib"),
)
def test_force_site_idempotent_root_redirects_data(
    force_site,
    wheel_purelib,
    other_site,
    wheel_contents,
    wheel,
    tmpdir,
):
    """
    Check force_site already aligned with Root-Is-Purelib keeps the
    root unchanged but still redirects .data/<other-site> content to
    the chosen site.
    """
    contents = wheel_contents(purelib=wheel_purelib)
    contents[f"foo-1.0.data/{other_site}/extra.txt"] = "content\n"
    destdir = tmpdir / "destdir"
    destdir.mkdir()

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        force_site=force_site,
    )

    scheme = get_installation_scheme("foo")
    chosen_sitedir = Path(str(destdir) + scheme[force_site])
    other_sitedir = Path(str(destdir) + scheme[other_site])

    # root stayed in chosen site (no change vs default)
    assert (chosen_sitedir / "foo" / "__init__.py").exists()
    if chosen_sitedir != other_sitedir:
        assert not (other_sitedir / "foo" / "__init__.py").exists()
    # .data/<other-site> content followed the override
    assert (chosen_sitedir / "extra.txt").exists()
    if chosen_sitedir != other_sitedir:
        assert not (other_sitedir / "extra.txt").exists()


@pytest.mark.parametrize(
    "force_site",
    ("platlib", "purelib"),
)
def test_force_site_both_data_subdirs_consolidated(
    force_site,
    wheel_contents,
    wheel,
    tmpdir,
):
    """
    Check force_site consolidates both .data/purelib and .data/platlib
    content into the chosen site.
    """
    contents = wheel_contents()
    contents["foo-1.0.data/purelib/from_purelib.txt"] = "p\n"
    contents["foo-1.0.data/platlib/from_platlib.txt"] = "P\n"
    destdir = tmpdir / "destdir"
    destdir.mkdir()

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        force_site=force_site,
    )

    chosen_sitedir = Path(
        str(destdir) + get_installation_scheme("foo")[force_site],
    )
    assert (chosen_sitedir / "from_purelib.txt").exists()
    assert (chosen_sitedir / "from_platlib.txt").exists()


@pytest.mark.parametrize(
    "force_site",
    ("platlib", "purelib"),
    ids=("force_platlib", "force_purelib"),
)
@pytest.mark.parametrize(
    "wheel_purelib",
    (True, False),
    ids=("wheel_purelib", "wheel_platlib"),
)
@pytest.mark.parametrize(
    "data_purelib",
    ("purelib", "platlib"),
    ids=("data_purelib", "data_platlib"),
)
def test_rpm_filelist_under_force_site(
    force_site,
    wheel_purelib,
    data_purelib,
    wheel_contents,
    wheel,
    tmpdir,
):
    """
    Check rpm filelist under force_site.
    """
    contents = wheel_contents(purelib=wheel_purelib)
    contents[f"foo-1.0.data/{data_purelib}/extra.txt"] = "content\n"
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    filelist = tmpdir / "foo.files"

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        rpm_filelist=filelist,
        force_site=force_site,
    )

    chosen_sitedir = get_installation_scheme("foo")[force_site]
    recorded_files = filelist.read_text(encoding="utf-8").splitlines()
    expected_files = sorted(
        (
            f"%dir {chosen_sitedir}/foo",
            f"{chosen_sitedir}/foo/__init__.py",
            f"%dir {chosen_sitedir}/foo/__pycache__",
            *expected_pyc_lines(f"{chosen_sitedir}/foo/__init__.py"),
            f"%dir {chosen_sitedir}/foo-1.0.dist-info",
            f"{chosen_sitedir}/foo-1.0.dist-info/METADATA",
            f"{chosen_sitedir}/extra.txt",
        ),
    )
    assert recorded_files == expected_files


@pytest.mark.parametrize(
    "bad_value",
    ("scripts", "data", "headers", "bogus", ""),
)
def test_force_site_invalid_value_rejected(
    bad_value,
    wheel_contents,
    wheel,
    tmpdir,
):
    """
    Check install_wheel rejects force_site values outside purelib/platlib.
    """
    contents = wheel_contents()
    destdir = tmpdir / "destdir"
    destdir.mkdir()

    with pytest.raises(
        ValueError,
        match=r"force_site must be 'purelib' or 'platlib'",
    ):
        install_wheel(
            wheel(contents=contents),
            destdir=destdir,
            force_site=bad_value,
        )


def test_install_exclude_paths_default_empty(
    wheel_contents,
    wheel,
    installed_wheel,
):
    """
    Check install behavior is unchanged when exclude_paths is omitted.
    Tests are not stripped.
    """
    contents = wheel_contents()
    contents["foo/tests/__init__.py"] = ""
    contents["foo/tests/test_x.py"] = ""
    dest_wheel = installed_wheel()

    install_wheel(wheel(contents=contents), destdir=dest_wheel.destdir)

    expected_filelist = {
        dest_wheel.sitedir / f
        for f in (
            "foo/__init__.py",
            "foo/tests/__init__.py",
            "foo/tests/test_x.py",
            "foo-1.0.dist-info/METADATA",
        )
    }
    assert dest_wheel.filelist() == expected_filelist


def test_install_exclude_paths_drops_matching_members(
    wheel_contents,
    wheel,
    installed_wheel,
):
    """
    Check exclude_paths drops every matching wheel member.
    """
    contents = wheel_contents()
    contents["foo/tests/__init__.py"] = ""
    contents["foo/tests/test_x.py"] = ""
    contents["foo/core.py"] = ""
    dest_wheel = installed_wheel()

    install_wheel(
        wheel(contents=contents),
        destdir=dest_wheel.destdir,
        exclude_paths=["*/tests/*"],
    )

    expected_filelist = {
        dest_wheel.sitedir / f
        for f in (
            "foo/__init__.py",
            "foo/core.py",
            "foo-1.0.dist-info/METADATA",
        )
    }
    assert dest_wheel.filelist() == expected_filelist


def test_install_exclude_paths_does_not_create_empty_parent_dirs(
    wheel_contents,
    wheel,
    installed_wheel,
):
    """
    Check the parent directory of an excluded member is not created
    when the excluded file is the sole occupant of that directory.
    zipfile.ZipFile.extractall(members=...) only creates listed
    paths, so a directory that would have held only the excluded
    file is never instantiated in the destdir.
    """
    contents = wheel_contents()
    contents["foo/tests/test_x.py"] = ""
    dest_wheel = installed_wheel()

    install_wheel(
        wheel(contents=contents),
        destdir=dest_wheel.destdir,
        exclude_paths=["foo/tests/test_x.py"],
    )

    expected_filelist = {
        dest_wheel.sitedir / f
        for f in (
            "foo/__init__.py",
            "foo-1.0.dist-info/METADATA",
        )
    }
    assert dest_wheel.filelist() == expected_filelist


def test_install_exclude_paths_can_strip_dist_info_files(
    wheel_contents,
    wheel,
    installed_wheel,
):
    """
    Check a pattern targeting a dist-info file does strip it.
    Excluding entry_points.txt is the canonical use: it suppresses
    the generated console-script wrappers because the script
    generator only runs when the file is present in the install
    tree.
    """
    contents = wheel_contents()
    contents["foo-1.0.dist-info/entry_points.txt"] = (
        "[console_scripts]\nbar = foo:main\n"
    )
    dest_wheel = installed_wheel()

    install_wheel(
        wheel(contents=contents),
        destdir=dest_wheel.destdir,
        exclude_paths=["*.dist-info/entry_points.txt"],
    )

    expected_filelist = {
        dest_wheel.sitedir / f
        for f in (
            "foo/__init__.py",
            "foo-1.0.dist-info/METADATA",
        )
    }
    assert dest_wheel.filelist() == expected_filelist


def test_install_exclude_paths_with_rpm_filelist_omits_stripped(
    wheel_contents,
    wheel,
    tmpdir,
):
    """
    Check rpm_filelist contains only non-excluded entries.
    """
    contents = wheel_contents()
    contents["foo/tests/__init__.py"] = ""
    contents["foo/tests/test_x.py"] = ""
    destdir = tmpdir / "destdir"
    destdir.mkdir()
    filelist = tmpdir / "foo.files"

    install_wheel(
        wheel(contents=contents),
        destdir=destdir,
        rpm_filelist=filelist,
        exclude_paths=["*/tests/*"],
    )

    recorded_files = filelist.read_text(encoding="utf-8").splitlines()
    purelib = get_installation_scheme("foo")["purelib"]
    expected_files = sorted(
        (
            f"%dir {purelib}/foo",
            f"{purelib}/foo/__init__.py",
            f"%dir {purelib}/foo/__pycache__",
            *expected_pyc_lines(f"{purelib}/foo/__init__.py"),
            f"%dir {purelib}/foo-1.0.dist-info",
            f"{purelib}/foo-1.0.dist-info/METADATA",
        ),
    )
    assert recorded_files == expected_files
