from .deps_config import DEFAULT_CONFIG_NAME
from .collectors import SUPPORTED_COLLECTORS
from ._deps_command import deps_command


__all__ = ["deps_command", "SUPPORTED_COLLECTORS", "DEFAULT_CONFIG_NAME"]
