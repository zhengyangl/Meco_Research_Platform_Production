# Handover Guide

*Last updated: August 2026*

This is the day-to-day operating manual. For one-time setup (AWS, database, credentials), see `environment_setup.md` — do that first if you haven't already. For how the system is designed and why, see `architecture.md`.

---

## 1. Quick start

This platform classifies bio-inspired research papers against 22 ecosystem services, using an LLM, and shows the results on a Streamlit dashboard. New papers flow in through Google Drive, get classified, and — depending on how confident the model is — either go straight into the database or get checked by a person first. Full detail on all of this is in `architecture.md`; this document assumes you've read it.

---

## 2. The three Google resources, at a glance

The pipeline uses three separate Google resources, all shared with the same service account (see `environment_setup.md` Section 8 for how the account itself is set up).

| Resource | What it's for | Used by | Current ID (⚠ swap for your own — see note below) |
|---|---|---|---|
| **Review Sheet** | Pre-ingestion QC queue — papers the model was only medium/low confidence about | `classify.py` (pushes rows), `run_pipeline.py reviewed` (pulls finished rows) | `15MvAFOnq7b0dGKqzQZPCTwxhSgJdGNmQn8YZFw8BleA`, worksheet `needs_review` |
| **Feedback Sheet** | Crowd-sourced misclassification reports, submitted by dashboard visitors on already-published papers | `explorer.py`'s "Report a Misclassification" form | `1NV89GAdZJfdDSRS1M5ndxjALg8YSvK94WV8iqhnPmbs` *(⚠ inherited from project notes — confirm this is still the correct sheet before relying on it)* |
| **Drive upload folder** | Where a researcher drops a new raw WoS export | `run_pipeline.py new-data` (detects new files here) | `1D6pNaDPJFiRqlcTpL-lux3tCyWs3HuRU` — **explicitly temporary**, created for development. Must be replaced with a real production folder before this goes live long-term. |

**⚠ If you're setting this up fresh (not continuing from the original project), create your own Sheets and Drive folder rather than reusing these IDs.** Reusing someone else's live spreadsheet means your test runs and the original maintainer's real data end up mixed together. Whichever IDs you land on:

- Update `DEFAULT_REVIEW_SHEET_ID` in `classify.py` (or set the `REVIEW_SHEET_ID` env var instead, which overrides it).
- Update `spreadsheet_id` under `[feedback_sheet]` in `.streamlit/secrets.toml`.
- Update `DRIVE_FOLDER_ID` in `run_pipeline.py`.
- Share each new resource individually with the service account's email as Editor — see `environment_setup.md` Section 8.4. This step is per-resource; access to one doesn't carry over to another.

The Review Sheet also holds four reviewer-override columns (`reviewer_decision`, `reviewer_category`, `reviewer_service`, `reviewer_technology`) plus `reviewer_notes`, `reviewed_by`, `reviewed_at`. **These last three fields — who reviewed a paper, when, and why — exist ONLY in this sheet.** The database's `classification_audit` table deliberately does not store them (see `data_schema_supplement.md` Section 5). If you ever need to know who made a particular correction, this sheet is the only place to look — there's no database query that will answer that question.

---

## 3. Day-to-day operating rhythm

Nothing here runs on its own by default — someone needs to trigger each piece, either by hand or by setting up a cron job.

| Command | When to run it | Suggested cadence |
|---|---|---|
| `python run_pipeline.py new-data` | After a researcher uploads a new WoS export to Drive | On demand, or a daily cron check |
| `python run_pipeline.py reviewed` | To pick up whatever's been finished in the Review Sheet | Daily |
| `python run_pipeline.py aggregate` | To refresh the narrative page's files and the Explorer's fallback snapshot | Weekly |

These three are independent — see `architecture.md` Section 3.4 for why they're not one combined command. Running one doesn't require or trigger the others.

The Explorer itself needs no manual step — it queries the database directly and refreshes on its own every 15 minutes.

### 3.1 If self-hosted on EC2 (see environment_setup.md Section 11)

Once the dashboard moves off Streamlit Community Cloud, both apps run as systemd services instead of ad-hoc `streamlit run` commands:

```bash
sudo systemctl status meco-narrative      # check if running
sudo systemctl restart meco-narrative     # restart after a code update
sudo journalctl -u meco-narrative -f      # tail live logs
```
Same commands apply to `meco-explorer`. This is not yet the current setup — see Section 9.

---

## 4. Connecting to the server and database

### 4.1 Direct SSH + psql (quickest for a one-off check)

```bash
cd ~/Downloads   # wherever your .pem key lives
ssh -i my-aws-key.pem ubuntu@<SERVER_PUBLIC_IP>

# once connected:
psql -U pipeline_user -d me_dashboard -h 127.0.0.1 -W
```

Useful commands once you're at the `me_dashboard=>` prompt:

```sql
\dt                                              -- list tables
\d paper_features                                -- show a table's structure
SELECT COUNT(*) FROM papers;                     -- every query needs a trailing semicolon
\q                                                -- exit psql
```

Then `exit` to leave the SSH session.

### 4.2 SSH tunnel + local Jupyter (for data exploration, not production)

Useful when you want to explore data or write/debug new code with fast feedback, without editing files on the server directly.

Open a tunnel in one Terminal window and leave it running:

```bash
ssh -i ~/Downloads/my-aws-key.pem -L 5432:localhost:5432 ubuntu@<SERVER_PUBLIC_IP> -N
```

This makes `localhost:5432` on your own machine act as if it were the server's PostgreSQL. In a separate Jupyter notebook (or any local Python):

```python
import pandas as pd

DB_URI = "postgresql://pipeline_user:<password>@127.0.0.1:5432/me_dashboard"

# Pull data down for local exploration
df = pd.read_sql("SELECT * FROM some_table", DB_URI)
df.to_parquet("my_data.parquet", index=False)   # use parquet, not csv, if the table is large

# Or run aggregate queries without pulling all the rows
totals = pd.read_sql("SELECT COUNT(*) FROM papers", DB_URI)
```

For write operations (`UPDATE`/`INSERT`), use `psycopg2` directly rather than `pandas.read_sql` (which is read-only):

```python
import psycopg2

conn = psycopg2.connect(DB_URI)
cur = conn.cursor()

cur.execute(
    "UPDATE paper_features SET is_current = FALSE WHERE feature_set = %s AND feature_key = %s AND is_current = TRUE",
    (FEATURE_SET, feature_key),
)

conn.commit()   # don't forget this — nothing is saved until you commit
cur.close()
conn.close()
```

---

## 5. Manual workflow vs. the automated pipeline

**These are two different things — don't confuse them.**

- **`run_pipeline.py`** is the production, automated system. It's what actually keeps the database and dashboard current. Section 3 above is how it's meant to be used.
- **The SCP-based manual workflow below** is a development convenience — useful when you're editing a script locally and want to test it against the real server data, without going through the full pipeline. It is not automation, and it doesn't update anything the automated pipeline wouldn't otherwise update on its own schedule.

```bash
# 1. Upload your locally-edited script to the server
scp -i ~/Downloads/my-aws-key.pem ~/Desktop/aggregate.py ubuntu@<SERVER_PUBLIC_IP>:~/

# 2. Connect and run it
ssh -i ~/Downloads/my-aws-key.pem ubuntu@<SERVER_PUBLIC_IP>
python3 ~/aggregate.py
exit

# 3. Pull the results back down to your own machine
scp -i ~/Downloads/my-aws-key.pem ubuntu@<SERVER_PUBLIC_IP>:~/dashboard_data/corpus_meta.json ~/Desktop/meco_dashboard/dashboard_data/
```

If you use this to test a change to a pipeline script, remember to also upload the finished version to wherever `run_pipeline.py` expects to find it (see `pipeline/` in the repo layout) once you're done testing — otherwise the automated pipeline keeps running the old version.

---

## 6. Troubleshooting

Real issues hit while building and testing this pipeline, in case they come up again:

| Symptom | Cause | Fix |
|---|---|---|
| `bash: export: '=': not a valid identifier` | Spaces around the `=` in an `export` command | `export VAR=value`, no spaces. `export VAR = value` is three separate tokens, not an assignment. |
| `OSError: DATABASE_URL is not set` | Env var not exported in the current shell session, or exported in a different session than the one running the script | Re-run the `export DATABASE_URL=...` command in the same terminal session you're running the script from. Exported variables don't persist across new SSH connections or new terminal windows. |
| `EnvironmentError: GOOGLE_SERVICE_ACCOUNT_FILE is not set` | Same as above, for the Google credentials path | Same fix — re-export it, or add it to `~/.bashrc` if you want it to persist automatically on every login. |
| Drive/Sheets calls fail with a permissions error | The resource (Sheet or Drive folder) hasn't been individually shared with the service account's email | Open the resource, click Share, add the `client_email` from the service account's JSON key as Editor. Being the same account used elsewhere does not carry over automatically — see Section 2 above. |
| `pip install` fails with a disk-related error even though `df -h` shows plenty of free space | `/tmp` is a small tmpfs (RAM-backed), not the main disk — large packages like `torch` don't fit there even when the real disk has room | `mkdir -p ~/pip_tmp && export TMPDIR=~/pip_tmp` before installing. Full detail in `environment_setup.md` Section 5. |
| `UserWarning: pandas only supports SQLAlchemy connectable...` when using `pd.read_sql` with a raw `psycopg2` connection | Harmless — pandas prefers a SQLAlchemy engine but works fine with a plain `psycopg2` connection too | Safe to ignore. |
| `file_cache is only supported with oauth2client<4.0.0` when using the Google Drive API | A version-mismatch warning from the `google-api-python-client` library | Harmless, doesn't affect functionality. Only worth fixing if it becomes visually annoying — not a functional bug. |
| Explorer's sidebar filters don't respond when clicked (page loads, nothing happens) — *only applies once self-hosted, see environment_setup.md Section 11* | nginx reverse proxy is missing the WebSocket headers (`proxy_http_version 1.1`, `Upgrade`/`Connection`) — Streamlit needs a live WebSocket for interactivity | Add the missing headers to the nginx config block, then `sudo nginx -t && sudo systemctl restart nginx` |

---

## 7. Rotating credentials

**Database password:**
1. Connect as `pipeline_user` or the `postgres` superuser and run: `ALTER USER pipeline_user WITH PASSWORD 'new_password';`
2. Update `DATABASE_URL` everywhere it's set (server environment, any local `.env` files used for the SSH-tunnel workflow in Section 4.2).

**OpenRouter key:**
1. Go to [openrouter.ai/keys](https://openrouter.ai/keys), delete the old key.
2. Create a new one, update `OPENROUTER_API_KEY`.

**Google service account key:**
1. In the Google Cloud Console, go to the service account → Keys → Add Key → Create new key (JSON) — this creates a new key without invalidating the old one yet.
2. Upload the new JSON file to the server, update `GOOGLE_SERVICE_ACCOUNT_FILE` to point at it, and update `.streamlit/secrets.toml` for `explorer.py`.
3. Confirm everything still works (see the verification checklist in `environment_setup.md`).
4. Only then go back and delete the old key from the Cloud Console.
5. Note: the `client_email` doesn't change when you rotate a key, so you do **not** need to re-share any Sheets or Drive folders — they're shared with the account, not the specific key.

**If a key was ever accidentally committed to git:** rotating it is not enough on its own — treat it as compromised (assume someone could have seen it), revoke it immediately, and check whether it needs to be scrubbed from git history (not just deleted from the current version of a file).

---

## 8. Where to look when something's wrong

| Question | Where to look |
|---|---|
| "Did a pipeline run finish? When? How many papers?" | `pipeline_runs` table — one row per script run, including `run_pipeline.py`'s own summary rows (`model_version = 'orchestrator'`) |
| "What did the model actually say about this paper?" | `classification_audit` table — `raw_output` (JSONB) has the exact response, `confidence` has the numeric score |
| "Who reviewed this paper, and why did they change it?" | The Review Sheet — **not** the database, see Section 2 |
| "Is this paper's classification current, or an old version?" | `classifications.is_current` — only one `TRUE` row per `wos_id` is allowed at a time |
| "Why does this paper have no country/institution/technology cluster?" | Check `paper_features` for that `wos_id` — if `text_analysis.py` hasn't run since the paper was added, these will be missing |

---

## 9. Known limitations and open items

- **`cluster_technologies()`'s low-confidence assignments aren't blocked, only logged.** A new paper with a technology phrase that doesn't closely resemble any of the 25 existing clusters still gets force-assigned to the nearest one. If the "low confidence" count in a run's output starts looking large, that's a signal the 25 clusters may need revisiting (see `data_dictionary.md` Section 7) — the pipeline won't decide that on its own.
- **The full `new-data` chain hasn't been run end-to-end against real new papers in production yet.** Drive detection has been confirmed working. The individual pieces (`classify.py`, `ingest_incremental.py`, `text_analysis.py`) have each been tested separately, and `cluster_technologies()` specifically has been run for real against the live database (successfully recomputed centroids from 35,433 labeled papers). But the full chain — a real new file, classified, auto-ingested, and features extracted, all through `run_pipeline.py new-data` without `--dry-run` — has not yet been exercised together. Do this as an early test with a small batch before relying on it for anything real.
- **The Feedback Sheet ID in Section 2 needs confirming.** It's carried over from project notes rather than freshly verified against `explorer.py`'s actual configuration.
- - **The dashboard is still hosted on Streamlit Community Cloud, not the self-hosted EC2 + nginx setup described in `environment_setup.md` Section 11.** That migration is planned — motivated by removing Streamlit's free-tier branding icons for a cleaner embed into the ME website — but hasn't been executed yet. Streamlit in Snowflake was evaluated as an alternative and rejected: the Explorer's AgGrid-based table doesn't run inside Snowflake's sandbox, and switching would mean losing the current custom cell rendering (DOI links, paradigm color-coding).
