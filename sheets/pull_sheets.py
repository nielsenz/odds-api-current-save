# /// script
# requires-python = ">=3.11"
# ///
"""Pull archived sheet PDFs from GitHub release assets into sheets/pdfs/.

The Fly job `book_sheets` (nhl repo, betting-tracking/cloud/collectors) uploads Circa Sports
and South Point PDFs once a day at 09:07 Pacific. This copies any you don't have yet to
    sheets/pdfs/<book>/<pulled_at stamp>/<source name>
and prints the new paths, ready for render_sheets.py.

    uv run sheets/pull_sheets.py [--since 2026-11-01] [--book circa]
"""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = "nielsenz/odds-api-current-save"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--since", help="only pulls on or after this UTC date (YYYY-MM-DD)")
    ap.add_argument("--book", choices=["circa", "southpoint"])
    ap.add_argument("--dest", type=Path, default=HERE / "pdfs")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        subprocess.run(["gh", "release", "download", "sheets-manifest", "--repo", args.repo,
                        "--pattern", "manifest.csv", "--dir", td], check=True)
        rows = list(csv.DictReader((tmp / "manifest.csv").open(newline="")))
        todo = defaultdict(list)
        for r in rows:
            if args.since and r["pulled_at_utc"][:10] < args.since:
                continue
            if args.book and r["book"] != args.book:
                continue
            stamp = r["pulled_at_utc"].replace("-", "").replace(":", "")
            out = args.dest / r["book"] / stamp / r["source_name"]
            if not out.exists():
                todo[r["release_tag"]].append((r["asset_name"], out))
        for tag, items in todo.items():
            patterns = [x for a, _ in items for x in ("--pattern", a)]
            subprocess.run(["gh", "release", "download", tag, "--repo", args.repo, "--dir", td,
                            "--clobber", *patterns], check=True)
            for asset, out in items:
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tmp / asset, out)  # copy: two manifest rows may share one asset
                print(out)
    n = sum(len(v) for v in todo.values())
    print(f"{n} new PDFs ({len(rows)} in manifest)")


if __name__ == "__main__":
    main()
