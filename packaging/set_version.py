"""Extrae el número de versión de un tag y, opcionalmente, lo escribe en korvex/__init__.py.

Acepta cualquier formato de tag: "v1.2.0", "Version1.2", "1.2", "release-1.2.0-beta1"...

Uso:
    python packaging/set_version.py --print Version1.2   -> imprime "1.2"
    python packaging/set_version.py Version1.2           -> escribe __version__ = "1.2"
"""
import pathlib
import re
import sys

_VERSION_RE = re.compile(r"\d+(?:\.\d+)*(?:[-+~][0-9A-Za-z.+~]+)?")


def parse(tag):
    match = _VERSION_RE.search(tag or "")
    if not match:
        raise SystemExit(f"No se encuentra un número de versión en el tag: {tag!r}")
    # En Debian, "-" separa la revisión del paquete; "~" ordena antes que la versión final.
    return match.group(0).replace("-", "~")


def write(version):
    path = pathlib.Path(__file__).resolve().parent.parent / "korvex" / "__init__.py"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'^__version__ = .*$', f'__version__ = "{version}"', text, count=1, flags=re.M)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--print":
        print(parse(args[1] if len(args) > 1 else ""))
    elif len(args) == 1:
        version = parse(args[0])
        write(version)
        print(f"__version__ = {version}")
    else:
        raise SystemExit(__doc__)
