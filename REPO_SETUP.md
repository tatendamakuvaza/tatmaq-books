# Putting Tatmaq Books on GitHub — 60-second guide

The project in this folder is already a **git repository with one clean commit**
(62 tracked files). Everything needed to create the GitHub repo is prepared; the
push itself has to happen from your side, because this sandbox has no GitHub
credentials (and you should never paste a personal access token into a chat).

Two paths — pick one.

---

## Path A — Browser + 3 commands (recommended)

**1. Create the empty repository**

* Go to **https://github.com/new**
* Repository name: `tatmaq-books`
* Visibility: **Private** (this is commercial software)
* Do **not** tick "Add a README", ".gitignore" or "licence" — the repo must start empty
* Click **Create repository**

**2. Push this project**

From a terminal in this project folder:

```bash
git remote add origin https://github.com/<your-username>/tatmaq-books.git
git push -u origin main
```

If the folder has no `.git` (for example you downloaded the zip instead), initialise it first:

```bash
git init -b main
git config user.name  "Your Name"
git config user.email "you@example.com"
git add -A
git commit -m "Tatmaq Books v1.1"
git remote add origin https://github.com/<your-username>/tatmaq-books.git
git push -u origin main
```

**3. Or just run the included script**

```bash
./push-to-github.sh https://github.com/<your-username>/tatmaq-books.git
```

The script sets a git identity if needed, initialises the repo if missing, runs the
32-check smoke test before pushing, and prints the Railway deployment steps when done.

---

## Path B — GitHub CLI (one command)

If you have `gh` installed and signed in (`gh auth login`):

```bash
./push-to-github.sh --create tatmaq-books
```

That creates a **private** repo and pushes in one step.

---

## What gets committed — and what does not

| Committed | Ignored (see `.gitignore`) |
|---|---|
| All Python modules, templates, static assets | `tatmaq.db` — the database is rebuilt by `python3 db.py` |
| `tests/smoke_test.py`, CI workflow | `.env` — your secret key stays local |
| `Dockerfile`, `railway.json`, `Procfile` | `__pycache__/`, `.venv/`, logs, backups |
| Docs: README, USER_GUIDE, HOSTING_AND_MONETISATION, brochure | |

Why the database is excluded: it contains password hashes and demo data. The app
creates and seeds a fresh one on first boot, so a clean clone runs immediately.

---

## After the push — deploy straight from the repo

1. **railway.app → New Project → Deploy from GitHub repo** → pick `tatmaq-books`
2. Railway reads `railway.json` automatically:
   * start command `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4`
   * health check `GET /healthz`
3. Add a **Volume** mounted at `/data`, then set two environment variables:

   | Variable | Value |
   |---|---|
   | `TATMAQ_SECRET` | run `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` and paste the output |
   | `TATMAQ_DB` | `/data/tatmaq.db` |

4. Deploy. Your URL is `https://tatmaq-books-production.up.railway.app` (rename the
   service to change it).
5. Open `/register` on the live URL and create the **first real workspace** — that
   company, its users and its books are yours; the shared demo logins do not appear
   in workspaces you register yourself.

---

## Guardrails already in the repo

* **CI on every push** (`.github/workflows/ci.yml`): runs the 32-check smoke test, then
  boots gunicorn and hits `/healthz` and `/login`. A red X means don't deploy.
* **`.env.example`** documents the two environment variables — never commit `.env`.
* **`LICENSE`** is proprietary ("all rights reserved") by default. Swap it for MIT or
  Apache-2.0 if you ever want the code open.

## Good first issues to log in the repo

Create these as GitHub issues so the build has a visible backlog:

1. Ledger locking + append-only audit log (who posted what, when, from where)
2. SMTP for real user invites and password resets
3. Nightly backup job with a monthly restore drill
4. Recurring invoices and payment reminders
5. Customer portal (invoice download, statement, pay-online link)
6. ZIMRA fiscalisation (FDMS) integration
