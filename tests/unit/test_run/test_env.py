from itertools import product
from pathlib import Path
from sysconfig import get_path, get_paths
import json
import os
import re
import site
import sys
import textwrap

import pytest

from pyproject_installer.install_cmd import install_wheel
from pyproject_installer.errors import RunCommandError, RunCommandEnvError
from pyproject_installer.run_cmd import run_command, _run_env, _run_command
from pyproject_installer.lib.scripts import SCRIPT_TEMPLATE, build_shebang


@pytest.fixture
def project(tmpdir, monkeypatch):
    """Prepare everything needed to run a command in project root"""
    project_path = tmpdir / "project"
    project_path.mkdir()
    monkeypatch.chdir(project_path)
    return project_path


@pytest.fixture
def wheel_no_csript(wheel, wheel_contents):
    """Build wheel without console scripts"""

    def _build_wheel(distr="foo"):
        contents = wheel_contents(distr=distr)
        try:
            del contents[f"{contents.distinfo}/entry_points.txt"]
        except KeyError:
            pass
        return wheel(name=f"{distr}-1.0-py3-none-any.whl", contents=contents)

    return _build_wheel


@pytest.fixture
def wheel_cscript(wheel, wheel_contents):
    """Build wheel with console script"""

    def _build_wheel(script_name, distr="foo"):
        contents = wheel_contents(distr=distr)
        contents[f"{distr}/__init__.py"] = textwrap.dedent(
            f"""\
                def main():
                    print("Hello, World! ({script_name})")
            """
        )
        contents[
            f"{contents.distinfo}/entry_points.txt"
        ] = f"[console_scripts]\n{script_name} = {distr}:main\n"

        return wheel(name=f"{distr}-1.0-py3-none-any.whl", contents=contents)

    return _build_wheel


@pytest.fixture
def mock_ssps(destdir, mocker):
    """Mock _run_env.site.getsitepackages"""
    sysconf_paths = get_paths()
    ssps_dirs = []
    ssps_path = destdir / "ssps"
    for libtype in ["purelib", "platlib"]:
        path = Path(sysconf_paths[libtype]).resolve()
        ssps_dir = ssps_path / path.relative_to(path.root)
        ssps_dir.mkdir(parents=True, exist_ok=True)
        ssps_dirs.append(str(ssps_dir))

    mocker.patch.object(
        _run_env.site,
        "getsitepackages",
        autospec=True,
        return_value=ssps_dirs,
    )
    return ssps_path, ssps_dirs


@pytest.fixture
def mock_usps(destdir, mocker):
    """Mock _run_env.site.getusersitepackages"""
    usps_path = destdir / "usps"
    # install_wheel doesn't support installation into user sitepackage,
    # make it purelib only
    path = Path(get_path("purelib")).resolve()
    usps_dir = usps_path / path.relative_to(path.root)
    usps_dir.mkdir(parents=True, exist_ok=True)

    mocker.patch.object(
        _run_env.site,
        "getusersitepackages",
        autospec=True,
        return_value=str(usps_dir),
    )
    return usps_path, str(usps_dir)


def idf_outs(value):
    return "_".join(value)


def idf_console_data(value):
    return "{}_ssp_{}_usp_{}_vsp".format(
        *(map(lambda x: "with" if x else "without", value))
    )


def test_env_has_system_sitepackages(project, wheel_no_csript):
    """Check if system sitepackages appended to venv's sys.path

    venv sitepackages => user sitepackages => system sitepackages:
    https://peps.python.org/pep-0405/#isolation-from-system-site-packages
    """
    # precreate user sitepackages (`site` adds only existent dirs)
    usp = site.getusersitepackages()
    Path(usp).mkdir(parents=True, exist_ok=True)

    code = textwrap.dedent(
        """\
        import json
        import site
        import sys

        print(
            json.dumps(
                {
                    "venv_syspath": sys.path,
                    "venv_sitepackages": site.getsitepackages([sys.prefix]),
                }
            )
        )
        """
    )
    cmd = ["python", "-c", code]
    res = run_command(wheel_no_csript(), command=cmd, capture_output=True)
    json_data = json.loads(res.stdout.decode("utf-8"))

    venv_syspath = json_data["venv_syspath"]
    vsp_indexes = [
        venv_syspath.index(vsp) for vsp in json_data["venv_sitepackages"]
    ]

    usp_index = venv_syspath.index(usp)
    assert usp_index > max(vsp_indexes)

    # assume system sitepackages always exist
    ssps = site.getsitepackages([sys.base_prefix])
    ssp_indexes = [venv_syspath.index(ssp) for ssp in ssps]
    assert min(ssp_indexes) > max(vsp_indexes)
    assert min(ssp_indexes) > usp_index


def test_env_has_built_package(project, wheel_no_csript):
    """Check if built package is installed into venv"""
    code = textwrap.dedent(
        """\
        from foo import main
        main()
        """
    )
    cmd = ["python", "-c", code]
    res = run_command(wheel_no_csript(), command=cmd, capture_output=True)
    assert res.stdout == b"Hello, World!\n"
    assert res.stderr == b""


def test_env_default_venv_name(project, wheel_no_csript):
    """Check default venv name"""
    code = textwrap.dedent(
        """\
        from pathlib import Path
        import sys

        print(str(Path(sys.prefix).name))
        """
    )
    cmd = ["python", "-c", code]
    res = run_command(wheel_no_csript(), command=cmd, capture_output=True)
    assert res.stdout.strip().decode("utf-8") == ".run_venv"


def test_env_venv_name(project, wheel_no_csript):
    """Check custom venv name"""
    code = textwrap.dedent(
        """\
        from pathlib import Path
        import sys

        print(str(Path(sys.prefix).name))
        """
    )
    cmd = ["python", "-c", code]
    expected_name = "test_venv"
    res = run_command(
        wheel_no_csript(),
        venv_name=expected_name,
        command=cmd,
        capture_output=True,
    )
    assert res.stdout.strip().decode("utf-8") == expected_name


@pytest.mark.parametrize("env_path", ("path1", "path1:path2"))
def test_env_environ_path(env_path, project, wheel_no_csript, monkeypatch):
    """Check venv's PATH environ variable"""
    code = textwrap.dedent(
        """\
        import os
        import json
        import sysconfig

        print(
            json.dumps(
                {
                    "env_path": os.environ["PATH"],
                    "bin_dir": sysconfig.get_path("scripts"),
                }
            )
        )
        """
    )
    cmd = ["python", "-c", code]
    monkeypatch.setenv("PATH", env_path)
    res = run_command(wheel_no_csript(), command=cmd, capture_output=True)
    json_data = json.loads(res.stdout.decode("utf-8"))
    expected_path = os.pathsep.join([json_data["bin_dir"], env_path])
    assert json_data["env_path"] == expected_path


def test_env_environ_path_missing(project, wheel_no_csript, monkeypatch):
    """Check venv's PATH environ variable if global's one is missing"""
    code = textwrap.dedent(
        """\
        import os
        import json
        import sysconfig

        print(
            json.dumps(
                {
                    "env_path": os.environ["PATH"],
                    "bin_dir": sysconfig.get_path("scripts"),
                }
            )
        )
        """
    )
    cmd = ["python", "-c", code]
    monkeypatch.delenv("PATH")
    res = run_command(wheel_no_csript(), command=cmd, capture_output=True)
    json_data = json.loads(res.stdout.decode("utf-8"))
    assert json_data["env_path"] == json_data["bin_dir"]


def test_env_environ_virtual_env(project, wheel_no_csript):
    """Check venv's VIRTUAL_ENV environ variable"""
    code = textwrap.dedent(
        """\
        import os
        import json
        import sys

        print(
            json.dumps(
                {
                    "env_virtual_env": os.environ["VIRTUAL_ENV"],
                    "prefix": sys.prefix,
                }
            )
        )
        """
    )
    cmd = ["python", "-c", code]
    res = run_command(wheel_no_csript(), command=cmd, capture_output=True)
    json_data = json.loads(res.stdout.decode("utf-8"))
    assert json_data["env_virtual_env"] == json_data["prefix"]


def test_env_installation_failed(project):
    """Check the error on failed installation of built wheel"""
    command = ["any_command"]
    with pytest.raises(RunCommandEnvError) as exc:
        run_command(
            "nonexistent-1.0-py3-none-any.whl",
            command=command,
            capture_output=True,
        )
    assert "Installation of package failed" in str(exc.value)


@pytest.mark.parametrize(
    "error",
    (RunCommandEnvError, RunCommandError, Exception),
)
def test_env_venv_creation_error(error, project, wheel_no_csript, mocker):
    """Check the error on failed creation of venv"""
    err_msg = "some error"
    mocker.patch.object(
        _run_command.PyprojectVenv,
        "create",
        autospec=True,
        side_effect=error(err_msg),
    )
    command = ["any_command"]
    with pytest.raises(RunCommandEnvError, match=err_msg):
        run_command(
            wheel_no_csript(),
            command=command,
            capture_output=True,
        )


def test_env_command_nonexistent(project, wheel_no_csript, monkeypatch):
    """Check the error on nonexistent command"""
    # required for error message
    monkeypatch.setenv("LC_ALL", "C.utf8")
    command = ["nonexistent_cmd"]
    with pytest.raises(RunCommandError) as exc:
        run_command(wheel_no_csript(), command=command, capture_output=True)
    expected_ptrn = f".* No such file or directory: .*{command}.*"
    assert re.match(expected_ptrn, str(exc.value)) is not None


@pytest.mark.parametrize(
    "outs",
    (["stdout"], ["stderr"], ["stdout", "stderr"]),
    ids=idf_outs,
)
def test_env_command_failed_captured(project, wheel_no_csript, capfd, outs):
    """Check the error on failed command in captured mode

    - there should be captured stdout/stderr in exc message
    - there should be no message on stdout/stderr
    """

    code = textwrap.dedent(
        f"""\
        import sys

        for out in {outs!r}:
            getattr(sys, out).write(out + "\\n")
        sys.exit(1)
        """
    )
    command = ["python", "-c", code]
    with pytest.raises(RunCommandError) as exc:
        run_command(wheel_no_csript(), command=command, capture_output=True)

    for out in outs:
        assert f"Command's {out}:\n{out}\n" in str(exc.value)

    for noout in [x for x in ["stdout", "stderr"] if x not in outs]:
        assert f"Command's {noout}:\n" not in str(exc.value)

    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize(
    "outs",
    (["stdout"], ["stderr"], ["stdout", "stderr"]),
    ids=idf_outs,
)
def test_env_command_failed_notcaptured(project, wheel_no_csript, capfd, outs):
    """Check the error on failed command in uncaptured mode

    - there should message on stdout/stderr
    - there should be no captured stdout/stderr in exc message
    """

    code = textwrap.dedent(
        f"""\
        import sys

        for out in {outs!r}:
            getattr(sys, out).write(out + "\\n")
        sys.exit(1)
        """
    )
    command = ["python", "-c", code]
    with pytest.raises(RunCommandError) as exc:
        run_command(wheel_no_csript(), command=command, capture_output=False)

    assert "Command's std" not in str(exc.value)

    captured = capfd.readouterr()
    for out in outs:
        assert getattr(captured, out[3:]) == f"{out}\n"
    for noout in [x for x in ["stdout", "stderr"] if x not in outs]:
        assert getattr(captured, noout[3:]) == ""


@pytest.mark.parametrize(
    "outs",
    (["stdout"], ["stderr"], ["stdout", "stderr"]),
    ids=idf_outs,
)
def test_env_command_captured(project, wheel_no_csript, capfd, outs):
    """Check successful command in captured mode

    - there should be captured stdout/stderr in result
    - there should be no message on stdout/stderr
    """
    code = textwrap.dedent(
        f"""\
        import sys

        for out in {outs!r}:
            getattr(sys, out).write(out + "\\n")
        sys.exit(0)
        """
    )
    command = ["python", "-c", code]
    res = run_command(wheel_no_csript(), command=command, capture_output=True)
    for out in outs:
        assert getattr(res, out).decode("utf-8") == f"{out}\n"

    for noout in [x for x in ["stdout", "stderr"] if x not in outs]:
        assert getattr(res, noout) == b""

    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize(
    "outs",
    (["stdout"], ["stderr"], ["stdout", "stderr"]),
    ids=idf_outs,
)
def test_env_command_notcaptured(project, wheel_no_csript, capfd, outs):
    """Check successful command in uncaptured mode

    - there should be no captured stdout/stderr in result
    - there should be message on stdout/stderr
    """
    code = textwrap.dedent(
        f"""\
        import sys

        for out in {outs!r}:
            getattr(sys, out).write(out + "\\n")
        sys.exit(0)
        """
    )
    command = ["python", "-c", code]
    res = run_command(wheel_no_csript(), command=command, capture_output=False)
    assert res.stdout is None
    assert res.stderr is None

    captured = capfd.readouterr()
    for out in outs:
        assert getattr(captured, out[3:]) == f"{out}\n"
    for noout in [x for x in ["stdout", "stderr"] if x not in outs]:
        assert getattr(captured, noout[3:]) == ""


@pytest.fixture(
    params=(x for x in product(range(2), repeat=3) if x != (0, 0, 0)),
    ids=idf_console_data,
)
def console_scripts_data(request, mock_ssps, mock_usps):
    ssps, usps, vsp = request.param
    yield {
        # system site package
        "ssps": {
            "install": ssps,
            "run_result": ssps and not usps and not vsp,
            "destdir": mock_ssps[0],
            "pythonpath": os.pathsep.join(mock_ssps[1]),
            "external_install": True,
            "script": "ssps",
        },
        # user site package
        "usps": {
            "install": usps,
            "run_result": usps and not vsp,
            "destdir": mock_usps[0],
            "pythonpath": mock_usps[1],
            "external_install": True,
            "script": "usps",
        },
        # venv package
        "vsp": {
            "install": vsp,
            "run_result": vsp,
            "destdir": None,
            "pythonpath": None,
            "external_install": False,
            "script": "vsp",
        },
    }


def test_env_console_script(
    project, wheel_cscript, wheel_no_csript, monkeypatch, console_scripts_data
):
    """
    Check the precedence of packages having console scripts

    system site package => user site package => venv package,
    e.g. venv package has highest precedence and if there is a package
    in system/user sitepackages that has the same name as one installed
    into venv then console scripts of the package from those locations
    will be ignored.
    """
    for ps, data in console_scripts_data.items():
        if data["install"]:
            if data["external_install"]:
                # install wheels into mocked site packages
                install_wheel(wheel_cscript(ps), destdir=data["destdir"])
            else:
                # wheel with console script will be installed into venv on
                # command's run
                vsp_wheel = wheel_cscript(ps)
        elif not data["external_install"]:
            # wheel without console script will be installed into venv on
            # command's run
            vsp_wheel = wheel_no_csript("bar")

    expected_passes = [
        console_scripts_data[ps]
        for ps in console_scripts_data
        if console_scripts_data[ps]["run_result"]
    ]

    # should be only 1 passed result
    (expected_pass,) = expected_passes
    command = expected_pass["script"]
    pythonpath = expected_pass["pythonpath"]
    with monkeypatch.context() as m:
        if pythonpath:
            m.setenv("PYTHONPATH", pythonpath, prepend=os.pathsep)
        res = run_command(
            vsp_wheel,
            command=[command],
            capture_output=True,
        )
        assert res.returncode == 0
        expected_out = f"Hello, World! ({command})"
        assert res.stdout.strip().decode("utf-8") == expected_out
        assert res.stderr == b""

    expected_fails = [
        console_scripts_data[ps]
        for ps in console_scripts_data
        if not console_scripts_data[ps]["run_result"]
    ]
    for expected_fail in expected_fails:
        command = expected_fail["script"]
        with monkeypatch.context() as m:
            # for error message
            m.setenv("LC_ALL", "C.utf8")
            with pytest.raises(RunCommandError) as exc:
                run_command(
                    vsp_wheel,
                    command=[command],
                    capture_output=True,
                )
            expected_ptrn = f".* No such file or directory: .*{command}.*"
            assert re.match(expected_ptrn, str(exc.value)) is not None


def test_env_content_console_script(
    project, wheel_cscript, mock_usps, mock_ssps, monkeypatch
):
    """Check content of console scripts

    - installed from project's wheel
    - installed from system sitepackages
    - installed from user sitepackages
    """
    # build and install wheel into mocked user sitepackages
    usp = "usp"
    install_wheel(wheel_cscript(usp, distr=usp), destdir=mock_usps[0])

    # build and install wheel into mocked system sitepackages
    ssp = "ssp"
    install_wheel(wheel_cscript(ssp, distr=ssp), destdir=mock_ssps[0])

    # build project's wheel
    vsp = "vsp"
    code = textwrap.dedent(
        f"""\
        from pathlib import Path
        import json
        import sysconfig

        scp = Path(sysconfig.get_path("scripts"))
        script_names = ["{usp}", "{ssp}", "{vsp}"]
        content = {{
            k: (scp / k).read_text(encoding="utf-8") for k in script_names
        }}
        print(
            json.dumps(
                {{"bin_dir": str(scp), "content": content}}
            )
        )
        """
    )
    cmd = ["python", "-c", code]
    res = run_command(
        wheel_cscript(vsp, distr=vsp),
        command=cmd,
        capture_output=True,
    )
    json_data = json.loads(res.stdout.decode("utf-8"))
    # env_exec_cmd is used for shebangs and
    # is constructed as Path(sys.executable).name
    expected_shebang = build_shebang(
        str(Path(json_data["bin_dir"]) / Path(sys.executable).name)
    )
    # build_shebang is covered by installer's tests
    for name in [usp, ssp, vsp]:
        expected_content = SCRIPT_TEMPLATE.format(
            shebang=expected_shebang,
            module=name,
            attr="main",
            main="main",
        )
        assert expected_content == json_data["content"][name]
