#!/usr/bin/env bash
python -c '# Save this file as: templates/wrapper_zip.py.j2

import base64, io, importlib.abc, importlib.machinery, runpy, sys, zipfile, zlib


def _inflate() -> bytes:
    b64 = """eNoL8GZmEWFgYOBgODRJPrp49vGLRkCeKRDzAHFuZUF2un5yTqZeQaW3p2/wCd8zZy5f2PIoiKGpadGZPUK8qvzh8vL/fzDkf6/YHmCfruq7ISYwyzMzcF4TozhDAIrZHoz2gdxAHicQC8LNjo/PzMssiY8HWhAcdsJX55Sf7iMmNJ1Gpxk/WQB5Vmg6cxMz88A6T5/RPaGvFaixTueZlsapM9oXAz4VfP34sZ//Q1n/99IvX4IvBQZ46Xjpb2Myauj60vBmU4bz6ghfPaA1jEwiDLi9DwMNjAxogYGuE91zCJ0x2LyKrh3dhwjt07D5N8CblQ0kzQyEO4D0X7BiAJIoeuo="""
    return zlib.decompress(base64.b64decode(b64))


def _build_map(zbytes: bytes):
    zf = zipfile.ZipFile(io.BytesIO(zbytes))
    # Map of archive path -> file bytes
    return {info.filename: zf.read(info) for info in zf.infolist() if not info.is_dir()}


class _InMemZipLoader(importlib.abc.Loader):
    """Loader that serves modules out of an in-memory ZIP map.

    Implements get_source/get_code so callers like runpy.run_module can
    request code objects directly. This avoids the AttributeError you saw.
    """

    def __init__(self, zmap, fullname, is_pkg, arc_path):
        self._zmap = zmap
        self._fullname = fullname
        self._is_pkg = is_pkg
        self._arc_path = arc_path  # virtual filename for tracebacks

    # ---- helpers ----
    def _source_bytes(self, fullname: str) -> bytes:
        mod_path = fullname.replace(".", "/")
        if fullname == self._fullname:  # fast path for our primary module
            arc_path = self._arc_path
        elif self._is_pkg and fullname.startswith(self._fullname + "."):
            # submodules imported during package exec
            # delegate discovery back through meta_path, not here
            raise ImportError("Delegated to finder for submodule")
        else:
            # Not our module instance
            raise ImportError(f"Loader does not handle {fullname}")
        data = self._zmap.get(arc_path)
        if data is None:
            raise ImportError(f"No source for {fullname}")
        return data

    # ---- importlib.abc.InspectLoader API ----
    def get_source(self, fullname: str):  # type: ignore[override]
        return self._source_bytes(fullname).decode("utf-8")

    def get_code(self, fullname: str):  # type: ignore[override]
        src = self.get_source(fullname)
        return compile(src, self._arc_path, "exec")

    # ---- importlib.abc.Loader API ----
    def create_module(self, spec):  # default module creation
        return None

    def exec_module(self, module):
        code = self.get_code(self._fullname)
        module.__file__ = self._arc_path
        module.__package__ = self._fullname if self._is_pkg else self._fullname.rpartition(".")[0]
        if self._is_pkg:
            module.__path__ = [self._fullname]
        exec(code, module.__dict__)


class _InMemZipFinder(importlib.abc.MetaPathFinder):
    def __init__(self, zmap):
        self._zmap = zmap
        pkgs = set()
        mods = set()
        for path in zmap:
            if path.endswith("/__init__.py"):
                pkgs.add(path[:-12])
            elif path.endswith(".py"):
                mods.add(path[:-3])
        self._packages = {p.replace("/", ".") for p in pkgs}
        self._modules = {m.replace("/", ".") for m in mods}

    def find_spec(self, fullname, path, target=None):
        is_pkg = fullname in self._packages
        is_mod = fullname in self._modules
        if not (is_pkg or is_mod):
            return None
        if is_pkg:
            arc_path = fullname.replace(".", "/") + "/__init__.py"
        else:
            arc_path = fullname.replace(".", "/") + ".py"
        loader = _InMemZipLoader(self._zmap, fullname, is_pkg, arc_path)
        spec = importlib.machinery.ModuleSpec(fullname, loader, is_package=is_pkg)
        spec.origin = arc_path
        if is_pkg:
            spec.submodule_search_locations = [fullname]
        return spec

def _main():
    zbytes = _inflate()
    zmap = _build_map(zbytes)
    finder = _InMemZipFinder(zmap)
    sys.meta_path.insert(0, finder)

    
    # Entrypoint Type 1: Run a module (like python -m mypkg)
    # The __main__.py inside the package will be executed.
    runpy.run_module("mypkg", run_name="__main__", alter_sys=True)

    


if __name__ == "__main__":
    _main()' $@
