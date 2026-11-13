# Development rules

- Use simple English in chat, code comments, and documentation. Avoid jargon
  and prefer common words, such as "use" instead of "leverage".
- Avoid real project and distribution names in tests, examples,
  documentation, and similar material. Use fictional or generic names.
- Follow the supported Python versions listed in the
  [Python Developer's Guide](https://devguide.python.org/versions/).
  New syntax and standard-library calls must work on the oldest supported
  version.
- When changing Python support, keep `requires-python`, version classifiers,
  CI matrices, and the README badge in sync.
- Keep runtime dependencies limited to the standard library and vendored
  `packaging`. Do not add network I/O to runtime code.
- `src/pyproject_installer/lib/backend_helper/backend_caller.py` runs in a
  subprocess. Keep it standard-library-only, with no main-package imports.
- Builds are non-isolated. Checking and installing build dependencies is
  the caller's job.
- The backend in `backend/` builds this project. Keep it usable for
  self-hosting without external build dependencies.
- Installation drops `RECORD` (PEP 627) and does not compile bytecode.
  Preserve these deliberate choices.
- New features need tests and documentation. Follow the
  [test rules](testing.md) and, for CLI changes, the [CLI rules](cli.md).
- Update vendored dependencies through `vendored.txt` and the regeneration
  script. See [commands](commands.md) for setup and invocation.

## Commit messages

- Follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/).
  Use lowercase types, an optional scope, and a short, direct summary in the
  imperative, such as `fix(cli): handle an empty input`.
- Use `feat`, `fix`, `vendor`, `maint`, `deps`, `deprecate`, `remove`, or
  `security` for product changes, choosing the type that describes the change.
- Use `docs`, `readme`, `tests`, `ci`, `gha`, `ruff`, `lint`, `black`,
  `reformat`, or `pylint` for changes limited to those areas.
- Use `release: bump version to <version>` for version bumps.
- Follow [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
  for changelog entries. Describe notable changes clearly for users.
- Use the full issue URL in `Fixes:` lines in commit messages, rather
  than a short reference such as `#<issue-number>`.
- For commits written with an agent's help, end the message with one
  `Assisted-by: <agent-name>:<model-id>` trailer. Use the actual agent name
  and exact model ID. When amending or folding commits, keep the existing
  trailer instead of adding another one.

Example:

```text
fix(cli): reject an output path that points to a file

Report a usage error before building, so the user can correct the path.

Fixes: https://example.org/project/issues/<issue-number>
Assisted-by: <agent-name>:<model-id>
```
