# Design rules

- Treat existing design docs as historical records. Change them only when
  explicitly asked or when related behavior changes. Keep updates limited
  to the requested change or affected behavior.
- Before writing or changing a design, read related designs and the
  relevant code. Check which earlier decisions still apply.
- Store designs in docs/designs/<topic>.md, using a short, descriptive
  snake_case name.
- Aim for about 100 lines per design. Focus on the problem, behavior,
  key decisions, and examples. Link to existing docs instead of repeating
  them, and keep detailed implementation steps in a separate plan.
- Follow the usual structure: Abstract, Motivation, Specification,
  Example. Put examples beside the behavior they explain when clearer.
- Keep the abstract short. Explain the problem and the proposed change.
  Use the motivation to show a concrete downstream packaging need.
- Define observable behavior precisely: syntax, defaults, output,
  stored data, errors, exit codes, and side effects, where relevant.
- Cover meaningful edge cases and interactions with existing options.
  State what happens when input is absent, empty, invalid, or unchanged.
- For operations that write data, explain when writes happen and what
  remains saved after a failure. Distinguish verification from saving.
- Explain compatibility changes explicitly. Identify the behavior
  callers can continue to rely on.
- Include implementation details only when they explain an important
  choice, constraint, or reuse of existing code.
- Add trade-offs, rejected alternatives, and scope limits when they
  explain a real decision. Do not add empty sections or speculative
  future features.
- Give concrete commands and expected results. Include the cases that
  tests must prove without repeating the project's test instructions.
- Keep settled decisions separate from open questions. Do not present
  an assumption as an agreed requirement.
- When a design supersedes an earlier decision, add a short note and
  link in the affected design so readers can find the newer behavior.
