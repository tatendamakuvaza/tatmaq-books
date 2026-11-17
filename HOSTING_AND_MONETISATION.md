# Tatmaq Books — Hosting on $10 and turning it into income

You have **$10 total** (not per month). This plan gets Tatmaq Books online, keeps it online
for two months, and gets you to the first paying client with no further spend.

## 1. What you are hosting

One application serves both frontend and backend:

| Layer | Technology | Why |
|---|---|---|
| Frontend | Server-rendered Jinja2 + one CSS file + one JS file | No build step, no Node, no CDN — fast on 3G |
| Backend | Python 3 / Flask | Small memory footprint, easy to hire for |
| Database | SQLite file (`tatmaq.db`) | Zero cost, zero admin, one backup command |
| Server | gunicorn (2 workers) | Included in `Procfile` |

A single process on 512 MB RAM runs the whole system. That is why $5 is possible.

## 2. The $10 plan (option A — recommended)

### Phase 1 — Month 1 & 2: Railway Hobby ($5/month)

Railway's Hobby plan is **$5/month and includes $5 of usage**, so a small Flask app plus a
volume stays inside the fee. Total spend: **$5 in month 1, $5 in month 2 → $10 spent, two
months live.**

Steps:

1. Push this folder to a GitHub repository.
2. Create a Railway project → **Deploy from GitHub repo**.
3. Railway detects Python. Confirm the start command:
   `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4`
4. Add a **Volume** mounted at `/data`, then set environment variable
   `TATMAQ_DB=/data/tatmaq.db`.
5. Set `PORT` (Railway does this automatically) and deploy.
6. You get a free `https://<project>.up.railway.app` address — that is your live demo link
   for prospects. **No domain purchase needed yet.**
7. Seed the database once from the Railway shell: `python3 db.py`
   (or just open `/setup` and click a template — it seeds itself.)

### Phase 2 — Month 3 onward: Hetzner CX22 (€4.35 ≈ $4.70/month)

When the first client pays $29, move to Hetzner for more RAM, a real IP and unlimited
subdomain multi-tenancy:

```bash
# on a fresh Ubuntu 24.04 CX22
sudo apt update && sudo apt install -y python3-venv nginx
git clone <your repo> /opt/tatmaq && cd /opt/tatmaq
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
TATMAQ_DB=/opt/tatmaq/data/tatmaq.db .venv/bin/python db.py

# gunicorn service
sudo tee /etc/systemd/system/tatmaq.service >/dev/null <<'EOF'
[Unit]
Description=Tatmaq Books
After=network.target
[Service]
WorkingDirectory=/opt/tatmaq
Environment=TATMAQ_DB=/opt/tatmaq/data/tatmaq.db
ExecStart=/opt/tatmaq/.venv/bin/gunicorn app:app -b 127.0.0.1:8000 -w 2 -k gthread --threads 4
Restart=always
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now tatmaq

# nginx reverse proxy + TLS
sudo tee /etc/nginx/sites-available/tatmaq >/dev/null <<'EOF'
server {
  listen 80;
  server_name books.yourdomain.co.zw;
  location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; }
}
EOF
sudo ln -s /etc/nginx/sites-available/tatmaq /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo apt install -y certbot python3-certbot-nginx && sudo certbot --nginx -d books.yourdomain.co.zw
```

Nightly backup (one line in `crontab -e`):

```
15 2 * * * sqlite3 /opt/tatmaq/data/tatmaq.db ".backup /opt/tatmaq/backups/$(date +\%F).db"
```

### Cost table

| Item | Cost | When |
|---|---|---|
| Railway Hobby | $5 / month | Months 1–2 (paid from your $10) |
| Free `*.up.railway.app` subdomain | $0 | Forever |
| Hetzner CX22 | ≈ $4.70 / month | Month 3+, funded by client #1 |
| Domain (`.co.zw` ≈ $20–40/yr, `.com` ≈ $10–12/yr) | $0 initially | Only once revenue starts |
| TLS certificates | $0 | Let's Encrypt |
| Backups (local disk + free object storage tier) | $0 | From day one |
| **Total out of pocket before revenue** | **$10** | Two months online |

## 3. Lower-cost / no-cost alternatives

| Option | Cost | Trade-off |
|---|---|---|
| **Run locally on your laptop** | $0 | Perfect for demos and closing clients; not public |
| **Render free web service** | $0 | 512 MB, sleeps after idle — good for a public demo link |
| **Railway free trial credit** | $0 | $5 credit for 30 days, then $1/month credit |
| **Hetzner CX22 only** | ≈ $4.70/month | Best value, but you must be comfortable with SSH |
| **Oracle Cloud Always Free** | $0 | 1 GB ARM VM free forever, but sign-up friction is high |

My recommendation: **demo locally → publish on Railway for two months → move to Hetzner when
client #1 signs.** Spend nothing on a domain until a client is paying.

## 4. Turning it into money

### 4.1 Who buys this

* SMEs already using Excel or a paper cash book (the majority of Zimbabwean SMEs)
* Suppliers and contractors who must produce VAT invoices to win corporate work
* Schools, clinics, farms and haulage firms whose "industry" is not in global SaaS templates
* Accountants and consultants who want a tool to offer bookkeeping as a service

### 4.2 Pricing that works in this market

| Tier | Price | Target |
|---|---|---|
| Starter | **$15/month** | Solo traders, 1 user |
| Standard | **$29/month** | SMEs, up to 3 users, payroll + inventory |
| Industry Pro | **$49/month** | Multi-branch, AI analyst, custom KPIs |
| Setup / migration | **$150 one-off** | Highest-value sale: opening balances + training |
| Bookkeeping service | **$80–200/month** | You (or a partner accountant) run their books on Tatmaq Books |

Collect with **EcoCash, OneMoney, ZIPIT or Paynow** (Paynow integrates card + mobile money and
is the standard local gateway). Charge annually with a 2-month discount — it funds hosting for
the year.

### 4.3 Launch sequence (first 90 days)

1. **Week 1 — Finish the product demo.** Use the Industry Setup page to load the template that
   matches each prospect's sector. A mining client should never see a school chart of accounts.
2. **Week 2 — Build 3 demo links.** Same app, different industry template, seeded demo data.
   Send a link, not a PDF.
3. **Week 3–4 — First five meetings.** Target one business per industry (a mine, a school, a
   haulage firm, a farm, a clinic). Offer a **free month of setup** in exchange for a
   testimonial and permission to use them as a reference.
4. **Month 2 — Convert two clients.** Two Standard clients = $58/month ≈ 12× your hosting cost.
5. **Month 3 — Add the accountant channel.** Accountants bring 5–20 clients each. Give them a
   20% revenue share and a white-label workspace.

### 4.4 Unit economics

| Metric | Value |
|---|---|
| Hosting per server | ≈ $4.70/month (Hetzner CX22) |
| Clients per server (comfortable) | 10–30 small tenants |
| Hosting cost per client | ≈ $0.16–0.47/month |
| Revenue per client | $15–49/month |
| Gross margin | **> 95%** |
| Break-even | **1 client** |

### 4.5 What makes it defensible

* **Industry depth** — a competitor must rebuild 8 charts of accounts and KPIs, not one screen.
* **Local compliance** — ZIMRA PAYE bands, AIDS levy, NSSA, VAT schedules built in.
* **The executive dashboard** — owners buy visibility; accountants buy the ledger. You sell both.
* **The AI analyst** — closes deals in demos because it answers questions in the owner's words.

## 5. Security posture of this build

Shipped:

* **Authentication** — hashed passwords (Werkzeug PBKDF2), server-side sessions, 14-day expiry.
* **Multi-tenancy** — every query is scoped to the signed-in company; cross-tenant IDs are refused.
* **Roles enforced server-side** — Owner / Accountant / Sales Clerk / Auditor / Demo. Hiding a
  button is never the control; the POST itself is rejected.
* **Shareable demo links** — signed, 7-day expiry, seeded throwaway workspace only.
* **Secret key** — set `TATMAQ_SECRET` in production (see README).

Still to do before charging real money:

1. **Ledger locking** — posted journals immutable; corrections via reversing entries only.
2. **SMTP invites & password resets** — invites currently show a temporary password on screen.
3. **Backups + restore drill** — nightly `sqlite3 .backup` plus a monthly restore test.
4. **Audit log** — record every POST with user, IP and timestamp.
5. **Terms, privacy note and a service agreement** — clients' financial data is sensitive.
6. **HTTPS + daily monitoring** — already covered by the nginx/certbot steps above; add uptime checks.

Roadmap parity after that: recurring invoices & reminders → customer portal → bank feed
integrations → ZIMRA fiscalisation (FDMS) → multi-currency transactions.

## 6. Positioning line for your pitch

> “Zoho Books is built for everyone, so it is built for no one in particular.
> Tatmaq Books installs the ledger your industry actually uses — and puts the numbers
> an owner cares about on one screen.”
