import compileall
import shutil
import subprocess
import sysconfig
import textwrap
from pathlib import Path

import pytest

from pyproject_installer.install_cmd import install_wheel

RPMBUILD = shutil.which("rpmbuild")


def make_spec(filelist_path):
    return textwrap.dedent(
        f"""\
        %define _unpackaged_files_terminate_build 1
        Name:    pyproject-installer-filelist-test
        Version: 0.0
        Release: 0
        Summary: rpm filelist integration test
        License: MIT
        Group:   Development/Libraries
        BuildArch: noarch

        %description
        Dummy package for rpmbuild -bl filelist validation.

        %files -f {filelist_path}
        """,
    )


@pytest.mark.skipif(
    RPMBUILD is None,
    reason="rpmbuild is not available on PATH",
)
def test_rpmbuild_bl_accepts_generated_filelist(
    tmpdir,
    wheel,
    wheel_contents,
):
    contents = wheel_contents()
    contents["foo/__init__.py"] = "def main():\n    return 0\n"
    contents["foo/bar/__init__.py"] = "x = 1\n"
    contents["foo_compat.py"] = "y = 2\n"
    contents["foo-1.0.dist-info/entry_points.txt"] = textwrap.dedent(
        """\
        [console_scripts]
        foo_cli = foo:main
        """,
    )
    contents["foo-1.0.data/data/share/foo/asset.dat"] = "payload\n"

    buildroot = tmpdir / "buildroot"
    buildroot.mkdir()
    filelist = tmpdir / "foo.files"

    install_wheel(
        wheel(contents=contents),
        destdir=buildroot,
        rpm_filelist=filelist,
    )

    purelib_buildroot = Path(
        str(buildroot) + sysconfig.get_path("purelib"),
    )
    compileall.compile_dir(
        str(purelib_buildroot),
        optimize=[0, 1, 2],
        quiet=1,
    )

    spec = tmpdir / "foo.spec"
    spec.write_text(make_spec(filelist), encoding="utf-8")

    # rpmbuild -bl validates %files against the buildroot.
    # Exit code is 0 when every listed path exists in the buildroot.
    subprocess.check_call(
        [
            RPMBUILD,
            "--buildroot=" + str(buildroot),
            "--define",
            f"_topdir {tmpdir}",
            "--nodeps",
            "-bl",
            str(spec),
        ],
        stderr=subprocess.STDOUT,
    )
    assert filelist.read_text().splitlines()
