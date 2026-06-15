from collections.abc import Iterator

from ...lib import utils
from .metadata import MetadataCollector


class MetadataExtraCollector(MetadataCollector):
    """Record a project's optional-dependency group (extra) as a source.

    Builds the project's core metadata, validates that the requested
    extra is declared (Provides-Extra), and stores the full
    Requires-Dist list unchanged (markers intact). At eval time the
    recorded extra is applied via eval_env(), so the extra-gated deps
    surface without a command-line --extra.
    """

    name = "metadata_extra"

    def __init__(self, extra: str) -> None:
        self.extra = extra

    def collect(self) -> Iterator[str]:
        metadata = self.parsed_metadata()
        provided = {
            utils.canonicalize_name(e)
            for e in metadata.get_all("Provides-Extra", [])
        }
        if utils.canonicalize_name(self.extra) not in provided:
            err_msg = (
                f"{self.name}: extra '{self.extra}' not provided by project "
                f"(available: {', '.join(sorted(provided))})"
            )
            raise ValueError(err_msg) from None
        yield from self.iter_requires(metadata)

    def eval_env(self) -> dict[str, str]:
        return {"extra": self.extra}
