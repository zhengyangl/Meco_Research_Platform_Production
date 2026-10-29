# Environment Setup

*Last updated: October 2026*

This is a one-time guide. Follow it once, in order, to go from nothing to a working server. For day-to-day operation after that, see `handover.md`.

The server hosts both platforms in this repository: the MEco Research Data Platform (the narrative page and the Data Explorer, one Streamlit app, plus the PostgreSQL database and pipeline) and the BioM Innovation Database dashboard (`biom-dashboard/`, a separate Streamlit app that reads CSV files and needs no database).

Everything in this guide happens in a Terminal window on your own computer, using SSH to control the remote server. If you've never used SSH or a Terminal before: it's just a text window where you type commands instead of clicking buttons. Every command below is copy-pasteable.

---

## 0. What you'll need before starting

- An AWS account (needs a credit card — EC2 isn't free after the trial period)
- An OpenRouter account (needs a small prepaid balance — see Section 7)
- A Google account (for Google Cloud, Sheets, and Drive — see Section 8)
- A Terminal app on your computer (Mac: built-in "Terminal" app; Windows: use [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) or PuTTY)

---

## 1. Launch the server (AWS EC2)

1. Sign in to the [AWS Console](https://console.aws.amazon.com/ec2/) and open the EC2 dashboard.
2. Click **Launch Instance**.
3. Choose **Ubuntu** as the operating system (any recent 22.04/24.04 LTS image).
4. Choose an instance type. Use **t3.small** (2 vCPU, 2 GB RAM) for the self-hosted deployment in Section 11, which runs two Streamlit apps, PostgreSQL, and the pipeline on one machine. A **t3.micro** (1 GB RAM) can run the pipeline alone, but it's tight on memory — Section 4 covers the workaround.
5. Create a new key pair (or select an existing one) — this downloads a `.pem` file. **Save this file somewhere you won't lose it** (e.g. `~/Downloads/my-aws-key.pem`). You cannot download it again later; if you lose it, you lose access to the server. (Alternatively, import your own SSH public key in the EC2 console and use the matching private key in place of the `.pem` file throughout this guide.)
6. Under network settings, allow inbound **SSH (port 22)** from your IP only, plus **HTTP (80)** and **HTTPS (443)** from anywhere (needed by nginx and Let's Encrypt in Section 11). Do **not** open 8501/8502 — the Streamlit apps are reached only through nginx.
7. Launch the instance. Wait until its state shows **Running**.

Full official walkthrough if any of this is unclear: [Launch an EC2 instance — AWS documentation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EC2_GetStarted.html).

**A note on the IP address:** allocate an **Elastic IP** and associate it with the instance. Without one, the public IP changes whenever the instance is stopped and restarted, which would break the DNS records in Section 11.6. AWS charges a small hourly fee for every public IPv4 address (about $3.65/month at the published rate — confirm on the [AWS pricing page](https://aws.amazon.com/vpc/pricing/)).

---

## 2. Connect and do first-time setup

Open a Terminal on your own computer.

```bash
# Move into the folder where your .pem key file is
cd ~/Downloads

# Connect — replace with the server's Elastic IP
ssh -i my-aws-key.pem ubuntu@<SERVER_PUBLIC_IP>
```

If this is the first time connecting, you'll be asked to confirm the server's fingerprint — type `yes`.

Once connected, update the system and install the basics:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl zip python3-pip python3-venv
```

---

## 3. Install PostgreSQL and build the database

```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql   # so it restarts automatically on reboot
```

### 3.1 Allow password login

On Ubuntu 22.04/24.04 the default `pg_hba.conf` already allows password login over TCP from `127.0.0.1`, so on the production server (Ubuntu 24.04, PostgreSQL 16) no change was needed in this section. Skip to Section 3.2 and come back only if the connection test in Section 3.3 fails with an authentication error.

Find the config files (the exact path includes the version number, e.g. `16`):

```bash
sudo find /etc/postgresql -name "pg_hba.conf"
sudo find /etc/postgresql -name "postgresql.conf"
```

Only if that test fails, edit `pg_hba.conf` and add this line at the end:

```
host    all             all             127.0.0.1/32            md5
```

This allows password login over TCP, but only from the server itself (`127.0.0.1`) — the pipeline scripts and the dashboard both run on this same server, so they never need to connect from anywhere else. Don't open this beyond `127.0.0.1` unless you have a specific reason to.

Restart PostgreSQL for the change to take effect:

```bash
sudo systemctl restart postgresql
```

If anything about this step is unclear, the official reference is the [PostgreSQL `pg_hba.conf` documentation](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html), and there's a walkthrough in the [Ubuntu Server documentation](https://documentation.ubuntu.com/server/how-to/databases/install-postgresql/).

### 3.2 Build the database and tables

A ready-made script does this for you: `schema.sql` (in the repo root). It creates the database, the `pipeline_user` role, all seven tables, and the indexes that make the versioning pattern work. **This script has been tested end-to-end against a real PostgreSQL 16 instance** — every statement in it runs cleanly.

1. Upload it to the server (from your own computer, in a new Terminal window — don't close your SSH session):
   ```bash
   scp -i ~/Downloads/my-aws-key.pem schema.sql ubuntu@<SERVER_PUBLIC_IP>:~/
   ```
2. **Before running it**, open the file and change the placeholder password:
   ```bash
   nano ~/schema.sql
   # find the line: CREATE USER pipeline_user WITH PASSWORD 'CHANGE_ME_BEFORE_RUNNING';
   # replace the placeholder with a real password, then Ctrl+O, Enter, Ctrl+X to save and exit
   ```
3. Run it:
   ```bash
   sudo -u postgres psql < ~/schema.sql
   ```
   Use the `<` redirect rather than `-f ~/schema.sql`: the `postgres` system user cannot read files inside `/home/ubuntu`, so `-f` fails with a permission-denied error, whereas with `<` your own shell opens the file.
4. You should see a series of `CREATE DATABASE`, `CREATE ROLE`, `CREATE TABLE`, and `GRANT` confirmations, ending with a list of the 7 tables and two `0`-row counts (the database is empty until the pipeline adds data). If you see errors instead, don't proceed — fix the error first (the most common cause is forgetting to change the placeholder password, or running the script twice against a database that already exists).

Write down what you used for the database name, username, and password — you'll need them in Section 9. If you followed this guide exactly, they are:

```
Database: me_dashboard
User:     pipeline_user
Password: <whatever you set in step 2 above>
Host:     127.0.0.1
Port:     5432
```

### 3.3 Verify

```bash
psql -U pipeline_user -d me_dashboard -h 127.0.0.1 -W
# enter the password when prompted
```

If you land on a `me_dashboard=>` prompt, it worked. A few commands to try:

```sql
\dt                  -- list all tables
\d papers             -- show the papers table's structure
SELECT COUNT(*) FROM papers;   -- should return 0 on a fresh install
\q                    -- exit
```
The existing data (papers, labels, snapshot) is loaded later, once the code and environment variables are in place — see Section 9.1.

---

## 4. Memory management (if using t3.micro)

A t3.micro has 1 GB of RAM. Some pipeline steps — especially `text_analysis.py`'s technology-cluster step, which loads an embedding model — can use more than that briefly. Without swap space, this causes the process to be killed outright (an "out of memory" error) instead of just running slowly.

### 4.1 Create a swap file

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

Check it's active:

```bash
free -h
```

You should see a non-zero number under the `Swap` row.

### 4.2 Make it permanent (survive a reboot)

```bash
sudo bash -c 'echo "/swapfile none swap sw 0 0" >> /etc/fstab'
```

### 4.3 Tune swappiness (optional, but recommended)

`vm.swappiness` (0–100) controls how eagerly Linux uses swap even when RAM isn't full yet. The default (60) swaps proactively. For this server — mostly idle, with occasional short memory spikes during `aggregate.py` or the embedding step — a lower value means swap is only used when actually needed:

```bash
sudo sysctl vm.swappiness=10
sudo bash -c 'echo "vm.swappiness=10" >> /etc/sysctl.conf'   # make it permanent
```

Full reference if you want more detail: [How To Add Swap Space on Ubuntu — DigitalOcean](https://www.digitalocean.com/community/tutorials/how-to-add-swap-space-on-ubuntu-20-04) (the commands are OS-level, not DigitalOcean-specific — they work the same on EC2).

**If this still isn't enough** (repeated OOM kills even with swap), the real fix is upgrading the instance to t3.small — swap is a workaround for occasional spikes, not a substitute for RAM under sustained load.

---

## 5. Install Python dependencies

```bash
sudo apt install -y python3-pip
```

Get the repo onto the server first (Section 6), then, from the repo folder:

```bash
cd ~/meco_dashboard
pip3 install -r requirements.txt --break-system-packages
pip3 install -r requirements_pipeline.txt --break-system-packages
```

`requirements.txt` pins Streamlit to 1.66.0 and `streamlit-aggrid` to 1.2.1.post2, the versions this platform was tested against. The page styling depends on Streamlit's internal page structure, so don't upgrade Streamlit without re-testing (see `handover.md` Section 3.2, "Pinned versions"). `app.py` also uses `st.components.v1.html`, which Streamlit has announced it will remove in a future release.

These cover the MEco platform. The BioM dashboard has its own pinned `biom-dashboard/requirements.txt` (different package versions), so it gets its own virtual environment to keep the two from interfering:

```bash
python3 -m venv ~/meco_dashboard/biom-dashboard/.venv
~/meco_dashboard/biom-dashboard/.venv/bin/pip install -r ~/meco_dashboard/biom-dashboard/requirements.txt
```

**`sentence-transformers` (in `requirements_pipeline.txt`) pulls in `torch`, which is large (~500 MB+).** Two things that can go wrong here, both already hit once during this project's setup:

- **Disk error, even with plenty of disk space free.** This happens because `/tmp` is often a small tmpfs (RAM-backed, ~500 MB) on EC2 — not actually a disk space problem, a `/tmp` problem. Fix: point pip's temp directory somewhere with real room before installing:
  ```bash
  mkdir -p ~/pip_tmp
  export TMPDIR=~/pip_tmp
  pip3 install -r requirements_pipeline.txt --break-system-packages
  ```
  Note `export TMPDIR=...` only lasts for the current terminal session — set it again if you reconnect later and need to reinstall something.
- **CPU-only torch is smaller and sufficient.** This server never uses a GPU, so installing the full CUDA-enabled torch build wastes disk space for nothing. Install the CPU-only build first, then the rest:
  ```bash
  pip3 install torch --index-url https://download.pytorch.org/whl/cpu --break-system-packages
  pip3 install -r requirements_pipeline.txt --break-system-packages
  ```

---

## 6. Get the code onto the server

Clone the whole repo on the server — both platforms live in it, and the apps need more than just the scripts (`dashboard_data/`, `biom-dashboard/`, and the root `.streamlit/` folder):

```bash
git clone https://github.com/zhengyangl/meco_research_platform_production.git ~/meco_dashboard
```

If the repository is private, GitHub will ask for credentials; use a personal access token with read access as the password. Every path in the rest of this guide assumes the repo is at `~/meco_dashboard`.

To update the code later: `cd ~/meco_dashboard && git pull`, then restart the affected service (Section 11.4).

---

## 7. OpenRouter (for `classify.py`)

`classify.py` calls Qwen-2.5-72B through OpenRouter, not directly through Alibaba. Every maintainer should use their **own** account and key — never share one, and never commit one to the repo (see `.gitignore`).

1. Go to [openrouter.ai](https://openrouter.ai) and sign up (email, GitHub, or Google).
2. Go to the [Keys page](https://openrouter.ai/keys) and click **Create Key**. Copy it immediately — OpenRouter only shows it once.
3. **OpenRouter requires a prepaid balance before the API will work.** Go to the [Credits page](https://openrouter.ai/credits) and add funds. $5 is enough to start and test with — Qwen-2.5-72B is inexpensive per call.
4. Set the key as an environment variable on the server (see Section 9) — never hardcode it in a script.

If anything about API usage itself is unclear, the official reference is the [OpenRouter Quickstart Guide](https://openrouter.ai/docs/quickstart).

**One thing worth knowing before your first real run:** if `max_tokens` is set too high relative to your remaining credit balance, OpenRouter returns a 402 error, not a helpful "increase max_tokens" message. `classify.py` already has this handled (`MAX_TOKENS = 512`, tested and working) — don't change it without understanding why it's set where it is.

---

## 8. Google Cloud, Sheets, and Drive

The pipeline uses **three** separate Google resources, all accessed through **one** shared service account. This section sets up the service account; the three resources themselves (which sheets/folder to actually create) are described in `handover.md` since they're closer to day-to-day design than one-time setup.

### 8.1 Create a Google Cloud project and enable APIs

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or use an existing one).
3. Go to **APIs & Services → Library**, search for and enable:
   - **Google Sheets API**
   - **Google Drive API**

Official reference: [Enable Google Workspace APIs](https://developers.google.com/workspace/guides/enable-apis).

### 8.2 Create a service account

1. Go to **APIs & Services → Credentials → Create Credentials → Service Account**.
2. Give it a name (e.g. `meco-pipeline-service`). No specific role is required for what this project needs — the default is fine.
3. Once created, open the service account's detail page → **Keys** tab → **Add Key → Create new key → JSON**. This downloads a `.json` file containing a private key.

**This file is a credential — treat it like a password.** Don't commit it to git (see `.gitignore` — anything under `google_api_key/`, `credentials/`, or matching `*service-account*.json` is already excluded, but don't rely on that alone; keep it outside the repo folder entirely if you can).

Official reference: [Create service accounts](https://docs.cloud.google.com/iam/docs/service-accounts-create) and [Create and delete service account keys](https://docs.cloud.google.com/iam/docs/keys-create-delete).

### 8.3 Upload the key to the server

```bash
scp -i ~/Downloads/my-aws-key.pem /path/to/your-key.json ubuntu@<SERVER_PUBLIC_IP>:~/service-account.json
```

Then, on the server, move it into a private folder and restrict it to your user: `mkdir -p -m 700 ~/secrets && mv ~/service-account.json ~/secrets/service_account.json && chmod 600 ~/secrets/service_account.json`.

### 8.4 Share each Google resource with the service account

Open the downloaded JSON file and find the `client_email` field — it looks like `meco-pipeline-service@your-project-id.iam.gserviceaccount.com`.

**Every Google Sheet and Drive folder the pipeline touches must be individually shared with this email as Editor.** Having API access at the project level does *not* grant access to any specific sheet or folder — that's a separate, per-resource step. See `handover.md` for exactly which three resources need this, and what to name them if you're setting up fresh ones rather than reusing the project's originals.

### 8.5 explorer.py's credentials go somewhere different

Everything else in this section uses `GOOGLE_SERVICE_ACCOUNT_FILE` (an environment variable pointing at the JSON file). `explorer.py` is the one exception — because it runs inside Streamlit, it reads credentials from `.streamlit/secrets.toml` instead, using Streamlit's own secrets mechanism. On the server, create it at `~/meco_dashboard/.streamlit/secrets.toml` (the folder already exists in the repo; never commit this file — it's in `.gitignore`), then run `chmod 600` on it:

```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private_key_id"
private_key = "-----BEGIN PRIVATE KEY-----\nyour key content\n-----END PRIVATE KEY-----\n"
client_email = "meco-pipeline-service@your-project-id.iam.gserviceaccount.com"
client_id = "your-client_id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "your-client_x509_cert_url"

[feedback_sheet]
spreadsheet_id = "the misclassification-feedback sheet's ID — see handover.md"
```

Every field except `private_key` is a straight copy-paste from the JSON file. For `private_key`, keep the `\n` characters exactly as they appear in the JSON — don't reformat them into real line breaks.

Streamlit reads this file from the folder the app is started in, which is why the MEco service in Section 11.4 uses the repo root as its `WorkingDirectory`. The BioM dashboard needs no secrets.

If deploying `explorer.py` somewhere other than a self-hosted server (e.g. Streamlit Community Cloud), the same TOML content goes into that platform's **Settings → Secrets** page instead of a local file.

---

## 9. Set environment variables

Copy `.env.example` to `.env` in the repo folder and fill in the real values from the sections above:

```bash
cd ~/meco_dashboard
cp .env.example .env
nano .env
chmod 600 .env
```

```
DATABASE_URL=postgresql://pipeline_user:<your DB password>@127.0.0.1:5432/me_dashboard
OPENROUTER_API_KEY=<your OpenRouter key>
GOOGLE_SERVICE_ACCOUNT_FILE=/home/ubuntu/secrets/service_account.json
REVIEW_SHEET_ID=<review-queue sheet ID>
FEEDBACK_SHEET_ID=<misclassification-feedback sheet ID>
```

Write plain `KEY=value` lines with no `export` and no quotes — the same file is read by systemd (`EnvironmentFile`, Section 11.4). `REVIEW_SHEET_ID` and `FEEDBACK_SHEET_ID` override the sheet IDs hardcoded in `classify.py` and `sync_feedback.py`; set them when using new copies of the sheets. The Drive folder ID is currently hardcoded as `DRIVE_FOLDER_ID` in `run_pipeline.py` and has no environment-variable override, so a new folder requires editing that line.

To use these variables in an interactive SSH session (for example to run the pipeline by hand), load them first: `set -a; source ~/meco_dashboard/.env; set +a`. Variables exported in a plain SSH session disappear when you disconnect.

### 9.1 Load the existing data (one-time)

This was done once, when the production server was first set up. It is only needed to rebuild the database from scratch. Routine updates go through the pipeline (see the handover guide). Run it after Sections 3, 5, 6 and 9 are complete, in an SSH session where the variables are loaded (`set -a; source ~/meco_dashboard/.env; set +a`).

**Source files.** Copy these four files to `~/initial_data/` on the server (for example with `scp`):

- `1_WoS og data.xlsx` — the original Web of Science export
- `ManuEco_full data.xlsx` — the GPT classifications from Jacobs et al. (2025)
- `tech_labels.csv` — the current technology-cluster label for each paper
- `narrative_snapshot.csv` — the frozen copy of the classifications behind the original published corpus (used by the narrative page)

The two CSVs were exported from the previous (personal) server's database with:

```bash
psql -U pipeline_user -d me_dashboard -h 127.0.0.1 -W -c "\copy (SELECT wos_id, feature_set, feature_key, feature_val, is_current FROM paper_features WHERE feature_key = 'technology_cluster' AND is_current = TRUE) TO '/home/ubuntu/tech_labels.csv' CSV HEADER"
psql -U pipeline_user -d me_dashboard -h 127.0.0.1 -W -c "\copy classifications_narrative_snapshot TO '/home/ubuntu/narrative_snapshot.csv' CSV HEADER"
```

**Load in this order** (each step depends on the one before it):

1. **Papers and original classifications.** `ingest_initial.py` reads the two Excel files and writes `datasets`, `papers`, `classifications` and `pipeline_runs`. It takes a while, so run it in the background and watch the log:

```bash
cd ~/initial_data
nohup python3 -u ~/meco_dashboard/pipeline/ingest_initial.py > ~/initial_data/ingest.log 2>&1 &
tail -f ~/initial_data/ingest.log
```

   The script prints verification counts at the end. It expects 68,917 papers, 59,599 non-review, 35,433 Decision=Y and 31,593 in the target corpus. Also confirm that `SELECT dataset_id, source, version, record_count FROM datasets;` shows one row.

2. **Technology labels.** Load the CSV into `paper_features` (this needs the papers from step 1):

```bash
psql "$DATABASE_URL" -c "\copy paper_features (wos_id, feature_set, feature_key, feature_val, is_current) FROM '/home/ubuntu/initial_data/tech_labels.csv' CSV HEADER"
```

   Check that every Decision=Y paper has a label; `y_without_label` should be 0:

```bash
psql "$DATABASE_URL" -c "SELECT COUNT(*) AS y_without_label FROM classifications c LEFT JOIN paper_features pf ON pf.wos_id = c.wos_id AND pf.feature_key = 'technology_cluster' AND pf.is_current WHERE c.is_current AND c.decision = 'Y' AND pf.wos_id IS NULL;"
```

3. **Text-derived features.** Install `pycountry` if it is not installed yet, then run the four tasks one after another (the `technologies` task was not run here; its result comes from the CSV in step 2):

```bash
pip3 install "pycountry==26.2.16" --break-system-packages
cd ~/meco_dashboard
nohup bash -c 'for t in wos_categories countries institutions funding; do echo "=== $t ==="; python3 -u pipeline/text_analysis.py --task $t || exit 1; done' > ~/initial_data/text_analysis.log 2>&1 &
tail -f ~/initial_data/text_analysis.log
```

4. **Narrative snapshot.** `schema.sql` already creates the empty `classifications_narrative_snapshot` table, so only the load is needed:

```bash
psql "$DATABASE_URL" -c "\copy classifications_narrative_snapshot FROM '/home/ubuntu/initial_data/narrative_snapshot.csv' CSV HEADER"
```

   Check that no snapshot row refers to a paper that is missing from `papers`; `snapshot_not_in_papers` should be 0:

```bash
psql "$DATABASE_URL" -c "SELECT COUNT(*) AS snapshot_not_in_papers FROM classifications_narrative_snapshot s LEFT JOIN papers p ON p.wos_id = s.wos_id WHERE p.wos_id IS NULL;"
```

   You can also count how many snapshot rows differ from the current classifications. A non-zero number is not an error, because the snapshot is frozen on purpose:

```bash
psql "$DATABASE_URL" -c "SELECT COUNT(*) AS differing_rows FROM classifications_narrative_snapshot s JOIN classifications c ON c.wos_id = s.wos_id AND c.is_current WHERE s.decision IS DISTINCT FROM c.decision OR s.category IS DISTINCT FROM c.category OR s.ecosystem_service IS DISTINCT FROM c.ecosystem_service OR s.technology IS DISTINCT FROM c.technology;"
```

5. **Aggregate.** Build the dashboard data files from the database:

```bash
cd ~/meco_dashboard
nohup python3 -u pipeline/aggregate.py > ~/initial_data/aggregate.log 2>&1 &
tail -f ~/initial_data/aggregate.log
```

   Then compare the regenerated files against the committed ones with `git -C ~/meco_dashboard diff --stat -- dashboard_data`. Large unexpected differences mean something above did not load correctly.
   
---

## 10. Final verification checklist

Work through these in order. If any step fails, stop and fix it before moving to the next — later steps assume earlier ones work.

- [ ] `ssh` into the server successfully
- [ ] `psql -U pipeline_user -d me_dashboard -h 127.0.0.1 -W` connects and shows 7 tables via `\dt`
- [ ] `pip3 list` shows `pandas`, `psycopg2`, `sentence-transformers` installed
- [ ] After loading `.env` (Section 9), `echo $DATABASE_URL` (etc.) shows the values you set, not blank
- [ ] `python3 pipeline/classify.py --dry-run --input <any small test file>` runs without an environment-variable error (see `handover.md` for what a real dry run looks like)
- [ ] `cd ~/meco_dashboard/pipeline && python3 run_pipeline.py new-data --dry-run` successfully lists files in the Drive folder (confirms the Google service account setup works end to end)

---

## 11. Self-Hosting the Dashboard on EC2 (nginx + systemd)

*Status: this describes the production deployment as built in October 2026 (EC2 + nginx + systemd, Let's Encrypt HTTPS). Day-to-day operation is covered in `handover.md` Section 3.2.*

Two platforms were evaluated and rejected before landing on this approach:

- **Staying on Streamlit Community Cloud long-term** — free, but the free tier permanently injects two branding icons ("Hosted with Streamlit", a creator-profile badge) into the bottom-right corner of every app. There is no official way to remove them; only self-hosting outside Community Cloud removes them, since they're injected by the hosting layer itself, not the Streamlit framework.
- **Streamlit in Snowflake (SiS)** — rejected. `explorer.py`'s main table depends entirely on AgGrid (`GridOptionsBuilder`, custom `JsCode` renderers for DOI links and paradigm color-coding), and AgGrid does not run inside SiS's sandbox — this is a known platform limitation (confirmed via Snowflake's own community forum), not something a package install fixes. Migrating would mean rewriting the Explorer's table with `st.dataframe` (losing custom cell rendering) and rebuilding the data-loading layer to read from Snowflake Stages instead of local parquet/JSON. Not worth it for this project.

Both platforms run the same code as they did on Community Cloud, with one caveat: the page styling depends on the Streamlit version (see `handover.md` Section 3.2, "Pinned versions").

**Layout.** Two Streamlit processes, one subdomain each:

| Subdomain | Serves | Port | Working directory |
|---|---|---|---|
| `meco.manufacturedecosystems.com` | MEco narrative page (`app.py`) and Data Explorer (`pages/explorer.py`, at `/explorer`) — one app | 8501 | `~/meco_dashboard` |
| `biom.manufacturedecosystems.com` | BioM Innovation Database (`biom-dashboard/app.py`) | 8502 | `~/meco_dashboard/biom-dashboard` |

The working directory matters: Streamlit loads `.streamlit/config.toml` (and, for MEco, `secrets.toml`) from the folder it is started in, so each app must start in its own folder to get its own theme.

### 11.1 Why a domain is required (not just the server's IP)

The dashboards are public web pages and should be served over HTTPS, and Let's Encrypt (the free certificate authority used below) only issues certificates for domain names, never for a bare IP address. (The ME website links to the dashboards rather than embedding them; see Section 11.8.)

The simplest path: ask whoever manages the lab's domain to add two subdomains (`meco` and `biom`, below) pointed at the EC2 server. If the domain is already owned, adding subdomains costs nothing.

### 11.2 Install nginx

```bash
sudo apt update
sudo apt install nginx -y
```

### 11.3 Confirm both apps start

```bash
# MEco (narrative page + Explorer) — from the repo root
cd ~/meco_dashboard
streamlit run app.py --server.port 8501 --server.headless true

# BioM — in a second SSH window, from its own folder, using its own virtual environment
cd ~/meco_dashboard/biom-dashboard
.venv/bin/streamlit run app.py --server.port 8502 --server.headless true
```

(This is just to confirm both apps start on distinct ports before wiring up systemd — Ctrl+C out of these once confirmed.)

### 11.4 Make both apps persistent with systemd

Without this, both apps stop the moment the SSH session disconnects.

```bash
sudo nano /etc/systemd/system/meco-dashboard.service
```

```ini
[Unit]
Description=MEco Research Data Platform (narrative + Explorer)
After=network.target postgresql.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/meco_dashboard
EnvironmentFile=/home/ubuntu/meco_dashboard/.env
ExecStart=/usr/bin/python3 -m streamlit run app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true
Restart=always

[Install]
WantedBy=multi-user.target
```

`EnvironmentFile` is what gives the Explorer its `DATABASE_URL` (Section 9). Then the BioM service:

```bash
sudo nano /etc/systemd/system/biom-dashboard.service
```

```ini
[Unit]
Description=BioM Innovation Database
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/meco_dashboard/biom-dashboard
ExecStart=/home/ubuntu/meco_dashboard/biom-dashboard/.venv/bin/python -m streamlit run app.py --server.port 8502 --server.address 127.0.0.1 --server.headless true
Restart=always

[Install]
WantedBy=multi-user.target
```

BioM reads only CSV files in `biom-dashboard/data/clean/`, so it needs no environment file.

```bash
sudo systemctl daemon-reload
sudo systemctl enable meco-dashboard biom-dashboard
sudo systemctl start meco-dashboard biom-dashboard
```

`Restart=always` means both apps come back automatically after a crash or server reboot — no manual restart needed. After a `git pull`, restart the affected one: `sudo systemctl restart meco-dashboard` (or `biom-dashboard`).

### 11.5 nginx reverse proxy — WebSocket headers are not optional

Create one file per subdomain. First MEco:

```bash
sudo nano /etc/nginx/sites-available/meco-dashboard
```

```nginx
server {
    listen 80;
    server_name meco.manufacturedecosystems.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

Then BioM:

```bash
sudo nano /etc/nginx/sites-available/biom-dashboard
```

```nginx
server {
    listen 80;
    server_name biom.manufacturedecosystems.com;

    location / {
        proxy_pass http://127.0.0.1:8502;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

**The `proxy_http_version 1.1` and `Upgrade`/`Connection` lines are required in both files, not optional.** Streamlit relies on a WebSocket connection for interactivity (filters, reruns). Without these exact lines, the page loads visually but nothing responds when clicked — an nginx config that looks "basically right" but is missing these will produce a dashboard that appears broken with no error message anywhere.

```bash
sudo ln -s /etc/nginx/sites-available/meco-dashboard /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/biom-dashboard /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 11.6 DNS + HTTPS

1. At the domain's DNS provider (for this project, the domain is registered with Squarespace Domains), add two A records, `meco` and `biom`, both pointing to the EC2 instance's Elastic IP. Wait until they resolve (`nslookup meco.manufacturedecosystems.com` should return the Elastic IP) before the next step — certbot fails if DNS hasn't propagated.
2. Install the certificates:

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d meco.manufacturedecosystems.com -d biom.manufacturedecosystems.com
```

certbot asks for an email address (used for expiry notices) and to accept the terms, and offers to redirect HTTP to HTTPS — choose the redirect. It then rewrites both nginx files for HTTPS and sets up automatic renewal (Let's Encrypt certificates last 90 days; renewal runs from a systemd timer, so no manual step is needed).

3. Check that renewal works: `sudo certbot renew --dry-run` should report success, and `systemctl list-timers | grep certbot` should show the timer scheduled.

### 11.7 Security group

In the AWS Console, confirm ports **80 and 443** are open to `0.0.0.0/0`. Ports 8501/8502 should **not** be open externally — nginx is the only thing that needs to reach them, and it does so over localhost (the systemd units also bind them to `127.0.0.1`). SSH (22) should stay restricted to your own IP. When your public IP changes (a new network, a new ISP lease), SSH will time out until you edit the port-22 rule and set Source to "My IP" (see `handover.md` Section 6).

### 11.8 Linking from the Squarespace site

The two dashboards are **not** embedded in the ME website with iframes. An iframe test showed that the website's header, footer and blank space end up around the app and are hard to control, and it puts the website's navigation around a data platform. Instead, the website links to each dashboard and opens it in a new window:

1. In Squarespace, open the Main Navigation and add a folder for the two tools.
2. Inside it, add two **external links** with "open in new window" turned on: "Literature Explorer" → `https://meco.manufacturedecosystems.com`, and "Innovation Database" → `https://biom.manufacturedecosystems.com`.

Nothing needs to change on the server for this. Link labels can be renamed in Squarespace at any time.

### 11.9 Cost

| Item | Monthly cost |
|---|---|
| EC2 instance (t3.small) | ~$15.18 |
| EBS storage | ~$1–3 |
| Elastic IP (public IPv4 address) | ~$3.65 |
| Domain/subdomain | $0 if added under an existing domain |
| SSL certificate (Let's Encrypt) | $0 |
| Outbound data transfer | $0 (covered by AWS's free 100GB/month tier at this project's traffic level) |

Roughly **$20–24/month** total, versus $0 on Streamlit Community Cloud. Get an exact figure after a month of real usage via AWS Console → Billing → Cost Explorer, rather than relying on the estimate above — small extras (CloudWatch, EBS snapshots) sometimes show up that aren't obvious in advance.

### 11.10 Verification checklist

- [ ] Both `systemctl status meco-dashboard` and `biom-dashboard` show `active (running)`
- [ ] `https://meco.manufacturedecosystems.com` loads the narrative page, and `https://meco.manufacturedecosystems.com/explorer` loads the Explorer, both over HTTPS with a valid certificate (padlock icon, no browser warning)
- [ ] `https://biom.manufacturedecosystems.com` loads the BioM dashboard with its own theme and its case table
- [ ] The Explorer's sidebar filters actually filter the table when clicked (confirms the WebSocket proxy headers are correct — if filters don't respond, revisit Section 11.5)
- [ ] Reboot the EC2 instance and confirm both apps (and PostgreSQL) come back up on their own (confirms `systemctl enable` took effect)
- [ ] The ME website's navigation links open both dashboards in a new window

Once all of these pass, the environment is ready. Move on to `handover.md` for how to actually operate the platform day to day.
