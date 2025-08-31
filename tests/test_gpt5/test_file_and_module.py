import subprocess
import sys
from pathlib import Path

import pytest

from dashc.core import DashCException, b64z, render
from dashc.single_file import dashc as dashc_single
from dashc.single_module import COMPRESSION_MAP, _find_main_package, dashc_module, dir_to_zip_bytes
from dashc.validate_syntax import validate_bash_syntax


def test_single_file_dashc_plain_text_ok(tmp_path: Path):
    src = tmp_path / "hello.py"
    # Avoid single quotes to pass the current make_python_c restriction
    src.write_text('print("hello")\n', encoding="utf-8")
    cmd = dashc_single(src, plain_text=True, shebang=None)
    assert isinstance(cmd, str)
    assert cmd.startswith("python -c '")
    assert validate_bash_syntax(cmd) is True


def test_dir_to_zip_bytes_roundtrip(tmp_path: Path):
    d = tmp_path / "data"
    (d / "a").mkdir(parents=True)
    (d / "a" / "x.txt").write_text("X", encoding="utf-8")
    (d / "b").mkdir()
    (d / "b" / "y.txt").write_text("Y", encoding="utf-8")

    z = dir_to_zip_bytes(d, compression=COMPRESSION_MAP["deflated"], compresslevel=6)

    # Inspect it
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(z), "r") as zf:
        names = set(zf.namelist())
        assert "data/a/x.txt" in names
        assert "data/b/y.txt" in names
        assert zf.read("data/a/x.txt") == b"X"
        assert zf.read("data/b/y.txt") == b"Y"


def test__find_main_package_prefers_first_alphabetical(tmp_path: Path):
    src = tmp_path / "src"
    (src / "app").mkdir(parents=True)
    (src / "other").mkdir()

    (src / "app" / "__init__.py").write_text("", encoding="utf-8")
    (src / "app" / "__main__.py").write_text("print('app')", encoding="utf-8")

    (src / "other" / "__init__.py").write_text("", encoding="utf-8")
    (src / "other" / "__main__.py").write_text("print('other')", encoding="utf-8")

    # The helper returns the first candidate in sorted(dir list)
    entry = _find_main_package(src)
    assert entry in {"app", "other"}  # deterministic but allow either if FS ordering changes
    # In practice with sorted order, "app" should win:
    assert entry == "app"


def test_wrapper_zip_executes_via_render_and_payload(tmp_path: Path):
    # Build a package and execute it through the wrapper (run_module path)
    src = tmp_path / "p"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (src / "pkg" / "__main__.py").write_text("print('RUNZIP')", encoding="utf-8")

    zip_bytes = dir_to_zip_bytes(src)
    payload_b64 = b64z(zip_bytes)

    wrapper = render("wrapper_zip.py.j2", {"payload_b64": payload_b64, "run_module": "p.pkg"})
    script = tmp_path / "wrapper.py"
    script.write_text(wrapper, encoding="utf-8")

    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert proc.returncode == 0
    assert "RUNZIP" in proc.stdout


def test_dashc_module_returns_a_command_string(tmp_path: Path):
    src = tmp_path / "src"
    (src / "my_pkg").mkdir(parents=True)
    (src / "my_pkg" / "__init__.py").write_text("", encoding="utf-8")
    (src / "my_pkg" / "__main__.py").write_text("print('ok')", encoding="utf-8")

    cmd = dashc_module(src, entrypoint=None, shebang=None, zip_compression="deflated")
    assert isinstance(cmd, str)
    assert cmd.startswith("python -c '")
    # Should be valid bash syntax (shlex-level at minimum if bash missing)
    assert validate_bash_syntax(cmd) is True
