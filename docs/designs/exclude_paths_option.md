## Abstract
This RFE proposes a new opt-in install option `--exclude-paths
<PATTERN> [<PATTERN> ...]` that drops wheel members matching one or
more `fnmatch` glob patterns before extraction. Intended for
downstream packagers - primarily RPM - who want to strip test files
and other artifacts the upstream project shipped inside the wheel
but that aren't useful in installed form.

## Motivation
Some Python projects ship test files (e.g. `pkg/tests/`,
`test_*.py`, `*_test.py`) inside their wheel. For RPM packaging
those files:

- bloat the installed package without adding value to end users;
- conflict with the distro convention that test code is not shipped
  in runtime packages;
- have to be removed today by a separate post-install rm/find step
  in the spec, which duplicates the install-time knowledge of
  wheel member paths and is fragile across project layouts.

Letting the installer drop these files during extraction is the
correct boundary: the installer already iterates over the wheel
namelist and decides what to write to the destdir. Excluded
members are simply never extracted, so no post-install cleanup
runs and no empty parent directories are leaked.

The option is opt-in because:

- the default behaviour (byte-identical to today) is unchanged -
  callers who don't pass `--exclude-paths` pay nothing;
- not every consumer of the installer wants stripping - some need
  the full wheel content for testing or development installs;
- patterns are defined by the RPM macro on the consumer side; the
  installer ships no hard-coded defaults.

## Specification

### User-facing contract
- Syntax: `python -m pyproject_installer install --exclude-paths
  <PATTERN> [<PATTERN> ...] [other install args...]`.
- `--exclude-paths` is declared on the `install` subparser only.
- `nargs="+"`: at least one pattern is required when the flag is
  present. Default is an empty list - feature disabled.
- Programmatic API: `install_wheel(..., exclude_paths=())` accepts
  any `Sequence[str]`.

### Pattern syntax
Each `PATTERN` is an `fnmatch` glob (Python stdlib
`fnmatch.fnmatchcase`):

- `*` matches any run of characters including `/` (slash-blind).
- `?` matches one character including `/`.
- `[abc]`, `[!abc]` character classes.
- The whole path must match the whole pattern.

Because `*` is slash-blind, every pattern should include literal
`/` anchors to avoid leaking across directory boundaries. A typical
RPM-macro payload uses one root-anchored form and one nested form
per abstract goal, e.g.:

```
tests/*       */tests/*
test_*.py     */test_*.py
*_test.py     */*_test.py
```

### Path format
Patterns are matched against the wheel's ZIP `namelist()` entries
verbatim. Per PEP 427 and the ZIP specification, those entries are
always forward-slash separated POSIX paths with no leading `/` and
no `./` prefix, regardless of host operating system. Concrete
examples of what a pattern matches against: `pkg/foo.py`,
`pkg/sub/foo.py`, `pkg-1.0.dist-info/METADATA`,
`pkg-1.0.data/scripts/cli`. Directory-only zip entries (names
ending in `/`) are dropped upstream by `WheelFile.memberlist` and
never reach the matcher.

### Behaviour
A wheel member is excluded if its path matches any supplied
pattern. Excluded members are never written to the destdir, so:

- excluded files don't appear in the install tree;
- parent directories that would have held only excluded files are
  never created (`zipfile.ZipFile.extractall(members=...)` only
  creates listed paths);
- when combined with `--rpm-filelist`, excluded paths don't appear
  in the generated filelist;
- when `--exclude-paths` is absent, behaviour is byte-identical to
  the current release.

There are no hard-coded exceptions: a pattern that matches anything
inside `dist-info` (or `.data`) strips it. System-level policy for
`dist-info` content remains controlled by `--no-strip-dist-info`.

### Scope: wheel members only
Patterns apply to the wheel's namelist before extraction. Content
synthesised downstream by the install pipeline is **not** subject
to these patterns:

- console-script wrappers generated from `entry_points.txt`;
- the `INSTALLER` file written by `--installer`;
- `.pyc` files produced post-install by external bytecompile steps
  (e.g. RPM's `brp-python-bytecompile`).

To suppress generated console scripts, exclude
`*.dist-info/entry_points.txt`: the generator skips its work when
the file is absent from the install tree.

### Interaction with `filter_dist_info`
`filter_dist_info` runs upstream of `filter_exclude_paths`. By
default (`strip_dist_info=True`), only `METADATA` and
`entry_points.txt` survive from `dist-info` and reach the exclude
filter. With `--no-strip-dist-info`, every `dist-info` file reaches
the exclude filter and is subject to user patterns.

### argparse positional interaction
`nargs="+"` is greedy: it consumes positional-looking tokens until
it sees another flag, the `--` terminator, or end-of-argv. The
wheel positional must therefore either precede `--exclude-paths`,
be separated from the pattern list by `--`, or be preceded by
another flag - otherwise the wheel argument is consumed as another
pattern. This matches the existing constraint on `deps eval
--exclude`.

## Example

```
# Strip test artifacts at install time (typical RPM packaging use).
python -m pyproject_installer install \
    --destdir /tmp/buildroot \
    --exclude-paths 'tests/*' '*/tests/*' \
                    'test_*.py' '*/test_*.py' \
                    '*_test.py' '*/*_test.py'
```

For RPM-macro consumption, the macro defines the pattern payload
and forwards it:

```rpm-spec
%global pyproject_excluded_paths tests/* */tests/* test_*.py */test_*.py *_test.py */*_test.py

%pyproject_install %{wheelpath} --exclude-paths %{pyproject_excluded_paths}
```

Given a wheel containing:

- `pkg/__init__.py`
- `pkg/core.py`
- `pkg/tests/__init__.py`
- `pkg/tests/test_core.py`
- `pkg-1.0.dist-info/METADATA`

After installing with the macro's patterns, the destdir contains
only:

- `pkg/__init__.py`
- `pkg/core.py`
- `pkg-1.0.dist-info/METADATA`

The `pkg/tests/` directory is never created.
