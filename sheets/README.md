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
- South Point futures print fractional odds in OPENING and CURRENT columns; `odds` is the current
  price in American, the printed prices are in notes (`opening=`, `current=`). A blank current price
  is skipped (the Grey Cup's eliminated teams). South Point prints no "Updated" stamp.
- `updated_at` is the sheet's own "Updated" stamp (Pacific). `pulled_at_utc` is when it was downloaded.

## Runs

| Label | Pull | Scope | Rows |
|---|---|---|---|
| `circa_20261104T051714Z` | Circa, manual download Nov 3, 2026 21:17 PT | NHL, NFL, CFB, college basketball (current + archive) | 4,151 market rows, 167 game-period rows |
| `southpoint_20261104T054312Z` | South Point, manual download Nov 3, 2026 21:43 PT | all 11 PDFs: CFB and NFL game sheets; NFL, CFB, CFL, NBA, CBB, NHL, UCL, EPL and Masters futures | 841 market rows, 76 game-period rows |
| `circa_20261104T170700Z-20261105T233728Z` | Circa, the first Fly pulls: Nov 4 09:07 PT, Nov 5 09:07 PT, Nov 5 15:37 PT (forced run); 20 new or changed PDFs | NHL (Nov 4, Nov 5 twice) and props, TNF (two pulls), CBK, NBA, soccer and soccer futures, PGA Tour, DP World Tour (two pulls), NASCAR, UFC and boxing, Power Slap, Circa Million VIII week 9 contest lines (`contest_spread`, not wagers) | 4,845 market rows, 355 game-period rows |
| `circa_20261106T170700Z-20261108T170700Z` | Circa, Fly pulls Nov 6, 7 and 8, 2026 at 09:07 PT; 19 of the 30 new or changed PDFs (NHL, NFL, CFB, CBK) | NHL game sheets Nov 6 (two pulls), Nov 7 and Nov 8 with NHL props Nov 7; CBK Nov 6 (plus Extra), Nov 7 and Nov 8 (each with an Extra Games page); NFL week 9 (two pulls), week 10 early lines, week 9 props (two pulls), Bucs vs Bears single-game sheet, week 9 first TD scorer; CFB props Nov 6 and Nov 7 and CFB player props | 5,013 market rows, 393 game-period rows |

Not yet translated from the Nov 3 manual pull (golf, tennis, soccer, UFC, F1, NASCAR, MLB, NBA, WNBA, limits) or from the Nov 6–8 pulls (still in `sheets/pdfs/`: NBA Nov 6–8, DP World Tour, 2027 Masters, tennis, UFC, NASCAR).

Known gaps and doubts in `circa_20261104T170700Z-20261105T233728Z`: CBK Nov 5 p2 says "MORE ON REVERSE" but
the PDF has two pages; five Circa Million games print the higher team number on top, so their
away/home order is as listed (`top_row_has_higher_contest_number`), not confirmed; a few names are
clipped on the sheet (`name_clipped_on_sheet`, `name_truncated`).

Known gaps and doubts in `circa_20261106T170700Z-20261108T170700Z`: `build_tables.py` passed with no warnings; clipped team names kept as printed with `name_clipped_on_sheet` (CBK Extra pages); CBK Nov 7 p2 NC CENTRAL/LONGWOOD prints 11:50 PM, recorded as 23:50 but probably AM; NFL week 9 props print Braelon Allen twice (recorded once) and Jalen Coker as TEN on one page and CAR on the other; several prop team labels are truncated by the column edge. Later pulls of the same sheet (NHL Nov 6, NFL week 9, NFL week 9 props) are kept as separate `source_file` rows with their own `updated_at`.

Transcribed PDFs move to `sheets/archive/pdfs/<book>/<stamp>/` so `sheets/pdfs/` holds only what is
still to do. `pull_sheets.py` only checks `sheets/pdfs/`, so pull with a `--since` after the last
archived stamp or it downloads archived folders again.
