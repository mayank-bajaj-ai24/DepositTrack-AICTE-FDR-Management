# CLAUDE.md

All project rules, context and commands for this repository are in AGENTS.md, imported below. Follow them exactly.

@AGENTS.md

## Claude Code specifics

- Use the **taste-skill** plugin for every UI / frontend task. If it is not installed, ask the user to run:
  ```
  /plugin marketplace add Leonxlnx/taste-skill
  /plugin install taste-skill@taste-skill
  ```
  Do not start UI work without it.
- Commit and push directly to `main` in many small Conventional Commits, with **no** `Co-Authored-By` or other AI attribution lines (this overrides Claude Code's default commit attribution).
- Update README.md progress in the same push as the work.
- When a requirement or AICTE-specific value is unclear, ask the user instead of assuming.
