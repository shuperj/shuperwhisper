"""Smart text processing — pure logic, no hardware dependencies.

Handles spacing, capitalization, bullet points, and email formatting
based on preceding context from the focused text field.
"""

import re

SENTENCE_ENDERS = frozenset(".!?")

# Patterns for email greetings (at the start of transcribed text)
_GREETING_PATTERNS = re.compile(
    r"^(hi|hello|hey|dear|good morning|good afternoon|good evening)"
    r"(\s+\w+)?\s*,?",
    re.IGNORECASE,
)

# Patterns for email sign-offs (at the start of transcribed text)
_SIGNOFF_PATTERNS = re.compile(
    r"^(best|best regards|regards|thanks|thank you|sincerely|cheers|kind regards"
    r"|warm regards|yours truly|respectfully|take care)\s*,?$",
    re.IGNORECASE,
)


def apply_smart_spacing(context: str | None, text: str) -> str:
    """Add appropriate spacing between existing context and new text.

    Args:
        context: The text preceding the cursor, or None if unavailable.
        text: The newly transcribed text to insert.

    Returns:
        The text with appropriate leading spacing and capitalization.
    """
    if not text:
        return text

    # No context available — safe default: prepend a space
    if not context:
        return " " + text

    # Context ends with a newline — no space, but capitalize (check before isspace)
    if context[-1] in ("\n", "\r"):
        return _capitalize_first(text)

    # Context ends with other whitespace — no extra space needed
    if context[-1].isspace():
        return text

    # Context ends with a sentence-ending punctuation — space + capitalize
    if context[-1] in SENTENCE_ENDERS:
        return " " + _capitalize_first(text)

    # Context ends with other characters (mid-word, comma, etc.) — just add space
    return " " + text


def apply_bullet_mode(context: str | None, text: str) -> str:
    """Format text as a bullet point list item.

    Args:
        context: The text preceding the cursor, or None if unavailable.
        text: The newly transcribed text.

    Returns:
        Text formatted as a bullet point.
    """
    if not text:
        return text

    bullet = f"- {text}"

    if not context:
        return bullet

    # If context already ends with a newline, just add the bullet
    if context.endswith("\n") or context.endswith("\r"):
        return bullet

    # Otherwise, add a newline before the bullet
    return "\n" + bullet


def apply_email_mode(text: str) -> str:
    """Apply email formatting to transcribed text.

    Adds line breaks after greetings and before sign-offs.

    Args:
        text: The newly transcribed text.

    Returns:
        Text with email formatting applied.
    """
    if not text:
        return text

    # Check if the entire text is a sign-off
    if _SIGNOFF_PATTERNS.match(text.strip()):
        return "\n\n" + text

    # Check if text starts with a greeting
    match = _GREETING_PATTERNS.match(text)
    if match:
        greeting_end = match.end()
        greeting = text[:greeting_end].rstrip()
        body = text[greeting_end:].lstrip()
        if body:
            return greeting + "\n\n" + body
        # Greeting only, add double newline after
        return greeting + "\n\n"

    return text


def process_text(
    context: str | None,
    text: str,
    smart_spacing: bool = True,
    bullet_mode: bool = False,
    email_mode: bool = False,
) -> str:
    """Apply all enabled text processing to transcribed text.

    Args:
        context: The text preceding the cursor, or None if unavailable.
        text: The raw transcribed text.
        smart_spacing: Whether to apply smart spacing.
        bullet_mode: Whether to format as bullet points.
        email_mode: Whether to apply email formatting.

    Returns:
        Processed text ready for injection.
    """
    if not text:
        return text

    result = text

    if email_mode:
        result = apply_email_mode(result)

    if bullet_mode:
        result = apply_bullet_mode(context, result)
    elif smart_spacing:
        result = apply_smart_spacing(context, result)

    return result


def _capitalize_first(text: str) -> str:
    """Capitalize the first character of a string."""
    if not text:
        return text
    return text[0].upper() + text[1:]
