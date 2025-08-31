"""
Enhanced Python package to dash-c converter.

This module provides functionality to package Python modules into a single
python -c command for easy distribution and execution.

Requires Jinja2 for template rendering during generation.
The generated code has no external dependencies.
"""

from __future__ import annotations

import base64
import gzip
import json
import pathlib
import shlex
import textwrap
from enum import Enum
from typing import Dict, Union
import importlib.util
import sys

from jinja2 import Environment, FileSystemLoader, select_autoescape


class CompressionMode(Enum):
    """Compression options for the payload."""
    COMPRESSED = "compressed"
    UNCOMPRESSED = "uncompressed"


class InputSource:
    """Represents different types of input sources."""

    def __init__(self, source: Union[str, pathlib.Path], entry_module: str):
        self.source = source
        self.entry_module = entry_module

    def collect_modules(self) -> Dict[str, str]:
        """Collect Python modules from the input source."""
        if isinstance(self.source, str):
            # Treat as a single module string
            return {"__main__": self.source}

        source_path = pathlib.Path(self.source)

        if source_path.is_file() and source_path.suffix == ".py":
            # Single file
            code = source_path.read_text(encoding="utf-8")
            module_name = source_path.stem if source_path.stem != "__main__" else "__main__"
            return {module_name: code}

        if source_path.is_dir():
            # Directory/package
            return self._collect_from_directory(source_path)

        raise ValueError(f"Invalid source: {self.source}")

    def _collect_from_directory(self, root: pathlib.Path) -> Dict[str, str]:
        """Collect .py files from a directory as modules."""
        sources: Dict[str, str] = {}

        for path in root.rglob("*.py"):
            rel = path.relative_to(root).with_suffix("")  # strip .py
            parts = list(rel.parts)

            if parts[-1] == "__init__":
                parts = parts[:-1]

            mod = ".".join(parts) if parts else "__main__"
            code = path.read_text(encoding="utf-8")
            sources[mod] = code

        return sources


def _escape_for_shell(text: str) -> str:
    """
    Safely escape text for shell execution.

    Args:
        text: The text to escape

    Returns:
        Escaped text safe for shell execution
    """
    # Handle backslashes first, then other characters
    # Order matters here!
    escaped = text.replace("\\", "\\\\")  # Escape backslashes first
    escaped = escaped.replace('"', '\\"')  # Escape quotes
    escaped = escaped.replace("\n", "\\n")  # Escape newlines
    escaped = escaped.replace("\r", "\\r")  # Escape carriage returns
    escaped = escaped.replace("\t", "\\t")  # Escape tabs
    escaped = escaped.replace("!", "\\!")  # Escape bash history expansion
    escaped = escaped.replace("$", "\\$")  # Escape variable expansion
    escaped = escaped.replace("`", "\\`")  # Escape command substitution
    return escaped


def _get_template_environment(template_dir: pathlib.Path) -> Environment:
    """Create and configure Jinja2 environment."""
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(['html', 'xml']),
        trim_blocks=True,
        lstrip_blocks=True
    )

    # Add custom filters
    env.filters['repr'] = repr
    env.filters['shell_escape'] = _escape_for_shell

    return env


def package_to_dash_c(
    source: Union[str, pathlib.Path],
    entry_module: str,
    compression_mode: CompressionMode = CompressionMode.COMPRESSED,
    readonly_filesystem: bool = False,
    template_dir: pathlib.Path = None
) -> str:
    """
    Convert a Python package/module into a single python -c command.

    Args:
        source: Source to package - can be:
            - str: Python code as string
            - pathlib.Path pointing to a .py file
            - pathlib.Path pointing to a directory/package
        entry_module: Module to run (e.g., 'app.__main__' or 'app.cli')
        compression_mode: Whether to compress the payload
        readonly_filesystem: Optimize for read-only filesystem execution
        template_dir: Directory containing Jinja2 templates (defaults to ./templates)

    Returns:
        Complete python -c command string

    Raises:
        ValueError: If source is invalid or entry_module is malformed
    """
    if not entry_module or not isinstance(entry_module, str):
        raise ValueError("entry_module must be a non-empty string")

    if template_dir is None:
        template_dir = pathlib.Path(__file__).parent / "templates"

    # Collect all modules
    input_source = InputSource(source, entry_module)
    sources = input_source.collect_modules()

    if not sources:
        raise ValueError("No Python modules found in source")

    # Serialize the data using stdlib json only
    serialized_data = json.dumps(sources)

    # Prepare payload based on compression mode
    if compression_mode == CompressionMode.COMPRESSED:
        compressed_data = gzip.compress(serialized_data.encode('utf-8'))
        payload = base64.b64encode(compressed_data).decode("ascii")
    else:
        payload = serialized_data

    # Generate runner code using Jinja2 template
    env = _get_template_environment(template_dir)
    template = env.get_template('runner.py.j2')

    runner = template.render(
        payload=payload,
        entry_module=entry_module,
        compression_mode=compression_mode,
        readonly_filesystem=readonly_filesystem
    )

    # Clean up the runner and escape for shell
    runner = textwrap.dedent(runner).strip()
    escaped_runner = shlex.quote(runner) # _escape_for_shell(runner)

    return f'python -c {escaped_runner}'


def main() -> None:
    """Example usage and testing."""
    import tempfile
    import os

    # Example: Create a simple app structure for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        app_dir = pathlib.Path(tmpdir) / "app"
        app_dir.mkdir()

        # Create __init__.py
        (app_dir / "__init__.py").write_text('print("App package initialized")')

        # Create __main__.py with main function
        main_py = '''
def main():
    print("Hello from embedded app!")
    return 0

if __name__ == "__main__":
    main()
'''
        (app_dir / "__main__.py").write_text(main_py)

        # Create util.py
        (app_dir / "util.py").write_text('def helper(): return "utility function"')

        # Test different compression modes
        for compression in CompressionMode:
            cmd = package_to_dash_c(
                source=app_dir,
                entry_module="__main__",
                compression_mode=compression,
                readonly_filesystem=True
            )
            print(f"\n{compression.value.title()} mode command length: {len(cmd)}")
            print(f"Command preview: {cmd[:100]}...")
            with open("out.sh", "w") as o:
                o.write(cmd)


if __name__ == "__main__":
    main()