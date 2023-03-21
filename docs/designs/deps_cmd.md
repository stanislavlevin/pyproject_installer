Collect dependencies from different source types, store or evaluate them.

Use cases:
As a downstream maintainer I have to sync distro dependencies to upstream.

# Specification #

# TODO
deps [--depsfile]

    add
    
    del
    
    sync
    
    show
    
    verify
    
    eval


# Examples #

## Example of deps.json
```json
{
    groups: {
        "build": {
            "filters": {
                "include": (),
                "exclude": (),
            },
            "sources": {
                "pep518": {
                    "srctype": "pep518",
                    "srcargs": (),
                    "deps": (),
                    "extra": "",
                },
                "pep517": {
                    "srctype": "pep517",
                    "srcargs": (),
                    "deps": (),
                    "extra": "",
                }
            }
        }
    }
}
```

## CLI usage

# group management

deps group add build
deps group del build

# source management
deps source add build pep518 pep518
deps source del build pep518

# filter management
deps filter add build (exclude|include) types- pytest-
deps filter del build (exclude|include)

# sync dependencies (parse according to configuration and dump deps to deps file)
deps sync build

# evaluate deps of build group
deps eval build

# verify deps
deps verify build

# show config
deps show

# how to add at first time (build deps)
- create dependencies config.
  This step requires installed pyproject-installer >= TBD.
  
  For example,
  ```
  # create group of dependencies named 'build'
  python3 -m pyproject_installer deps --depsfile .gear/pyproject_deps.json add build

  # add PEP518 as a source of dependencies for group 'build'
  python3 -m pyproject_installer deps --depsfile .gear/pyproject_deps.json source add build pep518 pep518             
  ```
  This generates configuration file at .gear/pyproject_deps.json that only
  defines *sources* of dependencies. Resolving of sources happens in build
  environment.

  Produced config can be examined with:
  ```
  python3 -m pyproject_installer deps --depsfile .gear/pyproject_deps.json show
  ```

- %pyproject_deps * RPM macros are shipped in rpm-build-pyproject RPM package.
  They expect to find its configuration in RPM sources directory. Thereby,
  - replace rpm-build-python3 with rpm-build-pyproject
  - add 'copy: .gear/pyproject_deps.json' to .gear/rules
  - add Source1: pyproject_deps.json to RPM specfile

- prepend RPM build phase with `%pyproject_builddeps build` macro that:
  - eval deps of selected group (all groups by default)
  - map them to distro names
  - mark result as build dependencies
  - verify list of deps against resynced ones, otherwise resync

- run %build phase. The build should fail at that phase with report like:
  ```json
  {
    "build": {
      "new_deps": [
        "types-psutil",
        "mypy_extensions>=1.0.0",
        "typing_extensions>=3.10",
        "types-typed-ast>=1.5.8,<1.6.0",
        "setuptools >= 40.6.2",
        "types-setuptools",
        "tomli>=1.1.0; python_version<'3.11'",
        "wheel >= 0.30.0",
        "typed_ast>=1.4.0,<2; python_version<'3.8'"
      ]
    }
  }
  ```

- dependencies can be filtered in or out.
  For example, all `types-xxx` can be filtered out from `build` group with:
  ```
  python3 -m pyproject_installer deps --depsfile .gear/pyproject_deps.json filter add build exclude 'types-'
  ```

  Rerun %build phase to resync list of dependencies with filters.
  For example,
  ```json
  {
    "build": {
      "new_deps": [
        "mypy_extensions>=1.0.0",
        "tomli>=1.1.0; python_version<'3.11'",
        "wheel >= 0.30.0",
        "typed_ast>=1.4.0,<2; python_version<'3.8'",
        "setuptools >= 40.6.2",
        "typing_extensions>=3.10"
      ]
    }
  }
  ```

- stored config should be updated with produced one
  For example,
  ```
  cp ~/hasher/chroot/usr/src/RPM/SOURCES/pyproject_deps.json .gear/
  ```

- add PEP517 and its `get_requires_for_build_wheel` as an additional source of
  dependencies for group 'build'
  ```
  python3 -m pyproject_installer deps --depsfile .gear/pyproject_deps.json source add build pep517 pep517             
  ```
  And rerun %build step to resync list of dependencies.
  For example,
  ```json
  {
    "build": {
      "new_deps": [
        "wheel"
      ]
    }
  }
  ```

- stored config should be updated with produced one
  For example,
  ```
  cp ~/hasher/chroot/usr/src/RPM/SOURCES/pyproject_deps.json .gear/
  ```

# now check dependencies can be added
- create group of dependencies named 'check'
  ```
  python3 -m pyproject_installer deps --depsfile .gear/pyproject_deps.json add check
  ```

  # add `test` extras of current package
  ```
  python3 -m pyproject_installer deps --depsfile .gear/pyproject_deps.json source add build extras_test metadata test
  ```
