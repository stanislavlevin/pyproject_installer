from email.parser import Parser
from importlib.metadata import PathDistribution
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile, Path as ZipPath
import base64
import hashlib
import logging
import shutil
import sys
import sysconfig
import csv

__all__ = [
    "install_wheel",
]

# current Wheel spec by PEP427 is 1.0
WHEEL_SPECIFICATION_VERSION = (1, 0)

MAGIC_SHEBANG = b"#!python"

SCRIPT_TEMPLATE = """\
{shebang}

import sys

from {module} import {attr}


if __name__ == "__main__":
    sys.exit({main}())
"""

ALLOW_DIST_INFO_LIST = ("METADATA", "entry_points.txt")
DENY_DIST_INFO_LIST = ("RECORD",)

logger = logging.getLogger(__name__)


def parse_entry_points(dist_info, group):
    """
    Compat only.
    - module and attr attributes of ep are available since Python 3.9
    - "selectable" entry points were introduced in Python 3.10
    """
    distr = PathDistribution(dist_info)
    distr_eps = distr.entry_points
    try:
        # since Python3.10
        distr_eps.select
    except AttributeError:
        eps = (ep for ep in distr_eps if ep.group == group)
    else:
        eps = distr_eps.select(group=group)

    for ep in eps:
        try:
            # module is available since Python 3.9
            ep_module = ep.module
        except AttributeError:
            ep_match = ep.pattern.match(ep.value)
            ep_module = ep_match.group("module")

        try:
            # attr is available since Python 3.9
            ep_attr = ep.attr
        except AttributeError:
            ep_attr = ep_match.group("attr")

        yield (ep.name, ep.value, ep_module, ep_attr)


def digest_for_record(name, data):
    digest = hashlib.new(name, data).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class WheelFile:
    def __init__(self, wheel_path):
        self._zipfile = ZipFile(wheel_path)
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
        for ep_group in ("console_scripts", "gui_scripts"):
            for _, ep_value, ep_module, ep_attr in parse_entry_points(
                self.dist_info, ep_group
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
        return Path(scheme[sitedir]).resolve()

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
        supported_format = (
            "{distribution}-{version}(-{build tag})?-{python tag}-{abi tag}-"
            "{platform tag}.whl"
        )
        err_msg = (
            f"Invalid wheel filename: {self.name}, "
            f"expected format: {supported_format}"
        )
        logger.debug("Parsing wheel filename")
        if not self.name.endswith(".whl"):
            raise ValueError(err_msg)

        name_parts = self.name[: -len(".whl")].split("-")
        if len(name_parts) not in (5, 6):
            raise ValueError(err_msg)

        dist_name = name_parts[0]
        if not dist_name:
            raise ValueError(err_msg)

        dist_version = name_parts[1]
        if not dist_version:
            raise ValueError(err_msg)

        return dist_name, dist_version

    def extract(self, path, members=None):
        if members is None:
            members = self.memberlist
        self._zipfile.extractall(path, members=members)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self._zipfile.close()

    def __del__(self):
        self.close()


def build_shebang():
    """
    man 2 execve
    The kernel imposes a maximum length on the text that follows the "#!" char‐
    acters  at  the  start of a script; characters beyond the limit are ignored.
    Before Linux 5.1, the limit is 127 characters.  Since Linux 5.1,  the  limit
    is 255 characters.
    """
    executable = sys.executable
    if " " not in executable and len(executable) <= 127:
        return f"#!{sys.executable}"

    # originally taken from distlib.scripts; how it works:
    # https://github.com/pradyunsg/installer/pull/4#issuecomment-623668717
    return "#!/bin/sh\n'''exec' " + executable + ' "$0" "$@"\n' + "' '''"


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


def generate_entrypoints_scripts(dist_info, scheme, destdir):
    """
    Optional entry_points
    https://packaging.python.org/en/latest/specifications/entry-points/
    """
    logger.info("Generating entrypoints scripts")
    for ep_group in ("console_scripts", "gui_scripts"):
        for ep_name, _, ep_module, ep_attr in parse_entry_points(
            dist_info, ep_group
        ):
            script_text = SCRIPT_TEMPLATE.format(
                shebang=build_shebang(),
                module=ep_module,
                attr=ep_attr.split(".", maxsplit=1)[0],
                main=ep_attr,
            )
            scripts_path = Path(scheme["scripts"]).resolve()
            rootdir = destdir / scripts_path.relative_to(scripts_path.root)
            rootdir.mkdir(parents=True, exist_ok=True)
            script_path = rootdir / ep_name
            script_path.write_text(script_text, encoding="utf-8")
            script_path.chmod(script_path.stat().st_mode | 0o555)


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
        path = Path(scheme[f.name]).resolve()
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
                                    (build_shebang() + "\n").encode("utf-8")
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
        generate_entrypoints_scripts(
            dist_info_path, scheme=scheme, destdir=destdir
        )

    if installer is not None:
        # write installer of this distribution if requested
        installer_path = dist_info_path / "INSTALLER"
        installer_path.write_text(f"{installer}\n", encoding="utf-8")

    data_path = rootdir / f"{dist_name}-{dist_version}.data"
    if data_path.exists():
        install_wheel_data(data_path, scheme=scheme, destdir=destdir)

    logger.info("Wheel was installed")
