import base64
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

from dashc.core import (
    DashCException,
    b64z,
    compress_to_b64,
    make_python_c,
    render,
    render_wrapper,
    render_wrapper_plain,
)
from dashc.validate_syntax import validate_bash_syntax


def run_py_code_as_file(py_src: str, tmp_path: Path):
    script = tmp_path / "script.py"
    script.write_text(py_src, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_compress_to_b64_roundtrip_text():
    text = "hello 🌊\nline2"
    b64 = compress_to_b64(text)
    out = zlib.decompress(base64.b64decode(b64)).decode("utf-8")
    assert out == text


def test_b64z_roundtrip_bytes():
    data = b"\x00\x01\x02 hello \xff\xfe"
    b64 = b64z(data)
    out = zlib.decompress(base64.b64decode(b64))
    assert out == data


def test_render_wrapper_exec_and_virtual_filename(tmp_path: Path):
    # Payload: when executed, prints the virtual filename and a result
    source = 'print("OK"); import sys; print(__file__)'
    payload_b64 = compress_to_b64(source)
    wrapper = render_wrapper(payload_b64, "hello.py")

    rc, out, err = run_py_code_as_file(wrapper, tmp_path)
    assert rc == 0
    lines = [ln.strip() for ln in out.splitlines()]
    assert "OK" in lines
    # Ensure the wrapper sets __file__ to the virtual name we passed in
    assert "hello.py" in lines


def test_render_wrapper_plain_exec(tmp_path: Path):
    # Use only double-quotes so we avoid the single-quote restriction in make_python_c
    src = 'x = 1 + 1\nprint("P:", x)'
    wrapper = render_wrapper_plain(src, "plain.py")
    rc, out, err = run_py_code_as_file(wrapper, tmp_path)
    assert rc == 0
    assert "P: 2" in out


def test_make_python_c_rejects_invalid_python():
    with pytest.raises(DashCException):
        make_python_c("def :\n  pass", python_exe="python", shebang=None)


def test_make_python_c_single_line_command_syntax_is_ok_for_bash(tmp_path: Path):
    code = "x=1\n"
    cmd = make_python_c(code, python_exe="python", shebang=None)
    # We don't execute shell here; just make sure it's plausibly valid bash
    assert validate_bash_syntax(cmd) is True
    assert cmd.startswith("python -c '")


def test_render_wrapper_zip_run_module_exec(tmp_path: Path):
    # Build a tiny package with __main__.py and a submodule
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "util.py").write_text("def add(a,b): return a+b\n", encoding="utf-8")
    (pkg / "__main__.py").write_text("from .util import add\nprint('Z', add(2,3))\n", encoding="utf-8")

    # Create zip payload (zip bytes -> b64(zlib(...)))
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in pkg.parent.rglob("*"):
            if p.is_file():
                arc = p.relative_to(pkg.parent).as_posix()
                zf.writestr(arc, p.read_bytes())
    payload_b64 = b64z(buf.getvalue())

    wrapper = render("wrapper_zip.py.j2", {"payload_b64": payload_b64, "run_module": "pkg"})
    rc, out, err = run_py_code_as_file(wrapper, tmp_path)
    assert rc == 0
    assert "Z 5" in out


def test_render_wrapper_zip_import_module_call_function(tmp_path: Path):
    # Build a module with a callable entrypoint
    root = tmp_path / "src"
    (root / "mod").mkdir(parents=True)
    (root / "mod" / "__init__.py").write_text("", encoding="utf-8")
    (root / "mod" / "cli.py").write_text("def main():\n    print('CLI OK')\n    return 0\n", encoding="utf-8")

    # zip payload
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in root.rglob("*"):
            if p.is_file():
                arc = p.relative_to(root).as_posix()
                zf.writestr(arc, p.read_bytes())
    payload_b64 = b64z(buf.getvalue())

    wrapper = render(
        "wrapper_zip.py.j2",
        {"payload_b64": payload_b64, "import_module": "mod.cli", "call_function": "main"},
    )
    rc, out, err = run_py_code_as_file(wrapper, tmp_path)
    assert rc == 0
    assert "CLI OK" in out
