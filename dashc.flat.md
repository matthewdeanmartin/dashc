# Contents of dashc source tree

## File: single_file.py

```python
from __future__ import annotations

import base64
import subprocess
import zlib
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def compress_to_b64(source: str) -> str:
    raw = source.encode("utf-8")
    comp = zlib.compress(raw, 9)
    return base64.b64encode(comp).decode("ascii")


def render_wrapper(payload_b64: str, virtual_filename: str) -> str:
    env = Environment(loader=FileSystemLoader("templates"))
    tmpl = env.get_template("wrapper.py.j2")
    return tmpl.render(payload_b64=payload_b64, virtual_filename=virtual_filename)


def dashc(source_path: Path) -> str:
    source_text = source_path.read_text(encoding="utf-8")
    payload_b64 = compress_to_b64(source_text)
    code = render_wrapper(payload_b64, source_path.name)
    return f"python -c '{code}'"

```

## File: single_module.py

```python
from __future__ import annotations

import base64
import io
import zipfile
import zlib
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def dir_to_zip_bytes(src_dir: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in src_dir.rglob("*"):
            if p.is_file():
                arcname = p.relative_to(src_dir).as_posix()
                zf.writestr(arcname, p.read_bytes())
    return buf.getvalue()


def choose_package_with_main(src_dir: Path) -> str:
    candidates: list[str] = []
    for pkg_dir in sorted([d for d in src_dir.rglob("*") if d.is_dir()]):
        main_py = pkg_dir / "__main__.py"
        if main_py.exists():
            rel = pkg_dir.relative_to(src_dir)
            candidates.append(".".join(rel.parts))
    if not candidates:
        raise RuntimeError("No package with __main__.py found under src_dir")
    return candidates[0]


def b64z(data: bytes) -> str:
    return base64.b64encode(zlib.compress(data, 9)).decode("ascii")


def render_wrapper_zip(template_dir: Path, payload_b64: str, root_pkg: str) -> str:
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    tmpl = env.get_template("wrapper_zip.py.j2")
    return tmpl.render(payload_b64=payload_b64, root_pkg=root_pkg)


def make_python_c(code: str, python_exe: str = "python") -> str:

    return f"{python_exe} -c '{code}'"

```

