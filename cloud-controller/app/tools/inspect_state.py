"""Ad-hoc consistency inspection helper (also handy during the lab demo).

Usage:
    python -m app.tools.inspect_state            # uses the current .env
    python -m app.tools.inspect_state --db x.db

It prints:
  * SQLite row counts (users, files, audit events)
  * whether audit details contain anything that looks like a secret
  * whether the metadata file size matches the object stored in the adapter
  * whether any file row has no corresponding object (orphan metadata)
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

SECRET_PATTERNS = [
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}"),      # JWT-ish
    re.compile(r"\$argon2"),
    re.compile(r"\$2[aby]\$"),
    re.compile(r"(?i)password\s*[=:]"),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)

    from app.core.config import get_settings
    from app.services.hdfs_service import build_hdfs_service

    settings = get_settings()
    db_path = args.db or settings.database_url.replace("sqlite:///", "")
    path = Path(db_path)
    if not path.is_file():
        print(f"Database not found: {path}", file=sys.stderr)
        return 1

    # Read through plain sqlite3 so this helper does not depend on the ORM.
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    users = con.execute("SELECT username, role FROM users ORDER BY username").fetchall()
    files = con.execute(
        "SELECT id, owner_id, original_name, size_bytes, hdfs_path FROM file_records"
    ).fetchall()
    audit = con.execute(
        "SELECT event_type, detail FROM audit_events ORDER BY created_at DESC LIMIT 200"
    ).fetchall()

    print(f"Database           : {path}")
    print(f"Storage adapter    : {settings.hdfs_adapter}")
    print(f"Users ({len(users)})")
    for row in users:
        print(f"  - {row['username']:<20} role={row['role']}")
    print(f"File rows          : {len(files)}")
    print(f"Audit events (last 200): {len(audit)}")
    print(f"Audit event types  : {sorted({r['event_type'] for r in audit})}")

    leaked = [
        r["event_type"] for r in audit
        if r["detail"] and any(p.search(r["detail"]) for p in SECRET_PATTERNS)
    ]
    print(f"Audit details that look like secrets: {leaked or 'none'}")

    hdfs = build_hdfs_service(settings)
    missing, mismatched = [], []
    for row in files:
        try:
            if not hdfs.exists(row["hdfs_path"]):
                missing.append(row["id"])
                continue
            parent = row["hdfs_path"].rsplit("/", 1)[0]
            entries = hdfs.list_status(parent)
            actual = next((e["size"] for e in entries
                           if e["path"] == row["hdfs_path"]), None)
            if actual is not None and actual != row["size_bytes"]:
                mismatched.append((row["id"], row["size_bytes"], actual))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! could not check {row['id']}: {exc}")

    print(f"Objects missing in storage : {missing or 'none'}")
    print(f"Size mismatches            : {mismatched or 'none'}")
    if settings.is_mock_hdfs:
        print("NOTE: mock adapter active - these objects are on local disk, "
              "not in HDFS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
