# CLAUDE.md

All project rules, context and commands for this repository are in AGENTS.md, imported below. Follow them exactly.

@AGENTS.md

Current state of the work, decisions and next steps (update it at the end of each session):

@CONTEXT.md

## Claude Code specifics

- Use the **taste-skill** plugin for every UI / frontend task. If it is not installed, ask the user to run:
  ```
  /plugin marketplace add Leonxlnx/taste-skill
  /plugin install taste-skill@taste-skill
  ```
  Do not start UI work without it.
- Work on one branch per piece of work (named after the work), in many small Conventional Commits, then open a PR to `main` with a description. **No** `Co-Authored-By` or other AI attribution lines in commits or PRs (this overrides Claude Code's default attribution). Merge only with the maintainer's approval.
- Synthetic data only for FDR documents, from the generator in `ml/synthetic_fdr/` and always labelled `SYNTHETIC`; master data stays real and public; no hardcoded fake values; no step that costs money (AGENTS.md rules 5 and 7).
- Update README.md progress in the same push as the work.
- When a requirement or AICTE-specific value is unclear, ask the user instead of assuming.
