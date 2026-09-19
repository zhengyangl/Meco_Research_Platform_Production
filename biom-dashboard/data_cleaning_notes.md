# BioM Innovation Database — Data Cleaning Notes

Companion documentation for `clean_biom_data.py`. This explains what the
pipeline does to the raw Excel export and why, field by field. Code
comments were kept deliberately minimal — this document is the source of
truth for the reasoning.

---

## Part 1: Manual Data Realignment (done by Julian, outside the pipeline)

Before the pipeline described in this document could run reliably, the
raw Google Sheet export had extensive **column-shift contamination**: for
a meaningful number of rows, one or more cells were left blank somewhere
in the middle of the row, which caused every field after that point to
land one (or more) positions off from where it belonged. This was not a
single, uniform pattern — the starting point and the number of fields
affected varied from row to row.

**Confirmed examples of the pattern** (illustrative, not an exhaustive
log — the full scope of what was corrected was not tracked field-by-field
during the manual review):

- `Continent` held what should have been in `City`; further along the
  same rows, `Telephone` held what should have been in `Continent`.
- Rows in roughly the 217–370 range had `Perceived Level`'s content
  sitting under `Difference between actual and perceived`.
- `Academia or Industry`'s value appeared under a different column
  entirely for a number of rows; corrected by using `case_id` to locate
  the right row and move the value back to the correct field.

**How this was resolved:** Julian manually reviewed and corrected these
cases directly in the source Google Sheet, row by row, using `case_id` to
confirm which row a misplaced value belonged to before moving it back.
This work is not logged at the individual-cell level — there is no
change-by-change audit trail for it. The evidence that the sheet is now
internally consistent comes from the pipeline's own checks after the
fact: `suspected_shifted_rows.csv` (a diagnostic that flags values
matching a neighboring field's whitelist — see Part 2) currently returns
0 rows against the full 510-row dataset, and the structural validation
script (`validate_cleaned_output.py`) confirms row counts, ID uniqueness,
and referential integrity across all output tables.

**What the pipeline itself automated vs. what was manual:** Exactly one
shift pattern was precise and consistent enough to safely auto-correct in
code — `correct_academia_industry_shift()`, triggered specifically when
`Academia or Industry` is blank and `Company or Institution Name` holds
exactly `"Academia"` or `"Industry"` (the only two values that field can
legitimately hold). This was verified field-by-field against real
examples before being automated, and affects roughly 40 of the 510 rows.
Every other instance of misalignment — including all three examples
above — did not follow a single, safely-automatable pattern (different
starting points, different numbers of affected fields, sometimes more
than one blank cell in the same row) and was corrected manually instead.
Automating a "best guess" fix for these would have risked introducing
new, harder-to-detect misalignment, so the decision was to leave them
flagged for manual review rather than guess.

**Recommendation (Julian's, not a pipeline conclusion):** future updates
to this dataset should be based on the cleaned output of this pipeline
(`cases.csv` and the four child tables), not by continuing to layer new
entries onto the original raw sheet. Given how extensively the original
sheet was contaminated, continuing to build directly on it going forward
is not considered worthwhile.

---

## Part 2: Field-by-Field Cleaning Rules

### 2.1 Fields excluded entirely

**Dropped as PII** (`PII_FIELDS_TO_DROP`) — real interviewee contact
information, never meant for a public-facing output:

- Contact Name
- Address
- Telephone
- Email
- Interviewee Name and Expertise

**Dropped as internal/out-of-scope** (`INTERNAL_METHODOLOGY_FIELDS`) —
interview-process bookkeeping, geographic detail finer than
Country/Continent, and free-text linguistic-analysis fields not meant for
public display:

- All `Interview: *` fields (Date, Type, Product Phase, Concept/
  Prototype/Commercial Year, Patent Year(s), Mimic, Process Type,
  Disciplines Involved)
- Perceived Level
- Difference between actual and perceived
- Number of models previously explored
- Novel Solution
- Impact on Field
- Was a biologist on the team?
- Multidisciplinary Challenges?
- In-Depth Interview?
- Notification of Database Availability?
- Interview & General Notes
- Outcome
- Developer Name(s)
- Product Biomimetic Phrase
- City
- Copy of Patent in Dropbox Folder (values found didn't match the
  field's intended Yes/No/N/A shape and were judged unreliable)

**Kept, despite being considered for exclusion:** `Product Name` and
`Product Description`. These are the primary human-readable identifiers
for each case — used as the display title / detail content in the
dashboard — so they stay in the output even though they need light
cleaning (see 2.2).

### 2.2 Product Name / Product Description

Light cleaning only: strips stray whitespace, treats a whitespace-only
cell as blank. `Product Name` is genuinely missing for a meaningful
share of rows (confirmed against real data).

A derived `display_name` column is added for dashboard use:
1. Real `Product Name` if present.
2. Otherwise, a fallback built from `Mimic` (`"<Mimic>-inspired design"`).
3. Otherwise, a fallback built from `Company or Institution Name`
   (`"<Company> project"`).
4. Otherwise, `"Untitled case"`.

`Product Name` itself is never overwritten — it stays genuinely blank
where it's genuinely blank. `display_name` is purely a UI-facing field.

### 2.3 Case identifier

The source sheet's first column has a blank header (reads as `Unnamed:
0` in pandas) rather than a labeled `Case Number` column — this is
treated as the real case identifier and renamed to `case_id`, rather
than generating a new sequential ID that would duplicate it.

`case_id` is cast to pandas' nullable `Int64` dtype specifically to avoid
displaying as `"5001.0"` instead of `"5001"` — a side effect of any
single missing value elsewhere in the column forcing the whole column to
float64 by default.

### 2.4 Multi-value fields — split into child tables

| Source field(s) | Output table | Notes |
|---|---|---|
| `Disciplines involved` | `case_disciplines` (`case_id`, `discipline`) | newline-separated |
| `Keywords` | `case_keywords` (`case_id`, `keyword`, `keyword_type='product'`) | newline-separated |
| `Patent Keywords` | `case_keywords` (`keyword_type='patent'`) | newline-separated |
| `Patent Year(s)` + `Patent Number(s)` | `case_patents` (`case_id`, `patent_year`, `patent_year_raw`, `patent_year_qualifier`, `patent_number`) | **positionally paired** — see 2.5 |
| `Which one?` | `case_ecosystem_services` (`case_id`, `ecosystem_service`) | comma-separated (discovered from real data — not newline like the others) |

### 2.5 Patent Year(s) / Patent Number(s) pairing

These two fields are positionally paired (the Nth year corresponds to
the Nth patent number) but can have **mismatched lengths** — a patent
number recorded with no matching year, or vice versa. When lengths
differ, the pipeline pairs up to the shorter list's length and flags the
row (with its `case_id`) for manual verification rather than guessing
which entries correspond. As of the most recent full run, 3 rows
(`case_id` 27, 134, 320) have this mismatch and are still open.

`patent_year_raw` holds the original text; `patent_year` is the parsed
year (see 2.7); `patent_year_qualifier` marks `"approximate"` or
`"expected"` where relevant.

### 2.6 `Which one?` / `Is this an Ecosystem Service` cross-check

`Which one?` should only be filled in when `Is this an Ecosystem
Service` is `Yes`. The pipeline flags any row where `Which one?` has a
value but `Is this an Ecosystem Service` is not `Yes` — as of the most
recent run, 5 rows are flagged this way and still need manual review.
The literal text `"None"` in `Which one?` is treated as blank, not as a
service name.

### 2.7 Year fields

Applies to `Concept Year`, `Prototype Year`, `Commercial Year`, and
(separately) the patent years extracted in 2.5. Each source column is
replaced with three: `{field}_year` (parsed, nullable integer),
`{field}_year_raw` (original text, untouched), `{field}_year_qualifier`
(`"approximate"` / `"expected"` / blank).

Parsing rules:
- A range (`"1995/1996"`, `"1995-96"`) → the **earlier** year.
- A decade with a modifier: `early` = decade+2, `mid` = decade+5, `late`
  = decade+8, no modifier = decade+0 (e.g. `"late 90s"` → 1998,
  `"early 70s"` → 1972, `"1970s"` → 1970).
- `"Expected <month> <year>"` → the year, qualifier = `"expected"`.
- `"circa"` / `"ca."` / `"c."` / `"approx"` / `"~"` + a year → the year,
  qualifier = `"approximate"`.
- Anything else (`"N/A"`, `"No Information"`, `"?"`, `"Patent pending"`,
  `"Korean patent"`, etc.) → left blank, original text preserved in
  `_raw`, flagged in the report. **Not guessed at.**

A 2-digit decade shorthand (`"70s"` rather than `"1970s"`) is assumed to
mean 19_0s, not 20_0s — flagged separately as a WARNING so it can be
double-checked rather than trusted silently.

As of the most recent full run: Concept Year has 3 unparseable values,
Prototype Year 18, Commercial Year 48, and patent years 91 — these are
genuine gaps in the source data (the year was never recorded), not a
parsing-rule gap.

### 2.8 Yes/No fields

`YES_NO_FIELDS` are normalized to `True` / `False` / blank, recognizing
common variants (`"Y"`, `"TRUE"`, `"1"`, etc.) case-insensitively. A
value that doesn't match any recognized form is left as-is (not
coerced) and flagged as an ERROR.

`FIELD_SPECIFIC_NA_OVERRIDES` handles a small number of confirmed messy
values, scoped to one specific field rather than loosening the global
Yes/No parsing — currently just `Innovator?`, for three exact values
(`"No?"`, `"No - uses Claus Mattheck software"`, `"No? Building uses
the swarm intelligence software."`), all treated as unknown/NA (not
coerced to `False`, since e.g. `"No?"` carries genuine uncertainty in
the original data).

### 2.9 BioM Type

Raw values are pre-combined strings (e.g. `"Form, and Process"`) rather
than a true multi-select. Split into four boolean columns —
`biom_type_function`, `biom_type_form`, `biom_type_process`,
`biom_type_interaction` — plus `biom_type_na`, tracked **separately**
from "no components apply" (a blank/`N/A` original value is not the
same as a value that genuinely selected none of the four components).

### 2.10 Controlled-vocabulary (whitelist) fields

The following fields are validated against an exact whitelist. Casing
differences are auto-corrected first (`normalize_whitelist_case` — e.g.
`"Biology to design"` → `"Biology to Design"`); a value that still
doesn't match after that is flagged as an ERROR, never guessed at or
silently dropped:

- `Case Status`, `Product Phase`, `Kingdom`, `Group`, `Phylum`,
  `Mimic System`, `Mimic Subsystem`, `Mimic Suprasystem`, `Process
  Type`, `Continent`, `BioM Intensity`

**Confirmed-bad values, blanked rather than kept as errors**
(`WHITELIST_BLANK_VALUES`) — reviewed and confirmed as genuine anomalies,
not a gap in the whitelist itself:

| Field | Blanked value(s) | Why |
|---|---|---|
| Kingdom | Viridae | Not one of the 5 traditional kingdoms |
| Group | Bacteria, Viruses | Not part of the confirmed Group whitelist |
| Phylum | Actinopoda, Alveolata, Bacillariophyta, Basidiomycota | Whitelist re-confirmed unchanged; these 4 are genuine anomalies |
| Mimic Suprasystem | Taxa | Not part of the shared 11-level organization whitelist |

**Continent — multi-country contamination:** a semicolon-joined list of
countries occasionally appears instead of a single continent (e.g.
`"Argentina; Chile; Netherlands; Brazil"`). Any `Continent` value
containing `;` is blanked (matched generally, not as one exact string,
since other rows could have a similar but different multi-country
value).

### 2.11 Suspected-shift diagnostic (never modifies data)

Separate from the one automated correction in Part 1,
`diagnose_shifted_rows()` flags rows where a whitelist-checked field's
value exactly matches a *neighboring* field's whitelist (e.g. `Kingdom`
containing a Yes/No value, or `Group` containing a Kingdom value) — a
signal that the row may still have unresolved misalignment. It also
flags Yes/No fields containing long, clearly-non-Yes/No text (possible
bleed-through from a neighboring free-text field). This never modifies
any data — it only writes `suspected_shifted_rows.csv` for manual
review. As of the most recent full run, this returns 0 rows.

---

## Output files

| File | Grain | Key columns |
|---|---|---|
| `cases.csv` | one row per case | `case_id`, `display_name`, all single-valued fields, `biom_type_*`, `{field}_year`/`_year_raw`/`_year_qualifier` ×3 |
| `case_disciplines.csv` | one row per (case, discipline) | `case_id`, `discipline` |
| `case_keywords.csv` | one row per (case, keyword) | `case_id`, `keyword`, `keyword_type` |
| `case_patents.csv` | one row per (case, patent) | `case_id`, `patent_year`, `patent_year_raw`, `patent_year_qualifier`, `patent_number` |
| `case_ecosystem_services.csv` | one row per (case, service) | `case_id`, `ecosystem_service` |
| `suspected_shifted_rows.csv` | one row per flagged anomaly | `case_id`, `field`, `value_found`, `matches_whitelist_of`, `confidence` |

`case_id` in every child table is guaranteed (by `validate_cleaned_output.py`)
to reference a row that exists in `cases.csv`.
