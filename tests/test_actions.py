import pytest

from handcue.actions import normalize_url
from handcue.desktop_input import KEYS, parse_shortcut


@pytest.mark.parametrize("value, expected", [
    ("https://example.org", "https://example.org"),
    ("example.org/page", "https://example.org/page"),
    ("  http://example.org  ", "http://example.org"),
])
def test_web_urls_are_accepted(value, expected):
    assert normalize_url(value) == expected


@pytest.mark.parametrize("value", [
    "file:///etc/passwd", "javascript:alert(1)", "ftp://example.org", "smb://server/share", "https://",
])
def test_other_schemes_are_rejected(value):
    with pytest.raises(ValueError):
        normalize_url(value)


def test_parse_shortcut():
    assert parse_shortcut("ctrl+alt+t") == [KEYS["ctrl"], KEYS["alt"], ord("t")]
    assert parse_shortcut("Super") == [KEYS["super"]]
    assert parse_shortcut("ctrl + c") == [KEYS["ctrl"], ord("c")]


@pytest.mark.parametrize("value", ["", "+", "ctrl+nosuchkey"])
def test_parse_shortcut_errors(value):
    with pytest.raises(ValueError):
        parse_shortcut(value)
