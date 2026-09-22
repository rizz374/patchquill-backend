"""
Postgres storage layer — drop-in replacement for the SQLite db.py.

Every function has the exact same name and signature as the SQLite
version, so main.py / scan.py / compare.py don't need to change at all.
What changed: this now writes to a real Postgres database (e.g. a free
Neon project) instead of a local file — which means the Next.js frontend
can read the same tables and show the issue inbox on the actual website.

Requires DATABASE_URL to be set (the same env var the Next.js app already
uses). Get a free Postgres instance at https://neon.tech, and use the
SAME connection string in both places — that's what "wires them up".
"""

import os
import json
import secrets
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    record_phone TEXT,
    record_hours TEXT,
    record_address TEXT,
    -- A long random token used as this business's private URL, e.g.
    -- /issues/<slug>. Unguessable, unique, and how one customer is kept
    -- from ever seeing another customer's data without needing real
    -- accounts/passwords.
    slug TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_text TEXT NOT NULL,
    phones TEXT,
    hours_text TEXT,
    addresses TEXT
);

CREATE TABLE IF NOT EXISTS issues (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    evidence TEXT,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'open',
    draft_correction TEXT,
    severity TEXT NOT NULL DEFAULT 'normal',
    kind TEXT NOT NULL DEFAULT 'change'
);
"""


def _dsn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Get a free Postgres connection string "
            "from https://neon.tech and set it as an environment variable "
            "(the SAME string the Next.js app uses)."
        )
    return url


@contextmanager
def get_conn():
    conn = psycopg2.connect(_dsn(), cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)


def add_business(name, url, record_phone=None, record_hours=None, record_address=None):
    slug = secrets.token_urlsafe(24)  # long, random, unguessable — this IS the access control
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO businesses (name, url, record_phone, record_hours, record_address, slug)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, slug""",
                (name, url, record_phone, record_hours, record_address, slug),
            )
            return cur.fetchone()


def get_business_by_slug(slug):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM businesses WHERE slug = %s", (slug,))
            return cur.fetchone()


def list_businesses():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM businesses ORDER BY id")
            return cur.fetchall()


def get_business(business_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM businesses WHERE id = %s", (business_id,))
            return cur.fetchone()


def save_snapshot(business_id, raw_text, phones, hours_text, addresses):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO snapshots (business_id, raw_text, phones, hours_text, addresses)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (business_id, raw_text, json.dumps(phones), hours_text, json.dumps(addresses)),
            )
            return cur.fetchone()["id"]


def last_two_snapshots(business_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT * FROM snapshots WHERE business_id = %s
                   ORDER BY scanned_at DESC, id DESC LIMIT 2""",
                (business_id,),
            )
            return cur.fetchall()


def add_issue(business_id, field, old_value, new_value, evidence, draft_correction=None,
              severity="normal", kind="change"):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO issues (business_id, field, old_value, new_value, evidence,
                                        draft_correction, severity, kind)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (business_id, field, old_value, new_value, evidence, draft_correction, severity, kind),
            )
            return cur.fetchone()["id"]


def list_issues(business_id=None, status=None):
    query = """SELECT issues.*, businesses.name AS business_name
               FROM issues JOIN businesses ON businesses.id = issues.business_id"""
    clauses, params = [], []
    if business_id is not None:
        clauses.append("issues.business_id = %s")
        params.append(business_id)
    if status is not None:
        clauses.append("issues.status = %s")
        params.append(status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY issues.detected_at DESC"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def set_issue_status(issue_id, status):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE issues SET status = %s WHERE id = %s", (status, issue_id))
