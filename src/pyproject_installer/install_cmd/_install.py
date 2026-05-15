import logging
import shutil
import sys
import sysconfig
from collections.abc import Callable, Iterable, Iterator, Sequence
from importlib.metadata import PathDistribution
from pathlib import Path
from typing import Literal

from pyproject_installer.install_cmd._exclude_paths import filter_exclude_paths
from pyproject_installer.install_cmd._rpm_filelist import (
    write_rpm_filelist,
)
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

ALLOW_DIST_INFO_LIST: tuple[str, ...] = ("METADATA", "entry_points.txt")
DENY_DIST_INFO_LIST: tuple[str, ...] = ("RECORD",)


def get_installation_scheme(dist_name: str) -> dict[str, str]:
    scheme_dict = sysconfig.get_paths()

    # there is no headers in sysconfig for now
    # https://bugs.python.org/issue44445
    if "headers" not in scheme_dict:
        installed_base = sysconfig.get_config_var("base")

        scheme_dict["headers"] = str(
            Path(
                sysconfig.get_path(
                    "include",
                    vars={"installed_base": installed_base},
                ),
            )
            / dist_name,
        )

    return scheme_dict


def install_wheel_data(
    data_path: Path,
    scheme: dict[str, str],
    destdir: Path,
    *,
    installed_paths: set[Path] | None = None,
) -> None:
    """
    PEP427:
    Each subdirectory of distribution-1.0.data/ is a key into a dict of
    destination directories, such as
    distribution-1.0.data/(purelib|platlib|headers|scripts|data). The initially
    supported paths are taken from distutils.command.install.

    If `installed_paths` is not None, each destination file's path is
    added to it as `shutil.copytree` creates it. The hook is installed
    via the `copy_function` parameter, so every regular file copytree
    emits (including symlink-target copies under the default
    `symlinks=False`) is observed exactly once.
    """
    logger.info("Installing .data")

    copy_fn: Callable[[str, str], str]
    if installed_paths is None:
        copy_fn = shutil.copy2
    else:

        def copy_fn(src: str, dst: str) -> str:
            new_file = shutil.copy2(src, dst)
            installed_paths.add(Path(dst))
            return new_file

    # keys of .data dir were prechecked in `validate`
    for f in data_path.iterdir():
        path = Path(scheme[f.name]).absolute()
        rootdir = destdir / path.relative_to(path.root)
        shutil.copytree(
            data_path / f,
            rootdir,
            dirs_exist_ok=True,
            copy_function=copy_fn,
        )

        if f.name == "scripts":
            # PEP427
            # In wheel, scripts are packaged in
            # {distribution}-{version}.data/scripts/. If the first line of a
            # file in scripts/ starts with exactly b'#!python', rewrite to
            # point to the correct interpreter.
            for s in f.iterdir():
                if s.is_file() and not s.is_symlink():
                    script_path = rootdir / s.name
                    with s.open(mode="rb") as sf:
                        if sf.read(len(MAGIC_SHEBANG)) == MAGIC_SHEBANG:
                            sf.seek(0)
                            sf.readline()  # discard shebang
                            with script_path.open(mode="wb") as fsf:
                                fsf.write(
                                    (
                                        build_shebang(sys.executable) + "\n"
                                    ).encode("utf-8"),
                                )
                                shutil.copyfileobj(sf, fsf)
                    # make any file in scripts directory executable
                    # (can be a compiled binary for example)
                    script_path.chmod(script_path.stat().st_mode | 0o555)

        shutil.rmtree(data_path / f)

    shutil.rmtree(data_path)


def validate_wheel_path(wheel_path: Path) -> Path:
    try:
        wheel_path = wheel_path.resolve(strict=True)
    except (FileNotFoundError, RuntimeError):
        raise ValueError(
            f"Unable to resolve path for wheel: {wheel_path}",
        ) from None
    return wheel_path


def validate_destdir(destdir: Path) -> Path:
    try:
        destdir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise ValueError(
            f"Unable to create path for destdir: {destdir}",
        ) from None

    return destdir.resolve(strict=True)


def filter_dist_info(
    dist_info: str,
    *,
    members: Iterable[str],
    strip_dist_info: bool = True,
) -> Iterator[str]:
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
    wheel_path: Path,
    *,
    destdir: Path,
    installer: str | None = None,
    strip_dist_info: bool = True,
    rpm_filelist: Path | None = None,
    force_site: Literal["purelib", "platlib"] | None = None,
    exclude_paths: Sequence[str] = (),
) -> None:
    wheel_path = validate_wheel_path(wheel_path)
    destdir = validate_destdir(destdir)

    if force_site is not None and force_site not in ("purelib", "platlib"):
        raise ValueError(
            "force_site must be 'purelib' or 'platlib', "
            f"got: {force_site!r}",
        )

    logger.info("Installing wheel")
    logger.info("Wheel directory: %s", wheel_path.parent)
    logger.info("Wheel filename: %s", wheel_path.name)
    logger.info("Destination: %s", destdir)

    with WheelFile(wheel_path) as whl:
        dist_name = whl.dist_name
        dist_version = whl.dist_version
        data_name = whl.data_name
        scheme = get_installation_scheme(dist_name)
        if force_site is not None:
            scheme["purelib"] = scheme["platlib"] = scheme[force_site]
        extraction_root = whl.extraction_root(scheme)
        rootdir = destdir / extraction_root.relative_to(extraction_root.root)
        logger.info("Wheel installation root: %s", rootdir)

        dist_info = f"{dist_name}-{dist_version}.dist-info"
        chain: Iterator[str] = filter_dist_info(
            dist_info,
            members=whl.memberlist,
            strip_dist_info=strip_dist_info,
        )
        if exclude_paths:
            chain = filter_exclude_paths(chain, patterns=exclude_paths)
        members = tuple(chain)

        installed_paths: set[Path] | None = (
            set() if rpm_filelist is not None else None
        )

        logger.info("Extracting wheel")
        whl.extract(rootdir, members=members)
        if installed_paths is not None:
            # Skip .data/* members: install_wheel_data relocates them
            # to their scheme destinations below and records the final
            # paths. Recording the pre-move paths would emit phantom
            # entries (the .data/ tree is rmtree'd after relocation).
            for m in members:
                if Path(m).parts[0] == data_name:
                    continue
                installed_paths.add(rootdir / m)

    dist_info_path = rootdir / dist_info

    if (dist_info_path / "entry_points.txt").exists():
        logger.info("Generating entrypoints scripts")
        generate_entrypoints_scripts(
            PathDistribution(dist_info_path),
            python=sys.executable,
            scriptsdir=Path(scheme["scripts"]).absolute(),
            destdir=destdir,
            installed_paths=installed_paths,
        )

    if installer is not None:
        # write installer of this distribution if requested
        installer_path = dist_info_path / "INSTALLER"
        installer_path.write_text(f"{installer}\n", encoding="utf-8")
        if installed_paths is not None:
            installed_paths.add(installer_path)

    data_path = rootdir / data_name
    if data_path.exists():
        install_wheel_data(
            data_path,
            scheme=scheme,
            destdir=destdir,
            installed_paths=installed_paths,
        )

    if rpm_filelist is not None and installed_paths is not None:
        write_rpm_filelist(
            rpm_filelist,
            installed_paths,
            destdir=destdir,
            scheme=scheme,
            dist_info=str(extraction_root / dist_info),
        )

    logger.info("Wheel was installed")
