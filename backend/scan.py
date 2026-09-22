"""
Fetches a business's public page and pulls out the signals we care about:
phone numbers, an hours-of-operation block, and address-like lines.

This is deliberately simple pattern-matching, not a full NLP pipeline —
good enough to prove the monitor loop works, and a clear place to improve
later (e.g. swap in an LLM call to extract structured fields more reliably).
"""

import re
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "PatchquillMonitor/0.1 (prototype)"}

PHONE_RE = re.compile(
    r"(\+?\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}"
)

HOURS_KEYWORDS = [
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
    "hours", "open", "closed", "am", "pm",
]

ADDRESS_KEYWORDS = [
    "street", "st.", "ave", "avenue", "road", "rd.", "blvd",
    "suite", "floor", "bosnia", "herzegovina",
]


def fetch_text(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def extract_phones(text: str):
    found = set()
    for match in PHONE_RE.findall(text):
        pass
    # findall with groups returns only the group; re-run with finditer for full match
    for m in PHONE_RE.finditer(text):
        candidate = m.group(0).strip()
        digits = re.sub(r"\D", "", candidate)
        if 7 <= len(digits) <= 15:
            found.add(candidate)
    return sorted(found)


def extract_hours_block(text: str) -> str:
    lines = text.splitlines()
    hit_lines = []
    for i, line in enumerate(lines):
        low = line.lower()
        if any(k in low for k in HOURS_KEYWORDS) and any(c.isdigit() for c in line):
            hit_lines.append(line.strip())
    # de-dupe, keep order, cap length
    seen = []
    for ln in hit_lines:
        if ln not in seen:
            seen.append(ln)
    return " | ".join(seen[:8])


def extract_addresses(text: str):
    lines = text.splitlines()
    hits = []
    for line in lines:
        low = line.lower()
        if any(k in low for k in ADDRESS_KEYWORDS):
            hits.append(line.strip())
    # de-dupe, cap
    seen = []
    for ln in hits:
        if ln not in seen:
            seen.append(ln)
    return seen[:5]


def run_scan(url: str):
    """Returns (raw_text, phones, hours_text, addresses) for a URL."""
    raw_text = fetch_text(url)
    phones = extract_phones(raw_text)
    hours_text = extract_hours_block(raw_text)
    addresses = extract_addresses(raw_text)
    return raw_text, phones, hours_text, addresses
