"""Encode a local file path the way Premiere Pro actually writes ``<pathurl>``.

Why this is its own module
--------------------------
In an FCP7 (``xmeml``) document, ``<pathurl>`` is the single line that points at your
media. Encode it with stock percent-encoding and Premiere cannot find the file. With
one clip you get an offline clip. With many, the import collapses and Premiere only
says:

    "The project appears to be damaged and cannot be opened."

Nothing in that message mentions paths. The structure is valid, the media is on disk,
and you are left bisecting a 150-clip XML by hand.

How the rules were found
------------------------
Not by guessing. We exported a sequence *from Premiere itself* and diffed its XML
against ours, character by character. Premiere had written:

    file://localhost/C%3a/Users/me/Desktop/clips(OBS)[raw]/2025-09-30%2015-15-50.mp4

Four rules fall out of that line:

1. The drive colon is percent-encoded: ``C:`` becomes ``C%3a`` -- not left as-is.
2. Hex digits are **lowercase**: ``%3a``, not ``%3A``.
3. These characters are **left alone**: ``( ) [ ] & ~ ! $ ' * + , ; = @ _ - .``
   This is the one that bites. :func:`urllib.parse.quote` escapes parentheses by
   default, and ``%28`` in a path was exactly what broke our imports.
4. Spaces become ``%20``; non-ASCII is UTF-8 percent-encoded.

Verified on
-----------
Premiere Pro 25.x and 26.x on Windows, with paths containing spaces, parentheses,
square brackets and non-ASCII (Korean) characters.

Not tested: UNC paths (``\\\\server\\share``) and macOS volume paths. Patches welcome.
"""

from __future__ import annotations

import re
import urllib.parse

__all__ = ["pathurl", "UNRESERVED"]

#: Characters Premiere leaves unescaped. Stock ``quote`` escapes some of these,
#: which is the whole reason this module exists.
UNRESERVED = "/()[]&~!$'*+,;=@_-."

_PERCENT = re.compile(r"%[0-9A-F]{2}")


def pathurl(path: str, prefix: str = "file://localhost/") -> str:
    """Return *path* encoded for an FCP7 ``<pathurl>`` element.

    Accepts Windows or POSIX separators; backslashes are normalised to ``/``.

    >>> pathurl(r"C:\\clips\\take 1 (raw).mp4")
    'file://localhost/C%3a/clips/take%201%20(raw).mp4'
    """
    normalised = str(path).replace("\\", "/")
    encoded = urllib.parse.quote(normalised, safe=UNRESERVED, encoding="utf-8")
    return prefix + _PERCENT.sub(lambda m: m.group(0).lower(), encoded)
