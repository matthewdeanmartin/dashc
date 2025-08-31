# File: single_module.py

from __future__ import annotations

import io
import zipfile
from pathlib import Path

# Assuming dashc.core is in the python path or same directory
from dashc.core import b64z, make_python_c, render


def dir_to_zip_bytes(src_dir: Path) -> bytes:
    """Create a ZIP (bytes) of *src_dir contents* (recursive)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
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


def dashc_module(src_dir: Path, entrypoint: str | None = None) -> str:
    """
    Packages a module or package into a single dash-c command.

    Args:
        src_dir: The source directory of the package.
        entrypoint: The entrypoint to run.
                    - If None, searches for a package with __main__.py.
                    - If a string like "my_pkg", runs the package's __main__.py.
                    - If a string like "my_pkg.cli:main", imports the function and runs it.
    """
    if not entrypoint:
        # Fallback to auto-detection if no entrypoint is given
        entrypoint = _find_main_package(src_dir)
        print(f"No entrypoint specified, auto-detected '{entrypoint}'")

    zip_bytes = dir_to_zip_bytes(src_dir)
    payload_b64 = b64z(zip_bytes)

    template_data = {"payload_b64": payload_b64}

    # Parse the entrypoint and pass appropriate variables to the template
    if ":" in entrypoint:
        # Function entrypoint: "my_package.cli:main"
        module_path, function_name = entrypoint.split(":", 1)
        template_data["import_module"] = module_path
        template_data["call_function"] = function_name
    else:
        # Module entrypoint: "my_package"
        template_data["run_module"] = entrypoint

    # Use the generic render function
    code = render("wrapper_zip.py.j2", template_data)
    return make_python_c(code)