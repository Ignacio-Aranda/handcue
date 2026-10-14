"""gettext setup. Source strings are in English; catalogs live in po/ and are
compiled into locale/ at build time (see hatch_build.py)."""
import gettext
from pathlib import Path

DOMAIN = "handcue"
LOCALE_DIR = Path(__file__).resolve().parent / "locale"

_translation = gettext.translation(DOMAIN, LOCALE_DIR, fallback=True)
_ = _translation.gettext
ngettext = _translation.ngettext
