## Tree for dashc
```
├── core.py
├── single_file.py
├── single_module.py
└── templates/
    ├── wrapper.py.j2
    └── wrapper_zip.py.j2
```

## File: core.py
```python
import base64
import zlib
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader


def compress_to_b64(source: str) -> str:
    raw = source.encode("utf-8")
    comp = zlib.compress(raw, 9)
    return base64.b64encode(comp).decode("ascii")

def b64z(data: bytes) -> str:
    return base64.b64encode(zlib.compress(data, 9)).decode("ascii")


def make_python_c(code: str, python_exe: str = "python") -> str:
    # Outer uses single quotes; template must stick to double quotes only.
    return f"{python_exe} -c '{code}'"

# Get the directory containing the current script
_SCRIPT_DIR = Path(__file__).parent.resolve()
_TEMPLATE_DIR = _SCRIPT_DIR / "templates"

def render(template_name:str, data:dict[str,Any]) -> str:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    tmpl = env.get_template(template_name)
    return tmpl.render(data)

def render_wrapper_zip(payload_b64: str, root_pkg: str) -> str:
    return render("wrapper_zip.py.j2", {"payload_b64":payload_b64, "root_pkg":root_pkg})


def render_wrapper(payload_b64: str, virtual_filename: str) -> str:
    return render("wrapper.py.j2", {"payload_b64":payload_b64, "virtual_filename":virtual_filename})
```
## File: single_file.py
```python
from __future__ import annotations

from pathlib import Path

from dashc.core import compress_to_b64, make_python_c, render_wrapper


def dashc(source_path: Path) -> str:
    source_text = source_path.read_text(encoding="utf-8")
    payload_b64 = compress_to_b64(source_text)
    code = render_wrapper(payload_b64, source_path.name)
    return make_python_c(code)
```
## File: single_module.py
```python
from __future__ import annotations

import io
import zipfile
from pathlib import Path

def dir_to_zip_bytes(src_dir: Path) -> bytes:
    """Create a ZIP (bytes) of *src_dir contents* (recursive)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in src_dir.rglob("*"):
            if p.is_file():
                arcname = p.relative_to(src_dir).as_posix()
                zf.writestr(arcname, p.read_bytes())
    return buf.getvalue()


# BUG: this picks an entry point at random. Assumes multipe modules in package.
def choose_package_with_main(src_dir: Path) -> str:
    """Find a package under src_dir containing __main__.py and return its import name."""
    candidates: list[str] = []
    for pkg_dir in sorted([d for d in src_dir.rglob("*") if d.is_dir()]):
        main_py = pkg_dir / "__main__.py"
        if main_py.exists():
            rel = pkg_dir.relative_to(src_dir)
            candidates.append(".".join(rel.parts))
    if not candidates:
        raise RuntimeError("No package with __main__.py found under src_dir")
    return candidates[0]
```
## File: templates\wrapper.py.j2
```
# No single quotes anywhere in this template on purpose.
import base64, zlib, runpy, sys

def _decompress_b64_to_text(s):
    return zlib.decompress(base64.b64decode(s)).decode("utf-8")

# The payload is just base64 text. Triple-double-quoted to avoid single quotes entirely.
_PAYLOAD_B64 = """{{ payload_b64 }}"""

# Later: we can switch behavior here to import/run main from a module or package.
# For now: execute the decompressed source as __main__ with a nice filename for tracebacks.
_source = _decompress_b64_to_text(_PAYLOAD_B64)

_globals = {"__name__": "__main__", "__file__": "{{ virtual_filename }}"}
# Use compile so tracebacks point at the virtual filename and line numbers match post-decompression.
exec(compile(_source, "{{ virtual_filename }}", "exec"), _globals, _globals)
```
## File: templates\wrapper_zip.py.j2
```
# Save this file as: templates/wrapper_zip.py.j2
# NOTE: Use DOUBLE QUOTES ONLY in this template so the outer bash command can
# safely single-quote the entire -c payload without extra escaping.

import base64, io, importlib.abc, importlib.machinery, runpy, sys, zipfile, zlib


def _inflate() -> bytes:
    b64 = """{{ payload_b64 }}"""
    return zlib.decompress(base64.b64decode(b64))


def _build_map(zbytes: bytes):
    zf = zipfile.ZipFile(io.BytesIO(zbytes))
    # Map of archive path -> file bytes
    return {info.filename: zf.read(info) for info in zf.infolist() if not info.is_dir()}


class _InMemZipLoader(importlib.abc.Loader):
    """Loader that serves modules out of an in-memory ZIP map.

    Implements get_source/get_code so callers like runpy.run_module can
    request code objects directly. This avoids the AttributeError you saw.
    """

    def __init__(self, zmap, fullname, is_pkg, arc_path):
        self._zmap = zmap
        self._fullname = fullname
        self._is_pkg = is_pkg
        self._arc_path = arc_path  # virtual filename for tracebacks

    # ---- helpers ----
    def _source_bytes(self, fullname: str) -> bytes:
        mod_path = fullname.replace(".", "/")
        if fullname == self._fullname:  # fast path for our primary module
            arc_path = self._arc_path
        elif self._is_pkg and fullname.startswith(self._fullname + "."):
            # submodules imported during package exec
            # delegate discovery back through meta_path, not here
            raise ImportError("Delegated to finder for submodule")
        else:
            # Not our module instance
            raise ImportError(f"Loader does not handle {fullname}")
        data = self._zmap.get(arc_path)
        if data is None:
            raise ImportError(f"No source for {fullname}")
        return data

    # ---- importlib.abc.InspectLoader API ----
    def get_source(self, fullname: str):  # type: ignore[override]
        return self._source_bytes(fullname).decode("utf-8")

    def get_code(self, fullname: str):  # type: ignore[override]
        src = self.get_source(fullname)
        return compile(src, self._arc_path, "exec")

    # ---- importlib.abc.Loader API ----
    def create_module(self, spec):  # default module creation
        return None

    def exec_module(self, module):
        code = self.get_code(self._fullname)
        module.__file__ = self._arc_path
        module.__package__ = self._fullname if self._is_pkg else self._fullname.rpartition(".")[0]
        if self._is_pkg:
            module.__path__ = [self._fullname]
        exec(code, module.__dict__)


class _InMemZipFinder(importlib.abc.MetaPathFinder):
    def __init__(self, zmap):
        self._zmap = zmap
        pkgs = set()
        mods = set()
        for path in zmap:
            if path.endswith("/__init__.py"):
                pkgs.add(path[:-12])
            elif path.endswith(".py"):
                mods.add(path[:-3])
        self._packages = {p.replace("/", ".") for p in pkgs}
        self._modules = {m.replace("/", ".") for m in mods}

    def find_spec(self, fullname, path, target=None):
        is_pkg = fullname in self._packages
        is_mod = fullname in self._modules
        if not (is_pkg or is_mod):
            return None
        if is_pkg:
            arc_path = fullname.replace(".", "/") + "/__init__.py"
        else:
            arc_path = fullname.replace(".", "/") + ".py"
        loader = _InMemZipLoader(self._zmap, fullname, is_pkg, arc_path)
        spec = importlib.machinery.ModuleSpec(fullname, loader, is_package=is_pkg)
        spec.origin = arc_path
        if is_pkg:
            spec.submodule_search_locations = [fullname]
        return spec


def _main():
    zbytes = _inflate()
    zmap = _build_map(zbytes)
    finder = _InMemZipFinder(zmap)
    sys.meta_path.insert(0, finder)

    # Simulate: python -m {{ root_pkg }}
    runpy.run_module("{{ root_pkg }}.__main__", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    _main()
```
