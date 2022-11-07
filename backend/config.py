from pathlib import Path

try:
    # Python 3.11+
    import tomllib
except ModuleNotFoundError:
    from ._vendor import tomli as tomllib


def validate_path(cwd, path):
    err_msg = f"{path} should be relative"
    if path.is_absolute():
        raise ValueError(err_msg)

    abs_path = path.resolve(strict=True)
    try:
        abs_path.relative_to(cwd)
    except ValueError:
        raise ValueError(err_msg) from None
    return abs_path


def parse_backend_config(cwd, path):
    """Parses table tool.pyproject_installer.backend of pyproject.toml"""
    backend_config = {}
    with path.open("rb") as f:
        pyproject_data = tomllib.load(f)

    parsed_config = pyproject_data["tool"]["pyproject_installer"]["backend"]

    package_dir = parsed_config.get("package_dir", ".")
    package_dir = validate_path(cwd, Path(package_dir))
    backend_config["package_dir"] = str(package_dir)

    version_file = parsed_config.get("version_file")
    if version_file is not None:
        version_file = str(validate_path(cwd, Path(version_file)))
    backend_config["version_file"] = version_file

    include_dirs_sdist = parsed_config.get("include_dirs_sdist")
    if include_dirs_sdist is not None:
        if not isinstance(include_dirs_sdist, list):
            raise TypeError(
                "include_dirs_sdist should be a list, "
                f"given: {include_dirs_sdist!r}"
            )
        include_dirs_sdist = [
            str(validate_path(cwd, Path(x))) for x in include_dirs_sdist
        ]
    backend_config["include_dirs_sdist"] = include_dirs_sdist

    # pre-PEP639 support for inclusion of license files
    # https://peps.python.org/pep-0639/#add-license-files-key
    default_license_files = ["LICEN[CS]E*", "COPYING*", "NOTICE*", "AUTHORS*"]
    license_files = parsed_config.get("license_files", default_license_files)
    if not isinstance(license_files, list):
        raise TypeError(
            f"license_files should be a list, given: {license_files!r}"
        )
    backend_config["license_files"] = license_files

    return backend_config
