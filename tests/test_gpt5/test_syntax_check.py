import shutil
import sys

import pytest

from dashc.validate_syntax import validate_bash_syntax, validate_python_syntax


def test_validate_python_syntax_valid_and_invalid():
    assert validate_python_syntax("x = 1\nprint(x)") is True
    # very obviously invalid
    assert validate_python_syntax("def :\n    pass") is False


def test_validate_bash_syntax_valid_and_unterminated_quote():
    # Works whether bash exists or not:
    # - if bash exists: `bash -n -c` should succeed/fail accordingly
    # - if bash doesn't: fallback shlex.split() will succeed/fail accordingly
    assert validate_bash_syntax("echo hello") is True
    # Unterminated quote should be caught by bash -n or raise in shlex.split
    assert validate_bash_syntax("echo 'unterminated") is False

    # If bash is present, a *shell-grammar* error should be caught by `bash -n -c`
    if shutil.which("bash"):
        # Missing 'then'
        assert validate_bash_syntax("if true; echo nope; fi") is False
