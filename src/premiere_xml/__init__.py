"""Build Premiere Pro-importable FCP7 (``xmeml``) sequences from a JSON cut list.

    from premiere_xml import build_sequence
    xml, summary = build_sequence(cutlist)

No dependencies, no Premiere needed to run it.
"""

from .pathurl import pathurl
from .sequence import build_sequence, frame_rate

__version__ = "0.1.0"
__all__ = ["build_sequence", "frame_rate", "pathurl", "__version__"]
