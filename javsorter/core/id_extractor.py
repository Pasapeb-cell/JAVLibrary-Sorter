from __future__ import annotations

import re
from pathlib import Path

from .models import ExtractedId

# Bracketed/parenthesized tags, e.g. "[1080p]", "(hhd800.com)".
_BRACKET_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)")

# Leading site-tag/watermark prefixes, e.g. "hhd800.com@MIAB-369".
_SITE_TAG_RE = re.compile(r"^[\w-]+(?:\.[\w-]+)+@")

# Resolution/codec tokens that can appear anywhere, separated by brackets,
# spaces, underscores, or dots, e.g. "MIST-435.1080p".
_QUALITY_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:\d{3,4}p|4K|8K|FHD|UHD|HD|SD|HEVC|AVC|x264|x265|H264|H265)(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Core content-ID shape: studio letters + hyphen + digits. Preferred over the
# hyphen-less fallback since it rarely false-positives on stray text.
_HYPHEN_ID_RE = re.compile(r"(?P<studio>[A-Za-z]{2,6})-(?P<num>\d{2,6})")
# Fallback for filenames that dropped the hyphen entirely. Lower confidence.
_LOOSE_ID_RE = re.compile(r"(?P<studio>[A-Za-z]{2,6})(?P<num>\d{2,6})")

# Multi-CD/part markers, e.g. "-cd1", "-part2", "-disc1".
_PART_SUFFIX_RE = re.compile(r"^-?(cd\d|part\d|disc\d)", re.IGNORECASE)
# "-A"/"-B" are unambiguously part markers by convention.
_AB_SUFFIX_RE = re.compile(r"^-([ABab])(?![A-Za-z0-9])")
# "-C" is ambiguous: it's the common uncensored-leak marker, but also the
# third part in an A/B/C split. Default to "uncensored"; the scanner
# reinterprets it as a part label when sibling -A/-B files are found for the
# same base ID.
_C_SUFFIX_RE = re.compile(r"^-([Cc])(?![A-Za-z0-9])")


def _normalize(stem: str) -> str:
    stem = _SITE_TAG_RE.sub("", stem)
    stem = _BRACKET_RE.sub(" ", stem)
    stem = _QUALITY_TOKEN_RE.sub(" ", stem)
    return stem


def extract_id(filename: str) -> ExtractedId:
    """Isolate a JAV content ID out of a real-world, often noisy, filename."""
    stem = Path(filename).stem
    normalized = _normalize(stem)

    match = _HYPHEN_ID_RE.search(normalized)
    high_confidence = True
    if match is None:
        match = _LOOSE_ID_RE.search(normalized)
        high_confidence = False

    if match is None:
        return ExtractedId(
            raw_filename=filename,
            content_id=None,
            studio=None,
            number=None,
            uncensored=False,
            part_label=None,
            ambiguous_part_marker=False,
            high_confidence=False,
        )

    studio = match.group("studio").upper()
    number = match.group("num")
    remainder = normalized[match.end():]

    uncensored = False
    part_label: str | None = None
    ambiguous_part_marker = False

    part_match = _PART_SUFFIX_RE.match(remainder)
    if part_match:
        part_label = part_match.group(1).lower()
    else:
        ab_match = _AB_SUFFIX_RE.match(remainder)
        if ab_match:
            part_label = ab_match.group(1).lower()
        else:
            c_match = _C_SUFFIX_RE.match(remainder)
            if c_match:
                ambiguous_part_marker = True
                uncensored = True

    content_id = f"{studio}-{number}"
    if uncensored:
        content_id += "-C"

    return ExtractedId(
        raw_filename=filename,
        content_id=content_id,
        studio=studio,
        number=number,
        uncensored=uncensored,
        part_label=part_label,
        ambiguous_part_marker=ambiguous_part_marker,
        high_confidence=high_confidence,
    )
