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
            "deps": (),
            "sources": {
                "pep518": {
                    "srctype": "pep518",
                    "srcargs": (),
                },
                "pep517_wheel": {
                    "srctype": "pep517",
                    "srcargs": ("build_wheel"),
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

# RPM specfile
BuildRequires: evaluate, map and print deps

%prep
# configuration is required
deps verify

# howto add at first time
- don't add any of 'pyproject_installer deps'-based macros into RPM spec file
- build a package with pyproject_installer
