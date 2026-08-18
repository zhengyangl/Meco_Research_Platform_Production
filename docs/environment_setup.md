# Environment Setup

*Last updated: August 2026*

This is a one-time guide. Follow it once, in order, to go from nothing to a working server. For day-to-day operation after that, see `handover.md`.

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
4. Choose an instance type. The current production server uses **t3.micro** (1 vCPU, 1 GB RAM). This is enough to run everything, but it's tight on memory — Section 5 below covers how to work around that. If you'd rather not deal with memory workarounds at all, a **t3.small** (2 GB RAM) removes the problem entirely for a small cost increase.
5. Create a new key pair (or select an existing one) — this downloads a `.pem` file. **Save this file somewhere you won't lose it** (e.g. `~/Downloads/my-aws-key.pem`). You cannot download it again later; if you lose it, you lose access to the server.
6. Under network settings, make sure inbound rules allow **SSH (port 22)** from your IP, at minimum. If the dashboard or Explorer will ever be accessed directly from a browser (rather than embedded elsewhere), also open the relevant port (e.g. 8501 for Streamlit's default).
7. Launch the instance. Wait until its state shows **Running**.

Full official walkthrough if any of this is unclear: [Launch an EC2 instance — AWS documentation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EC2_GetStarted.html).

**A note on the IP address:** this server does not have a fixed (Elastic) IP configured. Its public IP can change if the instance is stopped and restarted. Before connecting, check the **Public IPv4 address** field on the instance's page in the AWS Console — don't assume it's the same as last time.

---

## 2. Connect and do first-time setup

Open a Terminal on your own computer.

```bash
# Move into the folder where your .pem key file is
cd ~/Downloads

# Connect — replace with the current public IP from the AWS Console
ssh -i my-aws-key.pem ubuntu@<SERVER_PUBLIC_IP>
```

If this is the first time connecting, you'll be asked to confirm the server's fingerprint — type `yes`.

Once connected, update the system and install the basics:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl zip python3-pip
```

---

## 3. Install PostgreSQL and build the database

```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql   # so it restarts automatically on reboot
```

### 3.1 Allow password login

By default, PostgreSQL only trusts local connections from the `postgres` system user — nothing else. You need to open a password-based login for the pipeline's database user.

Find the config files (the exact path includes the version number, e.g. `16`):

```bash
sudo find /etc/postgresql -name "pg_hba.conf"
sudo find /etc/postgresql -name "postgresql.conf"
```

Edit `pg_hba.conf` and add this line at the end:

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

A ready-made script does this for you: `schema.sql` (in the repo root). It creates the database, the `pipeline_user` role, all six tables, and the indexes that make the versioning pattern work. **This script has been tested end-to-end against a real PostgreSQL 16 instance** — every statement in it runs cleanly.

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
   sudo -u postgres psql -f ~/schema.sql
   ```
4. You should see a series of `CREATE DATABASE`, `CREATE ROLE`, `CREATE TABLE`, and `GRANT` confirmations, ending with a list of the 6 tables and two `0`-row counts (the database is empty until the pipeline adds data). If you see errors instead, don't proceed — fix the error first (the most common cause is forgetting to change the placeholder password, or running the script twice against a database that already exists).

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

Upload `requirements.txt` and `requirements_pipeline.txt` from the repo (or clone the whole repo — see Section 6), then:

```bash
pip3 install -r requirements.txt --break-system-packages
pip3 install -r requirements_pipeline.txt --break-system-packages
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

Either clone the repo directly (if the server has access to it) or upload files individually with `scp`, run from your own computer:

```bash
scp -i ~/Downloads/my-aws-key.pem -r pipeline/ app.py pages/ requirements*.txt \
  ubuntu@<SERVER_PUBLIC_IP>:~/meco_pipeline/
```

Adjust paths to wherever your local copy of the repo lives.

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

### 8.4 Share each Google resource with the service account

Open the downloaded JSON file and find the `client_email` field — it looks like `meco-pipeline-service@your-project-id.iam.gserviceaccount.com`.

**Every Google Sheet and Drive folder the pipeline touches must be individually shared with this email as Editor.** Having API access at the project level does *not* grant access to any specific sheet or folder — that's a separate, per-resource step. See `handover.md` for exactly which three resources need this, and what to name them if you're setting up fresh ones rather than reusing the project's originals.

### 8.5 explorer.py's credentials go somewhere different

Everything else in this section uses `GOOGLE_SERVICE_ACCOUNT_FILE` (an environment variable pointing at the JSON file). `explorer.py` is the one exception — because it runs inside Streamlit, it reads credentials from `.streamlit/secrets.toml` instead, using Streamlit's own secrets mechanism. Create this file locally (never commit it — it's in `.gitignore`):

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

If deploying `explorer.py` somewhere other than local development (e.g. Streamlit Community Cloud), the same TOML content goes into that platform's **Settings → Secrets** page instead of a local file.

---

## 9. Set environment variables

Copy `.env.example` to `.env` (or export these directly in your shell / a systemd service / cron's environment) and fill in the real values from the sections above:

```bash
export DATABASE_URL="postgresql://pipeline_user:<your DB password>@127.0.0.1:5432/me_dashboard"
export OPENROUTER_API_KEY="<your OpenRouter key>"
export GOOGLE_SERVICE_ACCOUNT_FILE="$HOME/service-account.json"
```

These need to be set in whatever context actually runs the pipeline scripts — a plain SSH session's exported variables disappear when you disconnect. For anything that needs to survive across sessions or run unattended (cron, a systemd service), set them in that context specifically, not just in your interactive shell.

---

## 10. Final verification checklist

Work through these in order. If any step fails, stop and fix it before moving to the next — later steps assume earlier ones work.

- [ ] `ssh` into the server successfully
- [ ] `psql -U pipeline_user -d me_dashboard -h 127.0.0.1 -W` connects and shows 6 tables via `\dt`
- [ ] `pip3 list` shows `pandas`, `psycopg2`, `sentence-transformers` installed
- [ ] `echo $DATABASE_URL` (etc.) shows the values you set, not blank
- [ ] `python3 pipeline/classify.py --dry-run --input <any small test file>` runs without an environment-variable error (see `handover.md` for what a real dry run looks like)
- [ ] `python3 pipeline/run_pipeline.py new-data --dry-run` successfully lists files in the Drive folder (confirms the Google service account setup works end to end)
---

## 11. Self-Hosting the Dashboard on EC2 (nginx + systemd)

*Status: this is the target architecture, not yet executed — the dashboard is currently still on Streamlit Community Cloud. See `handover.md` Section 9.*

Two platforms were evaluated and rejected before landing on this approach:

- **Staying on Streamlit Community Cloud long-term** — free, but the free tier permanently injects two branding icons ("Hosted with Streamlit", a creator-profile badge) into the bottom-right corner of every app. There is no official way to remove them; only self-hosting outside Community Cloud removes them, since they're injected by the hosting layer itself, not the Streamlit framework.
- **Streamlit in Snowflake (SiS)** — rejected. `explorer.py`'s main table depends entirely on AgGrid (`GridOptionsBuilder`, custom `JsCode` renderers for DOI links and paradigm color-coding), and AgGrid does not run inside SiS's sandbox — this is a known platform limitation (confirmed via Snowflake's own community forum), not something a package install fixes. Migrating would mean rewriting the Explorer's table with `st.dataframe` (losing custom cell rendering) and rebuilding the data-loading layer to read from Snowflake Stages instead of local parquet/JSON. Not worth it for this project.

The plan below keeps every line of existing code unchanged — both apps run exactly as they do today, just self-hosted instead of on Community Cloud.

### 11.1 Why a domain is required (not just the server's IP)

The ME website (Squarespace) is served over HTTPS. Browsers block an HTTPS page from embedding an HTTP iframe ("mixed content"). So the dashboard must also run over HTTPS — and Let's Encrypt (the free certificate authority used below) only issues certificates for domain names, never for a bare IP address.

The simplest path: ask whoever manages the lab's domain to add a subdomain (e.g. `dashboard.manufacturedecosystems.com`) pointed at the EC2 server. If the domain is already owned, adding a subdomain costs nothing.

### 11.2 Install nginx

```bash
sudo apt update
sudo apt install nginx -y
```

### 11.3 Run both apps on separate ports

```bash
# Narrative page
streamlit run app.py --server.port 8501

# Data Explorer
streamlit run explorer.py --server.port 8502
```

(This is just to confirm both apps start correctly on distinct ports before wiring up systemd — Ctrl+C out of these once confirmed.)

### 11.4 Make both apps persistent with systemd

Without this, both apps stop the moment the SSH session disconnects.

```bash
sudo nano /etc/systemd/system/meco-narrative.service
```

```ini
[Unit]
Description=MEco Narrative Dashboard
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/meco_dashboard
ExecStart=/usr/bin/python3 -m streamlit run app.py --server.port 8501 --server.headless true
Restart=always

[Install]
WantedBy=multi-user.target
```

Repeat for the Explorer (`meco-explorer.service`), changing the port to `8502` and the script to `explorer.py`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable meco-narrative meco-explorer
sudo systemctl start meco-narrative meco-explorer
```

`Restart=always` means both apps come back automatically after a crash or server reboot — no manual restart needed.

### 11.5 nginx reverse proxy — WebSocket headers are not optional

```bash
sudo nano /etc/nginx/sites-available/meco
```

```nginx
server {
    listen 80;
    server_name dashboard.manufacturedecosystems.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    location /explorer/ {
        proxy_pass http://127.0.0.1:8502/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

**The `proxy_http_version 1.1` and `Upgrade`/`Connection` lines are required, not optional.** Streamlit relies on a WebSocket connection for interactivity (filters, reruns). Without these exact lines, the page loads visually but nothing responds when clicked — a nginx config that looks "basically right" but is missing these will produce a dashboard that appears broken with no error message anywhere.

```bash
sudo ln -s /etc/nginx/sites-available/meco /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 11.6 DNS + HTTPS

1. Have whoever controls the domain's DNS add an A record: `dashboard` → the EC2 instance's public IP.
2. Install the certificate:

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d dashboard.manufacturedecosystems.com
```

`certbot` rewrites the nginx config for HTTPS automatically and sets up auto-renewal (Let's Encrypt certificates expire every 90 days; no manual renewal needed after this).

### 11.7 Security group

In the AWS Console, confirm ports **80 and 443** are open to `0.0.0.0/0`. Ports 8501/8502 should **not** be open externally — nginx is the only thing that needs to reach them, and it does so over localhost.

### 11.8 Embedding into the Squarespace site

Requires a Squarespace **Business plan or higher** — the Embed/Code block used here isn't available on the Personal plan.

1. Edit the target page → add an **Embed** block (or **Code** block, same effect) → paste:

```html
<iframe src="https://dashboard.manufacturedecosystems.com/?embed=true"
        style="height: 1200px; width: 100%; border: none;">
</iframe>
```

2. `?embed=true` removes Streamlit's top toolbar. On a self-hosted app (unlike Community Cloud), there's no bottom-right branding to worry about — it only exists on the free hosting tier.
3. **iframe height is fixed, app content is not.** If a user expands something or a filtered table grows longer than the iframe's set height, it either scrolls inside the iframe (double-scrollbar) or gets cut off. There's no official auto-resize; starting with a generous fixed height (1200px+) is the practical workaround.
4. Test at mobile width specifically before considering this done — the Explorer's sidebar filters are especially prone to being squeezed in a narrow iframe.

### 11.9 Cost

| Item | Monthly cost |
|---|---|
| EC2 instance (t3.small, if upgraded from t3.micro) | ~$15.18 |
| EBS storage | ~$1–3 |
| Domain/subdomain | $0 if added under an existing domain |
| SSL certificate (Let's Encrypt) | $0 |
| Outbound data transfer | $0 (covered by AWS's free 100GB/month tier at this project's traffic level) |

Roughly **$16–20/month** total, versus $0 on Streamlit Community Cloud. Get an exact figure after a month of real usage via AWS Console → Billing → Cost Explorer, rather than relying on the estimate above — small extras (CloudWatch, EBS snapshots) sometimes show up that aren't obvious in advance.

### 11.10 Verification checklist

- [ ] Both `systemctl status meco-narrative` and `meco-explorer` show `active (running)`
- [ ] `https://dashboard.manufacturedecosystems.com` loads the narrative page over HTTPS with a valid certificate (padlock icon, no browser warning)
- [ ] The Explorer's sidebar filters actually filter the table when clicked (confirms the WebSocket proxy headers are correct — if filters don't respond, revisit Section 11.5)
- [ ] Reboot the EC2 instance and confirm both apps come back up on their own (confirms `systemctl enable` took effect)
- [ ] Embed the iframe on a Squarespace test page and check it at both desktop and mobile widths

Once all of these pass, the environment is ready. Move on to `handover.md` for how to actually operate the platform day to day.
