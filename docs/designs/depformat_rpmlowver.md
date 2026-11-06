## Abstract
New `deps eval --depformat` substitution `$rpmlowver`: the lower
version limit of a dependency, converted for RPM (`foo>=1.2` gives
`python3-foo >= 1.2`). Opt-in; RPM never rejects a version
that PEP 440 accepts.

## Motivation
`--depformat` drops version specifiers on purpose: a distro usually
ships one version of each project, and upstream ranges are often
narrower than needed (maintainers play safe, automated tools narrow
them further).

Without a version, RPM installs the package even when the
dependency on the system is too old, and the package fails when it
runs. Today the version is added by hand, which is easy to miss.

Only the lower limit is printed: an upper limit mostly blocks a
newer version that still works (`foo<4` while the distro ships
`foo` 4.1). Lower limits can be too narrow too (automated tools
raise them), so the caller decides whether to use `$rpmlowver`.

## Goals
- Print the lower limit of a dependency through `--depformat`.
- One dependency still yields one line (per extra).
- RPM never rejects a version PEP 440 accepts.

## Specification

### Contract
- `$rpmlowver`: the folded, converted lower limit with a leading
  space (`' >= 1.3'`), or `''` without a lower limit, so a format
  can end with it. The operator is `>=` or `>`.
- With extras, every extra line gets the limit.
- One requirement per line is mandatory.

```
python -m pyproject_installer deps eval build \
    --depformat='python3-$nname$fextra$rpmlowver' \
    --depformatextra='+$nextra'
```

With `build` storing `foo[a,b]>=1.2.0,>1.3a1,!=1.5,<2` and `bar`:

```
python3-bar
python3-foo+a >= 1.3
python3-foo+b >= 1.3
```

### Lower limits
- `>=V` -> `>= V`
- `>V` -> `> V`
- `~=V`, `==V.*` -> `>= V`
- all others, including `==V` and `===V` (equality) -> none
  (an exact pin usually names the version upstream tested with,
  not the oldest one that works)

### Folding
All lower limits of one dependency (same PEP 503 name, extras
included, after markers and `excludes`) fold into the strictest
one, by PEP 440 rules.

Limits from all evaluated sources are combined, since the output
is one list. With `foo>=1.2` in `build` and `foo` in `run`,
evaluating both sources prints one line: `python3-foo >= 1.2`.

### Version conversion
RPM compares versions differently from PEP 440:

- `1.0rc1`: RPM treats it as newer than `1.0`, PEP 440 as older
- `1.0.0`: RPM treats it as newer than `1.0`, PEP 440 as equal

So:

- keep the release numbers only:
  - PEP 440 normalized: `01.02.0` -> `1.2`
  - trailing zeros dropped: `2.0.0` -> `2`, so `>= 2` accepts a
    package with `Version: 2.0`, which `>= 2.0.0` would reject
  - epoch dropped: `1!2.0` -> `2`; folding compares epochs (the
    default is 0), so `>=1!1.0,>=5` folds into `>=1!1.0` and prints
    the looser `>= 1`
  - pre-release dropped: `0.1.0a39` -> `0.1`
  - post-release dropped: `2.9.0.post1` -> `2.9`
  - dev release dropped: `1.0.dev2` -> `1`
- `>` on a version that lost a pre, post or dev part becomes `>=`:
  `>1.3a1` -> `>= 1.3`
- the printed limit never has an RPM epoch (`Epoch:`); not supported

### Turning a limit off
A lower limit can be wrong for a distro: upstream raises it without
need, or the distro's version of the dependency is numbered
differently. `--ignore-rpmlowver NAME...` makes the `$rpmlowver`
substitution empty for the named requirements:

- exact project names, not patterns; both sides are compared
  PEP 503-normalized (`Foo_Bar` matches `foo-bar`, `foo` does not)
- the name gets no limit from any evaluated source
- the requirement is still printed; `--exclude` drops it instead and
  wins when a name is in both
- requires `--depformat`; without the `$rpmlowver` substitution in the
  format it changes nothing

```
python -m pyproject_installer deps eval build \
    --depformat='python3-$nname$fextra$rpmlowver' \
    --depformatextra='+$nextra' \
    --ignore-rpmlowver foo
```

With `build` storing `foo[a,b]>=1.2.0,>1.3a1,!=1.5,<2` and `bar>=2`:

```
python3-bar >= 2
python3-foo+a
python3-foo+b
```
