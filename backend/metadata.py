from abc import ABC, abstractmethod
from contextlib import suppress
from email.generator import BytesGenerator
from email.message import Message
from email.headerregistry import Address
from io import BytesIO
from pathlib import Path
import ast

try:
    # Python 3.11+
    import tomllib
except ModuleNotFoundError:
    from ._vendor import tomli as tomllib


def parse_version_from_file(version_file):
    """
    Parse version from given file,
    expected format: version = "version_value"
    """
    err_msg = f"missing version in: {version_file}"

    with open(version_file, encoding="utf-8") as f:
        node = ast.parse(f.read())

    if len(node.body) != 1:
        raise ValueError(err_msg)

    child = node.body[0]
    if (
        isinstance(child, ast.Assign)
        and len(child.targets) == 1
        and isinstance(child.targets[0], ast.Name)
        and child.targets[0].id == "version"
        and isinstance(child.value, ast.Str)
    ):
        return child.value.value

    raise ValueError(err_msg)


def parse_pep621_metadata(path, backend_config):
    """
    Parses pyproject.toml with predefined set of fields names.

    Actual pre-validation of config is made by validate-pyproject.
    """
    metadata = {}
    with path.open("rb") as f:
        pyproject_data = tomllib.load(f)

    project = pyproject_data["project"]

    supported_fields = {
        "name",
        "version",
        "description",
        "readme",
        "requires-python",
        "license",
        "authors",
        "keywords",
        "classifiers",
        "dynamic",
        "urls",
    }
    extra_fields = project.keys() - set(supported_fields)
    if extra_fields:
        raise ValueError(
            f"Unexpected fields in project table: {', '.join(extra_fields)}"
        )

    for attr in supported_fields:
        with suppress(KeyError):
            metadata[attr] = project[attr]

    dynamic = project["dynamic"]

    if "version" in metadata and dynamic and "version" in dynamic:
        raise ValueError(
            "version cannot be specified as static and dynamic simultaneously"
        )

    if "version" in metadata and backend_config["version_file"] is not None:
        raise ValueError(
            "version cannot be specified as static and version_file "
            "simultaneously"
        )

    if "version" not in metadata:
        if "version" not in dynamic:
            raise KeyError("Missing version of project")

        metadata["version"] = parse_version_from_file(
            backend_config["version_file"]
        )

    return metadata


class Metadata(ABC):
    @abstractmethod
    def __init__(self, metadata):
        self._metadata = Message()

    def dump_as_bytes(self):
        fp = BytesIO()
        g = BytesGenerator(fp, maxheaderlen=0)
        g.flatten(self._metadata)
        return fp.getvalue()


class CoreMetadata(Metadata):
    """
    Convert PEP621 metadata to core metadata without content validation
    """

    def __init__(self, metadata):
        super().__init__(metadata)

        # files required for build sdist/wheel
        self.required_files = set()

        # required fields: Metadata-Version, Name and Version
        self._metadata["Metadata-Version"] = "2.1"
        self._metadata["Name"] = metadata["name"]
        self._metadata["Version"] = metadata["version"]

        # optional fields
        with suppress(KeyError):
            self._metadata["Summary"] = metadata["description"]

        try:
            authors = metadata["authors"]
        except KeyError:
            pass
        else:
            _authors, _a_emails = self._parse_authors(authors)
            if _authors:
                self._metadata["Author"] = ",".join(_authors)
            if _a_emails:
                self._metadata["Author-email"] = ",".join(_a_emails)

        try:
            maintainers = metadata["maintainers"]
        except KeyError:
            pass
        else:
            _maintainers, _m_emails = self._parse_authors(maintainers)
            if _maintainers:
                self._metadata["Maintainer"] = ",".join(_maintainers)
            if _m_emails:
                self._metadata["Maintainer-email"] = ",".join(_m_emails)

        try:
            license = metadata["license"]
        except KeyError:
            pass
        else:
            if license.keys() not in ({"file"}, {"text"}):
                raise ValueError(
                    "keys of license field should be either file or text, "
                    f"given: {', '.join(license.keys())}"
                )

            if "file" in license:
                filename = license["file"]
                self._metadata["License"] = Path(filename).read_text(
                    encoding="utf-8"
                )
                self.required_files.add(filename)
            else:
                self._metadata["License"] = license["text"]

        try:
            urls = metadata["urls"]
        except KeyError:
            pass
        else:
            for k, v in urls.items():
                # The label is free text limited to 32 characters
                self._metadata["Project-URL"] = f"{k[:32]},{v}"

        try:
            keywords = metadata["keywords"]
        except KeyError:
            pass
        else:
            self._metadata["Keywords"] = ",".join(keywords)

        try:
            classifiers = metadata["classifiers"]
        except KeyError:
            pass
        else:
            for classifier in classifiers:
                self._metadata["Classifier"] = classifier

        with suppress(KeyError):
            self._metadata["Requires-Python"] = metadata["requires-python"]

        try:
            readme = metadata["readme"]
        except KeyError:
            pass
        else:
            if isinstance(readme, str):
                if readme.lower().endswith(".md"):
                    content_type = "text/markdown"
                elif readme.lower().endswith(".rst"):
                    content_type = "text/x-rst"
                else:
                    content_type = "text/plain"

                self._metadata["Description-Content-Type"] = content_type
                self._metadata.set_payload(
                    Path(readme).read_text(encoding="utf-8")
                )
                self.required_files.add(readme)

            elif isinstance(readme, dict):
                if readme.keys() not in (
                    {"file", "content-type"},
                    {"text", "content-type"},
                ):
                    raise ValueError(
                        "keys of readme field should be (file or text) "
                        f"and content-type, given: {', '.join(readme.keys())}"
                    )

                self._metadata["Description-Content-Type"] = readme[
                    "content-type"
                ]

                if "file" in readme:
                    filename = readme["file"]
                    self._metadata.set_payload(
                        Path(filename).read_text(encoding="utf-8")
                    )
                    self.required_files.add(filename)
                else:
                    self._metadata.set_payload(readme["text"])

            else:
                raise TypeError(
                    f"readme should be string or dictionary, given: {readme!r}"
                )

    def _parse_authors(self, authors):
        for author in authors:
            unknown_keys = author.keys() - {"name", "email"}
            if unknown_keys:
                raise ValueError(
                    "Unexpected keys in authors table: "
                    f"{', '.join(unknown_keys)}"
                )

            msg_authors = []
            msg_emails = []
            if "name" in author and "email" not in author:
                msg_authors.append(author["name"])
            elif "email" in author and "name" not in author:
                msg_emails.append(author["email"])
            else:
                msg_emails.append(
                    str(Address(author["name"], addr_spec=author["email"]))
                )

        return msg_authors, msg_emails


class WheelMetadata(Metadata):
    def __init__(self, metadata):
        super().__init__(metadata)
        self._metadata["Wheel-Version"] = metadata["wheel-version"]
        self._metadata["Generator"] = metadata["generator"]
        self._metadata["Root-Is-Purelib"] = metadata["root-is-purelib"]
        for tag in metadata["tags"]:
            self._metadata["Tag"] = tag
