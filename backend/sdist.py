"""
Self-hosted backend for self-build (bootstrap): build_sdist.

build_sdist:
0. Parse self-config
1. Parse PEP621 metadata
2. Parse dynamic version(`version_file`) with ast
3. Make archive:
   - search in `package_dir` and `include_dirs_sdist`
   - include *.py for now
   - exclude __pycache__ and .pyc
"""
from io import BytesIO
from pathlib import Path
import logging
import os
import tarfile
import time

from .common import normalize_name_pep427, source_date_time
from .config import parse_backend_config
from .metadata import CoreMetadata, parse_pep621_metadata

__all__ = [
    "build_sdist",
]

logger = logging.getLogger(__name__)


class SdistBuilder:
    def __init__(self, cwd, distr_name, distr_version, sdist_directory):
        self.cwd = cwd
        self.distr_name = distr_name
        self.distr_version = distr_version
        self.filename = f"{distr_name}-{distr_version}.tar.gz"
        self.root_dir = Path(f"{distr_name}-{distr_version}")
        self.sdist_path = sdist_directory / self.filename
        self._tarfile = tarfile.open(
            self.sdist_path, "w:gz", format=tarfile.PAX_FORMAT
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self._tarfile.close()

    def __del__(self):
        self.close()

    def package_modules(self, package_dir):
        """Package Python packages and modules"""
        for root, dirs, files in os.walk(package_dir):
            dirs[:] = [d for d in sorted(dirs) if d != "__pycache__"]

            for f in sorted(files):
                fp = Path(root) / f

                if fp.suffix == ".pyc":
                    continue

                # allow only Python modules for now
                if fp.suffix not in (".py",):
                    continue

                fp_rel = fp.relative_to(self.cwd)
                if fp.is_symlink():
                    logger.debug("Ignoring symlink: %s", fp_rel)
                    continue

                if not fp.is_file():
                    logger.debug("Ignoring not a regular file: %s", fp_rel)
                    continue

                logger.debug("Sdisting %s", fp_rel)

                stat = fp.stat()
                with fp.open("rb") as src:
                    self.package_file(
                        src,
                        filename=str(fp_rel),
                        size=stat.st_size,
                        date_time=source_date_time(stat.st_mtime),
                    )

    def package_metadata(self, core_metadata):
        with BytesIO(core_metadata) as src:
            self.package_file(
                src,
                filename="PKG-INFO",
                size=len(core_metadata),
                date_time=source_date_time(time.time()),
            )

    def package_files(self, files):
        for file in files:
            if Path(file).is_absolute():
                raise ValueError(f"Path should be relative, given: {file}")

            file_path = self.cwd / file
            if file_path.is_file() and not file_path.is_symlink():
                logger.debug("Packaging: %s", file)

                stat = file_path.stat()
                with file_path.open("rb") as src:
                    self.package_file(
                        src,
                        filename=file,
                        size=stat.st_size,
                        date_time=source_date_time(stat.st_mtime),
                    )

    def package_license_files(self, patterns):
        # supported license files from root directory only
        self.package_files(
            (f.name for ptrn in patterns for f in self.cwd.glob(ptrn))
        )

    def package_file(self, src, filename, size, date_time):
        tarinfo = tarfile.TarInfo(str(self.root_dir / filename))
        tarinfo.size = size
        tarinfo.mtime = date_time
        tarinfo.mode = 0o644
        self._tarfile.addfile(tarinfo, fileobj=src)


def build_sdist(sdist_directory, config_settings=None):
    cwd = Path.cwd()
    pyproject = cwd / "pyproject.toml"

    backend_config = parse_backend_config(cwd, pyproject)
    metadata_pep621 = parse_pep621_metadata(pyproject, backend_config)

    distr_name = normalize_name_pep427(metadata_pep621["name"])
    distr_version = metadata_pep621["version"]
    # accept only normalized version
    if "-" in distr_version:
        raise ValueError(
            "Normalized version numbers cannot contain -, "
            f"given: {distr_version}"
        )

    sdist_directory = Path(sdist_directory)
    sdist_directory.mkdir(parents=True, exist_ok=True)
    sdist_directory = sdist_directory.resolve(strict=True)

    logger.info("Building sdist in %s", cwd)
    logger.info("Sdist directory: %s", sdist_directory)

    search_dirs = [Path(backend_config["package_dir"])]
    include_dirs_sdist = backend_config["include_dirs_sdist"]
    if include_dirs_sdist is not None:
        search_dirs.extend([Path(d) for d in include_dirs_sdist])

    with SdistBuilder(cwd, distr_name, distr_version, sdist_directory) as sdist:
        for d in search_dirs:
            sdist.package_modules(package_dir=d)
        coremetadata = CoreMetadata(metadata_pep621)
        sdist.package_metadata(coremetadata.dump_as_bytes())

        required_files = {"pyproject.toml"}
        required_files.update(coremetadata.required_files)
        sdist.package_files(required_files)
        sdist.package_license_files(backend_config["license_files"])

    return sdist.filename
