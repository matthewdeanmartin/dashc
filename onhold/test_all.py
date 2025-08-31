"""
Unit tests for the improved make_dash_c module.
"""

import pathlib
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Assuming the main module is imported as make_dash_c
from dashc.core import (
    CompressionMode,
    InputSource,
    _escape_for_shell,
    _get_runner_template,
    _serialize_data,
    package_to_dash_c,
)


class TestEscapeForShell:
    """Test the shell escaping functionality."""

    def test_escape_basic_string(self):
        """Test escaping a basic string."""
        result = _escape_for_shell("hello world")
        assert result == "hello world"

    def test_escape_quotes(self):
        """Test escaping double quotes."""
        result = _escape_for_shell('say "hello"')
        assert result == 'say \\"hello\\"'

    def test_escape_backslashes(self):
        """Test escaping backslashes."""
        result = _escape_for_shell("path\\to\\file")
        assert result == "path\\\\to\\\\file"

    def test_escape_newlines(self):
        """Test escaping newlines and other whitespace."""
        result = _escape_for_shell("line1\nline2\r\nline3\ttabbed")
        assert result == "line1\\nline2\\r\\nline3\\ttabbed"

    def test_escape_complex_string(self):
        """Test escaping a complex string with multiple special characters."""
        complex_str = 'print("Hello\nWorld\\test")\r\n\tindented'
        result = _escape_for_shell(complex_str)
        expected = 'print(\\"Hello\\nWorld\\\\test\\")\\r\\n\\tindented'
        assert result == expected


class TestInputSource:
    """Test the InputSource class functionality."""

    def test_string_input(self):
        """Test InputSource with string input."""
        code = "print('hello world')"
        source = InputSource(code, "test_module")
        modules = source.collect_modules()

        assert modules == {"__main__": code}

    def test_single_file_input(self):
        """Test InputSource with single file input."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("print('test file')")
            f.flush()

            source = InputSource(pathlib.Path(f.name), "test_module")
            modules = source.collect_modules()

            expected_name = pathlib.Path(f.name).stem
            assert expected_name in modules
            assert modules[expected_name] == "print('test file')"

    def test_directory_input(self):
        """Test InputSource with directory input."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = pathlib.Path(tmpdir) / "test_package"
            test_dir.mkdir()

            # Create __init__.py
            (test_dir / "__init__.py").write_text("# package init")

            # Create main.py
            (test_dir / "main.py").write_text("def main(): pass")

            # Create subdirectory with module
            subdir = test_dir / "subpackage"
            subdir.mkdir()
            (subdir / "__init__.py").write_text("# sub init")
            (subdir / "utils.py").write_text("def utility(): pass")

            source = InputSource(test_dir, "test_package.main")
            modules = source.collect_modules()

            expected_modules = {
                "__main__": "# package init",
                "main": "def main(): pass",
                "subpackage": "# sub init",
                "subpackage.utils": "def utility(): pass"
            }

            assert modules == expected_modules

    def test_invalid_source(self):
        """Test InputSource with invalid source."""
        with pytest.raises(ValueError, match="Invalid source"):
            source = InputSource(pathlib.Path("/nonexistent/path"), "test")
            source.collect_modules()


class TestSerializeData:
    """Test data serialization functionality."""

    def test_serialize_simple_data(self):
        """Test serializing simple data."""
        data = {"module1": "code1", "module2": "code2"}
        result = _serialize_data(data)

        assert isinstance(result, bytes)
        # Should be valid JSON when decoded
        import json
        decoded = json.loads(result.decode('utf-8'))
        assert decoded == data

    @patch('dashc.make_dash_c._HAS_ORJSON', True)
    @patch('dashc.make_dash_c.json')
    def test_serialize_with_orjson(self, mock_orjson):
        """Test serialization uses orjson when available."""
        mock_orjson.dumps.return_value = b'{"test": "data"}'

        data = {"test": "data"}
        result = _serialize_data(data)

        mock_orjson.dumps.assert_called_once_with(data)
        assert result == b'{"test": "data"}'


class TestPackageToDashC:
    """Test the main package_to_dash_c functionality."""

    def test_basic_functionality(self):
        """Test basic package creation."""
        code = "def main(): print('hello'); return 0"
        result = package_to_dash_c(code, "test_module")

        assert result.startswith('python -c "')
        assert result.endswith('"')
        assert "test_module" in result

    def test_compression_modes(self):
        """Test different compression modes."""
        code = "def main(): print('hello'); return 0"

        compressed = package_to_dash_c(
            code, "test", CompressionMode.COMPRESSED
        )
        uncompressed = package_to_dash_c(
            code, "test", CompressionMode.UNCOMPRESSED
        )

        # Compressed should contain base64 and gzip references
        assert "base64" in compressed
        assert "gzip" in compressed

        # Uncompressed should not
        assert "base64" not in uncompressed or "gzip" not in uncompressed

    def test_readonly_filesystem_option(self):
        """Test readonly filesystem optimization."""
        code = "def main(): pass"

        readonly_cmd = package_to_dash_c(
            code, "test", readonly_filesystem=True
        )
        normal_cmd = package_to_dash_c(
            code, "test", readonly_filesystem=False
        )

        # Readonly version should include optimize=2
        assert "optimize=2" in readonly_cmd
        assert "optimize=2" not in normal_cmd

    def test_invalid_entry_module(self):
        """Test validation of entry_module parameter."""
        code = "def main(): pass"

        with pytest.raises(ValueError, match="entry_module must be a non-empty string"):
            package_to_dash_c(code, "")

        with pytest.raises(ValueError, match="entry_module must be a non-empty string"):
            package_to_dash_c(code, None)

    def test_empty_sources(self):
        """Test handling of empty source directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = pathlib.Path(tmpdir) / "empty"
            empty_dir.mkdir()

            with pytest.raises(ValueError, match="No Python modules found"):
                package_to_dash_c(empty_dir, "test")

    def test_directory_package(self):
        """Test packaging a directory with multiple modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            package_dir = pathlib.Path(tmpdir) / "mypackage"
            package_dir.mkdir()

            (package_dir / "__init__.py").write_text("# init")
            (package_dir / "main.py").write_text("def main(): return 0")
            (package_dir / "utils.py").write_text("def helper(): pass")

            result = package_to_dash_c(package_dir, "mypackage.main")

            assert "mypackage.main" in result
            assert isinstance(result, str)
            assert result.startswith('python -c "')


class TestTemplateGeneration:
    """Test template generation functionality."""

    def test_get_runner_template(self):
        """Test runner template generation."""
        template = _get_runner_template()

        assert isinstance(template, str)
        assert "_DictLoader" in template
        assert "find_spec" in template
        assert "exec_module" in template
        assert "entry_module" in template
        # Should contain Jinja2 template syntax
        assert "{{" in template and "}}" in template

    @patch('dashc.make_dash_c._HAS_JINJA2', False)
    def test_fallback_without_jinja2(self):
        """Test that the code works without Jinja2."""
        code = "def main(): print('test'); return 0"

        # This should not raise an exception
        result = package_to_dash_c(code, "test")
        assert isinstance(result, str)
        assert result.startswith('python -c "')


class TestIntegration:
    """Integration tests that actually execute the generated commands."""


    def test_simple_execution(self):
        """Test that a simple generated command actually works."""
        code = '''
def main():
    print("Integration test successful")
    exit(42)
'''

        cmd = package_to_dash_c(code, "__main__")

        # Extract just the python command part
        python_cmd = cmd.replace('python -c "', '').rstrip('"')
        python_cmd = python_cmd.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

        # Execute the command
        # try:
        result = subprocess.run(
            [sys.executable, "-c", python_cmd],
            capture_output=True,
            text=True,
            timeout=10
        )

        assert result.returncode == 42
        assert "Integration test successful" in result.stdout
        # except subprocess.TimeoutExpired:
        #     pytest.skip("Execution timeout - may indicate environment issues")
        # except Exception as e:
        #     pytest.skip(f"Execution failed - may indicate environment issues: {e}")


    def test_package_execution(self):
        """Test that a multi-module package works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = pathlib.Path(tmpdir) / "testpkg"
            pkg_dir.mkdir()

            (pkg_dir / "__init__.py").write_text("version = '1.0'")
            (pkg_dir / "main.py").write_text('''
from . import version
def main():
    print(f"Package version: {version}")
    exit(0)
''')

            cmd = package_to_dash_c(pkg_dir, "testpkg.main")
            python_cmd = cmd.replace('python -c "', '').rstrip('"')
            python_cmd = python_cmd.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

            result = subprocess.run(
                [sys.executable, "-c", python_cmd],
                capture_output=True,
                text=True,
                timeout=10
            )

            assert result.returncode == 0
            assert "Package version: 1.0" in result.stdout



# if __name__ == "__main__":
#     pytest.main([__file__, "-v"])