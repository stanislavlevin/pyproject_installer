"""
Check if pyproject_installer is buildable by other tools like `build` or `pip`
"""
import subprocess


from pyproject_installer import __version__ as installer_version


def install_pkg(context, pkg, ignore_installed=True):
    install_args = [
        context.env_exec_cmd,
        "-Im",
        "pip",
        "install",
    ]
    if ignore_installed:
        install_args.append("--ignore-installed")
    install_args.append(pkg)
    subprocess.check_call(install_args, cwd=context.env_dir)


def upgrade_pkg(context, pkg):
    install_args = [
        context.env_exec_cmd,
        "-Im",
        "pip",
        "install",
        "--upgrade",
        pkg,
    ]
    subprocess.check_call(install_args, cwd=context.env_dir)


def test_build_with_build(virt_env, wheeldir):
    install_pkg(virt_env, "build")

    build_args = [
        virt_env.env_exec_cmd,
        "-Im",
        "build",
        ".",
        "--outdir",
        str(wheeldir),
    ]
    subprocess.check_call(build_args)
    built_files = {f.name for f in wheeldir.iterdir()}
    expected_files = {
        f"pyproject_installer-{installer_version}-py3-none-any.whl",
        f"pyproject_installer-{installer_version}.tar.gz",
    }
    assert built_files == expected_files


def test_build_with_pip(virt_env, wheeldir):
    upgrade_pkg(virt_env, "pip")

    build_args = [
        virt_env.env_exec_cmd,
        "-Im",
        "pip",
        "wheel",
        ".",
        "-w",
        str(wheeldir),
    ]
    subprocess.check_call(build_args)
    built_files = {f.name for f in wheeldir.iterdir()}
    expected_files = {
        f"pyproject_installer-{installer_version}-py3-none-any.whl",
    }
    assert built_files == expected_files
