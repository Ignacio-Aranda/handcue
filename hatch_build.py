"""Compiles the translations in po/ into the package before building the wheel."""
from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from hatchling.builders.hooks.plugin.interface import BuildHookInterface

DOMAIN = "handcue"


def compile_translations(root):
    root = Path(root)
    out = root / "src" / "handcue" / "locale"
    for po in sorted((root / "po").glob("*.po")):
        with po.open("rb") as f:
            catalog = read_po(f, locale=po.stem)
        dest = out / po.stem / "LC_MESSAGES" / f"{DOMAIN}.mo"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            write_mo(f, catalog)


class TranslationsHook(BuildHookInterface):
    def initialize(self, version, build_data):
        compile_translations(self.root)
