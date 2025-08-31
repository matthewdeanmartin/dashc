#!/usr/bin/env bash
python -c '# The source code is embedded here as a string literal created by json.dumps()
_source = "import sys\nprint(\"HELLO_FILE\", \"args:\", sys.argv[1:])\n"

_globals = {"__name__": "__main__", "__file__": "hello_file.py"}

# Use compile so tracebacks point at the virtual filename and line numbers match.
exec(compile(_source, "hello_file.py", "exec"), _globals, _globals)' $@
