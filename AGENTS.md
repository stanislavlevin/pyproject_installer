# pyproject-installer

Builds and installs PEP 517/518 projects in network-isolated environments,
primarily for RPM packaging. Runtime uses the standard library and vendored
`packaging`, with no network I/O. The backend in `backend/` builds this project.

Read and follow the rules for the work you are doing:

- [Commands](docs/agents/commands.md): before environment setup, builds,
  validation, or dependency updates.
- [Development](docs/agents/development.md): before changing code or
  dependencies, or writing commit messages.
- [CLI](docs/agents/cli.md): before changing command behavior, output,
  messages, or CLI documentation.
- [Testing](docs/agents/testing.md): before adding or changing tests.
- [Designs](docs/agents/designs.md): before writing or changing designs.
