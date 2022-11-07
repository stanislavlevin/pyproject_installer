"""
Self-hosted backend for self-build (bootstrap): build_wheel.

build_wheel:
0. Parse self-config
1. Parse PEP621 metadata
2. Parse dynamic version(`version_file`) with ast
3. Make archive:
   - search in `package_dir`
   - include *.py for now
   - exclude __pycache__ and .pyc
"""
from base64 import urlsafe_b64encode
from io import TextIOWrapper, BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import csv
import hashlib
import logging
import os
import time

from .common import normalize_name_pep427, source_date_time_zinfo
from .config import parse_backend_config
from .metadata import CoreMetadata, parse_pep621_metadata, WheelMetadata

__all__ = [
    "build_wheel",
]

logger = logging.getLogger(__name__)


class WheelBuilder:
    def __init__(self, distr_name, distr_version, wheel_directory):
        self.distr_name = distr_name
        self.distr_version = distr_version
        self.filename = f"{distr_name}-{distr_version}-py3-none-any.whl"
        self.wheel_path = wheel_directory / self.filename
        self._zipfile = ZipFile(self.wheel_path, "w")
        self.dist_info = f"{distr_name}-{distr_version}.dist-info"
        self.records = []
        self.digest_alg = "sha256"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self._zipfile.close()

    def __del__(self):
        self.close()

    def add_record(self, filename, digest, size):
        self.records.append(
            (
                filename,
                "{}={}".format(
                    self.digest_alg,
                    urlsafe_b64encode(digest).rstrip(b"=").decode("ascii"),
                ),
                size,
            ),
        )

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

                fp_rel = fp.relative_to(package_dir)
                if fp.is_symlink():
                    logger.debug("Ignoring symlink: %s", fp_rel)
                    continue

                if not fp.is_file():
                    logger.debug("Ignoring not a regular file: %s", fp_rel)
                    continue

                logger.debug("Wheeling %s", fp_rel)

                stat = fp.stat()
                with fp.open("rb") as src:
                    self.package_file(
                        src,
                        str(fp_rel),
                        source_date_time_zinfo(stat.st_mtime),
                    )

    def package_wheel_metadata(self):
        dist_info_wheel = Path(self.dist_info) / "WHEEL"
        wheel_data = WheelMetadata(
            {
                "wheel-version": "1.0",
                # assume self-build
                "generator": f"pyproject_installer {self.distr_version}",
                "root-is-purelib": "true",
                "tags": ["py3-none-any"],
            }
        ).dump_as_bytes()

        with BytesIO(wheel_data) as src:
            self.package_file(
                src,
                str(dist_info_wheel),
                source_date_time_zinfo(time.time()),
            )

    def package_metadata(self, core_metadata):
        dist_info_metadata = Path(self.dist_info) / "METADATA"

        with BytesIO(core_metadata) as src:
            self.package_file(
                src,
                str(dist_info_metadata),
                source_date_time_zinfo(time.time()),
            )

    def package_license_files(self, cwd, patterns):
        # supported license files from root directory only
        for pattern in patterns:
            for file in cwd.glob(pattern):
                if file.is_file() and not file.is_symlink():
                    logger.debug("Packaging license: %s", file.name)
                    stat = file.stat()
                    with file.open("rb") as src:
                        self.package_file(
                            src,
                            str(Path(self.dist_info) / file.name),
                            source_date_time_zinfo(stat.st_mtime),
                        )

    def package_file(self, src, filename, date_time):
        zinfo = ZipInfo(filename, date_time=date_time)
        zinfo.external_attr = 0o644 << 16
        zinfo.compress_type = ZIP_DEFLATED

        h = hashlib.new(self.digest_alg)

        with self._zipfile.open(zinfo, "w") as dst:
            while True:
                read = src.read(64 * 1024)
                if not read:
                    break
                h.update(read)
                dst.write(read)

        self.add_record(filename, h.digest(), zinfo.file_size)

    def package_record(self):
        dist_info_record = Path(self.dist_info) / "RECORD"
        zinfo = ZipInfo(
            str(dist_info_record),
            date_time=source_date_time_zinfo(time.time()),
        )
        zinfo.external_attr = 0o644 << 16
        zinfo.compress_type = ZIP_DEFLATED

        self.records.append((str(dist_info_record), "", ""))
        with self._zipfile.open(zinfo, "w") as f, TextIOWrapper(
            f, encoding="utf-8", newline=""
        ) as csvf:
            writer = csv.writer(csvf, lineterminator="\n")
            writer.writerows(self.records)


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
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

    wheel_directory = Path(wheel_directory)
    wheel_directory.mkdir(parents=True, exist_ok=True)
    wheel_directory = wheel_directory.resolve(strict=True)

    logger.info("Building wheel in %s", cwd)
    logger.info("Wheel directory: %s", wheel_directory)

    package_dir = Path(backend_config["package_dir"])

    with WheelBuilder(distr_name, distr_version, wheel_directory) as whl:
        whl.package_modules(package_dir)

        # package dist-info
        whl.package_wheel_metadata()
        whl.package_metadata(CoreMetadata(metadata_pep621).dump_as_bytes())
        whl.package_license_files(cwd, backend_config["license_files"])
        whl.package_record()

    return whl.filename
