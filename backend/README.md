# Patchquill Monitor — Postgres edition (wired to the website)

Same scan/compare/normalize logic as before, now writing to Postgres
instead of a local SQLite file — so the Next.js website's `/issues` page
can read the same data.

## Setup

    pip install -r requirements.txt
    export DATABASE_URL="postgresql://...your neon connection string..."

## Use

    python main.py add-business "Konoba Zar" "https://your-business-site.com" \
      --phone "your correct phone" --hours "your correct hours" --address "your correct address"
    python main.py scan 1        # first run = baseline
    python main.py scan 1        # later runs = real comparison
    python main.py issues
    python main.py approve 1
    python main.py scan-all      # scan every tracked business — this is what runs on a schedule

## Wiring to the website

See DEPLOY.md in the website project for the full walkthrough. Short version:
1. Get a free Postgres database at https://neon.tech
2. Use that SAME connection string as DATABASE_URL in Vercel (website) AND
   as a `DATABASE_URL` GitHub Actions secret in this repo
3. Push this repo, including `.github/workflows/daily-scan.yml` — it runs
   `scan-all` automatically every day, no manual trigger, no subscription
4. Visit `/issues` on your deployed site to see what it found

## What's real vs. still ahead
Real: scheduled scanning (GitHub Actions), snapshot + business-record
comparison with normalization, evidence-backed issues with severity, a
website page reading live from the same database.

Still ahead: approve/dismiss only works from the CLI right now — writing
those actions back from the website's `/issues` page is the next piece.
Publishing an approved correction to Google/Instagram is also not built.

## Update: private per-customer links (no shared dashboard)

`add-business` now generates a random, unguessable `slug` for each
business, and prints its private URL right after you create it:

    python main.py add-business "Konoba Zar" "https://..." --phone "..." --hours "..."
    # -> Private link for this customer (share ONLY with them):
    #    https://YOUR-SITE.vercel.app/issues/<random-token>

That link is the only way to see that business's issues — the website's
`/issues/[slug]` route looks up the business by that token and shows only
its data. Nobody can browse to a generic "/issues" and see everyone; there
is no such page anymore. Two customers, two different links, no overlap.

This is intentionally lighter than real user accounts (no passwords, no
signup) — good enough for a handful of customers you're personally
onboarding. If you outgrow "share a private link manually," proper
login-based accounts are the next step up, but hold off until you actually
need it.
