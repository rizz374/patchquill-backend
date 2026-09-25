"""
Patchquill monitor prototype — CLI.

Usage:
  python main.py add-business "Name" "https://example.com"
  python main.py scan <business_id>
  python main.py scan-all
  python main.py issues [--business <id>] [--status open|approved|dismissed]
  python main.py approve <issue_id>
  python main.py dismiss <issue_id>
  python main.py list-businesses

This is a real, working loop: it fetches the URL, saves a snapshot, diffs it
against the previous one, and writes issues with evidence. Run `scan` twice
in a row after editing scan.py's test fixture (or after the real page
changes) to see an issue appear.

For a real background service, wire `scan-all` up to a cron job / scheduled
task instead of running it by hand.
"""

import argparse
import sys

import db
import scan
import compare


def cmd_add_business(args):
    db.init_db()
    result = db.add_business(
        args.name, args.url,
        record_phone=args.phone, record_hours=args.hours, record_address=args.address,
    )
    print(f"Added business #{result['id']}: {args.name} ({args.url})")
    print(f"\n  Private link for this customer (share ONLY with them):")
    print(f"  https://patchquill-onda.vercel.app/issues/{result['slug']}\n")
    if not (args.phone or args.hours or args.address):
        print("  Tip: pass --phone/--hours/--address to also store the "
              "source of truth, so drift can be caught even before the page changes.")


def cmd_list_businesses(args):
    db.init_db()
    rows = db.list_businesses()
    if not rows:
        print("No businesses yet. Add one with `add-business`.")
        return
    for r in rows:
        print(f"#{r['id']}  {r['name']}  —  {r['url']}")


def _scan_one(business_id):
    business = db.get_business(business_id)
    if business is None:
        print(f"No business with id {business_id}", file=sys.stderr)
        return

    print(f"Scanning {business['name']} ({business['url']}) ...")
    try:
        raw_text, phones, hours_text, addresses = scan.run_scan(business["url"])
    except Exception as e:
        print(f"  Scan failed: {e}", file=sys.stderr)
        return

    prev_rows = db.last_two_snapshots(business_id)
    prev_row = prev_rows[0] if len(prev_rows) >= 1 else None  # newest so far, becomes "previous"

    db.save_snapshot(business_id, raw_text, phones, hours_text, addresses)
    new_rows = db.last_two_snapshots(business_id)
    new_row = new_rows[0]  # the one we just inserted

    issues = compare.compare_snapshots(business, prev_row, new_row)
    if prev_row is None:
        print("  Baseline snapshot saved. Nothing to compare yet.")
        return

    if not issues:
        print("  No changes detected.")
        return

    for issue in issues:
        issue_id = db.add_issue(
            business_id,
            issue["field"],
            issue["old_value"],
            issue["new_value"],
            issue["evidence"],
            issue.get("draft_correction"),
            severity=issue.get("severity", "normal"),
            kind=issue.get("kind", "change"),
        )
        print(f"  Issue #{issue_id} [{issue['severity']}/{issue['kind']}/{issue['field']}] — {issue['evidence'][:80]}")


def cmd_scan(args):
    db.init_db()
    _scan_one(args.business_id)


def cmd_scan_all(args):
    db.init_db()
    for biz in db.list_businesses():
        _scan_one(biz["id"])


def cmd_issues(args):
    db.init_db()
    rows = db.list_issues(business_id=args.business, status=args.status)
    if not rows:
        print("No issues match.")
        return
    for r in rows:
        print(f"#{r['id']}  [{r['status']}]  {r['business_name']}  field={r['field']}")
        print(f"    detected: {r['detected_at']}")
        print(f"    evidence: {r['evidence']}")
        if r["draft_correction"]:
            print(f"    draft:    {r['draft_correction']}")
        print()


def cmd_approve(args):
    db.init_db()
    db.set_issue_status(args.issue_id, "approved")
    print(f"Issue #{args.issue_id} approved. "
          f"(Publishing the correction is the next build slice — "
          f"this just records the decision for now.)")


def cmd_dismiss(args):
    db.init_db()
    db.set_issue_status(args.issue_id, "dismissed")
    print(f"Issue #{args.issue_id} dismissed.")


def main():
    parser = argparse.ArgumentParser(description="Patchquill monitor prototype")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add-business")
    p.add_argument("name")
    p.add_argument("url")
    p.add_argument("--phone", default=None, help="The correct phone number (source of truth)")
    p.add_argument("--hours", default=None, help="The correct hours text (source of truth)")
    p.add_argument("--address", default=None, help="The correct address (source of truth)")
    p.set_defaults(func=cmd_add_business)

    p = sub.add_parser("list-businesses")
    p.set_defaults(func=cmd_list_businesses)

    p = sub.add_parser("scan")
    p.add_argument("business_id", type=int)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("scan-all")
    p.set_defaults(func=cmd_scan_all)

    p = sub.add_parser("issues")
    p.add_argument("--business", type=int, default=None)
    p.add_argument("--status", default=None, choices=["open", "approved", "dismissed"])
    p.set_defaults(func=cmd_issues)

    p = sub.add_parser("approve")
    p.add_argument("issue_id", type=int)
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("dismiss")
    p.add_argument("issue_id", type=int)
    p.set_defaults(func=cmd_dismiss)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
