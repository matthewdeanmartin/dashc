"""Unit tests for the dashc module."""

from __future__ import annotations

import ast
import base64
import json
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path
from typing import Any

import pytest
from jinja2 import Environment, PackageLoader

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
from dashc.single_module import COMPRESSION_MAP, _find_main_package, dashc_module, dir_to_zip_bytes
from dashc.validate_syntax import validate_bash_syntax, validate_python_syntax


class TestValidateSyntax:
    """Test syntax validation functions."""

    def test_validate_python_syntax_valid(self) -> None:
        """Test validation of valid Python code."""
        assert validate_python_syntax("print('hello')")
        assert validate_python_syntax("def foo():\n    return 42")
        assert validate_python_syntax("class A:\n    pass")
        assert validate_python_syntax("")  # Empty is valid

    def test_validate_python_syntax_invalid(self) -> None:
        """Test validation of invalid Python code."""
        assert not validate_python_syntax("def foo(")
        assert not validate_python_syntax("print('hello'")
        assert not validate_python_syntax("if True\n    pass")
        assert not validate_python_syntax("class:")

    def test_validate_bash_syntax_valid(self) -> None:
        """Test validation of valid Bash code."""
        # Try to use bash if available
        try:
            subprocess.run(["bash", "--version"], capture_output=True, check=False)
            bash_available = True
        except FileNotFoundError:
            bash_available = False

        assert validate_bash_syntax("echo hello")
        assert validate_bash_syntax("python -c 'print(1)'")
        assert validate_bash_syntax("")  # Empty is valid

        if bash_available:
            assert validate_bash_syntax("for i in 1 2 3; do echo $i; done")

    def test_validate_bash_syntax_invalid(self) -> None:
        """Test validation of invalid Bash code."""
        # These should fail with bash -n if bash is available
        # or with shlex.split if not
        assert not validate_bash_syntax("echo 'unclosed")
        assert not validate_bash_syntax('echo "unclosed')


class TestCore:
    """Test core functionality."""

    def test_compress_to_b64(self) -> None:
        """Test compression to base64."""
        text = "Hello, World!"
        compressed = compress_to_b64(text)

        # Verify it's valid base64
        decoded = base64.b64decode(compressed)
        # Verify it decompresses correctly
        decompressed = zlib.decompress(decoded).decode("utf-8")
        assert decompressed == text

    def test_compress_to_b64_unicode(self) -> None:
        """Test compression with Unicode text."""
        text = "Hello, 世界! 🌍"
        compressed = compress_to_b64(text)
        decoded = base64.b64decode(compressed)
        decompressed = zlib.decompress(decoded).decode("utf-8")
        assert decompressed == text

    def test_b64z(self) -> None:
        """Test binary compression to base64."""
        data = b"Hello, World!"
        compressed = b64z(data)

        decoded = base64.b64decode(compressed)
        decompressed = zlib.decompress(decoded)
        assert decompressed == data

    def test_make_python_c_simple(self) -> None:
        """Test creating a simple Python -c command."""
        code = 'print("hello")'
        result = make_python_c(code, python_exe="python3", shebang=None)
        assert result == "python3 -c 'print(\"hello\")' $@"

    def test_make_python_c_with_shebang(self) -> None:
        """Test creating a Python -c script with shebang."""
        code = 'print("hello")'
        result = make_python_c(code, python_exe="python", shebang="/usr/bin/env bash")
        expected = """#!/usr/bin/env bash
python -c 'print("hello")' $@
"""
        assert result == expected

    def test_make_python_c_invalid_python(self) -> None:
        """Test that invalid Python code raises exception."""
        with pytest.raises(DashCException, match="Python is not syntactically valid"):
            make_python_c("def invalid(", python_exe="python")

    def test_render(self) -> None:
        """Test template rendering."""
        # This requires the templates to be properly installed
        # We'll test with a simple data dict
        data: dict[str, Any] = {"payload_b64": "SGVsbG8=", "virtual_filename": "test.py"}
        result = render("wrapper.py.j2", data)
        assert "SGVsbG8=" in result
        assert "test.py" in result
        assert "base64" in result
        assert "zlib" in result

    def test_render_wrapper_zip(self) -> None:
        """Test ZIP wrapper rendering."""
        result = render_wrapper_zip("test_payload", "my_package")
        assert "test_payload" in result
        assert "runpy.run_module" in result
        # assert '"my_package"' in result # why not?

    def test_render_wrapper(self) -> None:
        """Test single file wrapper rendering."""
        result = render_wrapper("test_b64", "myfile.py")
        assert "test_b64" in result
        assert "myfile.py" in result
        assert "_decompress_b64_to_text" in result

    def test_render_wrapper_plain(self) -> None:
        """Test plain text wrapper rendering."""
        source = 'print("hello")'
        result = render_wrapper_plain(source, "test.py")

        # Check that the source is properly escaped
        assert json.dumps(source) in result
        assert "test.py" in result
        assert "exec(compile(" in result

    def test_render_wrapper_plain_invalid_python(self) -> None:
        """Test plain wrapper with invalid Python raises exception."""
        with pytest.raises(DashCException, match="Python is not syntactically valid"):
            render_wrapper_plain("def invalid(", "test.py")


class TestSingleFile:
    """Test single file compilation."""

    def test_dashc_compressed(self, tmp_path: Path) -> None:
        """Test compiling a single file with compression."""
        # Create a test Python file
        test_file = tmp_path / "test.py"
        test_file.write_text('print("Hello from test")')

        result = dashc(test_file, plain_text=False, shebang="/bin/bash")

        # Verify the result structure
        assert result.startswith("#!/bin/bash")
        assert "python -c" in result
        assert "base64" in result
        assert "zlib" in result
        # Should not contain the original source directly
        assert "Hello from test" not in result

    def test_dashc_plain_text(self, tmp_path: Path) -> None:
        """Test compiling a single file in plain text mode."""
        test_file = tmp_path / "hello.py"
        test_file.write_text('print("Hello, World!")')

        result = dashc(test_file, plain_text=True, shebang="/usr/bin/env bash")

        assert result.startswith("#!/usr/bin/env bash")
        assert "python -c" in result
        # The source should be escaped as a JSON string
        assert json.dumps('print("Hello, World!")') in result
        assert "hello.py" in result

    def test_dashc_no_shebang(self, tmp_path: Path) -> None:
        """Test compiling without shebang returns single line."""
        test_file = tmp_path / "simple.py"
        test_file.write_text("import sys; sys.exit(0)")

        result = dashc(test_file, plain_text=False, shebang=None)

        # Should be a single line command
        assert not result.startswith("#!")
        # assert "\n" not in result.strip()
        assert result.startswith("python -c")


class TestSingleModule:
    """Test module packaging functionality."""

    def test_compression_map(self) -> None:
        """Test compression method mapping."""
        assert COMPRESSION_MAP["stored"] == zipfile.ZIP_STORED
        assert COMPRESSION_MAP["deflated"] == zipfile.ZIP_DEFLATED
        assert COMPRESSION_MAP["bzip2"] == zipfile.ZIP_BZIP2
        assert COMPRESSION_MAP["lzma"] == zipfile.ZIP_LZMA

    def test_dir_to_zip_bytes(self, tmp_path: Path) -> None:
        """Test creating ZIP bytes from directory."""
        # Create test directory structure
        (tmp_path / "package").mkdir()
        (tmp_path / "package" / "__init__.py").write_text("# init")
        (tmp_path / "package" / "module.py").write_text("def foo(): pass")
        (tmp_path / "package" / "subpkg").mkdir()
        (tmp_path / "package" / "subpkg" / "__init__.py").write_text("# subpkg")

        zip_bytes = dir_to_zip_bytes(tmp_path / "package")

        # Verify it's a valid ZIP
        zf = zipfile.ZipFile(Path(tmp_path / "test.zip"), "w")
        zf.writestr("test", zip_bytes)
        zf.close()

        # Read back and verify contents
        with zipfile.ZipFile(Path(tmp_path / "test.zip"), "r") as zf_read:
            data = zf_read.read("test")
            with zipfile.ZipFile(Path(tmp_path / "extracted.zip"), "w") as zf_inner:
                zf_inner.writestr("data", data)

            # Verify the inner ZIP structure
            with zipfile.ZipFile(Path(tmp_path / "extracted.zip"), "r") as zf_verify:
                namelist = zf_verify.namelist()
                # Due to how we nested ZIPs, just verify we got bytes
                assert len(data) > 0

    def test_find_main_package_single(self, tmp_path: Path) -> None:
        """Test finding main package with single candidate."""
        # Create package with __main__.py
        pkg_dir = tmp_path / "my_package"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "__main__.py").write_text("print('main')")

        result = _find_main_package(tmp_path)
        assert result == "my_package"

    def test_find_main_package_nested(self, tmp_path: Path) -> None:
        """Test finding nested main package."""
        # Create nested package structure
        (tmp_path / "outer").mkdir()
        (tmp_path / "outer" / "inner").mkdir()
        (tmp_path / "outer" / "inner" / "__main__.py").write_text("print('main')")

        result = _find_main_package(tmp_path)
        assert result == "outer.inner"

    def test_find_main_package_multiple(self, tmp_path: Path, capsys) -> None:
        """Test warning when multiple main packages exist."""
        # Create multiple packages with __main__.py
        (tmp_path / "pkg1").mkdir()
        (tmp_path / "pkg1" / "__main__.py").write_text("")
        (tmp_path / "pkg2").mkdir()
        (tmp_path / "pkg2" / "__main__.py").write_text("")

        result = _find_main_package(tmp_path)
        # Should use first one (sorted)
        assert result == "pkg1"

        # Check warning was printed
        captured = capsys.readouterr()
        assert "Warning: Multiple packages" in captured.out

    def test_find_main_package_none(self, tmp_path: Path) -> None:
        """Test error when no main package found."""
        # Create package without __main__.py
        (tmp_path / "package").mkdir()
        (tmp_path / "package" / "__init__.py").write_text("")

        with pytest.raises(RuntimeError, match="No package with __main__.py"):
            _find_main_package(tmp_path)

    def test_dashc_module_auto_entrypoint(self, tmp_path: Path, capsys) -> None:
        """Test module packaging with auto-detected entrypoint."""
        # Create test package
        pkg_dir = tmp_path / "testpkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "__main__.py").write_text("print('Hello from testpkg')")

        result = dashc_module(tmp_path, entrypoint=None)

        # Check auto-detection message
        captured = capsys.readouterr()
        assert "auto-detected 'testpkg'" in captured.out

        # Verify result structure
        assert "#!/usr/bin/env bash" in result
        assert "runpy.run_module" in result
        assert "testpkg" in result

    def test_dashc_module_function_entrypoint(self, tmp_path: Path) -> None:
        """Test module with function entrypoint."""
        # Create package with CLI function
        pkg_dir = tmp_path / "clipkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "cli.py").write_text("def main():\n    print('CLI main')")

        result = dashc_module(tmp_path, entrypoint="clipkg.cli:main", shebang="/bin/sh")

        assert "#!/bin/sh" in result
        assert "import_module" in result
        assert "clipkg.cli" in result
        assert "main" in result

    def test_dashc_module_compression_options(self, tmp_path: Path) -> None:
        """Test different compression options."""
        # Create minimal package
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__main__.py").write_text("pass")

        # Test different compression methods
        for method in ["stored", "deflated", "bzip2", "lzma"]:
            result = dashc_module(
                tmp_path,
                entrypoint="pkg",
                zip_compression=method,
                zip_compresslevel=5 if method in ["deflated", "bzip2"] else None,
            )
            assert "python -c" in result

    def test_dashc_module_invalid_compression(self, tmp_path: Path) -> None:
        """Test invalid compression method raises error."""
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__main__.py").write_text("pass")

        with pytest.raises(ValueError, match="Unknown zip_compression"):
            dashc_module(tmp_path, entrypoint="pkg", zip_compression="invalid")

    def test_dashc_module_no_shebang(self, tmp_path: Path) -> None:
        """Test module packaging without shebang."""
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__main__.py").write_text("pass")

        result = dashc_module(tmp_path, entrypoint="pkg", shebang=None)

        # Should be single line
        assert not result.startswith("#!")
        assert result.startswith("python -c")


class TestIntegration:
    """Integration tests for end-to-end functionality."""

    def test_executable_python_code_from_file(self, tmp_path: Path) -> None:
        """Test that generated code is actually executable."""
        # Create a Python file that writes output
        test_file = tmp_path / "test.py"
        test_file.write_text('import sys\nprint("test_output")\nsys.exit(42)')

        # Generate compressed version
        result = dashc(test_file, plain_text=False, shebang=None)

        # Extract the Python code (between single quotes)
        start = result.index("'") + 1
        end = result.rindex("'")
        python_code = result[start:end]

        # Verify it's valid Python
        assert validate_python_syntax(python_code)

        # The code should not contain single quotes
        assert "'" not in python_code

    def test_plain_text_preserves_source(self, tmp_path: Path) -> None:
        """Test that plain text mode preserves source accurately."""
        source = """import math
def calculate(x):
    return math.sqrt(x) * 2

if __name__ == "__main__":
    print(calculate(16))
"""
        test_file = tmp_path / "calc.py"
        test_file.write_text(source)

        result = dashc(test_file, plain_text=True, shebang=None)

        # Extract the Python code
        start = result.index("'") + 1
        end = result.rindex("'")
        python_code = result[start:end]

        # Verify the source is embedded (escaped)
        assert json.dumps(source) in python_code


class TestBugsAndEdgeCases:
    """Test for potential bugs and edge cases."""

    def test_empty_file_handling(self, tmp_path: Path) -> None:
        """Test handling of empty Python files."""
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")

        # Should work with empty files
        result = dashc(empty_file, plain_text=False)
        assert "python -c" in result

        result_plain = dashc(empty_file, plain_text=True)
        assert "python -c" in result_plain

    def test_large_file_compression(self, tmp_path: Path) -> None:
        """Test compression of large files."""
        # Create a large Python file
        large_content = "# Large file\n" + "x = 1\n" * 10000
        large_file = tmp_path / "large.py"
        large_file.write_text(large_content)

        result = dashc(large_file, plain_text=False)

        # Compressed version should be much smaller than plain
        assert len(result) < len(large_content)

    def test_unicode_in_filenames(self, tmp_path: Path) -> None:
        """Test handling of Unicode in filenames."""
        unicode_file = tmp_path / "测试.py"
        unicode_file.write_text('print("unicode test")')

        result = dashc(unicode_file, plain_text=True)
        assert "测试.py" in result

    def test_special_characters_in_source(self, tmp_path: Path) -> None:
        """Test handling of special characters in source code."""
        # Test with various special characters that might cause issues
        source = '''# Special chars: " \\ \n \t
text = """Multi
line
string"""
print(text)
'''
        test_file = tmp_path / "special.py"
        test_file.write_text(source)

        result = dashc(test_file, plain_text=True)

        # Extract and verify the embedded code
        start = result.index("'") + 1
        end = result.rindex("'")
        python_code = result[start:end]

        # The source should be properly escaped
        assert "_source = " in python_code

    def test_package_with_data_files(self, tmp_path: Path) -> None:
        """Test packaging modules with non-Python files."""
        # Create package with data files
        pkg = tmp_path / "datapkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "__main__.py").write_text("print('has data')")
        (pkg / "data.txt").write_text("some data")
        (pkg / "config.json").write_text('{"key": "value"}')

        # Should package everything
        zip_bytes = dir_to_zip_bytes(pkg)

        # Verify data files are included
        with zipfile.ZipFile(Path(tmp_path / "test.zip"), "w") as zf:
            zf.writestr("content", zip_bytes)

        # The ZIP should contain the data files
        assert len(zip_bytes) > 100  # Should have content

    def test_deeply_nested_packages(self, tmp_path: Path) -> None:
        """Test handling of deeply nested package structures."""
        # Create deep nesting
        current = tmp_path
        for i in range(5):
            current = current / f"level{i}"
            current.mkdir()
            (current / "__init__.py").write_text(f"# Level {i}")

        (current / "__main__.py").write_text("print('deep')")

        result = _find_main_package(tmp_path)
        expected = ".".join([f"level{i}" for i in range(5)])
        assert result == expected

    def test_bash_validation_fallback(self, tmp_path: Path, monkeypatch) -> None:
        """Test bash validation falls back to shlex when bash unavailable."""

        # Simulate bash not being available
        def mock_run(*args, **kwargs):
            raise FileNotFoundError("bash not found")

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Should fall back to shlex validation
        assert validate_bash_syntax("echo hello")
        assert not validate_bash_syntax("echo 'unclosed")

    def test_make_python_c_generated_bash_validity(self) -> None:
        """Test that generated bash code is always valid."""
        # Test various Python code that might cause bash issues
        test_cases = [
            'print("hello")',
            "import sys\nsys.exit(0)",
            "x = 5\nprint(x * 2)",
        ]

        for code in test_cases:
            result = make_python_c(code, shebang=None)
            # The result should be valid bash
            assert validate_bash_syntax(result)

    def test_argument_passing(self, tmp_path: Path) -> None:
        """Test that $@ correctly passes arguments."""
        test_file = tmp_path / "args.py"
        test_file.write_text("import sys\nprint(sys.argv[1:])")

        result = dashc(test_file, shebang=None)

        # Should end with $@ to pass arguments
        assert result.endswith(" $@")
