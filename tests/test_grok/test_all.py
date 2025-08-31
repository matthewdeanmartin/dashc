import base64
import io
import json
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

import jinja2
import pytest
from jinja2 import TemplateSyntaxError

from dashc.core import (
    b64z,
    compress_to_b64,
    make_python_c,
    render,
    render_wrapper,
    render_wrapper_plain,
    render_wrapper_zip,
)
from dashc.custom_exceptions import DashCException
from dashc.single_file import dashc
from dashc.single_module import _find_main_package, dashc_module, dir_to_zip_bytes
from dashc.validate_syntax import validate_bash_syntax, validate_python_syntax


@pytest.fixture
def sample_python_code():
    return 'print("Hello, world!")'


@pytest.fixture
def sample_python_file(tmp_path, sample_python_code):
    file_path = tmp_path / "sample.py"
    file_path.write_text(sample_python_code, encoding="utf-8")
    return file_path


@pytest.fixture
def sample_module_dir(tmp_path):
    module_dir = tmp_path / "my_module"
    module_dir.mkdir()
    init_file = module_dir / "__init__.py"
    init_file.write_text("", encoding="utf-8")
    main_file = module_dir / "__main__.py"
    main_file.write_text('print("Running module")', encoding="utf-8")
    return module_dir


# Tests for core.py


def test_compress_to_b64():
    source = "test string"
    b64 = compress_to_b64(source)
    assert isinstance(b64, str)
    decoded = base64.b64decode(b64)
    decompressed = zlib.decompress(decoded)
    assert decompressed.decode("utf-8") == source


def test_compress_to_b64_empty():
    source = ""
    b64 = compress_to_b64(source)
    decoded = base64.b64decode(b64)
    decompressed = zlib.decompress(decoded)
    assert decompressed.decode("utf-8") == ""


def test_b64z():
    data = b"test bytes"
    b64 = b64z(data)
    assert isinstance(b64, str)
    decoded = base64.b64decode(b64)
    decompressed = zlib.decompress(decoded)
    assert decompressed == data


def test_b64z_empty():
    data = b""
    b64 = b64z(data)
    decoded = base64.b64decode(b64)
    decompressed = zlib.decompress(decoded)
    assert decompressed == b""


def test_make_python_c_simple():
    code = "print(42)"
    result = make_python_c(code)
    assert result == "python -c 'print(42)' $@"


def test_make_python_c_with_shebang():
    code = "print(42)"
    result = make_python_c(code, shebang="/usr/bin/env bash")
    assert result == "#!/usr/bin/env bash\npython -c 'print(42)' $@\n"


def test_make_python_c_custom_python_exe():
    code = "print(42)"
    result = make_python_c(code, python_exe="python3")
    assert result == "python3 -c 'print(42)' $@"


def test_make_python_c_invalid_python():
    code = "print(42"  # syntax error
    with pytest.raises(DashCException, match="Python is not syntactically valid"):
        make_python_c(code)


def test_render_valid_template():
    # Test a simple template from the package
    # Assuming wrapper_plain.py.j2 exists, render with data
    data = {"escaped_source_code": json.dumps("print(42)"), "virtual_filename": "test.py"}
    result = render("wrapper_plain.py.j2", data)
    assert "__name__" in result
    assert "test.py" in result


def test_render_invalid_template():
    with pytest.raises(jinja2.exceptions.TemplateNotFound):
        render("non_existent_template.j2", {})


def test_render_wrapper_zip():
    payload_b64 = "testb64"
    root_pkg = "my_pkg"
    result = render_wrapper_zip(payload_b64, root_pkg)
    assert "import base64, io, importlib.abc" in result
    assert "testb64" in result


def test_render_wrapper():
    payload_b64 = "testb64"
    virtual_filename = "test.py"
    result = render_wrapper(payload_b64, virtual_filename)
    assert "import base64, zlib" in result
    assert "testb64" in result
    assert "test.py" in result


def test_render_wrapper_plain():
    source_code = "print(42)"
    virtual_filename = "test.py"
    result = render_wrapper_plain(source_code, virtual_filename)
    assert "print(42)" in result
    assert "test.py" in result


def test_render_wrapper_plain_invalid_python():
    source_code = "print(42"  # invalid
    with pytest.raises(DashCException, match="Python is not syntactically valid"):
        render_wrapper_plain(source_code, "test.py")


# Tests for custom_exceptions.py
def test_dashc_exception():
    with pytest.raises(DashCException, match="test message"):
        raise DashCException("test message")


# Tests for single_file.py


def test_dashc_plain_text(sample_python_file):
    result = dashc(sample_python_file, plain_text=True)
    assert result.startswith("#!/usr/bin/env bash")
    assert "python -c" in result
    # Should contain the original code escaped
    assert "Hello, world!" in result
    # Execute
    # process = subprocess.run(result, shell=True, capture_output=True, text=True)
    # assert process.returncode == 0
    # assert "Hello, world!" in process.stdout


def test_dashc_no_shebang(sample_python_file):
    result = dashc(sample_python_file, shebang=None)
    assert not result.startswith("#!")
    assert result.startswith("python -c")


# Tests for single_module.py


def test_dir_to_zip_bytes(sample_module_dir):
    zip_bytes = dir_to_zip_bytes(sample_module_dir)
    assert isinstance(zip_bytes, bytes)
    # Unzip and check contents
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        files = zf.namelist()
        assert "my_module/__init__.py" in files
        assert "my_module/__main__.py" in files
        assert zf.read("my_module/__main__.py").decode("utf-8") == 'print("Running module")'


def test_dir_to_zip_bytes_different_compression(sample_module_dir):
    zip_bytes = dir_to_zip_bytes(sample_module_dir, compression=zipfile.ZIP_STORED)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert zf.infolist()[0].compress_type == zipfile.ZIP_STORED


def test__find_main_package(sample_module_dir):
    result = _find_main_package(sample_module_dir.parent)  # src_dir is parent, module is my_module
    assert result == "my_module"


def test__find_main_package_multiple(capfd, tmp_path):
    # Create two packages
    pkg1 = tmp_path / "pkg1"
    pkg1.mkdir()
    (pkg1 / "__main__.py").write_text("", encoding="utf-8")
    pkg2 = tmp_path / "pkg2"
    pkg2.mkdir()
    (pkg2 / "__main__.py").write_text("", encoding="utf-8")
    result = _find_main_package(tmp_path)
    captured = capfd.readouterr()
    assert "Multiple packages" in captured.out
    assert result == "pkg1"  # sorted alphabetically


def test__find_main_package_none(tmp_path):
    with pytest.raises(RuntimeError, match="No package with __main__.py found"):
        _find_main_package(tmp_path)


def test_dashc_module_auto_entrypoint(sample_module_dir, capfd):
    result = dashc_module(sample_module_dir.parent, entrypoint=None)  # src_dir parent
    captured = capfd.readouterr()
    assert "auto-detected 'my_module'" in captured.out
    assert result.startswith("#!/usr/bin/env bash")
    assert "python -c" in result


def test_dashc_module_invalid_compression(sample_module_dir):
    with pytest.raises(ValueError, match="Unknown zip_compression"):
        dashc_module(sample_module_dir.parent, zip_compression="invalid")


# Tests for validate_syntax.py


def test_validate_python_syntax_valid():
    assert validate_python_syntax("print(42)")


def test_validate_python_syntax_invalid():
    assert not validate_python_syntax("print(42")


def test_validate_bash_syntax_valid():
    assert validate_bash_syntax("echo hello")


def test_validate_bash_syntax_invalid():
    assert not validate_bash_syntax("echo 'hello")  # unmatched quote


# Regarding bugs:
# - In plain_text mode for single_file.dashc, if the source code contains single quotes, the generated bash is invalid and raises DashCException as expected (limitation, not bug).
# - In core.render_wrapper_zip, it assumes the template uses 'run_module': root_pkg, which it does via template_data["run_module"] = entrypoint in single_module, but in core it's root_pkg, which is entrypoint.
# - In wrapper_zip template, func() is called without arguments; assumes the function parses sys.argv itself, which is common for CLI entrypoints.
# - No obvious crashing bugs found, but potential limitation in plain mode with single quotes as noted.
# - In _find_main_package, sorting is on Path objects, which sort lexicographically on their str representation.
# - Templates avoid single quotes in compressed modes, good.
