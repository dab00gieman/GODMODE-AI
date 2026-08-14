"""
Project GODMODE — Telegram Message Formatter
Handles Markdown/HTML formatting, message splitting, and sanitization.
"""

import re
import html
from typing import List, Optional

# Telegram message limit
TELEGRAM_MAX_LENGTH = 4096
SAFE_CHUNK_SIZE = 3800  # Leave room for formatting overhead

# Characters that need escaping in Telegram HTML mode
def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML mode."""
    return html.escape(text)


def escape_markdown_v2(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    special = r"_*[]()~`>#+-=|{}.!"
    escaped = ""
    for char in text:
        if char in special:
            escaped += f"\\{char}"
        else:
            escaped += char
    return escaped


def split_message(text: str, max_length: int = SAFE_CHUNK_SIZE) -> List[str]:
    """
    Intelligently split a long message into chunks.
    Tries to break at paragraph boundaries, then sentences, then words.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to split at a paragraph break
        split_pos = remaining.rfind("\n\n", 0, max_length)
        if split_pos == -1 or split_pos < max_length // 2:
            # Try to split at a single newline
            split_pos = remaining.rfind("\n", 0, max_length)

        if split_pos == -1 or split_pos < max_length // 2:
            # Try to split at a sentence boundary
            for delim in [". ", "? ", "! "]:
                pos = remaining.rfind(delim, 0, max_length)
                if pos > max_length // 2:
                    split_pos = pos + len(delim)
                    break

        if split_pos == -1 or split_pos < max_length // 2:
            # Try to split at a word boundary
            split_pos = remaining.rfind(" ", 0, max_length)
            if split_pos > 0:
                split_pos += 1

        if split_pos <= 0:
            # Hard cut
            split_pos = max_length

        chunks.append(remaining[:split_pos].strip())
        remaining = remaining[split_pos:].strip()

    return chunks


def truncate_with_ellipsis(text: str, max_length: int = 100) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 1] + "…"


def format_model_label(model_id: str) -> str:
    """Format a model ID for display in Telegram."""
    from utils.config import get_model_label
    label = get_model_label(model_id)
    return f"🧠 {label}"


def format_stats(stats: dict) -> str:
    """Format stats dict into a readable string."""
    lines = []
    for key, value in stats.items():
        formatted_key = key.replace("_", " ").title()
        lines.append(f"  • {formatted_key}: {value}")
    return "\n".join(lines)


def sanitize_input(text: str) -> str:
    """
    Basic input sanitization — remove potentially dangerous characters
    while preserving content.
    """
    if not text:
        return ""
    # Remove null bytes and control characters (except newlines/tabs)
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Limit length
    if len(text) > 8000:
        text = text[:8000]
    return text.strip()


def is_url(text: str) -> bool:
    """Check if text looks like a URL."""
    url_pattern = re.compile(
        r"^https?://"
        r"(?:[-\w])+(?:\.[-\w]+)+"
        r"(?:/[-\w./?%&=#]*)?$",
        re.IGNORECASE
    )
    return bool(url_pattern.match(text.strip()))
