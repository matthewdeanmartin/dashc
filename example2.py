import subprocess
import sys
from pathlib import Path

from dashc.core import b64z, make_python_c, render_wrapper_zip
from dashc.single_module import dir_to_zip_bytes

# -----------------------------
# Demo harness (no argparse yet)
# -----------------------------

def write_demo_package(root: Path) -> str:
    pkg = root / "demoapp"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (pkg / "__main__.py").write_text(
        """
print("Hello from demoapp.__main__!")
""".lstrip(),
        encoding="utf-8",
    )
    return "demoapp"


def build_dashc_zip(src_dir: Path, root_pkg: str) -> str:
    zip_bytes = dir_to_zip_bytes(src_dir)
    payload_b64 = b64z(zip_bytes)
    code = render_wrapper_zip(Path("templates"), payload_b64, root_pkg)
    return make_python_c(code)


def main():
    # Ensure the standalone Jinja template exists at templates/wrapper_zip.py.j2
    if not (Path("templates") / "wrapper_zip.py.j2").exists():
        raise SystemExit(
            "Missing template: templates/wrapper_zip.py.j2. Create it using the Jinja file provided below."
        )

    # Create a small demo package under demo_src/
    workspace = Path("demo_src")
    workspace.mkdir(exist_ok=True)
    root_pkg = write_demo_package(workspace)

    # Build the python -c command (multi-line OK)
    cmd = build_dashc_zip(workspace, root_pkg)

    # Write and run out.sh
    Path("out2.sh").write_text("#!/usr/bin/env bash\n" + cmd + "\n", encoding="utf-8")

    print("Running out.sh...\n")
    result = subprocess.run(["bash", "out2.sh"], capture_output=True, text=True, check=True)
    print("STDOUT:\n" + result.stdout)
    if result.stderr:
        print("STDERR:\n" + result.stderr, file=sys.stderr)


if __name__ == "__main__":
    main()
