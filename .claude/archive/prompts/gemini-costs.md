# Task: the cost catalogue (cost-sources) into gemini's docs, checked and structured; no other change

## 0. Context and rules

- This is a new session. Read `AGENTS.md` and `.claude/docs/conventions.md` first and follow them.
- Repository: `/Users/sahand/Desktop/geomind-spe-geohackathon-2026/gemini`, remote `git@github.com:geomind-spe-geohackathon-2026/gemini.git`. `git fetch --prune`, `git checkout dev`, `git pull origin dev`, `git status` clean.
- **Branch:** `git checkout -b docs/cost-sources` from `dev`. At the end, if the development tests pass: merge into `dev` with `--no-ff`, push `origin dev`, delete the branch locally (and on `origin` if it was pushed).
- **Scope: documentation only.** Nothing in `gemini/`, `inputs/`, `examples/`, `tests/` (except the one docs test below) or any result changes. No value in any case file changes.
- **Source material (read-only, outside the repo):** `/Users/sahand/Desktop/geomind-spe-geohackathon-2026/docs/cost-sources/` holds `sources.csv` (74 rows: value, unit, source, publisher, year, page, verbatim quote, conversion, status verified / secondary / placeholder), `README.md`, Danish Energy Agency technology-catalogue PDFs and Excel files, `eurostat_prc_hicp_aind_EA_CP00.json` (euro-area HICP) and `ember_yearly_EU_CO2_intensity.csv`. Never change that folder.
- The catalogue is reference data for any gemini project: never read by `gemini/` code, never a default.
- **Temporary files** go to `.tmp/costs/` (git-ignored).
- Work yourself or with at most two subagents (sonnet for checking, haiku for reading); keep your own context small.

## 1. Check every row (no repo change)

- For every row with status `verified` or `secondary`, check against the local PDF, Excel or data file (or the quoted URL) that the value, unit, price year and quote match. Write `.tmp/costs/check.md`: row, OK / mismatch (what the source really says) / cannot open.
- Recompute every conversion to price year 2015 with the local euro-area HICP (2015 = 100): `value_2015 = value_year * 100 / HICP(year)`. List any row off by more than 0.5 %.
- Flag rows already known to be doubtful: the DEA fixed O&M of 500,000 EUR/MW/yr in table 45.1.a (looks like a catalogue error); the Arpagaus 10-80 K heat-pump lift range (not confirmed); chiller prices (secondary only); the drilling figures are 2013 prices and rise with depth (1,239 / 1,833 / 2,063 EUR/m at 2,300 / 3,000 / 4,000 m).
- A mismatch is corrected in the copy (section 2) and noted in the row; it never silently disappears.

## 2. `docs/cost-sources/` in the repo

```
docs/cost-sources/
  README.md
  sources.csv
  data/
    eurostat_prc_hicp_aind_EA_CP00.json
    ember_yearly_EU_CO2_intensity.csv
```

- `sources.csv`: every row, sorted by group (drilling and wells, pumps, heat pumps, chillers, heat exchangers and coolers, pipes and network, gas treatment, operating costs, energy prices, sale prices, finance, emissions), with columns `id` (stable, short, for example `drilling-nl-2013-3000m`), `group`, `item`, `value`, `unit`, `price_year`, `value_2015`, `unit_2015`, `status`, `source`, `publisher`, `year`, `page`, `url`, `quote`, `conversion`, `path`, `in_case`, `note`. `path` is the key a scenario uses for this value, spelled exactly as in `inputs/examples/hackathon_2026/case.json` (for example `assumptions.finance.capex.pipe`, `assumptions.finance.revenue.heat`, `assumptions.emissions.CO2.electricity`; the source folder's guessed names such as `district_pipe`, `heat_price`, `dry_cooler` are corrected); list any row you cannot match. `in_case` is the value that case file holds today for that path (empty if none), so the gap between the example and the evidence is visible; `case.json` itself is not changed. Units follow gemini's unit spellings. Placeholder rows stay, with status `placeholder` and empty source fields, so the gaps are visible.
- The two data files are copied unchanged, so every conversion and the grid factor can be recomputed from the repo.
- The PDFs and Excel files are not copied (size and licence); every row keeps its public URL.
- `README.md`: what the catalogue is and is not (reference data, not defaults; a project copies the values it uses into its own scenario and cites the `id`); the status meanings; how the 2015 conversion is done; a summary table per group (verified / secondary / placeholder counts and the main values); the known doubtful rows from section 1; the list of source documents with URLs; how to add a row.
- If the docs build scans `docs/`, exclude this folder or make it build cleanly.
- One test: `sources.csv` parses, `id` values are unique, every non-placeholder row has `url` and `quote`, and every `value_2015` matches the HICP conversion within 0.5 %.

## 3. Report (at most 20 lines)

- Commit, the merge into `dev`, the pushed hash; branch removed.
- Rows per status, and per group.
- Every mismatch found in section 1 and what was corrected.
- Confirmation that nothing outside `docs/cost-sources/` and the one test changed.
