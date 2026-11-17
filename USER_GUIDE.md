# Tatmaq Books — User Guide

A one-page operating manual for demoing and running the system.

## Getting in

Open the app and you land on **/login**. Demo accounts (password `demo1234`):

| Email | Role | What they can do |
|---|---|---|
| owner@tatmaqbooks.co.zw | Owner / Admin | Everything |
| accountant@tatmaqbooks.co.zw | Accountant | All documents and reports |
| sales@tatmaqbooks.co.zw | Sales Clerk | Invoices, quotes, credit notes, customers — no bills/payroll/settings |
| auditor@tatmaqbooks.co.zw | Auditor | Read-only: every report, no posting |

Or press **Explore the demo** for a throwaway seeded workspace, and **Create workspace** to
provision a clean company of your own.

| Screen | What you do there |
|---|---|
| **Dashboard** (home) | Read the business in 30 seconds: revenue, profit, cash, receivables, health score, aging, alerts, top customers, industry KPI |
| **Industry Setup** | Switch between the 8 industry templates. “Activate + demo data” loads 12 months of realistic transactions; “Start clean” gives you just opening balances |
| **Settings** | Company name, address, tax name/rate, fiscal year, currency, users, statutory rates |

## Daily cycle (the 6 actions that matter)

1. **Quote** → Sales ▸ Quotations ▸ New quotation. When the customer accepts, hit **Convert to invoice**.
2. **Invoice** → Sales ▸ Invoices ▸ New invoice. Pick items; totals, VAT and COGS post automatically.
3. **Record the money** → open the invoice ▸ **Record payment**. Bank, method and reference are captured.
4. **Buy properly** → Purchases ▸ Purchase Orders ▸ New purchase order → **Save receipt** → **Create bill**.
5. **Capture supplier bills** (for anything not ordered) → Purchases ▸ Bills ▸ New bill.
6. **Pay suppliers** → open the bill ▸ **Pay this bill**.
7. **Handle returns** → Sales ▸ Credit Notes (customers) and Purchases ▸ Vendor Credits (suppliers).
8. **Reconcile** → Operations ▸ Banking ▸ match each bank-feed line.

End of month: **Payroll ▸ Run payroll** (PAYE, AIDS levy and NSSA are computed) → **Reports ▸ VAT Return** → check **Reports ▸ Profit & Loss**.

## Module map

* **Invoices / Quotations** — filters for All, Unpaid, Overdue, Paid; search by number or customer; print to PDF.
* **Credit Notes** — sales returns that reverse revenue, VAT and (optionally) cost of sales; apply the credit to an open invoice or refund it to the bank.
* **Purchase Orders** — order → receive → bill in three steps; a PO is a commitment, never a ledger entry.
* **Bills / Vendor Credits / Payments** — supplier bills with input VAT, supplier credits for rebates and returns, payments in/out; every movement posts a journal.
* **Contacts** — customers and suppliers with live balances and document history.
* **Banking** — bank account cards with ledger balances, transaction feed, one-click match/unmatch.
* **Inventory & Items** — stock on hand, reorder alerts, valuation; “Set” a quantity to post an adjustment; add new goods or services.
* **Payroll** — employee register, live preview of PAYE/NSSA/net, monthly run, printable register.
* **Fixed Assets** — asset register, straight-line depreciation, capitalise new assets (Dr PPE / Cr Bank).
* **Journal** — full double-entry trail; manual journals are validated (Dr must equal Cr) before posting.
* **Chart of Accounts** — the sector-specific account list with natural balances; drill into any P&L account.
* **Reports** — P&L · Balance Sheet · Trial Balance · Cash Flow · VAT Return · Aging · General Ledger · Sales by Item · Inventory Valuation · Asset Register. Every report has a date range.

## The AI panel

Click **Ask Tatmaq AI** (bottom-right) and ask things like:

* “How is the business doing?”
* “What is my cash position and runway?”
* “Who owes me money?”
* “How much VAT do I owe?”
* “Biggest expenses”
* “Top customers”
* “What should I focus on?”
* “Forecast next month”

It reads the live ledger through `/api/dashboard`, so answers always match the reports.

## Demo script (5 minutes, for a prospect)

1. Dashboard — “this is your morning view”. Point at the **health gauge** and **needs attention**.
2. Industry Setup — switch to the prospect's sector; say “your chart of accounts, not a generic one”.
3. Create an invoice live → show the **journal preview** panel → open the invoice → record a payment.
4. Reports ▸ P&L and Balance Sheet — “both reconcile to the same trial balance”.
5. Ask Tatmaq AI “how is my cash runway?” — close on the $29/month Standard plan.
6. End on Operations ▸ Payroll — “ZIMRA PAYE and NSSA already done”.

## Roles at a glance

* **Owner / Admin** — all modules, users, settings, industry setup.
* **Accountant** — all documents and reports, may invite users.
* **Sales Clerk** — invoicing and customers only; bills, payroll, assets, journals and settings are blocked server-side (not just hidden).
* **Auditor** — read-only; every report and document is visible, posting is refused with a clear message.
* **Demo visitor** — full write access inside an isolated throwaway workspace.

## Housekeeping

* **Reset demo** (Settings, bottom-right card) regenerates fresh demo data at any time.
* Demo data is safe to play with — nothing here touches real client files.
* Backups: copy `tatmaq.db`. One file = the whole business.
