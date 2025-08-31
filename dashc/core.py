import base64
import zlib
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader


def compress_to_b64(source: str) -> str:
    raw = source.encode("utf-8")
    comp = zlib.compress(raw, 9)
    return base64.b64encode(comp).decode("ascii")

def b64z(data: bytes) -> str:
    return base64.b64encode(zlib.compress(data, 9)).decode("ascii")


def make_python_c(code: str, python_exe: str = "python") -> str:
    # Outer uses single quotes; template must stick to double quotes only.
    return f"{python_exe} -c '{code}'"

# Get the directory containing the current script
_SCRIPT_DIR = Path(__file__).parent.resolve()
_TEMPLATE_DIR = _SCRIPT_DIR / "templates"

def render(template_name:str, data:dict[str,Any]) -> str:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    tmpl = env.get_template(template_name)
    return tmpl.render(data)

def render_wrapper_zip(payload_b64: str, root_pkg: str) -> str:
    return render("wrapper_zip.py.j2", {"payload_b64":payload_b64, "root_pkg":root_pkg})


def render_wrapper(payload_b64: str, virtual_filename: str) -> str:
    return render("wrapper.py.j2", {"payload_b64":payload_b64, "virtual_filename":virtual_filename})
