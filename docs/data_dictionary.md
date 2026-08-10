# Data Dictionary

*Last updated: August 2026*

This document explains what the data **means** — the 22 ecosystem services, the R/E/S paradigm, what each classification field is, and where the numbers on the dashboard come from.

For field-by-field table/column definitions (types, constraints, which table something lives in), see `data_schema_supplement.md`. This document is about meaning, not schema.

---

## 1. The 22 ecosystem services

Every paper is checked against this list. It comes from Costanza et al. (1997) plus IPBES extensions, and groups into four families.

### Provisioning — products people get from ecosystems

| Service | Meaning |
|---|---|
| Biodiversity | The number of different species |
| Food | Ingredients from wild or domesticated habitats |
| Potable Water | Fresh water safe to drink |
| Fuel | Materials used to generate energy |
| Fibre/Hide/Wood | Materials used for clothing or construction |
| Biochemicals | Molecules used in medicine |

### Regulating — benefits from ecosystems regulating natural processes

| Service | Meaning |
|---|---|
| Atmospheric Regulation | Production/consumption of essential molecules (e.g. oxygen) |
| Climate Regulation | Stabilizing climatic conditions |
| Coastline Regulation | Stabilizing coastal land (e.g. mangroves, reefs) |
| Disease Regulation | Natural systems that reduce disease or disease vectors |
| Water Regulation | Timing and volume of water distribution across land |
| Waste Treatment | Filtering/treating waste (including organics and water) |
| Pollination | Distributing pollen for plant reproduction |

### Supporting — services other services depend on

| Service | Meaning |
|---|---|
| Primary Production | Creating sugars from sunlight |
| Soil Formation | Creating new soil |
| Nutrient Cycling | Moving nutrients through an ecosystem |

### Cultural — benefits to quality of life and community

| Service | Meaning |
|---|---|
| Inspiration/Education | Art, music, literature, architecture, engineering design |
| Aesthetic | Mental/physical health benefits of natural beauty |
| Recreation | Supporting people's physical and mental health |
| Cultural Heritage | Value placed on landscapes |
| Spiritual | Supporting people's spiritual lives |
| Cultural Identity | Societal identity shaped by an ecosystem (e.g. nomadic herding) |

This exact list is a whitelist enforced in code (`SERVICES_DEF` in `aggregate.py`, `_ALL_SERVICES` in `explorer.py`). A paper's `ecosystem_service` value must be one of these 22 — see [Section 6](#6-known-data-quality-notes) for what happens when the model outputs something else.

---

## 2. The R/E/S paradigm (Replace / Enhance / Support)

For every paper the model says "yes" to (see Section 3), it also decides *how* the technology relates to the natural process:

| Category | Meaning | Example |
|---|---|---|
| **Support** | Assists or maintains an existing natural process, without intensifying it | Adding baffles so river flow still scours sediment, just a little more efficiently |
| **Enhance** | Significantly boosts the efficiency or scale of a natural process, but still depends on that process | Embedding enzymes in a filter to double the nitrification rate — still needs the microbes |
| **Replace** | Creates an artificial substitute that works independently of the natural process | A photocatalytic panel that fixes nitrogen from air, with no biological process involved |

If a case is genuinely ambiguous between Enhance and Replace, the model is instructed to pick Enhance.

This is the platform's central finding lens: **Replace**-heavy fields (materials science, chemistry) dominate the corpus, while genuinely ecological fields barely appear — see the narrative page for the full argument.

---

## 3. Classification fields

Every paper gets these fields from the LLM (see `prompt_specification.md` for the exact prompt):

| Field | Meaning | Possible values |
|---|---|---|
| `decision` | Does this paper describe a technology that contributes to at least one ecosystem service? | `Y` / `N` |
| `category` | The R/E/S paradigm (Section 2) | `Replace` / `Enhance` / `Support`, blank if `decision = N` |
| `ecosystem_service` | Which of the 22 services (Section 1) | One of the 22, blank if `decision = N` |
| `technology` | Free-text label for the technology described | Short phrase, e.g. "soft robotic gripper" |
| `review_flag` | Is this a review/survey paper, not original research? | `review` or blank |
| `confidence` | How sure the model is about its own answer | `high` / `medium` / `low` |

`review_flag` is set whenever the abstract signals a review, survey, or meta-analysis. Review papers are excluded from the target corpus regardless of their `decision` value (see Section 5).

---

## 4. Confidence and what happens to each level

The model reports its own confidence on every classification. This isn't just a label — it decides what happens to the paper next:

| Confidence | What it means | What happens |
|---|---|---|
| **High** | Clearly matches one service; the R/E/S category is obvious | Written to the database automatically |
| **Medium** | Reasonable but not certain — more than one service could apply, or the category is a judgment call | Sent to a human review sheet |
| **Low** | Only vaguely related, or not enough evidence in the abstract | Sent to a human review sheet |

A failed API call or a response that couldn't be parsed as JSON is treated the same as "low confidence" — it goes to the review sheet, not silently dropped.

### Review status and reviewer overrides

Once a paper reaches the database, its `review_status` (tracked in the Google review sheet, not the database — see `handover.md`) is one of:

- `auto_high_confidence` — the model's answer, never seen by a person.
- `human_reviewed` — a person looked at it. A reviewer can independently correct any of four fields: `decision`, `category`, `ecosystem_service`, `technology`. Leaving a field blank means "confirmed as-is"; filling it in overrides just that field, not the whole row.

---

## 5. The corpus, in numbers

The platform tracks two different "corpus" numbers — see `architecture.md` Section 3.3 for why they're allowed to diverge.

**The original published corpus** (`dataset_id = 1`, what the narrative page shows, frozen):

| Number | Count |
|---|---|
| Total papers (WoS export, 2004–2025) | 68,917 |
| Non-review papers | 59,599 |
| Decision = Y, non-review (the "target corpus") | 31,559 |
| — Replace | 18,248 |
| — Enhance | 12,290 |
| — Support | 1,021 |

**The live corpus** (everything currently in the database, what the Explorer shows): grows over time as `run_pipeline.py` adds new papers. No fixed numbers to quote — query the database or check the Explorer's live count.

"Target corpus" means: non-review papers where the model said `decision = Y` and the `ecosystem_service` is one of the 22 whitelisted services.

---

## 6. Known data quality notes

- **Two hallucinated service values were filtered out.** Early classification runs produced `"Cultural"` and `"Ecosystem monitoring"` as `ecosystem_service` values — neither is one of the 22 services. Both filtered out by the whitelist. Both happened to be review papers, so they'd have been excluded anyway by the `is_review = FALSE` filter.
- **4.1% of papers have no DOI.** This is why `wos_id`, not DOI, is the primary key everywhere.
- **Funding agency matching covers about 74% of papers that report funding.** Funding text is free-form in the raw WoS export; it's matched against a whitelist of ~60 known funders. Unmatched funding text isn't shown as an error — it's just not included in the `funding_agencies` filter.

---

## 7. Technology clusters

Every classified paper gets a free-text `technology` label (Section 3) and, separately, a `technology_cluster` — one of **25 canonical categories** that groups similar technologies together (e.g. many different `technology` phrases about drone flight all land in the same cluster).

These two things were built differently, and it matters for anyone maintaining this going forward:

### How the original 25 clusters were created

This was a one-time, manual process, done locally, not something the pipeline re-runs:

1. Every paper's `technology` phrase was embedded and run through BERTopic (a clustering algorithm).
2. A person looked at each resulting cluster's contents and manually assigned it a readable name (`canonical_name`) — e.g. deciding that a cluster full of phrases like "soft actuator," "octopus-inspired gripper," "pneumatic muscle" should be called `"Bio-Applied"`.
3. Those 25 canonical names, and which papers belong to which, were written into the database.

The centroid embeddings from that original run were **not saved anywhere** — only the final cluster assignments survived. This matters for the next part.

### How NEW papers get assigned a cluster

Re-running the manual process above for every new paper isn't practical — it needs a person to look at cluster contents and possibly invent new names. So new papers are assigned automatically, without a human step, using **nearest-centroid matching**:

1. Every time this step runs, it recomputes the 25 clusters' centroid embeddings **fresh**, from whichever papers are currently labeled with each cluster (cheap to do — there's no saved centroid file to keep in sync).
2. Any paper that doesn't yet have a cluster gets its `technology` phrase embedded and compared to all 25 centroids.
3. It's assigned to the nearest one, by cosine similarity. No human involved.

**This means new papers are never used to invent a 26th cluster.** If a genuinely new kind of technology shows up that doesn't resemble any of the 25 existing clusters, it still gets forced into the closest one. There's no threshold that blocks this — a low-similarity match still gets assigned, just logged as low-confidence in the pipeline's output for a maintainer to notice if they're watching. If the 25 clusters start feeling stale or a genuinely new category keeps showing up in the "low confidence" log, that's a signal it may be time to repeat the original manual process (step 1 above) — not something the pipeline will decide on its own.

Existing papers' cluster assignments are never touched by this — only papers with no assignment yet get one.
