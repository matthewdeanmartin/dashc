python -c '# Save this file as: templates/wrapper_zip.py.j2
# NOTE: Use DOUBLE QUOTES ONLY in this template so the outer bash command can
# safely single-quote the entire -c payload without extra escaping.

import base64, io, importlib.abc, importlib.machinery, runpy, sys, zipfile, zlib


def _inflate() -> bytes:
    b64 = """eNoL8GZmEWFgYOBgyK+Ui3757fUVTSBPHYi5gTg5Py8tM10vqzg/b3WYlp+u5skz3uGbggI+eZw9eTLcQ/vU+VAND59zfj7+oR6eOp4hIatYGQJQTFx16BvTSSDPjhFiYnx8bmJmXny8XkFlbt9BL2ZDgbb3jXsO+1e90JtSof+FkaV/b6eO4cy7brs9Z/hcdK0p73R0/GDCfPj72e2Haw/t8l03ZffVoymnl4XGeKc5yl//kTMza9/G5b+qq1daZi4NXSB5/c2hJ8WzHhv1uK9lSGj/rBp2hGunwDWZjsuMdsaTxffs5J108AlT1+f1eYos6us2n7UNTZzzz3tD76yWe6kGtndkEn5V3w4wLuOdfMei9naO95rD/RU5T+ceeJm/L6w1eVKiGf9NVq4X7cp2vz7tWK8idHlT/S+Tx+KoPu6NanfdBPRtJhMDgwrYxwWVyYnJGanx8fpw3ycXVJZk5OfpGhsaAUMiOTXwfLawo8i/tHrTs1LfArpCJ7RVRPH+ZG76ssiJf6m4vhDTaTNjtWiz3afPsMxKUmTnnyr36qzTx3VPlH6kV3hqBMnsvdptvtXc32j3bYEPsfeqP9e+r32/92fM6lDGB//OLT8oxrhuQ0rZy/XzGSq4ubySSjze9fY59oa/mME2w1K3U/Y0w+aVJ3Wy7jIW9JUfmyIicXDGj2/+su++TQvVYVgW1lksupPhW29q1M8y48uTAp16M0/aNsVEFmj/L45/lDYv/cPZ2Kc8xx1npLbn6fvGufy9ts9D+H7Y6osG3jt7FttuPTXTw33P8RY+ZymPMoWpSztP9V2ewDV/RZcfs+LOC3df10v3375bp8K+eK8e79EF13VTdjka8CxW4Yi6GbFzl4VGyc+1n+4cYjc4yJ//+FL2mb3Hll6fU332+3l7udgKf/Xb92Pfb/m7629awcO8c2vOZu89sXD75LYpF6surooN127ylFStvR+Y3e0a1W27Q+zRL4uda4q6nFLTbbyesH+Y1RbDGyrHG2zVdVMs/vR+AQFdhv0+TidE39U1/z5u5Pm3XPTq18nVws+13yS/P2Mpfd78z8237MbPH4qbfK77D0zljEwiDLhzDgw0MDKg5iN0jegZBKExCDW7oGtET2cIjS6MxKW6AG9WNpAOZiA8AqQtmEEGAAD1Mp8E"""
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


    # Entrypoint Type 1: Run a module (like python -m my_app)
    # The __main__.py inside the package will be executed.
    runpy.run_module("my_app", run_name="__main__", alter_sys=True)




if __name__ == "__main__":
    _main()'
