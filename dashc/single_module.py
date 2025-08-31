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


def dir_to_zip_bytes(src_dir: Path, compression=zipfile.ZIP_DEFLATED, compresslevel=None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compression, compresslevel=compresslevel) as zf:
        for p in src_dir.rglob("*"):
            if p.is_file():
                # Prefix with the directory name (so "mypkg/cli.py" etc.)
                arcname = Path(src_dir.name) / p.relative_to(src_dir)
                zf.writestr(arcname.as_posix(), p.read_bytes())
    return buf.getvalue()


# def dir_to_zip_bytes(
#     src_dir: Path,
#     compression: int = zipfile.ZIP_DEFLATED,
#     compresslevel: int | None = None,
# ) -> bytes:
#     """Create a ZIP (bytes) of *src_dir contents* (recursive)."""
#     buf = io.BytesIO()
#     with zipfile.ZipFile(buf, mode="w", compression=compression, compresslevel=compresslevel) as zf:
#         for p in src_dir.rglob("*"):
#             if p.is_file():
#                 arcname = p.relative_to(src_dir).as_posix()
#                 zf.writestr(arcname, p.read_bytes())
#     return buf.getvalue()


def _find_main_package(src_dir: Path) -> str:
    """Find a default package under src_dir containing __main__.py."""
    candidates: list[str] = []
    # If src_dir itself is the package root, prefer it
    if (src_dir / "__init__.py").exists() and (src_dir / "__main__.py").exists():
        return src_dir.name  # e.g., "mypkg"

    for pkg_dir in sorted([d for d in src_dir.rglob("*") if d.is_dir()]):
        if (pkg_dir / "__main__.py").exists():
            rel = pkg_dir.relative_to(src_dir)
            if not rel.parts:  # Top-level __main__.py
                candidates.append("__main__")
            else:
                candidates.append(".".join(rel.parts))

    if not candidates and src_dir.is_dir():
        # uh oh. This is probably is the module, not the parent of the module.
        pkg_dir = src_dir
        if (pkg_dir / "__main__.py").exists():
            print(f"Found backup : {(pkg_dir / '__main__.py')}")
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
