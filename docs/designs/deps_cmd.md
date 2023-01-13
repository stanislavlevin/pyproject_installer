## Abstract
Collect [PEP508](https://peps.python.org/pep-0508/) requirements from different
sources, store and evaluate them in Python environment.

## Motivation
Distro dependencies of Python projects are managed externally with tools like
apt or dnf. Such tools usually are not awared of Python packaging standards and
don't honor [PEP508](https://peps.python.org/pep-0508/) dependency specification.
Downstreams employ different ways to manage runtime and buildtime dependencies,
for example:
- manual resyncing of dependencies' list to upstream on every project's release
- automatically parsing of source code and fetching all external imports
- automatically parsing of produced core metadata

Every method has its advantages and disadvantages.

This RFE proposes `external` source of upstream dependencies for
downstream packaging. Such a source may be configured with different
kinds of dependencies sources like [core metadata](https://packaging.python.org/en/latest/specifications/core-metadata/), [PEP518](https://peps.python.org/pep-0518/), [PEP517](https://peps.python.org/pep-0517/), etc.,
each of them can be synced, verified, resynced or evaluated.

## Specification
New `deps` command will implement this kind of functionality.

```
deps
    add    - configure source of Python dependencies
    delete - deconfigure source of Python dependencies
    show   - show configuration and data of dependencies's sources
    sync   - sync dependencies of configured sources
    eval   - evaluate dependencies according to PEP508 in current Python environment
```

Supported sources of Python dependencies:
- build dependencies' format is standardized by [PEP518](https://peps.python.org/pep-0518/) and [PEP517](https://peps.python.org/pep-0517/) (fully supported)
- runtime dependencies' format is standardized by [core metadata](https://packaging.python.org/en/latest/specifications/core-metadata/) (fully supported)
- tests/docs dependencies' format is not standardized and there are many
  tools that provide their own format (e.g. pip, tox, poetry) (limited support)

### Example
```
python -m pyproject_installer deps add build pep518
python -m pyproject_installer deps sync build
python -m pyproject_installer deps eval build
```
