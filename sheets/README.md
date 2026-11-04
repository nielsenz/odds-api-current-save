# Book sheets (Circa Sports, South Point)

The opening and current betting sheets that two Las Vegas books publish as PDFs:

- **Circa Sports**: a shared Dropbox folder (game sheets per sport and day, overnights, futures,
  props, plus an older `Circa Sports sheets/` subfolder kept as `archive/`).
- **South Point**: PDFs embedded on <https://southpointcasino.com/casino/sports-book>, mostly
  futures (NFL, NHL, NBA, CFB, NCAA men's basketball, CFP, Super Bowl, soccer, golf).

Circa draws every glyph as a vector outline, so the PDFs have no text layer and
pdftotext/pdfplumber return nothing. The PDFs are **downloaded daily on Fly** and **translated in
bulk on the Mac** by vision agents.

## Daily download (Fly)

Fly job `book_sheets` on `nhl-collectors` (nhl repo, `betting-tracking/cloud/collectors/jobs/`)
runs at 09:07 Pacific. It downloads both books, skips any PDF whose sha256 was already archived,
and uploads the rest to release assets on this repo:

| Release | Holds |
|---|---|
| `sheets-manifest` | `manifest.csv`: sha256, book, pulled_at_utc, source_name, source_url, bytes, release_tag, asset_name |
| `sheets-<year>-W<week>` | the PDFs, named `<book>__<YYYYMMDDTHHMMSSZ>__<slug>.pdf` |

Release assets keep the PDFs out of git history: a full Circa pull is about 32 MB of current
sheets (plus about 20 MB of archive files that never change), so committing changed PDFs could reach
several GB a year. Nothing is kept on the Fly volume. Failures comment on hl-analysis issue #290.
The job's token needs **Contents** write on this repo.

## Bulk translation (Mac)

```sh
uv run sheets/pull_sheets.py --since 2026-11-04            # -> sheets/pdfs/<book>/<stamp>/...
uv run sheets/render_sheets.py "$TMPDIR/sheets_render" sheets/pdfs/circa/<stamp> \
    --match 'NHL|NFL|CFB|CBK|NCAA'                          # pages + 800 px strips
```

Then hand the strips to agents in parallel batches of about 12–24 strips each. Each agent gets
`sheets/TRANSCRIBE.md` (the schema, layout hints and self-check), the render dir as `RENDER`, a batch
name and its page list, and writes `$RENDER/transcribed/<batch>.csv`. Merge and validate:

```sh
uv run sheets/build_tables.py "$RENDER/transcribed" <label>
cp -r "$RENDER/transcribed" sheets/transcribed/<label>       # keep the raw batches
```

`build_tables.py` exits 1 on hard errors (non-numeric odds, unmirrored spreads, total lines that
disagree, or a two-way market's implied probabilities summing outside 0.995–1.12) and lists
unpaired markets as warnings. Spot-check a few games against the page images before using a run.

## Outputs (`data/`)

- `sheet_markets_<label>.csv`: every selection, long format: `book, pulled_at_utc, source_file,
  page, sport, sheet_title, sheet_date, updated_at, event_date, event_time_pt, event, away_team,
  home_team, period, market, rot, selection, line, odds, notes`.
- `sheet_game_lines_<label>.csv`: one row per game and period with odds-api's columns
  (`ml_home, ml_away, spread_home, …, total_under_odds`), `commence_time` in UTC (converted from the
  sheet's Pacific time), the rotation numbers and `bookmaker` = book.

Caveats:
- Team names are as printed (`CAPITALS`, `Inidanapolis COLTS`), not normalised to odds-api names.
- When a sheet doesn't label over/under, the top juice is taken as over (`ou_order_assumed`).
- Football and basketball sheets print the spread only on the favourite's row, so the underdog's is
  mirrored (`dog_line_from_fav`). Totals and spreads without printed juice are -110 (`implied_-110`).
- `updated_at` is the sheet's own "Updated" stamp (Pacific). `pulled_at_utc` is when it was downloaded.

## Runs

| Label | Pull | Scope | Rows |
|---|---|---|---|
| `circa_20261104T051714Z` | Circa, manual download Nov 3, 2026 21:17 PT | NHL, NFL, CFB, college basketball (current + archive) | 4,151 market rows, 167 game-period rows |

Not yet translated from that pull: golf, tennis, soccer, UFC, F1, NASCAR, MLB, NBA, WNBA, limits.
