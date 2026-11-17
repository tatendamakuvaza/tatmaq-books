"""Tatmaq Books - analytics, KPIs and financial statements."""
from datetime import date, timedelta
from db import connect, PROFILES

PALETTE = ["#4f8cff", "#22c58b", "#f5a524", "#ff5c7a", "#a78bfa", "#38bdf8", "#94a3b8", "#f472b6"]


def today():
    return date.today()


def fy_start(company):
    try:
        return date.fromisoformat(company["fiscal_start"])
    except Exception:
        return date(today().year, 1, 1)


def month_list(n=12, end=None):
    end = end or today()
    d = end.replace(day=1)
    out = []
    for k in range(n - 1, -1, -1):
        y, m = d.year, d.month - k
        while m <= 0:
            m += 12
            y -= 1
        out.append(date(y, m, 1))
    return out


def mkey(dstr):
    return dstr[:7]


def company(conn):
    return conn.execute("SELECT * FROM companies ORDER BY id LIMIT 1").fetchone()


def accounts_map(conn, cid):
    return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM accounts WHERE company_id=?", (cid,))}


def acct_by_code(conn, cid):
    return {r["code"]: dict(r) for r in conn.execute("SELECT * FROM accounts WHERE company_id=?", (cid,))}


# ---------------------------------------------------------------- P&L / balance helpers
def pl_totals(conn, cid, start, end):
    rows = conn.execute("""SELECT a.type, a.subtype, SUM(jl.debit) dr, SUM(jl.credit) cr
        FROM journal_lines jl JOIN journal_entries je ON je.id=jl.entry_id
        JOIN accounts a ON a.id=jl.account_id
        WHERE je.company_id=? AND je.date>=? AND je.date<=?
        GROUP BY a.type, a.subtype""", (cid, str(start), str(end))).fetchall()
    out = {"revenue": 0, "other_income": 0, "cogs": 0, "expense": 0, "depreciation": 0, "payroll": 0}
    for r in rows:
        if r["type"] == "income":
            v = (r["cr"] or 0) - (r["dr"] or 0)
            if r["subtype"] == "other_income":
                out["other_income"] += v
            else:
                out["revenue"] += v
        elif r["type"] == "expense":
            v = (r["dr"] or 0) - (r["cr"] or 0)
            if r["subtype"] == "cogs":
                out["cogs"] += v
            elif r["subtype"] == "depreciation":
                out["depreciation"] += v
                out["expense"] += v
            else:
                out["expense"] += v
                if r["subtype"] == "payroll":
                    out["payroll"] += v
    gross = out["revenue"] - out["cogs"]
    net = gross + out["other_income"] - out["expense"]
    out.update(gross=gross, net=net, total_income=out["revenue"] + out["other_income"])
    rev = out["revenue"] or 1
    out["margin"] = gross / rev * 100
    out["net_margin"] = net / rev * 100
    return out


def account_balances(conn, cid):
    """Signed balance per account (debit-positive for asset/expense)."""
    rows = conn.execute("""SELECT jl.account_id, SUM(jl.debit) dr, SUM(jl.credit) cr
        FROM journal_lines jl JOIN journal_entries je ON je.id=jl.entry_id
        WHERE je.company_id=? GROUP BY jl.account_id""", (cid,)).fetchall()
    return {r["account_id"]: (r["dr"] or 0) - (r["cr"] or 0) for r in rows}


def acct_natural(conn, cid):
    """Balance in natural sign per account (assets/expenses debit-positive; others credit-positive)."""
    bal = account_balances(conn, cid)
    amap = accounts_map(conn, cid)
    out = {}
    for aid, v in bal.items():
        a = amap.get(aid)
        if not a:
            continue
        out[a["code"]] = v if a["type"] in ("asset", "expense") else -v
    return out


def balance_sheet(conn, cid, as_of=None):
    as_of = str(as_of or today())
    amap = acct_by_code(conn, cid)
    rows = conn.execute("""SELECT a.code, a.name, a.type, a.subtype, SUM(jl.debit) dr, SUM(jl.credit) cr
        FROM journal_lines jl JOIN journal_entries je ON je.id=jl.entry_id
        JOIN accounts a ON a.id=jl.account_id WHERE je.company_id=? AND je.date<=?
        GROUP BY a.id ORDER BY a.code""", (cid, as_of)).fetchall()
    assets, liabs, equity = [], [], []
    totals = dict(asset=0, liability=0, equity=0, income=0, expense=0)
    for r in rows:
        v = (r["dr"] or 0) - (r["cr"] or 0)
        if r["type"] == "asset":
            val = v
            if abs(val) > 0.004:
                assets.append({**dict(r), "value": val})
            totals["asset"] += val
        elif r["type"] == "liability":
            val = -v
            if abs(val) > 0.004:
                liabs.append({**dict(r), "value": val})
            totals["liability"] += val
        elif r["type"] == "equity":
            val = -v
            if abs(val) > 0.004:
                equity.append({**dict(r), "value": val})
            totals["equity"] += val
        elif r["type"] == "income":
            totals["income"] += -v
        else:
            totals["expense"] += v
    retained = totals["income"] - totals["expense"]
    equity_total = totals["equity"] + retained
    return dict(assets=assets, liabilities=liabs, equity=equity,
                total_assets=totals["asset"], total_liabilities=totals["liability"],
                total_equity=equity_total, current_profit=retained,
                check=totals["asset"] - (totals["liability"] + equity_total))


def pnl_statement(conn, cid, start, end):
    rows = conn.execute("""SELECT a.code, a.name, a.type, a.subtype, SUM(jl.debit) dr, SUM(jl.credit) cr
        FROM journal_lines jl JOIN journal_entries je ON je.id=jl.entry_id
        JOIN accounts a ON a.id=jl.account_id
        WHERE je.company_id=? AND je.date>=? AND je.date<=?
        GROUP BY a.id ORDER BY a.code""", (cid, str(start), str(end))).fetchall()
    income, cogs, opex, other = [], [], [], []
    for r in rows:
        v = (r["cr"] or 0) - (r["dr"] or 0)
        if r["type"] == "income":
            if r["subtype"] == "other_income":
                if abs(v) > 0.004: other.append({**dict(r), "value": v})
            elif abs(v) > 0.004:
                income.append({**dict(r), "value": v})
        elif r["type"] == "expense":
            v = -v
            if abs(v) > 0.004:
                (cogs if r["subtype"] == "cogs" else opex).append({**dict(r), "value": v})
    total_income = sum(i["value"] for i in income)
    total_cogs = sum(i["value"] for i in cogs)
    gross = total_income - total_cogs
    total_opex = sum(i["value"] for i in opex)
    total_other = sum(i["value"] for i in other)
    net = gross + total_other - total_opex
    return dict(income=income, cogs=cogs, opex=opex, other=other, total_income=total_income,
                total_cogs=total_cogs, gross=gross, total_opex=total_opex,
                total_other=total_other, net=net,
                margin=(gross / total_income * 100) if total_income else 0,
                net_margin=(net / total_income * 100) if total_income else 0)


# ---------------------------------------------------------------- dashboard
def monthly_series(conn, cid, months=12):
    start = month_list(months)[0]
    rows = conn.execute("""SELECT substr(je.date,1,7) m, a.type, a.subtype,
              SUM(jl.debit) dr, SUM(jl.credit) cr
        FROM journal_lines jl JOIN journal_entries je ON je.id=jl.entry_id
        JOIN accounts a ON a.id=jl.account_id
        WHERE je.company_id=? AND je.date>=? GROUP BY m, a.type, a.subtype""",
                        (cid, str(start))).fetchall()
    agg = {}
    for r in rows:
        m = r["m"]
        e = agg.setdefault(m, {"revenue": 0.0, "expenses": 0.0})
        if r["type"] == "income" and r["subtype"] != "other_income":
            e["revenue"] += (r["cr"] or 0) - (r["dr"] or 0)
        elif r["type"] == "expense":
            e["expenses"] += (r["dr"] or 0) - (r["cr"] or 0)
    series = []
    for m0 in month_list(months):
        k = m0.strftime("%Y-%m")
        e = agg.get(k, {"revenue": 0.0, "expenses": 0.0})
        series.append({"label": m0.strftime("%b"), "key": k, "revenue": round(e["revenue"], 2),
                       "expenses": round(e["expenses"], 2), "net": round(e["revenue"] - e["expenses"], 2)})
    return series


def cash_series(conn, cid, months=12):
    amap = acct_by_code(conn, cid)
    cash_ids = [a["id"] for c in ("1000", "1010", "1020") if c in amap for a in [amap[c]]]
    series = month_list(months)
    out = []
    running = 0.0
    # opening balance before first month
    q = ",".join("?" * len(cash_ids))
    pre = conn.execute(f"""SELECT SUM(jl.debit)-SUM(jl.credit) v FROM journal_lines jl
        JOIN journal_entries je ON je.id=jl.entry_id
        WHERE je.company_id=? AND jl.account_id IN ({q}) AND je.date<?""",
                       [cid] + cash_ids + [str(series[0])]).fetchone()["v"] or 0
    running = pre
    for m0 in series:
        nxt = (m0.replace(day=28) + timedelta(days=4)).replace(day=1)
        v = conn.execute(f"""SELECT SUM(jl.debit)-SUM(jl.credit) v FROM journal_lines jl
            JOIN journal_entries je ON je.id=jl.entry_id
            WHERE je.company_id=? AND jl.account_id IN ({q}) AND je.date>=? AND je.date<?""",
                         [cid] + cash_ids + [str(m0), str(nxt)]).fetchone()["v"] or 0
        running += v
        out.append({"label": m0.strftime("%b"), "value": round(running, 2)})
    return out


def expense_mix(conn, cid, start, end, top=6):
    rows = conn.execute("""SELECT a.name, SUM(jl.debit)-SUM(jl.credit) v
        FROM journal_lines jl JOIN journal_entries je ON je.id=jl.entry_id
        JOIN accounts a ON a.id=jl.account_id
        WHERE je.company_id=? AND a.type='expense' AND je.date>=? AND je.date<=?
        GROUP BY a.id ORDER BY v DESC""", (cid, str(start), str(end))).fetchall()
    rows = [r for r in rows if (r["v"] or 0) > 0]
    total = sum(r["v"] for r in rows) or 1
    items = [{"name": r["name"], "value": round(r["v"], 2),
              "pct": round(r["v"] / total * 100, 1), "color": PALETTE[i % len(PALETTE)]}
             for i, r in enumerate(rows[:top])]
    rest = total - sum(i["value"] for i in items)
    if rest > 1:
        items.append({"name": "Other expenses", "value": round(rest, 2),
                      "pct": round(rest / total * 100, 1), "color": PALETTE[top % len(PALETTE)]})
    return items


def aging(conn, cid, table, contact_col, date_col, due_col):
    kind = "invoices" if table == "invoices" else "bills"
    sign = 1
    rows = conn.execute(f"""SELECT c.name contact, {date_col} d, {due_col} due, total, amount_paid,
        total-amount_paid outstanding FROM {table} t JOIN contacts c ON c.id=t.{contact_col}
        WHERE t.company_id=? AND t.total-t.amount_paid > 0.01 ORDER BY due""", (cid,)).fetchall()
    buckets = {"current": 0.0, "b1": 0.0, "b2": 0.0, "b3": 0.0, "b4": 0.0}
    detail = []
    t = today()
    for r in rows:
        due = date.fromisoformat(r["due"])
        days = (t - due).days
        if days <= 0:
            b = "current"
        elif days <= 30:
            b = "b1"
        elif days <= 60:
            b = "b2"
        elif days <= 90:
            b = "b3"
        else:
            b = "b4"
        buckets[b] += r["outstanding"]
        detail.append({"contact": r["contact"], "date": r["d"], "due": r["due"],
                       "total": r["total"], "paid": r["amount_paid"],
                       "outstanding": r["outstanding"], "days": days, "bucket": b})
    return buckets, detail


def ar_aging(conn, cid):
    return aging(conn, cid, "invoices", "contact_id", "date", "due_date")


def ap_aging(conn, cid):
    return aging(conn, cid, "bills", "vendor_id", "date", "due_date")


def contacts_with_balance(conn, cid, ctype):
    tbl, col = ("invoices", "contact_id") if ctype == "customer" else ("bills", "vendor_id")
    rows = conn.execute(f"""SELECT c.*, COALESCE(SUM(t.total-t.amount_paid),0) bal, COUNT(t.id) cnt
        FROM contacts c LEFT JOIN {tbl} t ON t.{col}=c.id AND t.total-t.amount_paid>0.01
        WHERE c.company_id=? AND c.type=? GROUP BY c.id ORDER BY bal DESC""", (cid, ctype)).fetchall()
    return [dict(r) for r in rows]


def alerts(conn, cid):
    out = []
    ar = conn.execute("""SELECT COUNT(*) c, COALESCE(SUM(total-amount_paid),0) v FROM invoices
        WHERE company_id=? AND total-amount_paid>0.01 AND due_date<?""", (cid, str(today()))).fetchone()
    if ar["c"]:
        out.append({"severity": "danger", "icon": "alert",
                    "title": f"{ar['c']} overdue customer invoice{'s' if ar['c']>1 else ''}",
                    "detail": f"${ar['v']:,.2f} past due — chase before month end", "link": "/invoices?status=overdue"})
    ap = conn.execute("""SELECT COUNT(*) c, COALESCE(SUM(total-amount_paid),0) v FROM bills
        WHERE company_id=? AND total-amount_paid>0.01 AND due_date<?""", (cid, str(today()))).fetchone()
    if ap["c"]:
        out.append({"severity": "warn", "icon": "clock",
                    "title": f"{ap['c']} supplier bill{'s' if ap['c']>1 else ''} overdue",
                    "detail": f"${ap['v']:,.2f} owed — schedule payments to protect supplier terms", "link": "/bills?status=overdue"})
    low = conn.execute("""SELECT name, qty, reorder FROM items WHERE company_id=? AND tracked=1 AND qty<=reorder""",
                       (cid,)).fetchall()
    if low:
        out.append({"severity": "warn", "icon": "box",
                    "title": f"{len(low)} item{'s' if len(low)>1 else ''} at or below reorder level",
                    "detail": ", ".join(f"{r['name'].split(' (')[0]} ({r['qty']:.0f} left)" for r in low[:3]),
                    "link": "/inventory"})
    unrec = conn.execute("""SELECT COUNT(*) c FROM bank_txns WHERE company_id=? AND status='unreconciled'""", (cid,)).fetchone()
    if unrec["c"]:
        out.append({"severity": "info", "icon": "bank",
                    "title": f"{unrec['c']} bank transactions to reconcile",
                    "detail": "Review the bank feed to keep the ledger clean", "link": "/banking"})
    vat = vat_report(conn, cid, month_list(1)[0], today())
    if vat["payable"] > 0:
        out.append({"severity": "info", "icon": "percent",
                    "title": f"VAT payable ${vat['payable']:,.2f}",
                    "detail": f"Output ${vat['output']:,.2f} less input ${vat['input']:,.2f} — ZIMRA due by the 25th",
                    "link": "/reports/vat"})
    return out


def dashboard(conn, comp=None):
    c = comp or company(conn)
    cid = c["id"]
    t = today()
    ystart = fy_start(c)
    pl_ytd = pl_totals(conn, cid, ystart, t)
    pl_month = pl_totals(conn, cid, month_list(1)[0], t)
    prev_m = month_list(2)[0]
    prev_end = prev_m.replace(day=28) + timedelta(days=4)
    prev_end = prev_end.replace(day=1) - timedelta(days=1)
    pl_prev = pl_totals(conn, cid, prev_m, prev_end)

    cash_rows = conn.execute("""SELECT a.name, SUM(jl.debit)-SUM(jl.credit) v, a.code
        FROM journal_lines jl JOIN journal_entries je ON je.id=jl.entry_id
        JOIN accounts a ON a.id=jl.account_id
        WHERE je.company_id=? AND a.subtype IN ('cash','bank') GROUP BY a.id ORDER BY a.code""",
                             (cid,)).fetchall()
    cash_total = sum(r["v"] for r in cash_rows)
    ar = conn.execute("""SELECT COALESCE(SUM(total-amount_paid),0) v FROM invoices
        WHERE company_id=? AND total-amount_paid>0.01""", (cid,)).fetchone()["v"]
    ap = conn.execute("""SELECT COALESCE(SUM(total-amount_paid),0) v FROM bills
        WHERE company_id=? AND total-amount_paid>0.01""", (cid,)).fetchone()["v"]
    vat = vat_report(conn, cid, ystart, t)
    overdue = conn.execute("""SELECT COUNT(*) c, COALESCE(SUM(total-amount_paid),0) v FROM invoices
        WHERE company_id=? AND total-amount_paid>0.01 AND due_date<?""", (cid, str(t))).fetchone()

    months3 = month_list(3)[0]
    exp3 = pl_totals(conn, cid, months3, t)["expense"]
    runway = (cash_total / (exp3 / 3)) if exp3 > 0 else 0

    bs = balance_sheet(conn, cid, t)
    current_assets = sum(a["value"] for a in bs["assets"] if a["subtype"] in
                         ("cash", "bank", "ar", "inventory", "current_asset", "tax_receivable"))
    current_liabs = sum(a["value"] for a in bs["liabilities"] if a["subtype"] in
                        ("ap", "tax_payable", "current_liability"))
    current_ratio = (current_assets / current_liabs) if current_liabs else 0
    rev_growth = ((pl_month["revenue"] - pl_prev["revenue"]) / pl_prev["revenue"] * 100) if pl_prev["revenue"] else 0
    net_growth = None
    if abs(pl_prev["net"]) > max(1500, abs(pl_month["net"]) * 0.25):
        net_growth = (pl_month["net"] - pl_prev["net"]) / abs(pl_prev["net"]) * 100
        net_growth = max(-99.9, min(99.9, net_growth))
    rev_growth = max(-99.9, min(99.9, rev_growth))
    overdue_ratio = (overdue["v"] / ar * 100) if ar else 0
    health = 50
    health += 15 if pl_ytd["net_margin"] > 0 else -20
    health += 10 if current_ratio >= 1.5 else (5 if current_ratio >= 1 else -10)
    health += 10 if overdue_ratio < 15 else (-10 if overdue_ratio > 35 else 0)
    health += 5 if cash_total > 0 else -15
    health += min(10, max(-10, rev_growth / 3))
    health = max(5, min(99, round(health)))

    series = monthly_series(conn, cid, 12)
    cash = cash_series(conn, cid, 12)
    mix = expense_mix(conn, cid, ystart, t, 5)
    mix_total = sum(m["value"] for m in mix)
    ar_buckets, ar_detail = ar_aging(conn, cid)
    prof = PROFILES.get(c["industry"], PROFILES["mining"])

    # industry pulse
    tracked_sold = conn.execute("""SELECT COALESCE(SUM(il.qty),0) q FROM invoice_lines il
        JOIN invoices i ON i.id=il.invoice_id JOIN items it ON it.id=il.item_id
        WHERE it.tracked=1 AND i.date>=?""", (str(t - timedelta(days=30)),)).fetchone()["q"]
    billed = conn.execute("SELECT COUNT(*) c FROM invoices WHERE company_id=? AND date>=?",
                          (cid, str(t - timedelta(days=30)))).fetchone()["c"]
    emp = conn.execute("SELECT COUNT(*) c FROM employees WHERE company_id=? AND status='Active'", (cid,)).fetchone()["c"]

    top_customers = conn.execute("""SELECT c.name, SUM(i.total) v, COUNT(i.id) n FROM invoices i
        JOIN contacts c ON c.id=i.contact_id WHERE i.company_id=? AND i.date>=?
        GROUP BY c.id ORDER BY v DESC LIMIT 5""", (cid, str(ystart))).fetchall()

    activity = conn.execute("""SELECT * FROM (
        SELECT 'invoice' k, number ref, date, total amt, c.name party, i.status FROM invoices i
          JOIN contacts c ON c.id=i.contact_id WHERE i.company_id=?
        UNION ALL
        SELECT 'bill', b.number, b.date, b.total, c.name, b.status FROM bills b
          JOIN contacts c ON c.id=b.vendor_id WHERE b.company_id=?
        UNION ALL
        SELECT 'payment', p.reference, p.date, p.amount, c.name, p.kind FROM payments p
          JOIN contacts c ON c.id=p.contact_id WHERE p.company_id=?
        UNION ALL
        SELECT 'payroll', 'Payroll '||period, date, net, 'Payroll run', status FROM payroll_runs WHERE company_id=?
      ) ORDER BY date DESC LIMIT 9""", (cid, cid, cid, cid)).fetchall()

    return dict(company=c, pl_ytd=pl_ytd, pl_month=pl_month, cash_rows=cash_rows, cash_total=cash_total,
                ar=ar, ap=ap, vat=vat, overdue=overdue, runway=runway, health=health,
                series=series, cash=cash, mix=mix, ar_buckets=ar_buckets, ar_detail=ar_detail,
                rev_growth=rev_growth, net_growth=net_growth, current_ratio=current_ratio, mix_total=mix_total,
                overdue_ratio=overdue_ratio, alerts=alerts(conn, cid), profile=prof,
                tracked_sold=tracked_sold, billed=billed, employees=emp,
                top_customers=[dict(r) for r in top_customers], activity=[dict(r) for r in activity],
                cur_month=month_list(1)[0].strftime("%B %Y"))


# ---------------------------------------------------------------- VAT
def vat_report(conn, cid, start, end):
    out_rows = conn.execute("""SELECT i.*, c.name party FROM invoices i JOIN contacts c ON c.id=i.contact_id
        WHERE i.company_id=? AND i.date>=? AND i.date<=? ORDER BY i.date""", (cid, str(start), str(end))).fetchall()
    in_rows = conn.execute("""SELECT b.*, c.name party FROM bills b JOIN contacts c ON c.id=b.vendor_id
        WHERE b.company_id=? AND b.date>=? AND b.date<=? ORDER BY b.date""", (cid, str(start), str(end))).fetchall()
    output = sum(r["tax"] for r in out_rows)
    inputv = sum(r["tax"] for r in in_rows)
    return dict(output=round(output, 2), input=round(inputv, 2), payable=round(output - inputv, 2),
                sales=out_rows, purchases=in_rows,
                taxable_sales=sum(r["subtotal"] for r in out_rows),
                taxable_purchases=sum(r["subtotal"] for r in in_rows))


# ---------------------------------------------------------------- GL / cash flow
def general_ledger(conn, cid, account_id, start, end):
    acct = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    opening = conn.execute("""SELECT COALESCE(SUM(jl.debit)-SUM(jl.credit),0) v FROM journal_lines jl
        JOIN journal_entries je ON je.id=jl.entry_id WHERE jl.account_id=? AND je.date<?""",
                           (account_id, str(start))).fetchone()["v"]
    sign = 1 if acct["type"] in ("asset", "expense") else -1
    rows = conn.execute("""SELECT je.date, je.number, je.memo, je.source, jl.description, jl.debit, jl.credit
        FROM journal_lines jl JOIN journal_entries je ON je.id=jl.entry_id
        WHERE jl.account_id=? AND je.date>=? AND je.date<=? ORDER BY je.date, je.id""",
                        (account_id, str(start), str(end))).fetchall()
    running = opening * sign
    lines = []
    for r in rows:
        running += (r["debit"] - r["credit"]) * sign
        lines.append({**dict(r), "running": running})
    return dict(account=acct, opening=opening * sign, lines=lines, closing=running)


def cash_flow(conn, cid, start, end):
    def movement(codes):
        q = ",".join("?" * len(codes))
        ids = [r["id"] for r in conn.execute(
            f"SELECT id FROM accounts WHERE company_id=? AND code IN ({q})", [cid] + codes)]
        if not ids:
            return 0
        q2 = ",".join("?" * len(ids))
        return conn.execute(f"""SELECT COALESCE(SUM(jl.debit)-SUM(jl.credit),0) v FROM journal_lines jl
            JOIN journal_entries je ON je.id=jl.entry_id WHERE jl.account_id IN ({q2})
            AND je.date>=? AND je.date<=?""", ids + [str(start), str(end)]).fetchone()["v"]

    pl = pl_totals(conn, cid, start, end)
    wc_ar = -movement(["1100", "1110", "1120", "1130"])
    wc_inv = -movement(["1200", "1210", "1220", "1230", "1240", "1250"])
    wc_ap = movement(["2000"])
    wc_tax = movement(["2100", "2200", "2210", "2220"])
    operating = pl["net"] + pl["depreciation"] + wc_ar + wc_inv + wc_ap + wc_tax
    investing = -movement(["1500"])
    financing = movement(["2400", "2500", "3000"]) - movement(["3100", "3200"])
    net = operating + investing + financing
    open_bal = cash_series(conn, cid, 12)
    return dict(operating=operating, investing=investing, financing=financing, net=net,
                pl=pl, wc_ar=wc_ar, wc_inv=wc_inv, wc_ap=wc_ap, wc_tax=wc_tax)


# ---------------------------------------------------------------- inventory / assets / payroll helpers
def stock_summary(conn, cid):
    rows = conn.execute("""SELECT i.*, a.name account, i.qty*i.cost value FROM items i
        LEFT JOIN accounts a ON a.id=i.account_id WHERE i.company_id=? AND i.tracked=1 ORDER BY i.name""",
                        (cid,)).fetchall()
    return [dict(r) for r in rows]


def asset_register(conn, cid):
    rows = conn.execute("SELECT * FROM fixed_assets WHERE company_id=? ORDER BY purchase_date", (cid,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["nbv"] = d["cost"] - d["accum_dep"]
        d["monthly"] = d["cost"] / d["life"] / 12
        out.append(d)
    return out


def payroll_runs(conn, cid):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM payroll_runs WHERE company_id=? ORDER BY period DESC", (cid,))]


def item_sales(conn, cid, start, end):
    return [dict(r) for r in conn.execute("""SELECT it.name, it.unit, SUM(il.qty) qty,
        SUM(il.amount) revenue, SUM(il.qty*il.unit_cost) cost FROM invoice_lines il
        JOIN invoices i ON i.id=il.invoice_id JOIN items it ON it.id=il.item_id
        WHERE i.company_id=? AND i.date>=? AND i.date<=? GROUP BY it.id ORDER BY revenue DESC""",
        (cid, str(start), str(end)))]


def donut_segments(items):
    """Return cumulative stroke offsets for an SVG donut."""
    total = sum(i["value"] for i in items) or 1
    segs, acc = [], 0.0
    for i in items:
        frac = i["value"] / total
        segs.append({**i, "frac": frac, "offset": acc})
        acc += frac
    return segs
