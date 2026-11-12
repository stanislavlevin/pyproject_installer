"""Shared storage and validation for dependency configuration."""

import json
import logging
import sys
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from ..errors import DepsSourcesConfigError

DEFAULT_CONFIG_NAME = "pyproject_deps.json"

logger = logging.getLogger(__name__)


class DepsConfigSourceSpec(TypedDict):
    """Configuration and stored requirements for a dependency source."""

    srctype: str
    deps: NotRequired[tuple[str, ...]]
    srcargs: NotRequired[tuple[str, ...]]


class DepsConfigType(TypedDict):
    """Optional dependency source and Python version constraint fields."""

    sources: NotRequired[dict[str, DepsConfigSourceSpec]]
    requires_python: NotRequired[str]


class DepsConfig:
    """Load, validate, and save shared dependency configuration."""

    def __init__(self, file: str | Path | None = None) -> None:
        """Select the config file and defer loading until it is needed."""
        self.file = (
            Path.cwd() / DEFAULT_CONFIG_NAME if file is None else Path(file)
        )
        self._config: DepsConfigType | None = None

    def validate_config(self, config: DepsConfigType) -> None:
        """Require a dictionary as the configuration root."""
        if not isinstance(config, dict):
            raise DepsSourcesConfigError(
                f"Config should be dict, given: {config!r}",
            )

    @property
    def config(self) -> DepsConfigType:
        """Load and validate the config on first access."""
        if self._config is None:
            with self.file.open(encoding="utf-8") as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError as e:
                    raise DepsSourcesConfigError(
                        f"Invalid config file: {self.file}: {e}",
                    ) from e
                self.validate_config(config)
                self._config = config
            logger.debug("Loaded config file %s", self.file)
        return self._config

    @config.setter
    def config(self, value: DepsConfigType) -> None:
        """Replace the config with a copy of the value and save it."""
        self._config = deepcopy(value)
        self.save()

    def set_default(self) -> None:
        """Initialize and save a config with no dependency sources."""
        logger.debug("Initializing default config")
        self.config = {"sources": {}}

    def save(self) -> None:
        """Validate and save the current config as JSON."""
        self.validate_config(self.config)
        # first parse the whole config
        json_config = self._to_json(self.config)
        self.file.write_text(json_config, encoding="utf-8")
        logger.debug("Saved config file %s", self.file)

    def _to_json(self, conf: Mapping[str, Any]) -> str:
        """Serialize data as sorted, indented JSON with a final newline."""
        return json.dumps(conf, indent=2, sort_keys=True) + "\n"

    def _show(self, conf: Mapping[str, Any]) -> None:
        """Write JSON data to stdout before any later diagnostics."""
        sys.stdout.write(self._to_json(conf))
        # flush data (stdout) so it precedes any later diagnostics (stderr) in
        # a merged stream, regardless of stdout block-buffering when piped
        sys.stdout.flush()
