"""The encoding rules, checked against what Premiere Pro writes itself.

No Premiere, no media files, no network. If one of these fails, we are the ones who
drifted -- these expectations were read off a real Premiere export.
"""

import re

from premiere_xml import pathurl


def test_drive_colon_is_percent_encoded():
    """Leaving ``C:`` as-is makes Premiere unable to locate the media."""
    assert pathurl("C:/a.mp4") == "file://localhost/C%3a/a.mp4"


def test_hex_digits_are_lowercase():
    """Premiere writes ``%3a`` and ``%ec``, not ``%3A`` and ``%EC``.

    Scans every escape instead of hard-coding bytes. Hard-coded bytes let a typo in
    the *test* dictate behaviour -- that happened once while writing this file.
    """
    out = pathurl("C:/\ud55c\uae00 (a).mp4")
    escapes = re.findall(r"%..", out)
    assert escapes, "expected at least one escaped character for this to mean anything"
    assert all(e == e.lower() for e in escapes), escapes


def test_brackets_and_parentheses_are_left_alone():
    """The rule that bites: ``%28`` / ``%5b`` in a path is what broke our imports."""
    out = pathurl("C:/clips(OBS)[raw]/a.mp4")
    assert "(OBS)[raw]" in out
    assert "%28" not in out and "%5b" not in out


def test_spaces_become_percent_20():
    assert pathurl("C:/a b.mp4") == "file://localhost/C%3a/a%20b.mp4"


def test_backslashes_are_normalised():
    assert pathurl(r"C:\x\y.mp4") == pathurl("C:/x/y.mp4")


def test_prefix_is_overridable():
    assert pathurl("C:/a.mp4", prefix="file:///").startswith("file:///C%3a")


def test_all_four_rules_at_once():
    """One path exercising every rule: drive colon, spaces, brackets, non-ASCII."""
    path = "C:/Users/me/Desktop/\uc601\uc0c1 \uc790\ub8cc/" \
           "\ucc28\ud2b8\uc124\uba85(OBS)[\uc6d0\ubcf8]/2025-09-30 15-15-50.mp4"
    expected = (
        "file://localhost/C%3a/Users/me/Desktop/"
        "%ec%98%81%ec%83%81%20%ec%9e%90%eb%a3%8c/"
        "%ec%b0%a8%ed%8a%b8%ec%84%a4%eb%aa%85(OBS)[%ec%9b%90%eb%b3%b8]/"
        "2025-09-30%2015-15-50.mp4"
    )
    assert pathurl(path) == expected
