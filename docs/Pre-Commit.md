# Pre-Commit Hooks Configuration

This repository uses **pre-commit** to automatically format code, lint files, and prevent common mistakes before changes are committed. This helps maintain consistent code style, avoid large accidental commits, and keep the project clean.

Below is an overview of the tools included in `.pre-commit-config.yaml` and how to use them.

---

## What This Configuration Includes

### 1. **Clang-Format** (C/C++)

Ensures consistent formatting for all `*.cpp`, `*.hpp`, `*.cc`, `*.hh`, `*.c`, `*.h` files.

* Uses your project's `.clang-format` file.
* Runs automatically on commit.

### 2. **Black** (Python Formatter)

Formats Python code to follow a consistent, standardized style.

* Runs on all `*.py` files.
* Uses Python 3.

### 3. **Flake8** (Python Linter)

Checks Python files for:

* Styling issues
* Potential bugs
* Code smells

Includes:

* `flake8-bugbear` for additional safety checks
* Line length set to **120 characters**

### 4. **Pre-Commit Built-in Hooks**

Includes:

* `check-merge-conflict` – prevents committing merge conflict markers
* `check-added-large-files` – prevents committing files larger than **20 MB**

### 5. **Prettier** (YAML Formatting)

Automatically formats YAML (`.yaml` / `.yml`) files.

### 6. **xmllint** (XML Formatting)

Formats XML files using the system-installed `xmllint`.

### 7. **nbstripout** (Clean Jupyter Notebooks)

Strips output cells from Jupyter notebooks to keep diffs small and avoid committing large binary outputs.

---

## Getting Started

### Install pre-commit

```bash
pip install pre-commit
```

### Install the Git hooks

Run this once in the repo:

```bash
pre-commit install
```

This sets up Git to run the hooks automatically every time you run:

```bash
git commit
```

---

## Running Hooks Manually

Run hooks on all tracked files:

```bash
pre-commit run --all-files
```

Run a specific hook, e.g., Black:

```bash
pre-commit run black --all-files
```

---

## Tips for Development

* If a hook reformats files, the commit will stop — simply `git add` the changes and commit again.
* If a hook fails (e.g., flake8), fix the issues and re-run the commit.
* Hooks run only on staged files unless using `--all-files`.

---

## Updating Hooks

To update all hook versions to the newest supported releases:

```bash
pre-commit autoupdate
```

