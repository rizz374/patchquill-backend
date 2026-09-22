"""
Compares the newest snapshot of a business against two things:
  1. the previous snapshot (did the page itself change?)
  2. the stored "business record" (does the page conflict with what the
     owner says is actually true, even if the page hasn't changed?)

Values are normalised first so formatting differences (spacing, punctuation,
capitalisation) don't get mistaken for real changes. An AI drafting call is
only made when a finding is ambiguous enough to need human-quality wording;
everything else gets a template. This mirrors the "AI is optional, only
runs when useful" design.
"""

import json
import difflib

import normalize

WATCHED_FIELDS = ["phone", "hours", "address"]


def choose_severity(field: str, kind: str) -> str:
    if kind == "conflict":
        return "high"  # the live page contradicts what you told us is true
    if field == "phone":
        return "high"  # wrong phone number directly costs customers
    if field == "hours":
        return "normal"
    return "low"


def _draft_correction(business_name, field, old_value, new_value):
    """
    Template fallback. Swap for a real Claude API call, e.g.:

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6", max_tokens=200,
            messages=[{"role": "user", "content": (
                f"{business_name}'s {field} changed from '{old_value}' to "
                f"'{new_value}'. Draft a one-sentence customer-facing note."
            )}]
        )
        return response.content[0].text
    """
    if field == "phone":
        return (f"Phone changed from {old_value or 'none listed'} to "
                f"{new_value or 'none listed'}. Confirm, then update it everywhere "
                f"else {business_name} is listed.")
    if field == "hours":
        return (f"Hours changed. Was: \"{old_value or 'not listed'}\". "
                f"Now: \"{new_value or 'not listed'}\". Confirm before it reaches customers.")
    if field == "address":
        return f"Address-like line changed to \"{new_value}\". Check it's accurate."
    return "Content changed on the page. Review the evidence below."


def _extract_field(row, field):
    if field == "phone":
        return json.loads(row["phones"] or "[]")
    if field == "hours":
        return row["hours_text"] or ""
    if field == "address":
        return json.loads(row["addresses"] or "[]")
    return None


def _finding(business, field, before_raw, after_raw, kind):
    """Builds one finding dict if the normalised values actually differ."""
    before_norm = normalize.normalise_value(field, before_raw)
    after_norm = normalize.normalise_value(field, after_raw)
    if before_norm == after_norm:
        return None  # only formatting differed — not a real change

    ambiguous = normalize.is_uncertain(field, after_raw)
    severity = choose_severity(field, kind)

    before_display = ", ".join(before_raw) if isinstance(before_raw, list) else (before_raw or None)
    after_display = ", ".join(after_raw) if isinstance(after_raw, list) else (after_raw or None)

    finding = {
        "field": field,
        "kind": kind,
        "old_value": before_display,
        "new_value": after_display,
        "severity": severity,
        "is_ambiguous": ambiguous,
        "evidence": (f"[{kind}] {field}: \"{before_display or '(none)'}\" \u2192 \"{after_display or '(none)'}\""),
    }
    finding["draft_correction"] = (
        _draft_correction(business["name"], field, before_display, after_display)
        if ambiguous or field in ("phone", "hours")
        else None
    )
    return finding


def compare_snapshots(business, prev_row, new_row):
    """
    Returns a list of finding dicts ready for db.add_issue(). Checks both
    "did it change since last time" and "does it conflict with the stored
    business record", de-duplicated by field.
    """
    findings = []
    seen_fields = set()

    if prev_row is not None:
        for field in WATCHED_FIELDS:
            before = _extract_field(prev_row, field)
            after = _extract_field(new_row, field)
            f = _finding(business, field, before, after, kind="change")
            if f:
                findings.append(f)
                seen_fields.add(field)

    record_map = {
        "phone": business["record_phone"],
        "hours": business["record_hours"],
        "address": business["record_address"],
    }
    for field in WATCHED_FIELDS:
        if record_map[field] is None:
            continue
        if field in seen_fields:
            continue
        after = _extract_field(new_row, field)
        f = _finding(business, field, record_map[field], after, kind="conflict")
        if f:
            findings.append(f)

    if not findings and prev_row is not None:
        prev_text = prev_row["raw_text"] or ""
        new_text = new_row["raw_text"] or ""
        if prev_text != new_text:
            diff_lines = list(difflib.unified_diff(
                prev_text.splitlines(), new_text.splitlines(), lineterm="", n=0
            ))
            meaningful = [ln for ln in diff_lines if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
            if meaningful:
                findings.append({
                    "field": "general_text",
                    "kind": "change",
                    "old_value": None,
                    "new_value": None,
                    "severity": "low",
                    "evidence": "\n".join(meaningful[:12]),
                    "draft_correction": None,
                })

    return findings
