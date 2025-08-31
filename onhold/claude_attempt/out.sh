python -c 'import sys, types, importlib.util, importlib.abc, json

_PAYLOAD = json.loads('"'"'{"util": "def helper(): return \\"utility function\\"", "__main__": "\\ndef main():\\n    print(\\"Hello from embedded app!\\")\\n    return 0\\n\\nif __name__ == \\"__main__\\":\\n    main()\\n"}'"'"')

class _DictLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Custom loader for embedded modules."""

    def find_spec(self, fullname: str, path, target=None):
        """Find module spec for embedded modules."""
        if fullname in _PAYLOAD:
            return importlib.util.spec_from_loader(fullname, self)

        # Package support: if any child exists, mark as package
        pkg_prefix = fullname + "."
        if any(k.startswith(pkg_prefix) for k in _PAYLOAD):
            spec = importlib.machinery.ModuleSpec(fullname, self, is_package=True)
            return spec

        return None

    def create_module(self, spec):
        """Use default module creation."""
        return None

    def exec_module(self, module):
        """Execute the embedded module."""
        name = module.__spec__.name
        src = _PAYLOAD.get(name)

        if src is None and module.__spec__.submodule_search_locations is not None:
            # Its a package: synthesize empty __init__
            src = ""

        code = compile(src, f"<embedded {name}>", "exec", dont_inherit=True, optimize=2)
        exec(code, module.__dict__)

# Install our custom loader
sys.meta_path.insert(0, _DictLoader())

# Wheel loading support would be added here:
# TODO: Add support for embedded wheel files
# - Extract wheel metadata and dependencies
# - Add wheel contents to sys.path or create custom finders
# - Handle entry points and console scripts
# - Consider using importlib.metadata for wheel introspection

# Run the entry point
import importlib, runpy

try:
    mod = importlib.import_module('"'"'__main__'"'"')

    # Try to call main() if it exists and is callable
    if hasattr(mod, "main") and callable(getattr(mod, "main")):
        result = mod.main()
        if result is not None:
            sys.exit(result)
    # If no main() function, importing may have run the module already

except Exception as e:
    print(f"Error running '"'"'__main__'"'"': {e}", file=sys.stderr)
    sys.exit(1)'