Collect dependencies from different source types, store or evaluate them.

Use cases:
As a downstream maintainer I have to sync distro dependencies to upstream.

# Specification #
deps [--depsfile]

    add [--ignore REGEX]
        GROUP SRCNAME SOURCETYPE ARGS
    
    del [--srcname]
        [GROUP, ...]
    
    sync
    
    show
    
    verify [GROUP, ...]
    
    eval [GROUP, ...]


# Examples #

## Example of deps.json
```json
{
    groups: {
        "build": {
            "pep518": {
                "srctype": "pep518",
                "srcargs": [],
                "deps": [],
            },
            "pep517_wheel": {
                "srctype": "pep517",
                "srcargs": ["build_wheel"],
                "deps": [],
            },
        },
        "check": {
            "some_file": {
                "srctype": "file",
                "srcargs": [],
                "deps": [],
            },
            "testing": {
                "srctype": "file",
                "srcargs": [],
                "deps": [],
            },
        },
    }
}
```

## CLI usage

# create configuration
deps add build pep518 pep518
# sync dependencies (parse according to configuration and dump deps to deps file)
deps sync

# delete group of deps
deps del build
# delete source from group of deps
deps del --srcname pep518 build
# delete all groups of deps
deps del --all

# evaluate deps of build group
deps eval build

# RPM specfile
BuildRequires: read, evaluate, map and print deps

%pre
# configuration is required
deps sync
