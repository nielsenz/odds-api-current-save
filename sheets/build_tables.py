# /// script
# requires-python = ">=3.11"
# ///
"""Merge transcribed sheet CSVs, validate them, and write the tables.

    uv run sheets/build_tables.py <transcribed_dir> <label>

<transcribed_dir> holds per-batch CSVs in the long schema in TRANSCRIBE.md. Each row's
`source_file` is `<book>/<UTCSTAMP>/<pdf name>` (the path under sheets/pdfs/); book and
pulled_at_utc come from it. <label> names the outputs (e.g. a date or the pull stamp).

Writes:
    sheets/data/sheet_markets_<label>.csv     every selection (long format)
    sheets/data/sheet_game_lines_<label>.csv  game ML/spread/total per period, in
                                              odds-api's home/away column names
Prints validation problems; exits 1 if any are hard errors.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
LONG_COLS = [
    "source_file", "page", "sport", "sheet_title", "sheet_date", "updated_at", "event_date",
    "event_time_pt", "event", "away_team", "home_team", "period", "market", "rot", "selection",
    "line", "odds", "notes",
]
WIDE_COLS = [
    "date", "sport", "commence_time", "event_time_pt", "home_team", "away_team", "rot_away",
    "rot_home", "period", "bookmaker", "source_file", "sheet_updated_at_pt", "pulled_at_utc",
    "ml_home", "ml_away", "spread_home", "spread_home_odds", "spread_away", "spread_away_odds",
    "total_line", "total_over_odds", "total_under_odds", "notes",
]
PT = ZoneInfo("America/Los_Angeles")


def implied(odds: int) -> float:
    return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)


def num(s: str) -> float | None:
    s = (s or "").strip()
    return float(s) if s else None


def load(transcribed: Path) -> list[dict]:
    rows = []
    for f in sorted(transcribed.glob("*.csv")):
        with f.open(newline="") as fh:
            reader = csv.DictReader(fh)
            missing = set(LONG_COLS) - set(reader.fieldnames or [])
            if missing:
                sys.exit(f"{f.name}: missing columns {sorted(missing)}")
            for r in reader:
                rows.append({c: (r.get(c) or "").strip() for c in LONG_COLS} | {"_batch": f.stem})
    return rows


def validate(rows: list[dict]) -> tuple[list[str], list[str]]:
    errors, warns = [], []
    seen = set()
    for r in rows:
        key = tuple(r[c] for c in LONG_COLS if c != "notes")
        if key in seen:
            warns.append(f"duplicate row: {r['source_file']} {r['event']} {r['market']} {r['selection']}")
        seen.add(key)
        try:
            if r["odds"]:
                o = int(r["odds"])
                if -100 < o < 100:
                    errors.append(f"odds between -100 and 100: {r['source_file']} {r['event']} {r['market']} {r['selection']} {o}")
            if r["line"]:
                float(r["line"])
        except ValueError:
            errors.append(f"non-numeric odds/line: {r['source_file']} {r['event']} {r['market']} {r['selection']} {r['line']!r} {r['odds']!r}")
    # paired two-way game markets
    groups = defaultdict(list)
    for r in rows:
        if r["home_team"] and r["market"] in ("moneyline", "spread", "total") and r["odds"]:
            groups[(r["source_file"], r["event"], r["event_date"], r["period"], r["market"])].append(r)
    for (src, ev, _, per, mkt), g in groups.items():
        tag = f"{src} | {ev} | {per} {mkt}"
        if len(g) != 2:
            warns.append(f"{tag}: {len(g)} rows (expected 2)")
            continue
        a, b = g
        try:
            ia, ib = implied(int(a["odds"])), implied(int(b["odds"]))
        except ValueError:
            continue
        hold = ia + ib - 1
        if not (-0.005 <= hold <= 0.12):
            errors.append(f"{tag}: implied sum {ia + ib:.3f} ({a['odds']}/{b['odds']})")
        la, lb = num(a["line"]), num(b["line"])
        if mkt == "spread" and la is not None and lb is not None and la != -lb:
            errors.append(f"{tag}: spreads not mirrored ({la}/{lb})")
        if mkt == "total":
            if la != lb:
                errors.append(f"{tag}: totals differ ({la}/{lb})")
            if {a["selection"].lower(), b["selection"].lower()} != {"over", "under"}:
                errors.append(f"{tag}: total selections {a['selection']}/{b['selection']}")
    return errors, warns


def source_meta(src: str) -> tuple[str, str]:
    """(book, pulled_at_utc) from `<book>/<YYYYMMDDTHHMMSSZ>/<name>`."""
    parts = src.split("/")
    if len(parts) >= 3 and parts[0] in ("circa", "southpoint"):
        ts = datetime.strptime(parts[1], "%Y%m%dT%H%M%SZ").strftime("%Y-%m-%dT%H:%M:%SZ")
        return parts[0], ts
    sys.exit(f"source_file must be <book>/<UTCSTAMP>/<name>: {src!r}")


def wide(rows: list[dict]) -> list[dict]:
    games: dict[tuple, dict] = {}
    for r in rows:
        if not r["home_team"] or r["market"] not in ("moneyline", "spread", "total"):
            continue
        k = (r["source_file"], r["event_date"], r["away_team"], r["home_team"], r["period"])
        g = games.setdefault(k, {c: "" for c in WIDE_COLS})
        commence = ""
        if r["event_date"] and r["event_time_pt"]:
            dt = datetime.fromisoformat(f"{r['event_date']}T{r['event_time_pt']}").replace(tzinfo=PT)
            commence = dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        g.update(
            date=r["event_date"], sport=r["sport"], commence_time=commence,
            event_time_pt=r["event_time_pt"], home_team=r["home_team"], away_team=r["away_team"],
            period=r["period"], bookmaker=source_meta(r["source_file"])[0], source_file=r["source_file"],
            sheet_updated_at_pt=r["updated_at"], pulled_at_utc=source_meta(r["source_file"])[1],
        )
        side = "home" if r["selection"] == r["home_team"] else "away" if r["selection"] == r["away_team"] else ""
        if r["market"] == "moneyline" and side:
            g[f"ml_{side}"] = r["odds"]
            if r["rot"]:
                g[f"rot_{side}"] = r["rot"]
        elif r["market"] == "spread" and side:
            g[f"spread_{side}"], g[f"spread_{side}_odds"] = r["line"], r["odds"]
            if r["rot"] and not g[f"rot_{side}"]:
                g[f"rot_{side}"] = r["rot"]
        elif r["market"] == "total" and r["selection"].lower() in ("over", "under"):
            g["total_line"] = r["line"]
            g[f"total_{r['selection'].lower()}_odds"] = r["odds"]
        if "ou_order_assumed" in r["notes"] and "ou_order_assumed" not in g["notes"]:
            g["notes"] = (g["notes"] + ";ou_order_assumed").lstrip(";")
    return sorted(games.values(), key=lambda g: (g["sport"], g["date"], g["commence_time"], g["rot_away"], g["period"]))


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    transcribed, label = Path(sys.argv[1]), sys.argv[2]
    rows = load(transcribed)
    errors, warns = validate(rows)

    out_dir = HERE / "data"
    out_dir.mkdir(exist_ok=True)
    with (out_dir / f"sheet_markets_{label}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["book", "pulled_at_utc", *LONG_COLS])
        w.writeheader()
        for r in rows:
            book, pulled_at = source_meta(r["source_file"])
            w.writerow({"book": book, "pulled_at_utc": pulled_at, **{c: r[c] for c in LONG_COLS}})
    games = wide(rows)
    with (out_dir / f"sheet_game_lines_{label}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=WIDE_COLS)
        w.writeheader()
        w.writerows(games)

    by = defaultdict(int)
    for r in rows:
        by[(r["sport"], r["source_file"])] += 1
    for (sport, src), n in sorted(by.items()):
        print(f"{sport:5} {n:5}  {src}")
    print(f"{len(rows)} market rows, {len(games)} game-period rows")
    for e in errors:
        print("ERROR", e)
    for wmsg in warns:
        print("WARN ", wmsg)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
