
from __future__ import annotations
from typing import Any, List, Dict

def normalize_sections(sections: Any) -> List[Dict[str, str]]:
    """Convert arbitrary sectionizer output into a list of {'title','text'} dicts."""
    norm: List[Dict[str, str]] = []

    def add(title, text):
        t = (title or "").strip()
        x = (text or "").strip()
        if x:
            norm.append({"title": t or None, "text": x})

    if sections is None:
        return norm

    if isinstance(sections, str):
        add(None, sections)
        return norm

    if isinstance(sections, (list, tuple)):
        for item in sections:
            if item is None:
                continue
            if isinstance(item, str):
                add(None, item)
            elif isinstance(item, dict):
                title = item.get("title") or item.get("heading") or item.get("name")
                text  = (item.get("text") or item.get("content") or item.get("body") or
                         item.get("desc") or item.get("description"))
                if not text:
                    entries = item.get("entries") or item.get("entry") or item.get("sections")
                    if isinstance(entries, (list, tuple)):
                        text = "\n".join(s for s in entries if isinstance(s, str))
                if not text:
                    strings = []
                    for v in item.values():
                        if isinstance(v, str) and v.strip():
                            strings.append(v.strip())
                        elif isinstance(v, (list, tuple)):
                            strings.extend([s.strip() for s in v if isinstance(s, str) and s.strip()])
                    text = "\n".join(strings)
                add(title, text)
            elif isinstance(item, (list, tuple)):
                flat = "\n".join(s for s in item if isinstance(s, str))
                add(None, flat)
            else:
                add(None, str(item))
        return norm

    add(None, str(sections))
    return norm
