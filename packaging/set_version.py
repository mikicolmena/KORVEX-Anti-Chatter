"""Escribe la versión indicada en korvex/__init__.py (lo usa el workflow de CI)."""
import pathlib
import re
import sys

version = sys.argv[1].lstrip("v")
path = pathlib.Path(__file__).resolve().parent.parent / "korvex" / "__init__.py"
text = path.read_text(encoding="utf-8")
text = re.sub(r'^__version__ = .*$', f'__version__ = "{version}"', text, count=1, flags=re.M)
path.write_text(text, encoding="utf-8")
print(f"__version__ = {version}")
