# Test rules

- Pytest treats warnings as errors (`filterwarnings = ["error"]`).
- Follow [commands](commands.md) for environment setup, lint, test runs,
  and subprocess coverage.
- Read similar existing tests before writing or changing tests. Match
  their layout, fixtures, and assertions.
- Prefer plain, clear tests that each check one specific thing. Keep
  setup and assertions simple and explicit.
- Store actual and expected values in clearly named `actual_*` and
  `expected_*` variables before comparing them. Keep comparisons
  separate from computing or constructing those values.
- Keep collector and config tests in separate modules. A single
  collector does not need a collectors package.
- Put new CLI tests in `tests/unit/test_cli/`, grouped by command.
- Test collection through the command's `sync` action and check the
  saved config, following the existing collector tests.
- Reuse fixtures. Keep a fixture in its test module when only that
  module uses it. Put shared fixtures in the nearest common conftest.py.
- Keep separate tests for separate commands, subcommands, and build
  paths. Prefer separate tests over parametrization. Use parametrization,
  including parametrized fixtures, only when it makes cases for the same
  behavior clearer than separate tests.
- Test this project's behavior. Avoid repeating tests for argparse,
  packaging, or inherited behavior already covered elsewhere.
- Include only data needed for the behavior under test. Add unrelated
  fields only when testing their handling or preservation.
- In cache tests, make built and cached metadata differ so the result
  clearly shows which was used.
