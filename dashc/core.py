# File: dashc/core.py

from __future__ import annotations

import base64
import json
import zlib
from typing import Any

# 1. CHANGE: Import PackageLoader and select_autoescape
from jinja2 import Environment, PackageLoader, select_autoescape

from dashc.custom_exceptions import DashCException
from dashc.validate_syntax import validate_bash_syntax, validate_python_syntax


def compress_to_b64(source: str) -> str:
    raw = source.encode("utf-8")
    comp = zlib.compress(raw, 9)
    return base64.b64encode(comp).decode("ascii")


def b64z(data: bytes) -> str:
    return base64.b64encode(zlib.compress(data, 9)).decode("ascii")


def make_python_c(code: str, python_exe: str = "python", shebang: str | None = None) -> str:
    """
    Creates the final bash command or executable script.

    Args:
        code: The Python code to embed. Must not contain single quotes.
        python_exe: The python executable to use.
        shebang: If provided, creates a full script with this shebang line
                 (e.g., "/usr/bin/env bash"). If None, returns a single-line command.

    Returns:
        The bash command or script as a string.
    """
    if not validate_python_syntax(code):
        raise DashCException("Python is not syntactically valid")

    if shebang:
        # with the python process. '"$@"' passes all shell arguments to python.
        the_bash = f"""#!{shebang}
{python_exe} -c '{code}' $@
"""
    else:
        # Return the simple, single-line command
        the_bash = f"{python_exe} -c '{code}' $@"
    if not validate_bash_syntax(the_bash):
        print(the_bash)
        raise DashCException("Generated bash is not valid")
    return the_bash


# 2. REMOVE: These lines are no longer needed as we don't rely on the filesystem path
# _SCRIPT_DIR = Path(__file__).parent.resolve()
# _TEMPLATE_DIR = _SCRIPT_DIR / "templates"


def render(template_name: str, data: dict[str, Any]) -> str:
    # 3. CHANGE: Use PackageLoader.
    # It looks for a 'templates' folder inside the 'dashc' package.
    # autoescape is a good security practice.
    env = Environment(
        loader=PackageLoader("dashc", "templates"),
        autoescape=select_autoescape(),
    )
    tmpl = env.get_template(template_name)
    return tmpl.render(data)


def render_wrapper_zip(payload_b64: str, root_pkg: str) -> str:
    return render("wrapper_zip.py.j2", {"payload_b64": payload_b64, "root_pkg": root_pkg})


def render_wrapper(payload_b64: str, virtual_filename: str) -> str:
    return render("wrapper.py.j2", {"payload_b64": payload_b64, "virtual_filename": virtual_filename})


def render_wrapper_plain(source_code: str, virtual_filename: str) -> str:
    """Renders the plain text wrapper."""
    # Use json.dumps to safely escape the source code into a JSON string,
    # which is a valid Python string literal. This handles all quotes and
    # special characters correctly.
    if not validate_python_syntax(source_code):
        raise DashCException("Python is not syntactically valid")
    escaped_source = json.dumps(source_code)
    return render(
        "wrapper_plain.py.j2",
        {"escaped_source_code": escaped_source, "virtual_filename": virtual_filename},
    )
