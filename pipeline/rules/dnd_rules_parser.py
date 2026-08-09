# dnd_rules_parser.py
from __future__ import annotations

import re

# Expanded heading & anchor patterns for D&D rules
# Accept headings that optionally end with ':' or '.'
RE_HEADING_CORE = re.compile(
    r"""^
    (?:[A-Z][A-Za-z][A-Za-z '\-/()]{1,}|[A-Z][A-Z '\-/()]{2,})   # TitleCase or SHOUTY
    [:.]?$                                                       # optional trailing ':' or '.'
    """,
    re.X,
)

# Common rule anchors that should trigger a sub-split even inside large sections
RULE_ANCHORS = [
    "attack rolls",
    "saving throws",
    "ability checks",
    "proficiency bonus",
    "armor class",
    "hit points",
    "temporary hit points",
    "conditions",
    "advantage",
    "disadvantage",
    "initiative",
    "actions in combat",
    "bonus actions",
    "reactions",
    "cover",
    "damage types",
    "resistance",
    "vulnerability",
    "immunity",
    "spellcasting",
    "concentration",
    "components",
    "spell save dc",
    "spell attack",
    "resting",
    "movement",
    "difficult terrain",
    "line of sight",
    "range",
    "grappled",
    "restrained",
    "prone",
    "unconscious",
    "frightened",
    "poisoned",
    "stunned",
    "blinded",
    "deafened",
    "invisible",
]

# Markdown-ish markers and list markers often found in exports
RE_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+\S")
RE_LIST_MARK = re.compile(r"^\s*(?:-|\*|\+)\s+")
RE_TABLE_BORDER = re.compile(r"^\s*\|[^|]+\|\s*$")  # pipe tables
RE_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
RE_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n+")
RE_LINE_BOUNDARY = re.compile(r"\n+")
RE_SENTENCE_BREAK = re.compile(r"[.!?][\"')\]]?\s+")
RE_CLAUSE_BREAK = re.compile(r"[:;]\s+")
RE_COMMA_BREAK = re.compile(r",\s+")
RE_WHITESPACE_BREAK = re.compile(r"\s+")


def _is_heading(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    if RE_MD_HEADING.match(line):
        return True
    # Keep lines that look like headings (allow trailing punctuation)
    if len(line) <= 100 and RE_HEADING_CORE.match(line):
        return True
    # Numbered headings like "2.1 Combat" or "10: Spellcasting"
    if re.match(r"^\s*(\d+(\.\d+)*[:.)]\s+)\S", line):
        return True
    return False


def _collapse_small_blocks(paragraphs: list[str], min_chars: int = 180) -> list[str]:
    """
    Merge consecutive small paragraphs so we don't over-fragment.
    """
    out: list[str] = []
    buf = ""
    for p in paragraphs:
        if len((buf + " " + p).strip()) < min_chars:
            buf = (buf + "\n\n" + p).strip()
        else:
            if buf:
                out.append(buf)
                buf = ""
            out.append(p)
    if buf:
        out.append(buf)
    return out


def _split_by_rule_anchors(text: str) -> list[str]:
    """
    Within a big section, sub-split on strong rule anchor phrases to get finer granularity.
    """
    parts: list[str] = []
    idx = 0

    anchors_sorted = sorted(set(RULE_ANCHORS), key=lambda s: -len(s))  # longest first
    rx = re.compile(r"(?mi)^(?:\s*[-*+]\s*)?(" + "|".join([re.escape(a) for a in anchors_sorted]) + r")\b")
    for match in rx.finditer(text):
        start = match.start()
        if start - idx > 200:  # avoid producing ultra tiny preface chunks
            parts.append(text[idx:start].strip())
            idx = start
    parts.append(text[idx:].strip())
    parts = [part for part in parts if part]
    return parts if len(parts) > 1 else [text]


def _last_match_end(text: str, pattern: re.Pattern[str], start: int, end: int) -> int:
    last_end = -1
    for match in pattern.finditer(text, start, end):
        last_end = match.end()
    return last_end


def _choose_split_point(text: str, max_chars: int) -> int:
    search_end = min(len(text), max_chars)
    preferred_window = max(120, max_chars // 5)
    preferred_start = max(0, search_end - preferred_window)
    minimum_split = max(40, max_chars // 3)

    boundary_patterns = [
        RE_PARAGRAPH_BOUNDARY,
        RE_LINE_BOUNDARY,
        RE_SENTENCE_BREAK,
        RE_CLAUSE_BREAK,
        RE_COMMA_BREAK,
        RE_WHITESPACE_BREAK,
    ]

    for pattern in boundary_patterns:
        split_at = _last_match_end(text, pattern, preferred_start, search_end)
        if split_at >= minimum_split:
            return split_at
        split_at = _last_match_end(text, pattern, 0, search_end)
        if split_at >= minimum_split:
            return split_at

    return search_end


def _hard_split_text(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        split_at = _choose_split_point(remaining, max_chars)
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return [chunk for chunk in chunks if chunk]


def _split_oversized_paragraph(text: str, max_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    sentences = [part.strip() for part in RE_SENTENCE_BOUNDARY.split(text) if part.strip()]
    if len(sentences) <= 1:
        return _hard_split_text(text, max_chars)

    chunks: list[str] = []
    cur = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.extend(_hard_split_text(sentence, max_chars))
            continue

        candidate = sentence if not cur else f"{cur} {sentence}"
        if len(candidate) <= max_chars:
            cur = candidate
            continue

        if cur:
            chunks.append(cur)
        cur = sentence

    if cur:
        chunks.append(cur)
    return [chunk for chunk in chunks if chunk]


def parse_into_segments(cleaned_text: str) -> list[tuple[str, str]]:
    """
    Segment cleaned text into (heading, body) pairs.

    Strategy:
    - Treat TitleCase/ALLCAPS lines (with optional ':' or '.') as headings.
    - Also treat markdown-style '#', and numbered headings '2.1 Combat'.
    - Inside very large sections, sub-split on RULE_ANCHORS to capture many more atomic rules.
    - Collapse tiny paragraphs to reduce noise.
    """
    lines = [line.rstrip() for line in cleaned_text.split("\n")]
    segments: list[tuple[str, str]] = []
    cur_head = "Document"
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        body = "\n".join(buf).strip()
        if not body:
            return
        subparts = _split_by_rule_anchors(body)
        if len(subparts) == 1:
            segments.append((cur_head, body))
        else:
            for part in subparts:
                first_line = part.split("\n", 1)[0].strip()
                if _is_heading(first_line) or len(first_line) <= 80:
                    sub_head = first_line.rstrip(":.")
                else:
                    sub_head = cur_head
                segments.append((f"{cur_head} - {sub_head}", part))

    for line in lines:
        if _is_heading(line):
            flush()
            cur_head = line.strip().rstrip(":.")
            buf = []
        else:
            buf.append(line)
    flush()

    final: list[tuple[str, str]] = []
    for head, body in segments:
        paras = [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]
        paras = _collapse_small_blocks(paras, min_chars=180)
        body2 = "\n\n".join(paras)
        final.append((head, body2))

    return final


def chunk_segments(segs: list[tuple[str, str]], max_chars: int = 2000, overlap: int = 180) -> list[tuple[str, str]]:
    """
    Chunk segments into ~max_chars with slight overlap so rules that straddle a boundary remain readable.
    """
    out: list[tuple[str, str]] = []
    for head, body in segs:
        if len(body) <= max_chars:
            out.append((head, body))
            continue

        paragraphs: list[str] = []
        for paragraph in [part for part in body.split("\n\n") if part.strip()]:
            paragraphs.extend(_split_oversized_paragraph(paragraph, max_chars))

        cur = ""
        for paragraph in paragraphs:
            if not cur:
                cur = paragraph
                continue
            if len(cur) + len(paragraph) + 2 <= max_chars:
                cur = (cur + "\n\n" + paragraph).strip()
            else:
                out.append((head, cur))
                if overlap > 0:
                    allowed_tail = max_chars - len(paragraph) - 2
                    if allowed_tail > 40:
                        tail = cur[-min(overlap, allowed_tail) :].strip()
                        cur = (tail + "\n\n" + paragraph).strip()
                    else:
                        cur = paragraph
                else:
                    cur = paragraph
                if len(cur) > max_chars:
                    split_chunks = _split_oversized_paragraph(cur, max_chars)
                    out.extend((head, chunk) for chunk in split_chunks[:-1])
                    cur = split_chunks[-1]
        if cur:
            out.append((head, cur))
    return out
