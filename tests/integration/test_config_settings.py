import json
import subprocess


def test_config_settings_setuptools(
    virt_env_installer, setuptools_project, install_build_deps, wheeldir
):
    """
    1. Create virtualenv with installed pyproject_installer
    2. Create pyproject with setuptools build backend
    3. Install build requirements with pip
    4. Build with custom config_settings (today's setuptools respects
       `--global-option` key)
    """
    python = str(virt_env_installer.exe)
    install_build_deps(python, srcdir=setuptools_project)
    build_args = [
        python,
        "-m",
        "pyproject_installer",
        "build",
        "--backend-config-settings",
        json.dumps(
            {
                "--global-option": [
                    "--python-tag=test_tag",
                    "--build-number=123",
                    "--plat-name=test_plat",
                ],
            }
        ),
        "--outdir",
        wheeldir,
    ]
    subprocess.check_call(build_args, cwd=setuptools_project)
    build_files = {f.name for f in wheeldir.iterdir()}
    assert build_files == {
        "my_package-1.0-123-test_tag-none-test_plat.whl",
        ".wheeltracker",
    }


def test_config_settings_pdm(
    virt_env_installer, pdm_project, install_build_deps, wheeldir
):
    """
    1. Create virtualenv with installed pyproject_installer
    2. Create pyproject with pdm build backend
    3. Install build requirements with pip
    4. Build with custom config_settings (today's pdm respects
       `--python-tag`, `--py-limited-api` and `--plat-name` keys
    """
    python = str(virt_env_installer.exe)
    install_build_deps(python, srcdir=pdm_project)
    build_args = [
        python,
        "-m",
        "pyproject_installer",
        "build",
        "--backend-config-settings",
        json.dumps(
            {
                "--python-tag": "test_tag",
                "--plat-name": "test_plat",
            }
        ),
        "--outdir",
        wheeldir,
    ]

    subprocess.check_call(build_args, cwd=pdm_project)
    build_files = {f.name for f in wheeldir.iterdir()}
    assert build_files == {
        "my_package-1.0-test_tag-none-test_plat.whl",
        ".wheeltracker",
    }
