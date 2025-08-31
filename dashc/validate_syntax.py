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
