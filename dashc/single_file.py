from __future__ import annotations

from pathlib import Path

from dashc.core import compress_to_b64, make_python_c, render_wrapper, render_wrapper_plain


def dashc(
    source_path: Path,
    plain_text: bool = False,
    shebang: str | None = "/usr/bin/env bash",
) -> str:
    """
    Compiles a single Python file into a dash-c command or script.

    Args:
        source_path: The path to the Python source file.
        plain_text: If True, the output is human-readable and not compressed.
        shebang: The shebang line for the script (e.g., "/usr/bin/env bash").
                 If None, a single-line command is returned instead of a full script.
    """
    source_text = source_path.read_text(encoding="utf-8")

    if plain_text:
        code = render_wrapper_plain(source_text, source_path.name)
        return make_python_c(code, shebang=shebang)
    payload_b64 = compress_to_b64(source_text)
    code = render_wrapper(payload_b64, source_path.name)
    return make_python_c(code, shebang=shebang)
