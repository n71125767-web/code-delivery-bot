from __future__ import annotations

import re

# Telegram Bot is configured with parse_mode=None in this project.
# Keep outgoing text plain so users do not see raw <b>, <i>, <code> tags.
_TAG_RE = re.compile(r"</?(?:b|strong|i|em|u|s|del|strike|code|pre|blockquote|tg-spoiler)(?:\s+[^>]*)?>", re.IGNORECASE)
_A_RE = re.compile(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def plain_text(text: str | None) -> str:
    if text is None:
        return ""
    value = str(text)
    value = _A_RE.sub(lambda m: f"{m.group(2)} — {m.group(1)}".strip(), value)
    value = _BR_RE.sub("\n", value)
    value = _TAG_RE.sub("", value)
    return value
