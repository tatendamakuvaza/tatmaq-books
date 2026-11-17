# Tatmaq Books

Industry-adaptive, double-entry accounting system with an executive dashboard,
authentication, multi-tenancy and shareable demo workspaces.

```
tatmaq/
├─ app.py                   Flask application (routes, posting logic, guards)
├─ auth.py                  Sessions, hashed passwords, roles, signed demo links
├─ analytics.py             KPIs, P&L, balance sheet, aging, VAT, cash flow
├─ charts.py                Hand-rolled SVG charts (no CDN, no JS chart library)
├─ db.py                    Schema, tenant rebuilds, 8 profiles, demo data, PAYE
├─ templates/               Jinja2 templates (35 pages incl. public auth pages)
├─ static/                  style.css, app.js
├─ tests/smoke_test.py      32 checks: auth, roles, tenancy, lifecycle, ledger
├─ .github/workflows/ci.yml CI on every push (smoke test + gunicorn boot)
├─ Dockerfile               container image (gunicorn on 8000, /data volume)
├─ railway.json             Railway deploy config (start command, /healthz)
├─ Procfile                 generic PaaS entry point
├─ .env.example             the two environment variables you need
├─ push-to-github.sh        creates/pushes the repo after running the smoke test
├─ REPO_SETUP.md            GitHub + Railway walkthrough
└─ requirements.txt
```

## Repository & deployment

This folder is a git repository with one commit. To publish it:

```bash
./push-to-github.sh https://github.com/<you>/tatmaq-books.git   # or: --create tatmaq-books
```

Full walkthrough (empty-repo rules, Railway variables, volume mount) is in
**REPO_SETUP.md**. CI runs `tests/smoke_test.py` on every push, so a red X means
the build is not safe to deploy.

## Run locally

```bash
cd tatmaq
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 db.py          # create + seed the demo workspace
python3 app.py         # http://localhost:5000
```

Production:

```bash
gunicorn app:app --bind 0.0.0.0:8000 --workers 2 --threads 4
```

Or with Docker:

```bash
docker build -t tatmaq-books .
docker run -p 8000:8000 -v tatmaq_data:/data -e TATMAQ_SECRET=change-me tatmaq-books
```

Verify a checkout before deploying:

```bash
python3 tests/smoke_test.py     # 32 checks, exit 0 = green
```

Set `TATMAQ_SECRET` to a long random string in production — it signs sessions and demo links:

```bash
export TATMAQ_SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
```

## Signing in — demo accounts

The seeded workspace ships with four roles, all with password `demo1234`:

| Email | Role | Can do |
|---|---|---|
| `owner@tatmaqbooks.co.zw` | Owner / Admin | Everything, including users, settings and industry setup |
| `accountant@tatmaqbooks.co.zw` | Accountant | Everything except creating users |
| `sales@tatmaqbooks.co.zw` | Sales Clerk | Invoices, quotes, credit notes, customers, inventory — **no** bills, payroll, assets, journals, settings |
| `auditor@tatmaqbooks.co.zw` | Auditor (read-only) | Views every report and document; all posting is blocked |

Public routes: `/welcome` (marketing page), `/login`, `/register`, `/demo`.
Everything else requires a session — unauthenticated requests are redirected to `/login`.

## Multi-tenancy

* Every table carries `company_id`; every query filters on the identity's company.
* **Create workspace** (`/register`) provisions a new company with a clean chart of accounts,
  opening balance and *your* login only — plus demo customers/suppliers you can rename.
* **Explore the demo** (`/demo`) spins up a throwaway, fully seeded workspace with unique logins,
  so no visitor ever sees another company's books. `GET /demo/link/<token>` gives a signed,
  7-day shareable link for sending to a prospect.
* **Industry Setup** and **Reset demo** rebuild *only the current tenant* — never the whole database.

## What is wired to the ledger

| Action | Journal posted |
|---|---|
| Sales invoice | Dr Receivables · Cr Revenue · Cr VAT · Dr COGS / Cr Inventory |
| Customer payment | Dr Bank · Cr Receivables |
| Credit note (sales return) | Dr Sales returns · Dr VAT · Cr Customer credits available (+ inventory/COGS if restocked) |
| Credit note applied / refunded | Dr Customer credits · Cr Receivables / Bank |
| Supplier bill | Dr Expense/Inventory · Dr Input VAT · Cr Payables |
| Supplier payment | Dr Payables · Cr Bank |
| Vendor credit | Dr Payables · Cr Input VAT · Cr Supplier credits available |
| Vendor credit applied | Dr Supplier credits · Cr Payables |
| Purchase order → bill | Same as supplier bill; PO itself is a memo commitment, never a ledger entry |
| Quote → invoice | Same as invoice, no re-typing |
| Payroll run | Dr Salaries + employer NSSA · Cr PAYE, AIDS, NSSA, net wages |
| Net pay transfer | Dr Net wages accrued · Cr Bank |
| Asset capitalisation | Dr PPE · Cr Bank |
| Monthly depreciation | Dr Depreciation · Cr Accumulated depreciation |
| Stock adjustment | Dr/Cr Inventory vs Other income / Repairs |
| Manual journal | Validated Dr = Cr before posting |

Reports read the same journal lines, so Trial Balance, P&L and Balance Sheet always agree.

## Statutory (Zimbabwe)

* PAYE: ZIMRA USD monthly bands — 0% to $100, then 20/25/30/35/40%
* AIDS levy: 3% of PAYE
* NSSA: 4.5% employee + 4.5% employer, insurable earnings capped at $700/month
* VAT: 15% default, output − input schedule for the monthly return

Rates live in `db.paye_zim()` and in Settings — edit them as ZIMRA tables change.

## Still to do before charging real money

1. **Ledger locking** — posted journals should be immutable; corrections via reversing entries.
2. **Email delivery** — invited users get a temporary password on screen today; wire SMTP.
3. **Backups** — nightly `sqlite3 tatmaq.db ".backup ..."` (see `HOSTING_AND_MONETISATION.md`).
4. **Terms & privacy** — clients' financial data is sensitive; paper it.
5. **Postgres** for multi-company SaaS scale (SQLite is fine per-instance or under ~50 tenants).

Roadmap after that: recurring invoices & reminders → customer portal → bank feed integrations →
ZIMRA fiscalisation (FDMS) → multi-currency transactions.
