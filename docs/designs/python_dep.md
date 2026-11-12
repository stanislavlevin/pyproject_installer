## Abstract
Add a `python_dep` subcommand to collect, store, verify, and print the project's
Python version constraint from core metadata's `Requires-Python`. `deps`
continues to handle PEP 508 requirements exclusively.

## Motivation
Maintainers add a Python version dependency when needed; otherwise they usually
omit it. Projects already declare supported Python versions in
`Requires-Python`. Collecting that field lets downstream packaging generate an
interpreter dependency from upstream metadata and detect changes to the declared
constraint.

## Specification

### Commands and storage

```
python_dep sync [--verify]
python_dep print [--format FORMAT]
```

Share `pyproject_deps.json` under cwd; `--depsconfig PATH` on `python_dep`
selects another file, as with `deps`. Keep PEP 508 requirements under `sources`
and add a top-level `requires_python`. Both commands inherit shared config
handling from `DepsConfig`; its initialization creates `"sources": {}`.
Each command updates its own data and preserves other fields.
Only one process may manage a shared config file or metadata cache at a time.
Run commands one at a time when using the same config file or metadata cache.

The optional `requires_python` field contains a PEP 440 specifier-set string.
Omit the field when metadata has no `Requires-Python`:

```json
{"sources": {}, "requires_python": "<4,>=3.12"}
```

Each command validates only its own fields and preserves the others.
When present, `python_dep` requires `requires_python` to be a valid PEP 440
version specifier. A missing field means no declared version restriction.
Old configs without the field remain valid for both commands.

### Metadata collection
Reuse the existing metadata collection, validation, and caching behavior. As
with `metadata`, PEP 518 and PEP 517 build dependencies must be installed.
Collect `Requires-Python` when present and require a valid PEP 440 version
specifier. Treat empty specifier sets, including whitespace-only values, as
absent. Report metadata errors under `python_dep`.

### Sync and verification
`sync` creates a missing file and collects metadata in the same call. Store a
normalized constraint when present. If metadata omits `Requires-Python` or
supplies an empty specifier set, leave `requires_python` absent from the config,
deleting any previously stored value.
Validate existing data before updating. Compare parsed specifier sets, keeping
absence distinct from a constraint. An equal existing value need not be
rewritten. Save newly created files even without a constraint. With `--verify`,
save first, then print an `old`/`new` JSON diff and exit 4 on drift, otherwise
exit 0. Omit the absent side of a diff. Adding/removing a constraint counts as
drift. On first `sync --verify`, a collected constraint is saved and causes exit
4. If the config has no stored constraint and metadata has no `Requires-Python`,
verification succeeds. Config/metadata errors are not diffs. Without verify,
sync just saves changes.

### print
Bare `print` emits the normalized stored specifier, or nothing if absent.
With `--format`, substitute into the template once even without a
constraint:

- `$specifier`: the full constraint in `packaging`'s normalized PEP 440
  format (the string form of `packaging.specifiers.SpecifierSet`), or empty
  if absent.
- `$rpmlowver`: existing RPM lower-limit conversion with a leading space,
  or empty without a lower limit. Upper limits, exclusions, and exact pins
  give no lower limit; wildcard equality follows the existing conversion.

Combining `$specifier` and `$rpmlowver` in one format is a usage error
(exit code 2). Escaped dollar signs remain literals.

Use existing safe template substitution. Suppress an exactly empty result; do
not trim nonempty output. A literal format supplies the downstream interpreter
name.

### Implementation
Give `python_dep` its own parser and command module. Share a config base class
with `deps` and reuse metadata/cache and RPM helpers. Test sync-verify, constraint
addition/removal, cache sharing, saved diffs/status, and print.

## Example
Given `Requires-Python: >=3.12,<4`:

```
python -m pyproject_installer python_dep sync
python -m pyproject_installer python_dep print --format='python3$rpmlowver'
# python3 >= 3.12
```

Without `Requires-Python`, sync omits `requires_python`:

```
python -m pyproject_installer python_dep sync
python -m pyproject_installer python_dep print --format='python3$rpmlowver'
# python3
```

To print without a lower limit, even when a constraint is stored:

```
python -m pyproject_installer python_dep print --format='python3'
# python3
```
