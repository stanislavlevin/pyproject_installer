"""Manage the Python version constraint in the shared dependency config."""

import logging
import sys
from string import Template

from ..deps_cmd.deps_config import rpm_lower_limit
from ..deps_cmd.deps_config_base import DepsConfig, DepsConfigType
from ..errors import DepsSourcesConfigError, DepsUnsyncedError
from ..lib import specifiers
from .collector import MetadataPythonCollector

logger = logging.getLogger(__name__)


class PythonDepConfig(DepsConfig):
    """Manage the stored Python version constraint."""

    @staticmethod
    def validate_format(depformat: str) -> str:
        """Reject conflicting substitutions and return the unchanged format."""
        identifiers = Template(depformat).get_identifiers()
        if {"specifier", "rpmlowver"}.issubset(identifiers):
            raise ValueError(
                "$specifier and $rpmlowver cannot be used together in --format",
            )
        return depformat

    def validate_config(self, config: DepsConfigType) -> None:
        """Validate the optional stored Python version constraint."""
        super().validate_config(config)
        if "requires_python" in config:
            requires_python = config["requires_python"]
            if not isinstance(requires_python, str):
                constraint = None
            else:
                try:
                    constraint = specifiers.SpecifierSet(requires_python)
                except specifiers.InvalidSpecifier:
                    constraint = None
            if constraint is None:
                raise DepsSourcesConfigError(
                    "'requires_python' must be a valid PEP440 version "
                    f"specifier, given: {requires_python!r}",
                )

    def sync(self, *, verify: bool = False) -> None:
        """Sync the stored Python version constraint from project metadata.

        With verify, save changes before printing the diff and raising
        DepsUnsyncedError. Remove the stored constraint when metadata omits it.
        Treat empty metadata constraints as absent.
        """
        if not self.file.is_file():
            self.set_default()
        stored = self.config.get("requires_python")
        old = specifiers.SpecifierSet(stored) if stored is not None else None
        collected = next(MetadataPythonCollector().collect(), None)
        new = (
            specifiers.SpecifierSet(collected)
            if collected is not None
            else None
        )
        if old == new:
            logger.info("Python version constraint is in sync")
            return

        if new is None:
            del self.config["requires_python"]
        else:
            self.config["requires_python"] = str(new)
        self.save()

        if verify:
            diff = {}
            if old is not None:
                diff["old"] = str(old)
            if new is not None:
                diff["new"] = str(new)
            self._show({"requires_python": diff})
            logger.error(
                "Python version constraint changed since last check.\n"
                'The configuration was synced and saved into "%s"',
                self.file,
            )
            raise DepsUnsyncedError
        logger.info("Synced Python version constraint")

    def print(self, *, depformat: str | None = None) -> None:
        """Print the stored constraint, optionally using a template.

        Substitute $specifier or $rpmlowver once, even without a constraint.
        Suppress exactly empty output and preserve nonempty output's whitespace.
        """
        if depformat is not None:
            self.validate_format(depformat)
        stored = self.config.get("requires_python")
        constraint = (
            specifiers.SpecifierSet(stored) if stored is not None else None
        )
        output = str(constraint) if constraint is not None else ""
        if depformat is not None:
            template = Template(depformat)
            lower_limit = ""
            if (
                constraint is not None
                and "rpmlowver" in template.get_identifiers()
            ):
                lower_limit = rpm_lower_limit(constraint)
            output = template.safe_substitute(
                specifier=output,
                rpmlowver=f" {lower_limit}" if lower_limit else "",
            )
        if output:
            sys.stdout.write(output + "\n")
            sys.stdout.flush()
