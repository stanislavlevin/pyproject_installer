# CLI rules

- Send all logging and diagnostics to stderr, at every verbosity level.
  Reserve stdout for the output the command was asked to produce, such as
  dependency lists, JSON diffs, Python constraints, and completion scripts.
  Never print or log diagnostics to stdout.
- Start logs and errors with a capital letter. Start usage errors from
  `parser.error` and `ArgumentTypeError` with lowercase, like argparse.
  Collector errors deliberately start with `{collector}: `.
- In library errors, quote argument and option names and use their Python
  names, not CLI flags: `'srctype' is mutually exclusive with 'candidates'`.
- In usage errors, leave CLI flags and positional names unquoted:
  `--depformatextra option must be used with --depformat`, or `srcname`.
- Leave paths and pyproject.toml field paths such as `build-system.requires`
  unquoted in messages.
- Use the existing `ExitCodes` values when reporting an existing outcome.
  Keep usage errors distinct from operation failures and verification drift.
- For path arguments using `type=Path`, set a path metavar: `DIR` for
  directories, `FILE` or `PATH` for files. Completion uses these values.
- Document new CLI options in `README.md` with their name, description,
  and an example. Update the entry when an existing option changes.
