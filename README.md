# dashc

Tool to generate `python -c` bash scripts as if they were a package format.

[![tests](https://github.com/matthewdeanmartin/dashc/actions/workflows/build.yml/badge.svg)
](https://github.com/matthewdeanmartin/dashc/actions/workflows/tests.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/matthewdeanmartin/dashc/main.svg)
](https://results.pre-commit.ci/latest/github/matthewdeanmartin/dashc/main)
[![Downloads](https://img.shields.io/pypi/dm/dashc)](https://pypistats.org/packages/dashc)
[![Python Version](https://img.shields.io/pypi/pyversions/dashc)
![Release](https://img.shields.io/pypi/v/dashc)
](https://pypi.org/project/dashc/)

---

## About

`dashc` lets you bundle Python source code (a single file or an entire package) into an executable shell script.
Instead of shipping loose files, you can hand over a bash command (or `.sh` script) that self-contains your Python logic
and runs without needing to touch the filesystem.

Features:

* **Single file mode** – wrap a single `.py` into a compressed string or plain text.
* **Module mode** – zip up a package with `__main__.py` or a specified `module:function` entrypoint.
* **Bash-friendly** – outputs either a plain (`python -c '...'`) or a script with a shebang.
* **Validates syntax** – checks both Python and Bash syntax before generating.

---

## Installation

It is recommended to install with [pipx](https://pypa.github.io/pipx/):

```bash
pipx install dashc
```

This keeps `dashc` isolated in its own environment while making the CLI available globally.

---

## Usage

Run with:

```bash
dashc [--version] [--verbose|--quiet|--dry-run] <command> [options]
```

Global options:

* `--version` – show version
* `--verbose` – debug logging
* `--quiet` – suppress logs except errors
* `--dry-run` – simulate actions without writing files

### Commands

* `file` – Compile a single `.py` into a script.
* `module` – Package a directory and run `__main__.py` or a chosen entrypoint.

---

## Example

**Single file to script:**

```bash
dashc file send_email.py --out run_send_email.sh
./run_send_email.sh --to test@example.com
```

**Single file to script:**

```bash
dashc file send_email.py --one-line
# -> prints a bash command like: python -c '...'
```

**Module with `__main__.py`:**

```bash
dashc module ./send_email --out run_pkg.sh
./run_pkg.sh --config config.yaml
```

**Module with function entrypoint:**

```bash
dashc module ./send_email --entrypoint send_email.cli:main --out run_cli.sh
./run_cli.sh --to test@example.com
```

---

## Prior Art / Alternatives

* **zipapp** (`python -m zipapp`) – Standard library tool for packaging Python code into `.pyz` archives runnable with
  Python.
* **shiv**, **pex** – Build self-contained Python executables with full dependency resolution.
* **pyinstaller** – Freezes Python programs into standalone executables.

## Project Links

- [GitHub](https://github.com/matthewdeanmartin/dashc)
- [PyPI](https://pypi.org/project/dashc/)
- [Bug Tracker](https://github.com/matthewdeanmartin/dashc/issues)
- [Change Log](https://github.com/matthewdeanmartin/dashc/blob/main/CHANGELOG.md)
