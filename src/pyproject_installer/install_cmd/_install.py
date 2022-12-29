from importlib.metadata import PathDistribution
from pathlib import Path
import logging
import shutil
import sys
import sysconfig

from pyproject_installer.lib.scripts import (
    build_shebang,
    generate_entrypoints_scripts,
)
from pyproject_installer.lib.wheel import WheelFile

__all__ = [
    "install_wheel",
]

logger = logging.getLogger(__name__)

MAGIC_SHEBANG = b"#!python"

ALLOW_DIST_INFO_LIST = ("METADATA", "entry_points.txt")
DENY_DIST_INFO_LIST = ("RECORD",)


def get_installation_scheme(dist_name):
    scheme_dict = sysconfig.get_paths()

    # there is no headers in sysconfig for now
    # https://bugs.python.org/issue44445
    if "headers" not in scheme_dict:
        # distutils.command.install defines headers as:
        # '{base}/include/{implementation_lower}{py_version_short}{abiflags}/{dist_name}'
        installed_base = sysconfig.get_config_var("base")

        scheme_dict["headers"] = str(
            Path(
                sysconfig.get_path(
                    "include", vars={"installed_base": installed_base}
                )
            )
            / dist_name
        )

    return scheme_dict


def install_wheel_data(data_path, scheme, destdir):
    """
    PEP427:
    Each subdirectory of distribution-1.0.data/ is a key into a dict of
    destination directories, such as
    distribution-1.0.data/(purelib|platlib|headers|scripts|data). The initially
    supported paths are taken from distutils.command.install.
    """
    logger.info("Installing .data")
    # keys of .data dir were prechecked in `validate`
    for f in data_path.iterdir():
        path = Path(scheme[f.name]).absolute()
        rootdir = destdir / path.relative_to(path.root)
        shutil.copytree(data_path / f, rootdir, dirs_exist_ok=True)

        if f.name == "scripts":
            # PEP427
            # In wheel, scripts are packaged in
            # {distribution}-{version}.data/scripts/. If the first line of a
            # file in scripts/ starts with exactly b'#!python', rewrite to
            # point to the correct interpreter.
            for s in f.iterdir():
                if s.is_file() and not s.is_symlink():
                    with s.open(mode="rb") as sf:
                        if sf.read(len(MAGIC_SHEBANG)) == MAGIC_SHEBANG:
                            sf.seek(0)
                            sf.readline()  # discard shebang
                            script_path = rootdir / s.name
                            with script_path.open(mode="wb") as fsf:
                                fsf.write(
                                    (
                                        build_shebang(sys.executable) + "\n"
                                    ).encode("utf-8")
                                )
                                shutil.copyfileobj(sf, fsf)
                            script_path.chmod(
                                script_path.stat().st_mode | 0o555
                            )

        shutil.rmtree(data_path / f)

    shutil.rmtree(data_path)


def validate_wheel_path(wheel_path):
    try:
        wheel_path = wheel_path.resolve(strict=True)
    except (FileNotFoundError, RuntimeError):
        raise ValueError(
            f"Unable to resolve path for wheel: {wheel_path}"
        ) from None
    return wheel_path


def validate_destdir(destdir):
    try:
        destdir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ValueError(
            f"Unable to create path for destdir: {destdir}"
        ) from None

    return destdir.resolve(strict=True)


def filter_dist_info(dist_info, members, strip_dist_info=True):
    """
    If `strip_dist_info` is True then only `allow_list` is allowed in
    dist-info directory. The `deny_list` is unconditionally filtered out.
    """
    dist_info_path = Path(dist_info)
    allow_list = [str(dist_info_path / f) for f in ALLOW_DIST_INFO_LIST]
    deny_list = [str(dist_info_path / f) for f in DENY_DIST_INFO_LIST]

    for file in members:
        # select files from root's dist-info dir
        if Path(file).parts[0] == str(dist_info_path):
            if strip_dist_info and file not in allow_list:
                logger.debug("Filtering out not allowed file: %s", file)
                continue

            if file in deny_list:
                logger.debug("Filtering out denied file: %s", file)
                continue

        yield file


def install_wheel(
    wheel_path,
    destdir,
    installer=None,
    strip_dist_info=True,
):
    wheel_path = validate_wheel_path(wheel_path)
    destdir = validate_destdir(destdir)

    logger.info("Installing wheel")
    logger.info("Wheel directory: %s", wheel_path.parent)
    logger.info("Wheel filename: %s", wheel_path.name)
    logger.info("Destination: %s", destdir)

    with WheelFile(wheel_path) as whl:
        dist_name = whl.dist_name
        dist_version = whl.dist_version
        scheme = get_installation_scheme(dist_name)
        extraction_root = whl.extraction_root(scheme)
        rootdir = destdir / extraction_root.relative_to(extraction_root.root)
        logger.info("Wheel installation root: %s", rootdir)

        dist_info = f"{dist_name}-{dist_version}.dist-info"
        members = filter_dist_info(
            dist_info, members=whl.memberlist, strip_dist_info=strip_dist_info
        )

        logger.info("Extracting wheel")
        whl.extract(rootdir, members=members)

    dist_info_path = rootdir / dist_info

    if (dist_info_path / "entry_points.txt").exists():
        logger.info("Generating entrypoints scripts")
        generate_entrypoints_scripts(
            PathDistribution(dist_info_path),
            python=sys.executable,
            scriptsdir=Path(scheme["scripts"]).absolute(),
            destdir=destdir,
        )

    if installer is not None:
        # write installer of this distribution if requested
        installer_path = dist_info_path / "INSTALLER"
        installer_path.write_text(f"{installer}\n", encoding="utf-8")

    data_path = rootdir / f"{dist_name}-{dist_version}.data"
    if data_path.exists():
        install_wheel_data(data_path, scheme=scheme, destdir=destdir)

    logger.info("Wheel was installed")
