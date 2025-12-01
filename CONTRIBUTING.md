## Contributing to lang2pick

Thank you for your interest in contributing! This document explains how to report issues, propose changes, and submit pull requests so we can review and accept contributions quickly.

### Table of contents
- Getting started
- Code of Conduct
- Reporting bugs
- Requesting features
- Working on code (branches, commits, tests)
- Creating a pull request
- Review process & CI
- Style & testing
- Security
- Thank you

### Getting started

1. Fork the repository and clone your fork.
2. Create a topic branch for your change. Keep each branch focused on a single logical change.
3. Make changes in small, well-scoped commits.

Example (assuming a typical ROS2 workspace):

```bash
# from repo root
git checkout -b feat/short-description
# make changes
git add -A
git commit -m "feat(component): short description"
git push origin feat/short-description
```

If your change includes code that needs building or tests run in ROS2, we recommend building with `colcon` in the `ros2_ws` workspace and running tests locally before opening a PR.

### Code of Conduct

Be respectful and welcoming. If you don't already have a `CODE_OF_CONDUCT.md` in the repo, assume standard contributor-friendly behavior: be civil, inclusive, and constructive. If you believe a contributor violated the code of conduct, contact a repository maintainer.

### Reporting bugs

When filing an issue, include:

- A clear, descriptive title
- A short summary of the problem
- Steps to reproduce (minimal reproduction preferred)
- Expected vs actual behavior
- Environment details (OS, ROS2 distro, commit/branch, hardware if relevant)
- Any logs, stack traces, or screenshots

Good issue reports help us fix bugs faster.

### Requesting features

Open an issue describing the use-case, suggested design, and any alternatives you considered. Label it as `feature` if the repository uses labels.

### Working on code (branches & commits)

Branch naming convention:
	- feat/<short-description> for new features
	- fix/<short-description> for bug fixes
	- docs/<short-description> for documentation only
	- test/<short-description> for tests

- One logical change per branch/PR.
- Keep commits small and focused. Rebase to keep history tidy if requested by maintainers.

Commit message guidelines (recommendation):

- Use Conventional Commits style: `<type>(scope): short description`
	- Examples: `feat(motion): add trajectory smoothing`, `fix(driver): handle timeout`
- Keep the subject line <= 72 characters. Add a longer body if needed explaining the why and how.

### Creating a pull request

When ready, open a pull request from your branch to `main` (or the branch specified in the issue). In the PR description, include:

- Which issue the PR fixes or implements (use `Fixes #<issue>` when appropriate)
- Summary of changes
- Any setup or build steps for reviewers
- Testing done (unit/integration/manual)

PR checklist (please ensure before requesting review):

- [ ] The PR has a clear title and description
- [ ] Related issue referenced (if applicable)
- [ ] Tests added/updated for new behavior
- [ ] Documentation updated (README, code comments, configs)
- [ ] Code builds and tests pass locally
- [ ] CI checks are green

### Review process & CI

We use automated CI to run linters and tests. A PR requires at least one approving review from a maintainer before merge.

Maintainers may request changes; please respond to review comments and update the PR. Squash or rebase as requested.

### Style & testing

Try to match the repository's existing style. Common recommendations:

- C++: follow the project's clang-format/ament settings and ROS2 C++ style
- Python: follow Black and Flake8 conventions

Run these common commands when relevant (example):

```bash
# build a ROS2 workspace
colcon build --symlink-install
source install/setup.bash

# run tests
colcon test --packages-select <package_name>
colcon test-result --verbose
```

If you add new functionality, include or update unit tests where possible.

### Licensing and copyright

By contributing, you agree that your contributions will be licensed under this repository's license (see `LICENSE`). When in doubt, keep changes minimal and discuss large contributions in an issue first.

### Thank you

Thanks for helping make this project better! We appreciate every contribution :) large or small.


