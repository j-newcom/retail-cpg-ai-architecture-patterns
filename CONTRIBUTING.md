# Contributing

Thank you for your interest in this project.

## Scope

This repository contains reference architectures, notebooks, and technical writing focused on AI adoption patterns in Retail and Consumer Packaged Goods. Contributions that expand coverage within this domain are welcome.

## How to Contribute

1. **Open an issue first.** Describe what you'd like to add or change. This avoids duplicate work and ensures alignment with the project's scope.

2. **Fork and branch.** Create a feature branch from `main`. Use a descriptive name (e.g., `add-inventory-optimization-architecture`).

3. **Follow existing conventions.**
   - Architectures go in `architectures/<pattern-name>/` with a README, architecture doc, and diagrams folder.
   - Notebooks go in `notebooks/` with clear markdown cells explaining each step.
   - Technical perspectives go in `docs/` as standalone markdown files.

4. **Keep it vendor-aware but not vendor-locked.** Architectures reference specific cloud services where appropriate, but the patterns should be transferable. Explain the "why" behind service choices.

5. **No proprietary data.** Do not include customer names, internal company data, proprietary code, or anything covered by NDA.

6. **Submit a pull request.** Reference the related issue. Include a brief description of what the PR adds and why it belongs in this collection.

## Quality Standards

- Markdown files pass linting (see `.github/workflows/lint.yml`).
- Diagrams use Mermaid syntax (rendered natively by GitHub) or PNG exports with source files included.
- Code in notebooks and scripts runs without modification on a clean environment with documented dependencies.

## Code of Conduct

Be respectful, constructive, and focused on the technical content. This is a professional knowledge-sharing project.
