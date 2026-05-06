from pathlib import Path
from typing import Any

from .deps_config import DepsSourcesConfig


def deps_command(
    action: str,
    depsconfig: str | Path | None,
    **kwargs: Any,
) -> Any:
    config = DepsSourcesConfig(depsconfig)
    return getattr(config, action)(**kwargs)
