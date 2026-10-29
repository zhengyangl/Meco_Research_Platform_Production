# Handover Guide

*Last updated: October 29, 2026*

This is the day-to-day operating manual. For one-time setup (AWS, database, credentials), see `environment_setup.md` — do that first if you haven't already. For how the system is designed and why, see `architecture.md`.

---

## 1. Quick start

This platform classifies bio-inspired research papers against 22 ecosystem services, using an LLM, and shows the results on a Streamlit dashboard. New papers flow in through Google Drive, get classified, and — depending on how confident the model is — either go straight into the database or get checked by a person first. Full detail on all of this is in `architecture.md`; this document assumes you've read it.

The repository also contains a second, independent platform: the BioM Innovation Database dashboard in `biom-dashboard/` (510 cases, built from CSV files, no database or Google resources). Everything in Sections 2–9 below is about the MEco platform unless stated otherwise; BioM's operation is covered in Section 3.1, and its data pipeline is documented in `biom-dashboard/docs/data_cleaning_notes.md`.

---

## 2. The three Google resources, at a glance

The pipeline uses three separate Google resources, all shared with the same service account (see `environment_setup.md` Section 8 for how the account itself is set up).

| Resource | What it's for | Used by | Current ID |
|---|---|---|---|
| **Review Sheet** | Pre-ingestion QC queue — papers the model was only medium/low confidence about | `classify.py` (pushes rows), `run_pipeline.py reviewed` (pulls finished rows) | `1Ej671TNO1Ep-sm7NT547CynPub_8z3MjHZMEgFNbvt4`, worksheet `needs_review` |
| **Feedback Sheet** | Crowd-sourced misclassification reports, submitted by dashboard visitors on already-published papers | `explorer.py`'s "Report a Misclassification" form | `13mxr3glIdgMZji2hcLnuU9ETGVRqShacTbEXrK3E6Bw` |
| **Drive upload folder** | Where a researcher drops a new raw WoS export | `run_pipeline.py new-data` (detects new files here) | `1PTPH4Jz4XKFrmKCY4uy2ctPKR3_MfuyP` — the folder "MEco - New WoS Uploads", owned by Dr. Jacobs' Google account and shared with the service account as Editor. |

On the production server the two Sheet IDs are set in `~/meco_dashboard/.env` (`REVIEW_SHEET_ID`, `FEEDBACK_SHEET_ID`), which override the defaults written in the code (those defaults still point to the original project's sheets). The Drive folder ID has no environment override — it is written directly in `pipeline/run_pipeline.py` (`DRIVE_FOLDER_ID`). These IDs are identifiers, not credentials: access is controlled by sharing. Keep each resource shared only with named accounts (General access: Restricted), never "Anyone with the link".

**⚠ If you're setting this up fresh (not continuing from the original project), create your own Sheets and Drive folder rather than reusing these IDs.** Reusing someone else's live spreadsheet means your test runs and the original maintainer's real data end up mixed together. Whichever IDs you land on:

- Update `DEFAULT_REVIEW_SHEET_ID` in `classify.py` (or set the `REVIEW_SHEET_ID` env var instead, which overrides it).
- Update `spreadsheet_id` under `[feedback_sheet]` in `.streamlit/secrets.toml`.
- Update `DRIVE_FOLDER_ID` in `run_pipeline.py`.
- Share each new resource individually with the service account's email as Editor — see `environment_setup.md` Section 8.4. This step is per-resource; access to one doesn't carry over to another.

The Review Sheet also holds four reviewer-override columns (`reviewer_decision`, `reviewer_category`, `reviewer_service`, `reviewer_technology`) plus `reviewer_notes`, `reviewed_by`, `reviewed_at`. **These last three fields — who reviewed a paper, when, and why — exist ONLY in this sheet.** The database's `classification_audit` table deliberately does not store them (see `data_schema_supplement.md` Section 5). If you ever need to know who made a particular correction, this sheet is the only place to look — there's no database query that will answer that question.

---

## 3. Day-to-day operating rhythm

Nothing here runs on its own by default — someone needs to trigger each piece, either by hand or by setting up a cron job.

Run these from the pipeline folder, after loading the server's `.env` in the same terminal session:

​```bash
cd ~/meco_dashboard/pipeline
set -a && source ../.env && set +a
​```

Add `--dry-run` to `new-data` to list the files it would process without downloading, classifying or writing anything.

| Command | When to run it | Suggested cadence |
|---|---|---|
| `python3 run_pipeline.py new-data` | After a researcher uploads a new WoS export to Drive | On demand, or a daily cron check |
| `python3 run_pipeline.py reviewed` | To pick up whatever's been finished in the Review Sheet | Daily |
| `python3 run_pipeline.py aggregate` | To refresh the narrative page's files and the Explorer's fallback snapshot | Weekly |

These three are independent — see `architecture.md` Section 3.4 for why they're not one combined command. Running one doesn't require or trigger the others.

The Explorer itself needs no manual step — it queries the database directly and refreshes on its own every 15 minutes.

### 3.1 Production server (EC2 + nginx; see environment_setup.md Section 11)

The dashboards run as two systemd services on the production server:

| Service | What it serves |
|---|---|
| `meco-dashboard` | MEco narrative page and Data Explorer (one Streamlit app) |
| `biom-dashboard` | BioM Innovation Database |

```bash
sudo systemctl status meco-dashboard      # check if running
sudo systemctl restart meco-dashboard     # restart after a code update or .env change
sudo journalctl -u meco-dashboard -f      # tail live logs
```

The same commands apply to `biom-dashboard`. After pulling new code (`cd ~/meco_dashboard && git pull`), restart whichever service the change affects. 

**Updating the BioM data.** The BioM dashboard reads only the CSV files in `biom-dashboard/data/clean/`. To rebuild them from a new Excel export, run the three scripts in `biom-dashboard/pipeline/` from that folder, in this order: `clean_biom_data.py`, `geocode_countries.py`, `validate_cleaned_output.py` (details in `biom-dashboard/docs/data_cleaning_notes.md`). Commit the updated CSVs, `git pull` on the server, and `sudo systemctl restart biom-dashboard`.

### 3.2 How the two pages are served

| Page | URL | systemd service | Internal port | Code location |
|---|---|---|---|---|
| MEco (narrative page + Explorer) | https://meco.manufacturedecosystems.com | `meco-dashboard` | 8501 | `~/meco_dashboard` (`app.py`, `pages/explorer.py`) |
| BioM Innovation Database | https://biom.manufacturedecosystems.com | `biom-dashboard` | 8502 | `~/meco_dashboard/biom-dashboard` (its own virtual environment) |

- Both apps listen on `127.0.0.1` only. nginx is the public entry point (ports 80/443) and forwards each hostname to its app. Config files: `/etc/nginx/sites-available/meco-dashboard` and `biom-dashboard`.
- HTTPS uses one Let's Encrypt certificate covering both hostnames, issued with certbot and renewed automatically (`certbot.timer`). To check renewal: `sudo certbot renew --dry-run`.
- The AWS security group allows ports 80 and 443 from anywhere and SSH (port 22) only from specific IP addresses. Ports 8501/8502 are not exposed.
- DNS: the `meco` and `biom` A records at the domain registrar point to the server's static (Elastic) IP. If the server is ever rebuilt with a new IP, update both records. **[To fill in: who holds the registrar account, and whether domain auto-renewal is on.]**
- The ME website (manufacturedecosystems.com) links to the two pages from its navigation and opens them in a new window. They are deliberately **not** embedded in iframes: an iframe leaves the website's navigation and footer around a data platform and makes the layout hard to control.
- **Updating code:** edit on GitHub, then `cd ~/meco_dashboard && git pull` on the server and restart the affected service (`meco-dashboard` and/or `biom-dashboard`).
- **Pinned versions:** MEco runs Streamlit 1.66.0 and `streamlit-aggrid` 1.2.1.post2; BioM runs Streamlit 1.64.0 (see each `requirements.txt`). `pyarrow` is held at 24.0.0 on the server as a precaution against a crash reported with 26.0.0. The page styling depends on Streamlit's internal page structure, which changes between versions (for example, pill buttons changed from `data-testid="stBaseButton-pills"` to `data-variant="pills"`). **Before upgrading Streamlit, check the narrative page's pill buttons and the Explorer's tabs and sidebar filters.**
  
---

## 4. Connecting to the server and database

### 4.1 Direct SSH + psql (quickest for a one-off check)

```bash
ssh -i <path-to-your-private-key> ubuntu@meco.manufacturedecosystems.com

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

Your public key must be listed in `~ubuntu/.ssh/authorized_keys` on the server, and your current public IP must be allowed on port 22 in the AWS security group (see the troubleshooting table in Section 6).

### 4.2 SSH tunnel + local Jupyter (for data exploration, not production)

Useful when you want to explore data or write/debug new code with fast feedback, without editing files on the server directly.

Open a tunnel in one Terminal window and leave it running:

```bash
ssh -i <path-to-your-private-key> -L 5432:localhost:5432 ubuntu@meco.manufacturedecosystems.com -N
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
scp -i <path-to-your-private-key> ~/Desktop/aggregate.py ubuntu@meco.manufacturedecosystems.com:~/

# 2. Connect and run it
ssh -i <path-to-your-private-key> ubuntu@meco.manufacturedecosystems.com
python3 ~/aggregate.py
exit

# 3. Pull the results back down to your own machine
scp -i <path-to-your-private-key> ubuntu@meco.manufacturedecosystems.com:~/dashboard_data/corpus_meta.json ~/Desktop/meco_dashboard/dashboard_data/
```

If you use this to test a change to a pipeline script, remember to also commit the finished version to the repository and run `git pull` in `~/meco_dashboard` on the server once you're done testing — otherwise the automated pipeline keeps running the old version. Avoid editing files inside `~/meco_dashboard` directly on the server, since that makes the next `git pull` conflict.

---

## 6. Troubleshooting

Real issues hit while building and testing this pipeline, in case they come up again:

| Symptom | Cause | Fix |
|---|---|---|
| `bash: export: '=': not a valid identifier` | Spaces around the `=` in an `export` command | `export VAR=value`, no spaces. `export VAR = value` is three separate tokens, not an assignment. |
| `OSError: DATABASE_URL is not set` | Env var not exported in the current shell session, or exported in a different session than the one running the script | Load the server's `.env` file in the same terminal session you're running the script from: `set -a; source ~/meco_dashboard/.env; set +a`. Exported variables don't persist across new SSH connections or new terminal windows. (The systemd service reads `.env` itself, so this only affects scripts you run by hand.) |
| `EnvironmentError: GOOGLE_SERVICE_ACCOUNT_FILE is not set` | Same as above, for the Google credentials path | Same fix — load `.env` as above, and check that `GOOGLE_SERVICE_ACCOUNT_FILE` in it points at the real JSON file. |
| Changed `.env` or pulled new code, but the dashboard still behaves the old way | The Streamlit services only read `.env` and the code at startup | `sudo systemctl restart meco-dashboard` (or `biom-dashboard`) |
| Drive/Sheets calls fail with a permissions error | The resource (Sheet or Drive folder) hasn't been individually shared with the service account's email | Open the resource, click Share, add the `client_email` from the service account's JSON key as Editor. Being the same account used elsewhere does not carry over automatically — see Section 2 above. |
| `pip install` fails with a disk-related error even though `df -h` shows plenty of free space | `/tmp` is a small tmpfs (RAM-backed), not the main disk — large packages like `torch` don't fit there even when the real disk has room | `mkdir -p ~/pip_tmp && export TMPDIR=~/pip_tmp` before installing. Full detail in `environment_setup.md` Section 5. |
| `UserWarning: pandas only supports SQLAlchemy connectable...` when using `pd.read_sql` with a raw `psycopg2` connection | Harmless — pandas prefers a SQLAlchemy engine but works fine with a plain `psycopg2` connection too | Safe to ignore. |
| `file_cache is only supported with oauth2client<4.0.0` when using the Google Drive API | A version-mismatch warning from the `google-api-python-client` library | Harmless, doesn't affect functionality. Only worth fixing if it becomes visually annoying — not a functional bug. |
| Explorer's sidebar filters don't respond when clicked (page loads, nothing happens)  — see environment_setup.md Section 11 | nginx reverse proxy is missing the WebSocket headers (`proxy_http_version 1.1`, `Upgrade`/`Connection`) — Streamlit needs a live WebSocket for interactivity | Add the missing headers to the nginx config block, then `sudo nginx -t && sudo systemctl restart nginx` |
| `ssh: connect to host … port 22: Operation timed out` | The security group only allows SSH from specific IP addresses, and your public IP has changed | AWS console → EC2 → the instance's security group (`meco-biom-sg`) → Edit inbound rules → on the SSH (port 22) rule set Source to "My IP" → Save. Do not change the 80/443 rules. |
| Pill buttons, tabs or other widgets suddenly lose their styling after a Streamlit upgrade | The custom CSS targets Streamlit's internal markup, which changes between versions | Keep Streamlit pinned. After any upgrade, check the narrative page and Explorer; inspect the element in the browser and add the new selector next to the old one in the CSS. |

---

## 7. Rotating credentials

**Database password:**
1. Connect as `pipeline_user` or the `postgres` superuser and run: `ALTER USER pipeline_user WITH PASSWORD 'new_password';`
2. Update `DATABASE_URL` everywhere it's set (`~/meco_dashboard/.env` on the server, any local `.env` files used for the SSH-tunnel workflow in Section 4.2).
3. Run `sudo systemctl restart meco-dashboard` so the Explorer picks up the new password.

**OpenRouter key:**
1. Go to [openrouter.ai/keys](https://openrouter.ai/keys), delete the old key.
2. Create a new one, update `OPENROUTER_API_KEY` in `~/meco_dashboard/.env`. No service restart is needed — only `classify.py` uses it, and it is run by hand or by the pipeline, not by the Streamlit services.

**Google service account key:**
1. In the Google Cloud Console, go to the service account → Keys → Add Key → Create new key (JSON) — this creates a new key without invalidating the old one yet.
2. Upload the new JSON file to the server, update `GOOGLE_SERVICE_ACCOUNT_FILE` to point at it, and update `.streamlit/secrets.toml` for `explorer.py`, then run `sudo systemctl restart meco-dashboard`.
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
- **Hosting.** Both dashboards are self-hosted on the EC2 server described in Section 3.2. Any older copy on Streamlit Community Cloud is no longer the source of truth and can be retired. Streamlit in Snowflake was evaluated as an alternative and rejected: the Explorer's AgGrid-based table doesn't run inside Snowflake's sandbox, and switching would mean losing the current custom cell rendering (DOI links, paradigm color-coding).
- **The dashboard is still hosted on Streamlit Community Cloud, not the self-hosted EC2 + nginx setup described in `environment_setup.md` Section 11.** That migration is planned — motivated by removing Streamlit's free-tier branding icons for a cleaner embed into the ME website — but hasn't been executed yet. Streamlit in Snowflake was evaluated as an alternative and rejected: the Explorer's AgGrid-based table doesn't run inside Snowflake's sandbox, and switching would mean losing the current custom cell rendering (DOI links, paradigm color-coding).
