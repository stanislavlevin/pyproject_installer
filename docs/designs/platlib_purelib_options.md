## Abstract
This RFE proposes two new mutually-exclusive install options
`--platlib` and `--purelib` that override the wheel's
`Root-Is-Purelib` flag and consolidate the two `*lib` scheme keys
onto a single site directory for the install. Effect:

- `--platlib`: every file the installer would route to purelib goes
  to platlib instead, regardless of `Root-Is-Purelib` in WHEEL. This
  covers the unprefixed wheel root and any `.data/purelib/` content.
- `--purelib`: the symmetric inverse - everything purelib-keyed *and*
  platlib-keyed lands in purelib.

Default behaviour (neither flag set) is byte-identical to today.

## Motivation
The primary downstream consumer is RPM packaging, which sometimes
needs to forcibly relocate an "actually purelib" wheel to platlib (or
the reverse). Concrete drivers:

- **Multilib layouts (lib vs. lib64).** On split-layout distros the
  WHEEL spec's "Root-Is-Purelib: true" maps to `/usr/lib/...`, but a
  package paired with arch-dependent siblings, or one packaged for
  the platform-specific subpackage, must land under
  `/usr/lib64/...`. The reverse can also occur (a wheel marked
  platlib that contains no native code).
- **Wheel author's flag is wrong or coarse.** Some build backends
  emit `Root-Is-Purelib: true` even when the project also ships
  arch-specific data files; downstream packagers cannot easily
  rebuild the wheel and need a one-shot relocation switch instead.
- **`.data/purelib/` is also affected.** A file deliberately routed
  to `.data/purelib/` by the wheel author would otherwise still land
  in purelib regardless of the root override; the `--platlib` flag
  redirects that too, so all "purelib content" of the wheel is
  consolidated in one place. Same for the inverse direction.

The override is opt-in because:

- the default behaviour (honour `Root-Is-Purelib`) is unchanged - it
  is what every well-formed wheel and every other installer in the
  ecosystem does;
- it is intentionally a per-install decision, not configurable in
  the wheel itself, because the same wheel may be installed into
  different subpackages of the same RPM build with different
  policies;
- the WHEEL flag still wins by default - the override is a deliberate
  packager-level choice that should be invisible in the source tree.

## Specification

### User-facing contract
- Syntax: `python -m pyproject_installer install [--platlib | --purelib]
  [other install args...]`.
- Both flags are declared on the `install` subparser inside an
  `argparse.add_mutually_exclusive_group()`. Passing both produces the
  standard argparse error path (usage line on stderr, exit code 2).
- When neither flag is set, behaviour is byte-identical to the
  current release: `Root-Is-Purelib` from WHEEL drives the slot
  decision and the sysconfig scheme is consumed unmodified.
- When `--platlib` is set, the installer behaves as if every
  purelib-keyed location were aliased to the platlib path:
  - the wheel's unprefixed root is extracted under
    `scheme["platlib"]`, regardless of `Root-Is-Purelib` in WHEEL;
  - any file under `.data/purelib/` is dispatched to
    `scheme["platlib"]`;
  - any file under `.data/platlib/` continues to land in
    `scheme["platlib"]` (no change);
  - `.data/scripts/`, `.data/headers/`, `.data/data/` are unaffected.
- `--purelib` is the symmetric inverse: every platlib-keyed location
  is aliased to the purelib path. Same coverage of `.data/*`.
- The override is idempotent on already-aligned wheels. Passing
  `--platlib` to a `Root-Is-Purelib: false` wheel does not change the
  root extraction, but it still redirects any `.data/purelib/`
  content to platlib. No special-casing for "no-op" inputs.
- The override applies before destdir prepending. The `--destdir`
  contract is unchanged: the (possibly redirected) installation root
  is prepended with destdir as today.
- Programmatic API: `install_wheel(..., force_site=None)` accepts
  `Literal["purelib", "platlib"] | None`.

## Example

```
# Force a pure-Python wheel into platlib, e.g. because the RPM
# subpackage owning these files lives under /usr/lib64.
python -m pyproject_installer install \
    --destdir /tmp/buildroot \
    --platlib

# Symmetric: force a wheel marked Root-Is-Purelib: false into purelib.
python -m pyproject_installer install \
    --destdir /tmp/buildroot \
    --purelib

# Combined with --rpm-filelist: the emitted filelist reflects the
# consolidated slot. No code change in _rpm_filelist.py is needed -
# anchor classification + set-backed output deduplicates naturally.
python -m pyproject_installer install \
    --destdir /tmp/buildroot \
    --platlib \
    --rpm-filelist dist/foo.files
```
