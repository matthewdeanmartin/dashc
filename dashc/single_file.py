from __future__ import annotations

from pathlib import Path

from dashc.core import compress_to_b64, make_python_c, render_wrapper


def dashc(source_path: Path) -> str:
    source_text = source_path.read_text(encoding="utf-8")
    payload_b64 = compress_to_b64(source_text)
    code = render_wrapper(payload_b64, source_path.name)
    return make_python_c(code)
