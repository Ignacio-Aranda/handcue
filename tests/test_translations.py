import re
from pathlib import Path

from babel.messages.pofile import read_po

PO_DIR = Path(__file__).resolve().parent.parent / "po"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def load(path):
    with open(path, "rb") as f:
        return read_po(f)


def catalogs():
    return sorted(PO_DIR.glob("*.po"))


def test_there_is_at_least_one_translation():
    assert catalogs()


def test_translations_are_complete_and_keep_placeholders():
    template = {m.id for m in load(PO_DIR / "handcue.pot") if m.id}
    for po in catalogs():
        catalog = load(po)
        ids = {m.id for m in catalog if m.id}
        assert template <= ids, f"{po.name} is missing {template - ids}"
        for m in catalog:
            if not m.id or not m.string:
                continue
            ids_ = m.id if isinstance(m.id, tuple) else (m.id,)
            strings = m.string if isinstance(m.string, tuple) else (m.string,)
            allowed = set().union(*(PLACEHOLDER.findall(i) for i in ids_))
            for s in strings:
                assert set(PLACEHOLDER.findall(s)) <= allowed, f"{po.name}: {m.id!r}"
