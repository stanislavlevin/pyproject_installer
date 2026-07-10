# Changelog

All notable changes to pyproject-installer will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

History for releases prior to the first entry below is not captured here —
see git tags and commit history for earlier changes.

## [0.6.0] - 2026-07-10

### Added
- feat(cli): deduplicate repeated list inputs, preserving order ([#173](https://github.com/stanislavlevin/pyproject_installer/issues/173))
- feat(deps): report unsynced sources as a self-sufficient diagnostic ([#171](https://github.com/stanislavlevin/pyproject_installer/issues/171))
- feat(deps): add `add --sources` to configure a batch of named sources ([#169](https://github.com/stanislavlevin/pyproject_installer/issues/169))
- feat(deps): cache built core metadata in dist/metadata_cache ([#167](https://github.com/stanislavlevin/pyproject_installer/issues/167))
- feat(deps): add logging and split data/diagnostics streams ([#165](https://github.com/stanislavlevin/pyproject_installer/issues/165))
- feat(deps): add `metadata_extra` source for a core-metadata extra ([#161](https://github.com/stanislavlevin/pyproject_installer/issues/161))
- feat(deps): add `add --candidates` to autodiscover a source ([#159](https://github.com/stanislavlevin/pyproject_installer/issues/159))
- feat(deps): add `add --reconfigure` and `--sync` to cut per-source spawns ([#157](https://github.com/stanislavlevin/pyproject_installer/issues/157))
- feat(deps): add sync --verify-ignore-version option ([#155](https://github.com/stanislavlevin/pyproject_installer/issues/155))
- feat(completion): add bash completion for pyproject-installer ([#153](https://github.com/stanislavlevin/pyproject_installer/issues/153))
- feat(install): add --exclude-paths install option ([#151](https://github.com/stanislavlevin/pyproject_installer/issues/151))
- feat(install): add --platlib/--purelib install flags ([#147](https://github.com/stanislavlevin/pyproject_installer/issues/147))
- feat: add --rpm-filelist install option ([#142](https://github.com/stanislavlevin/pyproject_installer/issues/142))
- feat: add CHANGELOG and release-time entry generator ([#135](https://github.com/stanislavlevin/pyproject_installer/issues/135))
- feat(cli): add support for -C change-dir option ([#133](https://github.com/stanislavlevin/pyproject_installer/issues/133))

### Changed
- test(deps): cover PEP 503/685 extra-name normalization ([#163](https://github.com/stanislavlevin/pyproject_installer/issues/163))
- maint(types): annotate codebase and enable mypy strict ([#149](https://github.com/stanislavlevin/pyproject_installer/issues/149))
- vendor: update packaging to 26.2 ([#144](https://github.com/stanislavlevin/pyproject_installer/issues/144))
- refactor(lib): delegate pep503_normalized_name to packaging.utils ([#141](https://github.com/stanislavlevin/pyproject_installer/issues/141))
- refactor(deps): use packaging.dependency_groups for pep735 collector ([#141](https://github.com/stanislavlevin/pyproject_installer/issues/141))
- vendor: update packaging to 26.1 ([#139](https://github.com/stanislavlevin/pyproject_installer/issues/139))
- vendor: update tomli to 2.4.1 ([#123](https://github.com/stanislavlevin/pyproject_installer/issues/123))
- vendor: update packaging to 26.0 ([#118](https://github.com/stanislavlevin/pyproject_installer/issues/118))
- vendor: update tomli to 2.4.0 ([#117](https://github.com/stanislavlevin/pyproject_installer/issues/117))
- maint: drop support for EOL-d Python 3.9 ([#115](https://github.com/stanislavlevin/pyproject_installer/issues/115))
