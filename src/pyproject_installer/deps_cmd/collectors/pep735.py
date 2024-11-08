from pathlib import Path

from .collector import Collector
from ...lib import requirements
from ...lib import tomllib
from ...lib.normalization import pep503_normalized_name


class Pep735Collector(Collector):
    """Collect dependencies specified by Dependency Group according to PEP735

    Specification:
    - https://peps.python.org/pep-0735/#specification
    """

    name = "pep735"

    def __init__(self, group):
        # group name can be non-normalized
        self.group = group
        self._groups_data = None

    def collect(self):
        pyproject_file = Path.cwd() / "pyproject.toml"

        with pyproject_file.open("rb") as f:
            pyproject_data = tomllib.load(f)

        table_name = "dependency-groups"
        try:
            self._groups_data = pyproject_data[table_name]
        except KeyError:
            raise ValueError(
                f"pep735: missing {table_name} table in {pyproject_file.name}"
            ) from None

        if not isinstance(self._groups_data, dict):
            raise TypeError(
                "pep735: Dependency Groups is not a dict: "
                f"{self._groups_data!r}"
            )

        return self._resolve_dep_group(group_name=self.group)

    def _resolve_group_name(self, group_name, include_chain):
        """Resolve actual group's name"""
        # config group names can be non-normalized and duplicated
        group_nname = pep503_normalized_name(group_name)
        actual_group_names = sorted(
            (
                gp_name
                for gp_name in self._groups_data
                if pep503_normalized_name(gp_name) == group_nname
            )
        )

        if not actual_group_names:
            raise ValueError(
                "pep735: group dependencies are not configured ("
                f"group: {group_name}, "
                f"include chain: {'->'.join(include_chain)})"
            )
        if len(actual_group_names) > 1:
            raise ValueError(
                "pep735: duplicate group names ("
                f"group: {group_name}, "
                f"include chain: {'->'.join(include_chain)}"
                f"): {', '.join(actual_group_names)}"
            )

        (group_cname,) = actual_group_names
        return group_cname

    def _resolve_dep_group(self, group_name, visited_groups=()):
        """Recursively resolve Dependency Group's dependencies"""
        resolved_group_name = self._resolve_group_name(
            group_name,
            visited_groups + (group_name,) if visited_groups else [],
        )
        include_chain = (
            visited_groups + (resolved_group_name,) if visited_groups else []
        )

        group_nname = pep503_normalized_name(group_name)
        if group_nname in map(pep503_normalized_name, visited_groups):
            raise ValueError(
                "pep735: include cycle detected ("
                f"group: {resolved_group_name}, "
                f"include chain: {'->'.join(include_chain)})"
            )

        deps_data = self._groups_data[resolved_group_name]
        if not isinstance(deps_data, list):
            raise TypeError(
                "pep735: dependencies format is not a list ("
                f"group: {resolved_group_name}, "
                f"include chain: {'->'.join(include_chain)}"
                f"): {deps_data!r}"
            )

        for dep in deps_data:
            if isinstance(dep, str):
                # must be a valid PEP508 Dependency Specifier
                try:
                    requirements.Requirement(dep)
                except requirements.InvalidRequirement as e:
                    err_msg = (
                        "pep735: invalid PEP508 Dependency Specifier ("
                        f"group: {resolved_group_name}, "
                        f"include chain: {'->'.join(include_chain)}"
                        f"): {e}"
                    )
                    raise ValueError(err_msg) from None
                yield dep
            elif isinstance(dep, dict):
                if dep.keys() != {"include-group"}:
                    err_msg = (
                        "pep735: invalid Dependency Object Specifier ("
                        f"group: {resolved_group_name}, "
                        f"include chain: {'->'.join(include_chain)}"
                        f"): {dep!r}"
                    )
                    raise ValueError(err_msg)

                include_group = dep["include-group"]
                if not isinstance(include_group, str):
                    err_msg = (
                        "pep735: Dependency Group Include's value is not a "
                        "string ("
                        f"group: {resolved_group_name}, "
                        f"include chain: {'->'.join(include_chain)}"
                        f"): {include_group!r}"
                    )
                    raise TypeError(err_msg)

                yield from self._resolve_dep_group(
                    group_name=include_group,
                    visited_groups=visited_groups + (resolved_group_name,),
                )
            else:
                err_msg = (
                    "pep735: dependencies lists may contain strings or "
                    f"dicts ("
                    f"group: {resolved_group_name}, "
                    f"include chain: {'->'.join(include_chain)}"
                    f"): {dep!r}"
                )
                raise TypeError(err_msg)
