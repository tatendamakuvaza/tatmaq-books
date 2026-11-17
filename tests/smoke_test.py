#!/usr/bin/env python3
"""Tatmaq Books — smoke test.

Runs against a throwaway database so it can never touch real books.
Checks authentication, role permissions, tenant isolation, every page,
the document lifecycle and that the ledger stays balanced.

    python3 tests/smoke_test.py        # exit code 0 = all good
"""
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# isolate: fresh database per run, before importing the app
TMP_DB = pathlib.Path(tempfile.mkdtemp(prefix="tatmaq-smoke-")) / "smoke.db"
os.environ["TATMAQ_DB"] = str(TMP_DB)

import db  # noqa: E402

db.reset_and_seed("mining", demo=True)

import app as A  # noqa: E402

PASS, FAIL = [], []


def check(label, condition, detail=""):
    (PASS if condition else FAIL).append(label)
    mark = "ok  " if condition else "FAIL"
    print(f"  [{mark}] {label}{(' — ' + str(detail)) if detail and not condition else ''}")


def client():
    return A.app.test_client()


PASSWORD = "demo1234"
ROLES = ["owner", "accountant", "sales", "auditor"]

PAGES = [
    "/", "/invoices", "/invoices/new", "/quotes", "/quotes/new",
    "/credit-notes", "/credit-notes/new", "/bills", "/bills/new",
    "/vendor-credits", "/vendor-credits/new", "/purchase-orders", "/purchase-orders/new",
    "/payments", "/banking", "/contacts", "/contacts?tab=vendor", "/contacts/new",
    "/inventory", "/payroll", "/payroll/new", "/assets", "/journal", "/journal/new",
    "/accounts", "/reports", "/reports/pl", "/reports/bs", "/reports/tb", "/reports/cf",
    "/reports/vat", "/reports/aging", "/reports/gl", "/reports/sales-items",
    "/reports/stock", "/reports/assets-register", "/setup", "/settings", "/api/dashboard",
]


def main():
    print("\n1. Authentication")
    c = client()
    check("anonymous / redirects to login", c.get("/", follow_redirects=False).status_code == 302)
    check("anonymous API is 401", c.get("/api/dashboard").status_code == 401)
    check("login page renders", c.get("/login").status_code == 200)
    check("marketing page renders", c.get("/welcome").status_code == 200)
    check("health check renders", c.get("/healthz").status_code == 200)
    bad = c.post("/login", data={"email": "owner@tatmaqbooks.co.zw", "password": "wrong"})
    check("wrong password rejected", b"not recognised" in bad.data)

    print("\n2. Every page for every role")
    sessions = {}
    for role in ROLES:
        s = client()
        r = s.post("/login", data={"email": f"{role}@tatmaqbooks.co.zw", "password": PASSWORD},
                   follow_redirects=True)
        sessions[role] = s
        check(f"{role} can sign in", r.status_code == 200)
        broken = [(p, s.get(p).status_code) for p in PAGES if s.get(p).status_code != 200]
        check(f"{role}: all {len(PAGES)} pages return 200", not broken, broken)

    print("\n3. Role permissions (server-side, not just hidden buttons)")
    conn = db.connect()

    def count(table):
        return conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]

    n = count("invoices")
    sessions["auditor"].post("/invoices/new", data={
        "contact_id": "1", "item_id": ["1"], "qty": ["1"], "price": ["100"]})
    check("auditor cannot post an invoice", count("invoices") == n)

    n = count("bills")
    sessions["sales"].post("/bills/new", data={
        "vendor_id": "1", "line_account": ["acc:1"], "qty": ["1"], "unit_cost": ["10"]})
    check("sales clerk cannot create a bill", count("bills") == n)

    n = count("invoices")
    sessions["sales"].post("/invoices/new", data={
        "contact_id": "1", "item_id": ["1"], "qty": ["2"], "price": ["100"], "desc": ["smoke"]})
    check("sales clerk can invoice", count("invoices") == n + 1)

    print("\n4. Tenant isolation")
    demo = client()
    demo.get("/demo")
    demo_company = conn.execute("SELECT id, name FROM companies ORDER BY id DESC LIMIT 1").fetchone()
    own_invoice = conn.execute("SELECT id FROM invoices WHERE company_id=? LIMIT 1",
                               (demo_company["id"],)).fetchone()
    check("demo workspace gets its own company",
          demo_company["name"] != conn.execute("SELECT name FROM companies ORDER BY id LIMIT 1")
          .fetchone()["name"], demo_company["name"])
    check("demo can open its own invoice",
          demo.get(f"/invoices/{own_invoice['id']}").status_code == 200)
    check("owner cannot open demo's invoice",
          sessions["owner"].get(f"/invoices/{own_invoice['id']}", follow_redirects=False).status_code == 302)
    check("demo api is scoped to demo company",
          demo.get("/api/dashboard").get_json()["company"] !=
          sessions["owner"].get("/api/dashboard").get_json()["company"])

    print("\n5. Registration provisions an isolated workspace")
    new = client()
    r = new.post("/register", data={
        "name": "Smoke Owner", "email": "smoke@example.co.zw", "company": "Smoke Test Co",
        "industry": "transport", "password": "strongpass1", "confirm": "strongpass1"},
        follow_redirects=True)
    check("registration succeeds", r.status_code == 200)
    cid = conn.execute("SELECT id FROM companies WHERE name='Smoke Test Co'").fetchone()["id"]
    users = conn.execute("SELECT email FROM users WHERE company_id=?", (cid,)).fetchall()
    check("new tenant gets only its own owner login",
          [u["email"] for u in users] == ["smoke@example.co.zw"], [u["email"] for u in users])
    d = new.get("/api/dashboard").get_json()
    check("new tenant starts with zero revenue", d["revenue_ytd"] == 0, d["revenue_ytd"])

    print("\n6. Document lifecycle on a fresh tenant")
    cust = conn.execute("SELECT id FROM contacts WHERE company_id=? AND type='customer' LIMIT 1",
                        (cid,)).fetchone()["id"]
    vend = conn.execute("SELECT id FROM contacts WHERE company_id=? AND type='vendor' LIMIT 1",
                        (cid,)).fetchone()["id"]
    item = conn.execute("SELECT id FROM items WHERE company_id=? LIMIT 1", (cid,)).fetchone()["id"]
    acct = conn.execute("SELECT id FROM accounts WHERE company_id=? AND code='5220'",
                        (cid,)).fetchone()["id"]

    new.post("/invoices/new", data={"contact_id": cust, "date": "2026-11-01",
                                    "due_date": "2026-12-01", "item_id": [str(item)],
                                    "qty": ["2"], "price": ["1250"], "desc": ["Freight run"]})
    inv = conn.execute("SELECT * FROM invoices WHERE company_id=? ORDER BY id DESC LIMIT 1",
                       (cid,)).fetchone()
    check("invoice posted", inv["total"] == 2875.0, inv["total"])

    new.post(f"/invoices/{inv['id']}/pay", data={"amount": "500", "method": "EcoCash",
                                                 "date": "2026-11-05"})
    inv = conn.execute("SELECT * FROM invoices WHERE id=?", (inv["id"],)).fetchone()
    check("payment applied", inv["amount_paid"] == 500.0, inv["amount_paid"])

    new.post("/credit-notes/new", data={"contact_id": cust, "invoice_id": str(inv["id"]),
                                        "date": "2026-11-06", "reason": "Billing error",
                                        "item_id": [str(item)], "qty": ["0.5"], "price": ["1250"],
                                        "desc": ["Rate correction"], "restock": "on"})
    cn = conn.execute("SELECT * FROM credit_notes WHERE company_id=? ORDER BY id DESC LIMIT 1",
                      (cid,)).fetchone()
    check("credit note issued and auto-applied", cn is not None and cn["applied"] > 0,
          cn["applied"] if cn else None)

    new.post("/purchase-orders/new", data={"vendor_id": vend, "date": "2026-11-02",
                                           "delivery_date": "2026-11-09",
                                           "line_target": [f"acc:{acct}"], "qty": ["400"],
                                           "unit_cost": ["1.6"], "desc": ["Diesel"]})
    po = conn.execute("SELECT * FROM purchase_orders WHERE company_id=? ORDER BY id DESC LIMIT 1",
                      (cid,)).fetchone()
    pl = conn.execute("SELECT id, qty FROM purchase_order_lines WHERE purchase_order_id=?",
                      (po["id"],)).fetchone()
    new.post(f"/purchase-orders/{po['id']}/receive", data={f"recv_{pl['id']}": str(pl["qty"])})
    new.post(f"/purchase-orders/{po['id']}/bill", data={"date": "2026-11-09",
                                                        "due_date": "2026-12-09"})
    po = conn.execute("SELECT status, bill_id FROM purchase_orders WHERE id=?", (po["id"],)).fetchone()
    check("purchase order converted to bill", po["status"] == "billed" and po["bill_id"] is not None,
          dict(po))

    new.post("/payroll/new", data={"period": "2026-11", "date": "2026-11-15"})
    runs = conn.execute("SELECT COUNT(*) c FROM payroll_runs WHERE company_id=?", (cid,)).fetchone()["c"]
    check("payroll run posted", runs == 1, runs)

    print("\n7. Ledger integrity")
    r = conn.execute("SELECT SUM(debit) d, SUM(credit) c FROM journal_lines").fetchone()
    diff = round((r["d"] or 0) - (r["c"] or 0), 2)
    check("trial balance balances (Dr = Cr)", abs(diff) < 0.05, f"difference {diff}")
    check("journals exist", conn.execute("SELECT COUNT(*) c FROM journal_entries").fetchone()["c"] > 100)

    print("\n8. Sign out")
    s = client()
    s.post("/login", data={"email": "owner@tatmaqbooks.co.zw", "password": PASSWORD})
    s.get("/logout")
    check("session cleared after sign out", s.get("/", follow_redirects=False).status_code == 302)

    conn.close()
    total = len(PASS) + len(FAIL)
    print(f"\n{'=' * 56}")
    print(f"  {len(PASS)}/{total} checks passed" + (f" · {len(FAIL)} FAILED" if FAIL else " · all green"))
    print(f"{'=' * 56}\n")
    if FAIL:
        for f in FAIL:
            print("  failed:", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
