"""
Normalizes extracted values before comparison, so a change in formatting
(spacing, punctuation, capitalization) doesn't get mistaken for a real
change in the underlying fact.
"""

import re


def normalise_phone(value: str) -> str:
    if not value:
        return ""
    # Keep only digits — "033 555 123", "033-555-123", "(033) 555 123"
    # all normalise to the same string.
    return re.sub(r"\D", "", value)


def normalise_text_block(value: str) -> str:
    if not value:
        return ""
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^\w\s:,-]", "", value)
    # Strip a leading label like "hours:" that only appears because of how
    # the scraper found the block — not a real difference in meaning.
    value = re.sub(r"^(hours|opening hours)\s*:?\s*", "", value)
    return value.strip()


def _as_list(value):
    """Business-record fields are scalars; scraped fields are lists.
    Coerce both to a list so they compare on equal footing."""
    if value is None:
        return []
    if isinstance(value, (list, set, tuple)):
        return list(value)
    return [value]


def normalise_value(field: str, value):
    if field == "phone":
        return sorted({normalise_phone(v) for v in _as_list(value) if v})
    if field == "address":
        return sorted({normalise_text_block(v) for v in _as_list(value) if v})
    if field == "hours":
        items = _as_list(value)
        joined = " ".join(items)
        return normalise_text_block(joined)
    return value


def is_uncertain(field: str, new_value) -> bool:
    """
    Flags a change as ambiguous when a human would need context to word a
    correction well — e.g. hours changed in a way that doesn't cleanly
    parse, or a field went empty (did it disappear, or did we fail to find
    it?). Simple heuristic, meant to be tuned over time.
    """
    if not new_value:
        return True  # something vanished — worth an explanation, not just a diff
    if field == "hours":
        # If it doesn't look like a normal day/time pattern, a person should
        # phrase the correction rather than a template.
        has_digit = any(c.isdigit() for c in str(new_value))
        return not has_digit
    return False
