## Tree for dashc
```
├── core.py
├── custom_exceptions.py
├── plain_text.py
├── single_file.py
├── single_module.py
├── templates/
│   ├── wrapper.py.j2
│   ├── wrapper_plain.py.j2
│   ├── wrapper_zip.py.j2
│   └── wrapper_zip_with_data.py.j2
├── validate_syntax.py
├── __about__.py
└── __main__.py
```

## File: core.py
```python
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
```
## File: custom_exceptions.py
```python
class DashCException(Exception):
    """Something went wrong generating a python -c file"""
```
## File: single_file.py
```python
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
```
## File: single_module.py
```python
# File: single_module.py

from __future__ import annotations

import io
import zipfile
from pathlib import Path

# Assuming dashc.core is in the python path or same directory
from dashc.core import b64z, make_python_c, render

# Map user-friendly strings to zipfile constants
COMPRESSION_MAP = {
    "stored": zipfile.ZIP_STORED,
    "deflated": zipfile.ZIP_DEFLATED,
    "bzip2": zipfile.ZIP_BZIP2,
    "lzma": zipfile.ZIP_LZMA,
}


def dir_to_zip_bytes(
    src_dir: Path,
    compression: int = zipfile.ZIP_DEFLATED,
    compresslevel: int | None = None,
) -> bytes:
    """Create a ZIP (bytes) of *src_dir contents* (recursive)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=compression, compresslevel=compresslevel) as zf:
        for p in src_dir.rglob("*"):
            if p.is_file():
                arcname = p.relative_to(src_dir).as_posix()
                zf.writestr(arcname, p.read_bytes())
    return buf.getvalue()


def _find_main_package(src_dir: Path) -> str:
    """Find a default package under src_dir containing __main__.py."""
    candidates: list[str] = []
    for pkg_dir in sorted([d for d in src_dir.rglob("*") if d.is_dir()]):
        if (pkg_dir / "__main__.py").exists():
            rel = pkg_dir.relative_to(src_dir)
            if not rel.parts:  # Top-level __main__.py
                candidates.append("__main__")
            else:
                candidates.append(".".join(rel.parts))

    if not candidates:
        raise RuntimeError("No package with __main__.py found to use as default entrypoint.")
    if len(candidates) > 1:
        print(
            f"Warning: Multiple packages with __main__.py found: {candidates}. "
            f"Using '{candidates[0]}'. Specify an entrypoint for clarity."
        )
    return candidates[0]


def dashc_module(
    src_dir: Path,
    entrypoint: str | None = None,
    shebang: str | None = "/usr/bin/env bash",
    zip_compression: str = "deflated",
    zip_compresslevel: int | None = None,
) -> str:
    """
    Packages a module into a single dash-c command or script.

    Args:
        src_dir: The source directory of the package.
        entrypoint: The entrypoint to run (e.g., "my_pkg" or "my_pkg.cli:main").
        shebang: The shebang line for the script (e.g., "/usr/bin/env bash").
                 If None, a single-line command is returned.
        zip_compression: The compression method for the zip archive.
                         Options: "stored", "deflated", "bzip2", "lzma".
        zip_compresslevel: The compression level (integer), depends on the method.
                           For "deflated", 0-9. For "bzip2", 1-9.
    """
    if not entrypoint:
        entrypoint = _find_main_package(src_dir)
        print(f"No entrypoint specified, auto-detected '{entrypoint}'")

    # Validate and map the compression string
    compression_method = COMPRESSION_MAP.get(zip_compression.lower())
    if compression_method is None:
        raise ValueError(
            f"Unknown zip_compression: '{zip_compression}'. " f"Valid options are: {list(COMPRESSION_MAP.keys())}"
        )

    zip_bytes = dir_to_zip_bytes(
        src_dir,
        compression=compression_method,
        compresslevel=zip_compresslevel,
    )
    payload_b64 = b64z(zip_bytes)

    template_data = {"payload_b64": payload_b64}

    if ":" in entrypoint:
        module_path, function_name = entrypoint.split(":", 1)
        template_data["import_module"] = module_path
        template_data["call_function"] = function_name
    else:
        template_data["run_module"] = entrypoint

    code = render("wrapper_zip.py.j2", template_data)
    return make_python_c(code, shebang=shebang)
```
## File: validate_syntax.py
```python
import ast
import shlex
import subprocess  # nosec


def validate_python_syntax(code: str) -> bool:
    """
    Validate that a string is syntactically valid Python code.

    Args:
        code: Python source code as a string.

    Returns:
        True if the code parses successfully, False otherwise.
    """
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def validate_bash_syntax(code: str) -> bool:
    """
    Validate that a string is syntactically valid Bash code.

    Tries `bash -n -c` if bash exists; if not available, falls back
    to using `shlex.split` for a minimal sanity check.

    Args:
        code: Bash script source code as a string.

    Returns:
        True if the code parses successfully, False otherwise.
    """
    try:
        # Try using bash to check syntax (-n means no execution)
        result = subprocess.run(  # nosec
            ["bash", "-n", "-c", code],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        # Fallback: check if code can be tokenized by shlex
        try:
            shlex.split(code)
            return True
        except ValueError:
            return False
```
## File: __about__.py
```python
"""Metadata for dashc."""

__all__ = ["__title__", "__version__", "__description__", "__requires_python__"]

__title__ = "dashc"
__version__ = "0.1.0"
__description__ = "Tool to generate python -c bash as if it were a package format."
__requires_python__ = ">=3.8"
```
## File: __main__.py
```python
print("sooon...")
```
## File: templates\wrapper.py.j2
```
import base64, zlib

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
## File: templates\wrapper_plain.py.j2
```
# The source code is embedded here as a string literal created by json.dumps()
_source = {{ escaped_source_code }}

_globals = {"__name__": "__main__", "__file__": "{{ virtual_filename }}"}

# Use compile so tracebacks point at the virtual filename and line numbers match.
exec(compile(_source, "{{ virtual_filename }}", "exec"), _globals, _globals)
```
## File: templates\wrapper_zip.py.j2
```
# Save this file as: templates/wrapper_zip.py.j2

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

    {% if run_module %}
    # Entrypoint Type 1: Run a module (like python -m {{ run_module }})
    # The __main__.py inside the package will be executed.
    runpy.run_module("{{ run_module }}", run_name="__main__", alter_sys=True)

    {% elif import_module and call_function %}
    # Entrypoint Type 2: Import a module and call a function
    try:
        module = importlib.import_module("{{ import_module }}")
        func = getattr(module, "{{ call_function }}")
    except (ImportError, AttributeError) as e:
        print(f"Error: Could not find entrypoint \"{{ call_function }}\" in \"{{ import_module }}\".", file=sys.stderr)
        print(f"Underlying error: {e}", file=sys.stderr)
        sys.exit(1)

    # Call the function and exit with its return code (if any)
    # This correctly handles functions that return an exit code or None.
    sys.exit(func())

    {% else %}
    # This block should not be reached if the generator logic is correct.
    print("Error: Invalid entrypoint configuration in generated script.", file=sys.stderr)
    sys.exit(1)
    {% endif %}


if __name__ == "__main__":
    _main()
```
## File: templates\wrapper_zip_with_data.py.j2
```
import base64, io, importlib, importlib.abc, importlib.machinery, runpy, sys, zipfile, zlib


def _inflate() -> bytes:
    b64 = """{{ payload_b64 }}"""
    return zlib.decompress(base64.b64decode(b64))


def _build_map(zbytes: bytes):
    zf = zipfile.ZipFile(io.BytesIO(zbytes))
    # Map of archive path -> file bytes
    return {info.filename: zf.read(info) for info in zf.infolist() if not info.is_dir()}


class _InMemZipLoader(importlib.abc.InspectLoader, importlib.abc.ResourceReader):
    """Loader that serves modules and resources out of an in-memory ZIP map.

    Implements InspectLoader for get_source/get_code.
    Implements ResourceReader for get_data to support importlib.resources.
    """

    def __init__(self, zmap, fullname, is_pkg, arc_path):
        self._zmap = zmap
        self._fullname = fullname
        self._is_pkg = is_pkg
        self._arc_path = arc_path  # virtual filename for tracebacks

    # ---- helpers ----
    def _source_bytes(self, fullname: str) -> bytes:
        mod_path = fullname.replace(".", "/")
        if fullname == self._fullname:
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

    def _get_package_root(self) -> str:
        """Determines the directory path for the package inside the archive."""
        if self._is_pkg:
            # For a package, the path is the directory containing its __init__.py
            # e.g., for arc_path "my_pkg/__init__.py", this returns "my_pkg"
            return self._arc_path.rpartition("/")[0]
        else:
            # For a module, it is the package it belongs to
            # e.g., for fullname "my_pkg.utils", this returns "my_pkg"
            return self._fullname.rpartition(".")[0].replace(".", "/")

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

    # ---- NEW: importlib.abc.ResourceReader API ----
    def open_resource(self, resource: str):
        """Return a file-like object for binary reading of the resource."""
        pkg_root = self._get_package_root()
        resource_path = f"{pkg_root}/{resource}" if pkg_root else resource
        if resource_path not in self._zmap:
            raise FileNotFoundError(f"Resource \"{resource}\" not found in package \"{self._fullname}\"")
        return io.BytesIO(self._zmap[resource_path])

    def resource_path(self, resource: str):
        """Return the path to the resource. Not possible for in-memory zips."""
        raise FileNotFoundError("In-memory zip resources have no file system path")

    def is_resource(self, name: str) -> bool:
        """Return True if the named file is a resource in the package."""
        pkg_root = self._get_package_root()
        resource_path = f"{pkg_root}/{name}" if pkg_root else name
        return resource_path in self._zmap

    def get_data(self, path: str) -> bytes:
        """Return the bytes for the resource specified by path."""
        # For zip archives, "path" is the full, archive-relative path.
        # importlib.resources handles constructing this path correctly for us.
        try:
            return self._zmap[path]
        except KeyError:
            raise OSError(f"Resource not found in in-memory zip: {path}")

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

    {% if run_module %}
    # Entrypoint Type 1: Run a module (like python -m {{ run_module }})
    # The __main__.py inside the package will be executed.
    runpy.run_module("{{ run_module }}", run_name="__main__", alter_sys=True)

    {% elif import_module and call_function %}
    # Entrypoint Type 2: Import a module and call a function
    try:
        module = importlib.import_module("{{ import_module }}")
        func = getattr(module, "{{ call_function }}")
    except (ImportError, AttributeError) as e:
        print(f"Error: Could not find entrypoint \"{{ call_function }}\" in \"{{ import_module }}\".", file=sys.stderr)
        print(f"Underlying error: {e}", file=sys.stderr)
        sys.exit(1)

    # Call the function and exit with its return code (if any)
    # This correctly handles functions that return an exit code or None.
    sys.exit(func())

    {% else %}
    # This block should not be reached if the generator logic is correct.
    print("Error: Invalid entrypoint configuration in generated script.", file=sys.stderr)
    sys.exit(1)
    {% endif %}


if __name__ == "__main__":
    _main()
```
