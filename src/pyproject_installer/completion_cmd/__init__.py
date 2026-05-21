from collections.abc import Callable

from . import _bash

__all__ = ["SUPPORTED_SHELLS", "completion_command"]


SUPPORTED_SHELLS: dict[str, Callable[[], None]] = {
    "bash": _bash.emit,
}


def completion_command(shell: str) -> None:
    """Dispatch a `completion <shell>` request to the right emitter."""
    try:
        emitter = SUPPORTED_SHELLS[shell]
    except KeyError:
        raise ValueError(f"unsupported shell: {shell!r}") from None
    emitter()
