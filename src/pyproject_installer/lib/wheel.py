from email.parser import Parser
from importlib.metadata import PathDistribution
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile, Path as ZipPath, BadZipFile
import base64
import csv
import hashlib
import logging
import sys

from ..errors import WheelFileError
from .entry_points import parse_entry_points


logger = logging.getLogger(__name__)

# current Wheel spec by PEP427 is 1.0
WHEEL_SPECIFICATION_VERSION = (1, 0)


def digest_for_record(name, data):
    digest = hashlib.new(name, data).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def parse_name(name):
    """Parse wheel's name"""
    supported_format = (
        "{distribution}-{version}(-{build tag})?-{python tag}-{abi tag}-"
        "{platform tag}.whl"
    )
    err_msg = (
        f"Invalid wheel filename: {name}, "
        f"expected format: {supported_format}"
    )
    if not name.endswith(".whl"):
        raise ValueError(err_msg)

    name_parts = name[: -len(".whl")].split("-")
    if len(name_parts) not in (5, 6):
        raise ValueError(err_msg)

    dist_name = name_parts[0]
    if not dist_name:
        raise ValueError(err_msg)

    dist_version = name_parts[1]
    if not dist_version:
        raise ValueError(err_msg)

    return dist_name, dist_version


class WheelFile:
    def __init__(self, wheel_path):
        self._zipfile = None
        try:
            self._zipfile = ZipFile(wheel_path)
        except BadZipFile as e:
            raise WheelFileError(
                f"Error reading wheel {wheel_path}: {e}"
            ) from None
        self.name = Path(wheel_path).name
        self.dist_name, self.dist_version = self.parse_name()

        # zipfile.Path mutates namelist of original object by adding dirs,
        # while ZipFile.NameToInfo includes only files and fails on extract
        self._memberlist = self._zipfile.namelist()

        self.root = ZipPath(self._zipfile)
        self.dist_info = (
            self.root / f"{self.dist_name}-{self.dist_version}.dist-info"
        )
        self.data = self.root / f"{self.dist_name}-{self.dist_version}.data"
        self._wheel_metadata = None
        self.validate()

    @property
    def memberlist(self):
        yield from self._memberlist

    @property
    def wheel_metadata(self):
        if self._wheel_metadata is None:
            self._wheel_metadata = self.parse_wheel_metadata()
        return self._wheel_metadata

    def validate(self):
        """Validate wheel according to PEP427"""
        logger.debug("Validating wheel file")

        self.validate_dist_info()
        self.validate_wheel_spec_version()
        self.validate_record()

        if (self.dist_info / "entry_points.txt").exists():
            self.validate_entry_points()

        if self.data.exists():
            self.validate_data()

    def validate_entry_points(self):
        """
        the name of the entry point should be usable as a command in a system
        shell after the package is installed. The object reference points to a
        function which will be called with no arguments when this command is
        run.
        """
        distr = PathDistribution(self.dist_info)
        for ep_group in ("console_scripts", "gui_scripts"):
            for _, ep_value, ep_module, ep_attr in parse_entry_points(
                distr, ep_group
            ):
                if not ep_module or not ep_attr:
                    raise ValueError(
                        f"Invalid entry_points specification: {ep_value}"
                    )

    def validate_data(self):
        """
        Each subdirectory of distribution-1.0.data/ is a key into a dict of
        destination directories, such as
        distribution-1.0.data/(purelib|platlib|headers|scripts|data). The
        initially supported paths are taken from distutils.command.install.
        """
        INSTALL_PATHS = {"purelib", "platlib", "headers", "scripts", "data"}

        if not self.data.is_dir():
            raise ValueError("Optional .data should be a directory")

        # there should be no files, only dirs
        data_files = [f.name for f in self.data.iterdir() if f.is_file()]
        if data_files:
            raise ValueError(
                f"Optional .data cannot contain files: {', '.join(data_files)}"
            )

        # and those dirs should be a subset of known installation paths
        data_paths = {f.name for f in self.data.iterdir() if f.is_dir()}

        data_subpath_diff = data_paths - INSTALL_PATHS
        if data_subpath_diff:
            raise ValueError(
                "Optional .data contains unsupported scheme keys: "
                f"{', '.join(data_subpath_diff)}"
            )

    def validate_record(self):
        logger.debug("Validating RECORD")
        record_path = self.dist_info / "RECORD"
        recorded_files = set()

        if sys.version_info > (3, 9):
            # since Python3.9 zipfile.Path.open opens in text mode by default
            mode = "rb"
        else:
            # while Python3.8 zipfile.Path.open supports only binary mode
            mode = "r"

        with record_path.open(mode=mode) as csvbf, TextIOWrapper(
            csvbf, encoding="utf-8", newline=""
        ) as csvf:
            reader = csv.reader(csvf)
            for row in reader:
                # path, hash and size
                if len(row) != 3:
                    raise ValueError(
                        f"Invalid number of fields in RECORD row: {row}"
                    )

                recorded_file, hash_info, _ = row
                if recorded_file in recorded_files:
                    raise ValueError(f"Multiple records for: {recorded_file}")

                if recorded_file not in self.memberlist:
                    raise ValueError(
                        "Not packaged file but recorded in RECORD: "
                        f"{recorded_file}"
                    )

                # RECORD doesn't have hash
                if recorded_file != record_path.at:
                    self.validate_hash_record(recorded_file, hash_info)

                recorded_files.add(recorded_file)

        if not recorded_files:
            raise ValueError("Empty RECORD file")

        packaged_files = set(self.memberlist)
        # not recorded signatures from dist-info
        UNRECORDED_FILES = {
            (self.dist_info / f).at for f in ("RECORD.jws", "RECORD.p7s")
        }

        extra_packaged = packaged_files - recorded_files - UNRECORDED_FILES
        if extra_packaged:
            raise ValueError(
                "Extra packaged files not recorded in RECORD: "
                f"{', '.join(extra_packaged)}",
            )

    def validate_hash_record(self, recorded_file, hash_info):
        hash_name, _, hash_value = hash_info.partition("=")
        if not hash_name or not hash_value:
            raise ValueError(f"Invalid hash record: {hash_info}")

        hash_name = hash_name.lower()
        # hash algorithm must be sha256 or better;
        # specifically, md5 and sha1 are not permitted
        if hash_name in ("md5", "sha1"):
            raise ValueError(
                f"Too weak hash algorithm for records: {hash_name}"
            )

        digest = digest_for_record(
            hash_name, (self.root / recorded_file).read_bytes()
        )
        if digest != hash_value:
            raise ValueError(
                f"Incorrect hash for recorded file: {recorded_file}"
            )

    def extraction_root(self, scheme):
        """
        Root-Is-Purelib is true if the top level directory of the archive should
        be installed into purelib; otherwise the root should be installed into
        platlib.
        """
        if self.wheel_metadata.get("Root-Is-Purelib", "").lower() == "true":
            sitedir = "purelib"
        else:
            sitedir = "platlib"
        return Path(scheme[sitedir]).absolute()

    def validate_wheel_spec_version(self):
        """
        A wheel installer should warn if Wheel-Version is greater than the
        version it supports, and must fail if Wheel-Version has a greater major
        version than the version it supports.
        """
        logger.debug("Validating wheel spec version")
        wheel_version_text = self.wheel_metadata["Wheel-Version"]
        if wheel_version_text is None:
            raise ValueError("Missing version number of Wheel spec")

        wheel_version = wheel_version_text.strip()

        try:
            wheel_version_tuple = tuple(
                int(x) for x in wheel_version.split(".")
            )
        except ValueError:
            raise ValueError(
                f"Invalid version number of Wheel spec: {wheel_version}"
            ) from None

        if wheel_version_tuple[0] > WHEEL_SPECIFICATION_VERSION[0]:
            raise ValueError(
                f"Incompatible version of Wheel spec: {wheel_version}, supported: "
                f"{'.'.join([str(i) for i in WHEEL_SPECIFICATION_VERSION])}"
            )

        if wheel_version_tuple > WHEEL_SPECIFICATION_VERSION:
            logger.warning(
                "Installing wheel having Wheel spec version: %s "
                "newer than supported: %s",
                wheel_version,
                ".".join([str(i) for i in WHEEL_SPECIFICATION_VERSION]),
            )

    def validate_dist_info(self):
        if not self.dist_info.exists() or not self.dist_info.is_dir():
            raise ValueError(
                f"Missing mandatory dist-info directory: {self.dist_info}"
            )

        for f in ("METADATA", "WHEEL", "RECORD"):
            f_path = self.dist_info / f
            if not f_path.exists() or not f_path.is_file():
                raise ValueError(
                    f"Missing mandatory {f} in dist-info directory"
                )

    def parse_wheel_metadata(self):
        """
        PEP427:
        METADATA and WHEEL are Metadata version 1.1 or greater format metadata.

        PEP314:
        The PKG-INFO file format is a single set of RFC 822 headers parseable by the
        rfc822.py module.
        """
        logger.debug("Parsing wheel spec metadata")
        wheel_text = (self.dist_info / "WHEEL").read_text(encoding="utf-8")

        return Parser().parsestr(wheel_text)

    def parse_name(self):
        logger.debug("Parsing wheel filename")
        return parse_name(self.name)

    def extract(self, path, members=None):
        if members is None:
            members = self.memberlist
        self._zipfile.extractall(path, members=members)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        if self._zipfile is not None:
            self._zipfile.close()

    def __del__(self):
        self.close()
