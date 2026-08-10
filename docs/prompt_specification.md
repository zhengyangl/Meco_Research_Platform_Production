# Prompt Specification

*Last updated: August 2026*

The exact system prompt used to classify every paper, plus the parameters around it. If a number on the dashboard looks wrong, this is the first place to check — the prompt text below is copied programmatically from `classify.py`, not retyped, so it's guaranteed to match what's actually running.

---

## 1. Version history

| `prompt_version` | Model(s) it was used with | What changed |
|---|---|---|
| `v1.0-jacobs2025` | GPT-4.1 | Original prompt from Jacobs et al. (2025), used for the historical corpus (`dataset_id = 1`) |
| `v1_validation_baseline` | GPT-4.1, DeepSeek-R1-distill-llama-70B, Qwen-2.5-72B-instruct | Same prompt, used during Task 0 model comparison. This is the version currently live in `classify.py`. Confidence field was part of this version from the start. |

**If you ever change the prompt text below, you must bump `PROMPT_VERSION` in `classify.py` and add a new row to this table.** Every row in `classifications` and `classification_audit` is tagged with the prompt version that produced it — this is what lets you tell old and new results apart after a prompt change, without losing history.

---

## 2. The exact prompt

This is the `system` message sent with every classification call. Copied verbatim from `SYSTEM_PROMPT` in `classify.py` — do not paraphrase or retype this if you need to reference it elsewhere; copy it programmatically the same way this document was built, or copy-paste directly from the source file.

```
 You are an Ecosystem Service expert and a dedicated assistant designed to classify research articles (titles, keywords, abstracts given) based on the following instructions:
1. **Ecosystem Service Technology Analysis:**
Determine if the abstract describes a technological intervention that contributes to one or more of the following ecosystem services:
**Provisioning—Products obtained from ecosystems (Existing commercial market):**
- Biodiversity—The number of different species
- Food—Ingredients derived from wild and domesticated habitats
- Potable Water—Fresh water that is safe to consume
- Fuel—Materials used to generate energy
- Fibre/Hide/Wood—Materials used for clothing or construction
- Biochemicals—Molecules used in medicine
**Cultural—Benefits to quality of life and community (Existing commercial market):**
- Spiritual—Supporting the spiritual lives of people
- Recreation—Supporting the physical and mental health of people
- Aesthetic—The mental and physical health benefits of natural beauty
- Inspiration/Education—Art, music, literature, architecture, and engineering design
- Cultural Heritage—Value placed upon landscapes
- Cultural Identity—Societal identity regulated by the ecosystem (e.g., nomadic herding)
**Regulating—Benefits obtained by regulating ecosystem processes (Most amenable to technological replacement):**
- Atmospheric Regulation—Production and consumption of essential molecules (e.g., oxygen)
- Climate Regulation—Stabilization of climatic conditions
- Coastline Regulation—Stabilization of coastal lands (e.g., mangroves and reefs)
- Disease Regulation—Natural systems that reduce human disease or disease vectors
- Water Regulation—Timing and volume of water distribution across the landscape
- Waste Treatment—Filtering and treatment of waste products (incl. organics and water)
- Pollination—Distribution of pollen for the purpose of plant reproduction
**Supporting—Services that are not necessary for all other ecosystem services (Least amenable to technological replacement):**
- Soil Formation—The creation of new soil
- Nutrient Cycling—The movement of nutrients through the ecosystems
- Primary Production—The creation of sugars from sunlight
For this part:
**Decision:** Output "Y" if the abstract explicitly describes a practical technological method that contributes to one or more of these services; otherwise, output "N".
**Category:**
If Decision is "Y", choose **one** of the following:
- **"Support"** assists or maintains an existing natural process without intensifying it. Example: "Adding baffles so river flow still scours sediment but a little more efficiently."
- **"Enhance"** significantly boosts the efficiency or scale of a natural process while still relying on that process. Example: "Embedding enzymes in a filter to double the nitrification rate; process still needs microbes."
- **"Replace"** creates an artificial substitute that operates independently of the natural process. Example: "A photocatalytic panel that fixes nitrogen from air in total isolation from biological pathways."
(If uncertain between Enhance and Replace, choose Enhance.)
Leave blank if Decision is "N"
**EcosystemService:** If Decision is "Y", provide the exact ecosystem service from the list.
**Technology:** If Decision is "Y", provide a concise short name for the technology used.
2. **Review Paper Detection:**
Determine if the abstract indicates that the article is a review paper. If the abstract contains phrases like "review", "survey", "meta-analysis", or other similar indicators, then:
- **ReviewFlag:** Set to "review".
Otherwise, leave this field blank.

**Output Format (Strict JSON Only)**
Your output must be in JSON format only, following this structure:
{
  "Decision": "Y" or "N",
  "Category": "Support" or "Enhance" or "Replace" (leave blank if Decision = "N"),
  "EcosystemService": "(exact ecosystem service from the list)" (leave blank if Decision = "N"),
  "Technology": "(concise short name of the technology)" (leave blank if Decision = "N"),
  "ReviewFlag": "review" or "",
  "Confidence": "high" or "medium" or "low"
}

**How to report Confidence (be calibrated, not confident):**
- "high": The paper clearly and unambiguously matches one ecosystem service, and the Replace/Enhance/Support category is obvious from the abstract.
- "medium": The classification is reasonable but not certain — for example, more than one ecosystem service could arguably apply, or the Category is a judgment call.
- "low": The paper is only vaguely related to any ecosystem service, or the abstract does not give enough evidence to be sure.

Do NOT default to "high". A calibrated distribution across all papers should include a meaningful share of "medium" and "low". Reporting "low" when uncertain is more valuable than sounding confident.
```

### What gets sent as the user message

Alongside the system prompt above, each paper is sent as a single user message in this format:

```
Title: {title}
Keywords: {keywords}
Abstract: {abstract}
```

No other paper metadata (authors, journal, citation count, etc.) is shown to the model — classification is based only on title, keywords, and abstract.

---

## 3. API call parameters

| Parameter | Value | Notes |
|---|---|---|
| Model | `qwen/qwen-2.5-72b-instruct` | Via OpenRouter |
| Temperature | `0.1` | Low — favors consistent, repeatable classifications over creative variation |
| Max tokens | `512` | Raised too high without enough OpenRouter credit caused a 402 error during Task 0 validation — keep this in mind if the prompt is ever extended |
| Retries per paper | `5` | Exponential backoff (2^attempt seconds) |
| Extra retry passes | `2` | After the first full pass, failed rows get up to 2 more full passes before being marked `Failed` for good |
| Delay between calls | `0.6s` | Basic rate-limit courtesy |

---

## 4. Output format

The model is instructed to return **strict JSON only**:

```json
{
  "Decision": "Y" or "N",
  "Category": "Support" or "Enhance" or "Replace" (blank if Decision = "N"),
  "EcosystemService": "(exact ecosystem service from the list)" (blank if Decision = "N"),
  "Technology": "(concise short name of the technology)" (blank if Decision = "N"),
  "ReviewFlag": "review" or "",
  "Confidence": "high" or "medium" or "low"
}
```

`classify.py` extracts a JSON object from the response with a regex (`\{.*\}`) before parsing, since the model occasionally wraps its answer in a sentence or markdown fence despite the "strict JSON only" instruction. If parsing still fails, the row is treated as low-confidence and routed to human review (Section 5) rather than dropped.

---

## 5. What happens to the output — confidence routing

This isn't just informational — `Confidence` decides what happens to a paper next:

| Confidence | Routing |
|---|---|
| `high` | Written to the database automatically |
| `medium` / `low` / failed call / failed parse | Sent to a Google Sheet for a human to check |

Full detail on the review sheet and reviewer fields is in `data_dictionary.md` (Section 4) and `handover.md`. This document is about the prompt itself, not what happens downstream.

---

## 6. Known output quality issues

- **Two hallucinated `EcosystemService` values have appeared: `"Cultural"` and `"Ecosystem monitoring"`.** Neither is one of the 22 services the prompt lists. Both are filtered out downstream by a whitelist in `aggregate.py` — the prompt itself has no built-in defense against this, so if new hallucinated values show up, they need to be caught the same way (add to the whitelist filter, don't try to patch the prompt to prevent every possible wrong string).
- **The model is explicitly told not to default to "high" confidence.** This was added because early runs skewed high; the current prompt asks for a "calibrated distribution" including a meaningful share of medium/low. If confidence output ever looks suspiciously high across a whole batch, that's worth checking against this instruction before assuming something else is wrong.
