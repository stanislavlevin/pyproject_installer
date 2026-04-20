## Abstract
This RFE proposes a new opt-in install option `--rpm-filelist PATH`
that emits a deterministic RPM `%files`-compatible filelist describing
every file written by the installer, plus the computed bytecompiled
`.pyc` paths for every installed `.py` under purelib/platlib
(PEP 3147 / PEP 488). The file is consumable by rpm's `%files -f`
directive without post-processing.

## Motivation
The project's primary downstream consumer is RPM packaging: a spec
file runs `pyproject_installer build && pyproject_installer install
--destdir %{buildroot}`, then declares the package contents in
`%files`. Today the packager enumerates those files by hand (or with
globs), which:

- duplicates knowledge the installer already has (scheme paths,
  `.data/` relocation, dist-info filtering, generated entry-point
  scripts);
- is fragile across distros with different purelib/platlib layouts;
- misses or double-claims `__pycache__/*.pyc` files that RPM's
  bytecompile step produces post-install - the glob surface there is
  tag-dependent (`cpython-312`, `cpython-313`, ...) and varies per
  build.

The installer already knows, at install time, exactly which files
land where and which `.py` files will later be bytecompiled by RPM.
Emitting that knowledge as a filelist removes duplication in every
spec and matches the RPM workflow `%files -f <filelist>`.

The filelist is opt-in because:

- the default behaviour (byte-identical to today) is unchanged -
  callers who don't set the flag pay nothing;
- not every consumer of the installer builds RPMs (some use the same
  destdir mechanic for containers, chroots, etc.);
- writing a side file under `destdir` would pollute the buildroot
  with content that RPM later flags as unpackaged - the filelist
  must live outside the buildroot.

## Specification

### User-facing contract
- Syntax: `python -m pyproject_installer install --rpm-filelist <PATH>
  [other install args...]`.
- `--rpm-filelist` is declared on the `install` subparser only.
- `<PATH>` is a filesystem path. Relative paths resolve against the
  current working directory (after any `-C <dir>` handling in
  `main()`). Parent directory must exist; if it doesn't, the write
  step fails with `FileNotFoundError`. No `mkdir`: layout is the
  caller's responsibility.
- An existing target is overwritten.
- Output format: UTF-8, LF line endings, trailing newline, sorted
  ascending. Each non-empty line is either `<path>` (file) or
  `%dir <path>` (directory entry), with a single space separator
  after `%dir`.
- Paths are **system-absolute, destdir stripped**. Given
  `--destdir /tmp/buildroot` and a wheel targeting purelib at
  `/usr/lib/python3/site-packages`, emitted lines look like
  `/usr/lib/python3/site-packages/foo/__init__.py` (not
  `/tmp/buildroot/usr/...`). The purelib/platlib roots are taken
  from `sysconfig.get_paths()` of the running interpreter; on a
  split `lib`/`lib64` layout the two differ
  (e.g. platlib = `/usr/lib64/python3/site-packages`).
- When `--rpm-filelist` is absent, behaviour is byte-identical to
  the current release.
- Programmatic API: `install_wheel(..., rpm_filelist=None)` accepts
  `Path | None`.
- Precondition: `sys.pycache_prefix` must be at its default
  (`None`). `importlib.util.cache_from_source` respects it, so a
  non-default value (via `PYTHONPYCACHEPREFIX` or
  `-X pycache_prefix=...`) would redirect every computed `.pyc`
  path under that prefix and desync the filelist from the
  buildroot. Enforced inside `render_rpm_filelist` before any path
  composition runs: violations raise `ValueError`.

## Example

```
# Install into a buildroot and emit the filelist alongside the wheel.
python -m pyproject_installer install \
    --destdir /tmp/buildroot \
    --rpm-filelist dist/foo.files

# In the .spec file:
%files -f dist/foo.files
```
