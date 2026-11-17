"""Tatmaq Books - application server."""
import json
from datetime import date, datetime, timedelta

import secrets
from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session, url_for, flash)

import analytics as A
import auth
import charts
import db

app = Flask(__name__)
app.config["SECRET_KEY"] = auth.SECRET
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=14)

db.ensure_db()

PUBLIC_ENDPOINTS = {"landing", "login", "register", "demo_start", "demo_link",
                    "static", "healthz"}


@app.before_request
def _guard():
    """Authenticate every request and block writes the role may not perform."""
    if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    ident, source = auth.resolve_identity()
    if not ident:
        if request.path.startswith("/api/"):
            return jsonify({"error": "unauthorised"}), 401
        return redirect(url_for("login", next=request.path))
    g.ident = ident
    g.perms = auth.permissions(ident["role"])
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if not g.perms["write"] or not auth.gate_post(ident["role"], request.endpoint or ""):
            if request.path.startswith("/api/"):
                return jsonify({"error": "forbidden", "role": ident["role"]}), 403
            flash("That action is not available for your role — nothing was changed.", "error")
            return redirect(request.referrer or url_for("dashboard"))
    return None


# ------------------------------------------------------------------ plumbing
def conn():
    if "conn" not in g:
        g.conn = db.connect()
    return g.conn


@app.teardown_appcontext
def close_conn(exc):
    c = g.pop("conn", None)
    if c is not None:
        c.close()


def company():
    if "company_row" not in g:
        g.company_row = conn().execute("SELECT * FROM companies WHERE id=?",
                                       (g.ident["company_id"],)).fetchone()
    return g.company_row


def pdate(name, default):
    v = request.values.get(name) or ""
    try:
        return date.fromisoformat(v)
    except Exception:
        return default


def next_number(table, prefix):
    c = company()
    n = conn().execute(f"SELECT COUNT(*) c FROM {table} WHERE company_id=?", (c["id"],)).fetchone()["c"]
    return f"{prefix}-{n + 1:04d}"


def acct_id(code):
    c = company()
    row = conn().execute("SELECT id FROM accounts WHERE company_id=? AND code=?", (c["id"], code)).fetchone()
    return row["id"] if row else None


def post_je(when, memo, source, ref, lines):
    """lines: [(code, dr, cr, desc)]"""
    c = company()
    cur = conn().cursor()
    n = cur.execute("SELECT COUNT(*) c FROM journal_entries WHERE company_id=?", (c["id"],)).fetchone()["c"]
    num = f"JE-{n + 1:04d}"
    cur.execute("""INSERT INTO journal_entries(company_id,number,date,memo,source,reference,created_at)
                   VALUES(?,?,?,?,?,?,?)""", (c["id"], num, str(when), memo, source, ref, str(date.today())))
    eid = cur.lastrowid
    amap = A.acct_by_code(conn(), c["id"])
    for code, dr, cr, desc in lines:
        if abs(dr) < 0.005 and abs(cr) < 0.005:
            continue
        cur.execute("""INSERT INTO journal_lines(entry_id,account_id,description,debit,credit)
                       VALUES(?,?,?,?,?)""", (eid, amap[code]["id"], desc, round(dr, 2), round(cr, 2)))
    conn().commit()
    return num


@app.context_processor
def inject():
    ident = getattr(g, "ident", None)
    perms = getattr(g, "perms", None)
    if not ident:
        return dict(company=dict(id=0, name="Tatmaq Books", industry="mining", currency="USD",
                                 symbol="$", tax_name="VAT", tax_rate=15, address="", email="",
                                 phone="", fiscal_start=str(date.today())),
                    profiles=db.PROFILES, now=date.today(), overdue_count=0,
                    bills_overdue_count=0, status_of=status_of, nav_path=request.path,
                    ident=None, perms=auth.permissions("auditor"))
    c = company()
    overdue = conn().execute("""SELECT COUNT(*) c FROM invoices WHERE company_id=?
        AND total-amount_paid>0.01 AND due_date<?""", (c["id"], str(date.today()))).fetchone()["c"]
    bills_over = conn().execute("""SELECT COUNT(*) c FROM bills WHERE company_id=?
        AND total-amount_paid>0.01 AND due_date<?""", (c["id"], str(date.today()))).fetchone()["c"]
    return dict(company=dict(c), profiles=db.PROFILES, now=date.today(),
                overdue_count=overdue, bills_overdue_count=bills_over,
                status_of=status_of, nav_path=request.path, ident=ident, perms=perms,
                roles=auth.ROLES)


def status_of(row):
    total = (row["total"] if "total" in row.keys() else 0) or 0
    paid = (row["amount_paid"] if "amount_paid" in row.keys() else 0) or 0
    status = row["status"] if "status" in row.keys() else ""
    due = row["due_date"] if "due_date" in row.keys() else None
    if status in ("draft",):
        return {"label": "Draft", "cls": "chip-muted"}
    balance = total - paid
    if status == "converted":
        return {"label": "Invoiced", "cls": "chip-info"}
    if balance <= 0.011:
        return {"label": "Paid", "cls": "chip-good"}
    try:
        if due and date.fromisoformat(due) < date.today():
            return {"label": "Overdue", "cls": "chip-bad"}
    except Exception:
        pass
    if paid > 0.011:
        return {"label": "Part paid", "cls": "chip-warn"}
    if status == "accepted":
        return {"label": "Accepted", "cls": "chip-good"}
    return {"label": "Sent", "cls": "chip-info"}


# filters
@app.template_filter("money")
def f_money(v, dec=2):
    try:
        v = float(v or 0)
    except Exception:
        return v
    return f"{'-' if v < 0 else ''}{abs(v):,.{dec}f}"


@app.template_filter("compact")
def f_compact(v):
    try:
        v = float(v or 0)
    except Exception:
        return v
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000:
        return f"{sign}{v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"{sign}{v / 1_000:.1f}K"
    return f"{sign}{v:,.0f}"


@app.template_filter("ddate")
def f_date(v):
    if not v:
        return ""
    try:
        return date.fromisoformat(str(v)[:10]).strftime("%d %b %Y")
    except Exception:
        return v


@app.template_filter("sdate")
def f_sdate(v):
    if not v:
        return ""
    try:
        return date.fromisoformat(str(v)[:10]).strftime("%d %b")
    except Exception:
        return v


@app.template_filter("num")
def f_num(v, dec=0):
    try:
        return f"{float(v or 0):,.{dec}f}"
    except Exception:
        return v


@app.template_filter("initials")
def f_initials(name):
    parts = str(name or "?").replace("(Pvt) Ltd", "").split()
    return "".join(p[0] for p in parts[:2]).upper()


@app.template_filter("avatar_hue")
def f_hue(name):
    return sum(ord(ch) for ch in str(name or "x")) % 360



# ------------------------------------------------------------------ public: landing, auth, demo
@app.route("/welcome")
def landing():
    if auth.resolve_identity()[0]:
        return redirect(url_for("dashboard"))
    seats = conn().execute("SELECT COUNT(*) c FROM companies").fetchone()["c"]
    return render_template("landing.html", title="Tatmaq Books", seats=seats)


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "app": "tatmaq-books"})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        row = conn().execute("SELECT * FROM users WHERE lower(email)=? AND status='Active'",
                             (email,)).fetchone()
        if not row or not auth.verify_password(row["password_hash"], pw):
            flash("Email or password not recognised. Check your details, or use the demo access link below.", "error")
            return render_template("login.html", title="Sign in", email=email)
        conn().execute("UPDATE users SET last_login=? WHERE id=?", (str(date.today()), row["id"]))
        conn().commit()
        comp = conn().execute("SELECT name FROM companies WHERE id=?", (row["company_id"],)).fetchone()
        auth.sign_in(row["id"], row["company_id"], comp["name"] if comp else "",
                     remember=bool(request.form.get("remember")))
        flash(f"Welcome back, {row['name'].split()[0]}.", "success")
        nxt = request.args.get("next") or request.form.get("next") or ""
        return redirect(nxt if nxt.startswith("/") else url_for("dashboard"))
    if auth.resolve_identity()[0]:
        return redirect(url_for("dashboard"))
    return render_template("login.html", title="Sign in")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    auth.sign_out()
    flash("Signed out. Your data is safe.", "success")
    return redirect(url_for("landing"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        name = (f.get("name") or "").strip()
        email = (f.get("email") or "").strip().lower()
        pw = f.get("password") or ""
        profile = f.get("industry") or "mining"
        comp_name = (f.get("company") or "").strip() or f"{name.split()[0] if name else 'New'} Company"
        if profile not in db.PROFILES:
            profile = "mining"
        if len(pw) < 8:
            flash("Choose a password of at least 8 characters.", "error")
            return render_template("register.html", title="Create workspace", form=f)
        if conn().execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
            flash("That email is already registered — sign in instead.", "error")
            return render_template("register.html", title="Create workspace", form=f)
        cid = db.seed_company(conn(), profile, demo=False, user_mode="none")
        conn().execute("UPDATE companies SET name=?, email=?, phone=?, address=? WHERE id=?",
                       (comp_name, email, f.get("phone", ""), f.get("address", ""), cid))
        cur = conn().cursor()
        cur.execute("""INSERT INTO users(company_id,name,email,role,status,password_hash,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (cid, name or "Owner", email, "owner", "Active", auth.hash_password(pw), str(date.today())))
        conn().commit()
        auth.sign_in(cur.lastrowid, cid, comp_name)
        flash("Workspace created. Set your opening balances in Banking and Chart of Accounts.", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html", title="Create workspace", form={})


@app.route("/demo")
def demo_start():
    """Spin up an isolated, seeded workspace and sign in as a demo visitor."""
    profile = request.args.get("profile", "mining")
    if profile not in db.PROFILES:
        profile = "mining"
    cid = db.seed_company(conn(), profile, demo=True)
    session["demo_cid"] = cid
    session.permanent = True
    comp = conn().execute("SELECT name FROM companies WHERE id=?", (cid,)).fetchone()
    flash(f"Demo workspace ready — {db.PROFILES[profile]['label']} template with 12 months of data. "
          f"Nothing here touches real client books.", "success")
    return redirect(url_for("dashboard"))


@app.route("/demo/link/<token>")
def demo_link(token):
    payload = auth.read_demo_token(token)
    if not payload:
        flash("That demo link has expired. Start a fresh demo instead.", "error")
        return redirect(url_for("landing"))
    row = conn().execute("SELECT id, name FROM companies WHERE id=?", (payload["cid"],)).fetchone()
    if not row:
        flash("That demo workspace no longer exists.", "error")
        return redirect(url_for("landing"))
    session["demo_cid"] = row["id"]
    session.permanent = True
    return redirect(url_for("dashboard"))


# ------------------------------------------------------------------ dashboard
@app.route("/")
def dashboard():
    c = conn()
    d = A.dashboard(c, company())
    series = d["series"]
    rev_chart = charts.area_chart([
        {"name": "Revenue", "color": "#4f8cff", "values": [x["revenue"] for x in series]},
        {"name": "Expenses", "color": "#f5a524", "values": [x["expenses"] for x in series]},
    ], w=680, h=230)
    net_bars = charts.bar_chart([x["net"] for x in series], w=680, h=120)
    cash_spark = charts.sparkline([x["value"] for x in d["cash"]], w=150, h=56)
    rev_spark = charts.sparkline([x["revenue"] for x in series], w=150, h=56)
    net_spark = charts.sparkline([x["net"] for x in series], w=150, h=56)
    mix_donut = charts.donut(A.donut_segments(d["mix"]), size=176, thickness=24)
    health_gauge = charts.gauge(d["health"])
    max_aging = max([d["ar_buckets"][k] for k in ("current", "b1", "b2", "b3", "b4")] + [1])
    return render_template("dashboard.html", d=d, rev_chart=rev_chart, net_bars=net_bars,
                           cash_spark=cash_spark, rev_spark=rev_spark, net_spark=net_spark,
                           mix_donut=mix_donut, health_gauge=health_gauge, max_aging=max_aging,
                           title="Executive Dashboard")


# ------------------------------------------------------------------ sales: invoices
@app.route("/invoices")
def invoices():
    c = company()
    status = request.args.get("status", "all")
    q = request.args.get("q", "").strip()
    sql = """SELECT i.*, ct.name party FROM invoices i LEFT JOIN contacts ct ON ct.id=i.contact_id
             WHERE i.company_id=?"""
    args = [c["id"]]
    if q:
        sql += " AND (i.number LIKE ? OR ct.name LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY i.date DESC, i.id DESC"
    rows = [dict(r) for r in conn().execute(sql, args)]
    if status == "overdue":
        rows = [r for r in rows if (r["total"] - r["amount_paid"]) > 0.01 and r["due_date"] < str(date.today())]
    elif status == "unpaid":
        rows = [r for r in rows if (r["total"] - r["amount_paid"]) > 0.01]
    elif status == "paid":
        rows = [r for r in rows if (r["total"] - r["amount_paid"]) <= 0.011]
    totals = {"total": sum(r["total"] for r in rows),
              "balance": sum(r["total"] - r["amount_paid"] for r in rows)}
    return render_template("invoices.html", rows=rows, status=status, q=q, totals=totals, title="Sales Invoices")


@app.route("/invoices/new", methods=["GET", "POST"])
def invoice_new():
    c = company()
    contacts = conn().execute("SELECT * FROM contacts WHERE company_id=? AND type='customer' ORDER BY name",
                              (c["id"],)).fetchall()
    items = conn().execute("SELECT * FROM items WHERE company_id=? ORDER BY name", (c["id"],)).fetchall()
    if request.method == "POST":
        f = request.form
        cust = f.get("contact_id") or (contacts[0]["id"] if contacts else None)
        if not cust:
            flash("Create a customer first.", "error")
            return redirect(url_for("contacts", tab="customer"))
        when = f.get("date") or str(date.today())
        due = f.get("due_date") or str(date.fromisoformat(when) + timedelta(days=30))
        item_ids = f.getlist("item_id")
        qtys = f.getlist("qty")
        prices = f.getlist("price")
        descs = f.getlist("desc")
        lines, subtotal, tax, cogs = [], 0.0, 0.0, 0.0
        for i, iid in enumerate(item_ids):
            if not iid:
                continue
            it = conn().execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
            if not it:
                continue
            try:
                qty = float(qtys[i] or 0)
            except Exception:
                qty = 0
            if qty <= 0:
                continue
            price = float(prices[i]) if i < len(prices) and prices[i] else it["price"]
            desc = descs[i] if i < len(descs) and descs[i].strip() else it["name"]
            rate = c["tax_rate"]
            amt = round(qty * price, 2)
            lines.append(dict(item=it, qty=qty, price=price, desc=desc, rate=rate, amt=amt))
            subtotal += amt
            tax += round(amt * rate / 100, 2)
            if it["tracked"]:
                cogs += qty * (it["cost"] or 0)
        if not lines:
            flash("Add at least one line item.", "error")
            return redirect(url_for("invoice_new"))
        total = round(subtotal + tax, 2)
        number = next_number("invoices", "INV")
        cur = conn().cursor()
        cur.execute("""INSERT INTO invoices(company_id,number,contact_id,date,due_date,status,subtotal,tax,total,
                       amount_paid,notes,currency) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (c["id"], number, cust, when, due, "sent", round(subtotal, 2), round(tax, 2), total,
                     0, f.get("notes", ""), c["currency"]))
        iid_new = cur.lastrowid
        je = [("1100", total, 0, number)]
        for l in lines:
            cur.execute("""INSERT INTO invoice_lines(invoice_id,item_id,description,qty,unit_price,tax_rate,amount,unit_cost)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (iid_new, l["item"]["id"], l["desc"], l["qty"], l["price"], l["rate"], l["amt"],
                         l["item"]["cost"] or 0))
            acode = conn().execute("SELECT code FROM accounts WHERE id=?", (l["item"]["account_id"],)).fetchone()
            je.append((acode["code"] if acode else "4000", 0, l["amt"], l["desc"]))
            if l["item"]["tracked"]:
                cst = round(l["qty"] * (l["item"]["cost"] or 0), 2)
                je.append(("5000", cst, 0, "Cost of sales - " + l["desc"]))
                je.append(("1200", 0, cst, "Stock issued"))
                cur.execute("UPDATE items SET qty=qty-? WHERE id=?", (l["qty"], l["item"]["id"]))
        if tax:
            je.append(("2100", 0, round(tax, 2), "VAT on " + number))
        conn().commit()
        post_je(when, f"Sales invoice {number}", "invoice", number, je)
        flash(f"Invoice {number} posted to the ledger.", "success")
        return redirect(url_for("invoice_view", iid=iid_new))
    return render_template("invoice_new.html", contacts=contacts, items=items, title="New Invoice",
                           today=date.today().isoformat(),
                           due_default=(date.today() + timedelta(days=30)).isoformat())


@app.route("/invoices/<int:iid>")
def invoice_view(iid):
    c = company()
    inv = conn().execute("""SELECT i.*, ct.name party, ct.email, ct.phone, ct.address, ct.tax_no
        FROM invoices i LEFT JOIN contacts ct ON ct.id=i.contact_id WHERE i.id=? AND i.company_id=?""",
                         (iid, c["id"])).fetchone()
    if not inv:
        return redirect(url_for("invoices"))
    lines = conn().execute("SELECT * FROM invoice_lines WHERE invoice_id=?", (iid,)).fetchall()
    pays = conn().execute("SELECT * FROM payments WHERE invoice_id=? ORDER BY date", (iid,)).fetchall()
    banks = conn().execute("SELECT * FROM bank_accounts WHERE company_id=?", (c["id"],)).fetchall()
    credits = conn().execute("SELECT * FROM credit_notes WHERE invoice_id=? ORDER BY date", (iid,)).fetchall()
    return render_template("invoice_view.html", inv=inv, lines=lines, pays=pays, banks=banks,
                           credits=credits, title=inv["number"])


@app.route("/invoices/<int:iid>/pay", methods=["POST"])
def invoice_pay(iid):
    c = company()
    inv = conn().execute("SELECT * FROM invoices WHERE id=? AND company_id=?", (iid, c["id"])).fetchone()
    if not inv:
        return redirect(url_for("invoices"))
    f = request.form
    amt = float(f.get("amount") or 0)
    if amt <= 0:
        flash("Enter a payment amount.", "error")
        return redirect(url_for("invoice_view", iid=iid))
    when = f.get("date") or str(date.today())
    bank = conn().execute("SELECT * FROM bank_accounts WHERE id=?", (f.get("bank_account_id"),)).fetchone()
    method = f.get("method") or "Bank transfer"
    cur = conn().cursor()
    cur.execute("""INSERT INTO payments(company_id,kind,contact_id,invoice_id,date,amount,method,bank_account_id,reference)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (c["id"], "received", inv["contact_id"], iid, when, amt, method,
                 bank["id"] if bank else None, f.get("reference") or f"RCPT-{iid:04d}"))
    new_paid = round(inv["amount_paid"] + amt, 2)
    status = "paid" if new_paid >= inv["total"] - 0.011 else "partial"
    cur.execute("UPDATE invoices SET amount_paid=?, status=? WHERE id=?", (new_paid, status, iid))
    conn().commit()
    bank_code = "1010"
    if bank:
        ba = conn().execute("SELECT a.code FROM bank_accounts b JOIN accounts a ON a.id=b.account_id WHERE b.id=?",
                            (bank["id"],)).fetchone()
        bank_code = ba["code"] if ba else "1010"
    post_je(when, f"Payment received - {inv['number']}", "payment", inv["number"],
            [(bank_code, amt, 0, f"{method} receipt"), ("1100", 0, amt, inv["number"])])
    if bank:
        cur.execute("""INSERT INTO bank_txns(company_id,bank_account_id,date,description,reference,amount,direction,status,source)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (c["id"], bank["id"], when, f"Receipt - {inv['number']}", f.get("reference") or "RCPT",
                     amt, "in", "reconciled", "books"))
        conn().commit()
    flash(f"Payment of ${amt:,.2f} recorded against {inv['number']}.", "success")
    return redirect(url_for("invoice_view", iid=iid))


# ------------------------------------------------------------------ quotes
@app.route("/quotes")
def quotes():
    c = company()
    rows = conn().execute("""SELECT q.*, ct.name party FROM quotes q LEFT JOIN contacts ct ON ct.id=q.contact_id
        WHERE q.company_id=? ORDER BY q.date DESC""", (c["id"],)).fetchall()
    return render_template("quotes.html", rows=rows, title="Quotations")


@app.route("/quotes/new", methods=["GET", "POST"])
def quote_new():
    c = company()
    contacts = conn().execute("SELECT * FROM contacts WHERE company_id=? AND type='customer' ORDER BY name",
                              (c["id"],)).fetchall()
    items = conn().execute("SELECT * FROM items WHERE company_id=? ORDER BY name", (c["id"],)).fetchall()
    if request.method == "POST":
        f = request.form
        when = f.get("date") or str(date.today())
        lines, subtotal, tax = [], 0.0, 0.0
        for i, iid in enumerate(f.getlist("item_id")):
            if not iid:
                continue
            it = conn().execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
            try:
                qty = float(f.getlist("qty")[i] or 0)
            except Exception:
                qty = 0
            if qty <= 0:
                continue
            prices = f.getlist("price")
            price = float(prices[i]) if prices[i] else it["price"]
            amt = round(qty * price, 2)
            lines.append((it, qty, price, amt))
            subtotal += amt
            tax += round(amt * 0.15, 2)
        if not lines:
            flash("Add at least one line item.", "error")
            return redirect(url_for("quote_new"))
        number = next_number("quotes", "QT")
        cur = conn().cursor()
        cur.execute("""INSERT INTO quotes(company_id,number,contact_id,date,expiry,status,subtotal,tax,total,notes)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (c["id"], number, f.get("contact_id"), when,
                     f.get("expiry") or str(date.fromisoformat(when) + timedelta(days=21)),
                     "sent", round(subtotal, 2), round(tax, 2), round(subtotal + tax, 2), f.get("notes", "")))
        qid = cur.lastrowid
        for it, qty, price, amt in lines:
            cur.execute("""INSERT INTO quote_lines(quote_id,item_id,description,qty,unit_price,tax_rate,amount)
                           VALUES(?,?,?,?,?,?,?)""", (qid, it["id"], it["name"], qty, price, 15, amt))
        conn().commit()
        flash(f"Quotation {number} saved.", "success")
        return redirect(url_for("quotes"))
    return render_template("quote_new.html", contacts=contacts, items=items, title="New Quotation",
                           today=date.today().isoformat())


@app.route("/quotes/<int:qid>/convert", methods=["POST"])
def quote_convert(qid):
    c = company()
    q = conn().execute("SELECT * FROM quotes WHERE id=? AND company_id=?", (qid, c["id"])).fetchone()
    if not q:
        return redirect(url_for("quotes"))
    lines = conn().execute("SELECT * FROM quote_lines WHERE quote_id=?", (qid,)).fetchall()
    number = next_number("invoices", "INV")
    when = str(date.today())
    due = str(date.today() + timedelta(days=30))
    cur = conn().cursor()
    cur.execute("""INSERT INTO invoices(company_id,number,contact_id,quote_id,date,due_date,status,subtotal,tax,total,
                   amount_paid,notes,currency) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (c["id"], number, q["contact_id"], qid, when, due, "sent", q["subtotal"], q["tax"],
                 q["total"], 0, "Converted from " + q["number"], c["currency"]))
    iid = cur.lastrowid
    je = [("1100", q["total"], 0, number)]
    for l in lines:
        it = conn().execute("SELECT * FROM items WHERE id=?", (l["item_id"],)).fetchone() if l["item_id"] else None
        cur.execute("""INSERT INTO invoice_lines(invoice_id,item_id,description,qty,unit_price,tax_rate,amount,unit_cost)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (iid, l["item_id"], l["description"], l["qty"], l["unit_price"], l["tax_rate"], l["amount"],
                     it["cost"] if it else 0))
        acode = conn().execute("SELECT code FROM accounts WHERE id=?", (it["account_id"],)).fetchone() if it else None
        je.append((acode["code"] if acode else "4000", 0, l["amount"], l["description"]))
        if it and it["tracked"]:
            cst = round(l["qty"] * (it["cost"] or 0), 2)
            je.append(("5000", cst, 0, "Cost of sales"))
            je.append(("1200", 0, cst, "Stock issued"))
    je.append(("2100", 0, q["tax"], "VAT on " + number))
    cur.execute("UPDATE quotes SET status='converted', invoice_id=? WHERE id=?", (iid, qid))
    conn().commit()
    post_je(when, f"Sales invoice {number} (from {q['number']})", "invoice", number, je)
    flash(f"{q['number']} converted to invoice {number}.", "success")
    return redirect(url_for("invoice_view", iid=iid))


# ------------------------------------------------------------------ bills
@app.route("/bills")
def bills():
    c = company()
    status = request.args.get("status", "all")
    q = request.args.get("q", "").strip()
    sql = """SELECT b.*, ct.name party FROM bills b LEFT JOIN contacts ct ON ct.id=b.vendor_id
             WHERE b.company_id=?"""
    args = [c["id"]]
    if q:
        sql += " AND (b.number LIKE ? OR ct.name LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY b.date DESC, b.id DESC"
    rows = [dict(r) for r in conn().execute(sql, args)]
    if status == "overdue":
        rows = [r for r in rows if (r["total"] - r["amount_paid"]) > 0.01 and r["due_date"] < str(date.today())]
    elif status == "open":
        rows = [r for r in rows if (r["total"] - r["amount_paid"]) > 0.01]
    elif status == "paid":
        rows = [r for r in rows if (r["total"] - r["amount_paid"]) <= 0.011]
    totals = {"total": sum(r["total"] for r in rows),
              "balance": sum(r["total"] - r["amount_paid"] for r in rows)}
    return render_template("bills.html", rows=rows, status=status, q=q, totals=totals, title="Purchase Bills")


@app.route("/bills/new", methods=["GET", "POST"])
def bill_new():
    c = company()
    vendors = conn().execute("SELECT * FROM contacts WHERE company_id=? AND type='vendor' ORDER BY name",
                             (c["id"],)).fetchall()
    accounts = conn().execute("""SELECT * FROM accounts WHERE company_id=? AND type='expense' ORDER BY code""",
                              (c["id"],)).fetchall()
    stock_items = conn().execute("SELECT * FROM items WHERE company_id=? AND tracked=1 ORDER BY name",
                                 (c["id"],)).fetchall()
    if request.method == "POST":
        f = request.form
        vendor = f.get("vendor_id")
        if not vendor:
            flash("Create a supplier first.", "error")
            return redirect(url_for("contacts", tab="vendor"))
        when = f.get("date") or str(date.today())
        due = f.get("due_date") or str(date.fromisoformat(when) + timedelta(days=30))
        amap = A.acct_by_code(conn(), c["id"])
        lines, subtotal, tax = [], 0.0, 0.0
        for i, target in enumerate(f.getlist("line_account")):
            if not target:
                continue
            try:
                qty = float(f.getlist("qty")[i] or 1)
                cost = float(f.getlist("unit_cost")[i] or 0)
            except Exception:
                continue
            if cost <= 0:
                continue
            desc = f.getlist("desc")[i] or ""
            amt = round(qty * cost, 2)
            if target.startswith("item:"):
                it = conn().execute("SELECT * FROM items WHERE id=?", (target.split(":")[1],)).fetchone()
                code, item_id, desc = "1200", it["id"], desc or f"{it['name']} - stock purchase"
            else:
                code, item_id = target.split(":")[1], None
                code = [k for k, v in amap.items() if v["id"] == int(code)][0]
                desc = desc or amap[code]["name"]
            lines.append((code, item_id, desc, qty, cost, amt))
            subtotal += amt
            tax += round(amt * 0.15, 2)
        if not lines:
            flash("Add at least one line.", "error")
            return redirect(url_for("bill_new"))
        total = round(subtotal + tax, 2)
        number = next_number("bills", "BILL")
        cur = conn().cursor()
        cur.execute("""INSERT INTO bills(company_id,number,vendor_id,date,due_date,status,subtotal,tax,total,amount_paid,notes)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (c["id"], number, vendor, when, due, "open", round(subtotal, 2), round(tax, 2), total, 0,
                     f.get("notes", "")))
        bid = cur.lastrowid
        je = [("2000", 0, total, number), ("1400", round(tax, 2), 0, "Input VAT " + number)]
        for code, item_id, desc, qty, cost, amt in lines:
            cur.execute("""INSERT INTO bill_lines(bill_id,item_id,account_id,description,qty,unit_cost,tax_rate,amount)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (bid, item_id, amap[code]["id"], desc, qty, cost, 15, amt))
            je.append((code, amt, 0, desc))
            if item_id:
                cur.execute("UPDATE items SET qty=qty+?, cost=? WHERE id=?", (qty, cost, item_id))
        conn().commit()
        post_je(when, f"Vendor bill {number}", "bill", number, je)
        flash(f"Bill {number} recorded.", "success")
        return redirect(url_for("bill_view", bid=bid))
    return render_template("bill_new.html", vendors=vendors, accounts=accounts, stock_items=stock_items,
                           title="New Bill", today=date.today().isoformat(),
                           due_default=(date.today() + timedelta(days=30)).isoformat())


@app.route("/bills/<int:bid>")
def bill_view(bid):
    c = company()
    b = conn().execute("""SELECT b.*, ct.name party, ct.email, ct.phone, ct.address FROM bills b
        LEFT JOIN contacts ct ON ct.id=b.vendor_id WHERE b.id=? AND b.company_id=?""", (bid, c["id"])).fetchone()
    if not b:
        return redirect(url_for("bills"))
    lines = conn().execute("""SELECT bl.*, a.name account FROM bill_lines bl
        LEFT JOIN accounts a ON a.id=bl.account_id WHERE bl.bill_id=?""", (bid,)).fetchall()
    pays = conn().execute("SELECT * FROM payments WHERE bill_id=? ORDER BY date", (bid,)).fetchall()
    banks = conn().execute("SELECT * FROM bank_accounts WHERE company_id=?", (c["id"],)).fetchall()
    credits = conn().execute("SELECT * FROM vendor_credits WHERE bill_id=? ORDER BY date", (bid,)).fetchall()
    return render_template("bill_view.html", b=b, lines=lines, pays=pays, banks=banks, credits=credits,
                           title=b["number"])


@app.route("/bills/<int:bid>/pay", methods=["POST"])
def bill_pay(bid):
    c = company()
    b = conn().execute("SELECT * FROM bills WHERE id=? AND company_id=?", (bid, c["id"])).fetchone()
    if not b:
        return redirect(url_for("bills"))
    f = request.form
    amt = float(f.get("amount") or 0)
    when = f.get("date") or str(date.today())
    bank = conn().execute("SELECT * FROM bank_accounts WHERE id=?", (f.get("bank_account_id"),)).fetchone()
    cur = conn().cursor()
    cur.execute("""INSERT INTO payments(company_id,kind,contact_id,bill_id,date,amount,method,bank_account_id,reference)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (c["id"], "made", b["vendor_id"], bid, when, amt, f.get("method") or "Bank transfer",
                 bank["id"] if bank else None, f.get("reference") or f"PAY-{bid:04d}"))
    new_paid = round(b["amount_paid"] + amt, 2)
    cur.execute("UPDATE bills SET amount_paid=?, status=? WHERE id=?",
                (new_paid, "paid" if new_paid >= b["total"] - 0.011 else "partial", bid))
    conn().commit()
    bank_code = "1010"
    if bank:
        ba = conn().execute("SELECT a.code FROM bank_accounts b JOIN accounts a ON a.id=b.account_id WHERE b.id=?",
                            (bank["id"],)).fetchone()
        bank_code = ba["code"] if ba else "1010"
    post_je(when, f"Payment made - {b['number']}", "payment", b["number"],
            [("2000", amt, 0, b["number"]), (bank_code, 0, amt, "Supplier payment")])
    if bank:
        cur.execute("""INSERT INTO bank_txns(company_id,bank_account_id,date,description,reference,amount,direction,status,source)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (c["id"], bank["id"], when, f"Payment - {b['number']}", "PAY", amt, "out", "reconciled", "books"))
        conn().commit()
    flash(f"Payment of ${amt:,.2f} recorded against {b['number']}.", "success")
    return redirect(url_for("bill_view", bid=bid))


@app.route("/payments")
def payments():
    c = company()
    kind = request.args.get("kind", "all")
    sql = """SELECT p.*, ct.name party, i.number inv_no, b.number bill_no FROM payments p
        LEFT JOIN contacts ct ON ct.id=p.contact_id
        LEFT JOIN invoices i ON i.id=p.invoice_id LEFT JOIN bills b ON b.id=p.bill_id
        WHERE p.company_id=?"""
    args = [c["id"]]
    if kind in ("received", "made"):
        sql += " AND p.kind=?"
        args.append(kind)
    sql += " ORDER BY p.date DESC, p.id DESC"
    rows = conn().execute(sql, args).fetchall()
    totals = {"received": sum(r["amount"] for r in rows if r["kind"] == "received"),
              "made": sum(r["amount"] for r in rows if r["kind"] == "made")}
    return render_template("payments.html", rows=rows, kind=kind, totals=totals, title="Payments")


# ------------------------------------------------------------------ banking
@app.route("/banking")
def banking():
    c = company()
    banks = []
    amap = A.acct_by_code(conn(), c["id"])
    for b in conn().execute("SELECT * FROM bank_accounts WHERE company_id=?", (c["id"],)):
        bal = conn().execute("""SELECT COALESCE(SUM(jl.debit)-SUM(jl.credit),0) v FROM journal_lines jl
            JOIN journal_entries je ON je.id=jl.entry_id WHERE jl.account_id=? AND je.company_id=?""",
                             (b["account_id"], c["id"])).fetchone()["v"]
        banks.append({**dict(b), "balance": bal})
    txns = conn().execute("""SELECT t.*, b.name bank FROM bank_txns t JOIN bank_accounts b ON b.id=t.bank_account_id
        WHERE t.company_id=? ORDER BY CASE t.status WHEN 'unreconciled' THEN 0 ELSE 1 END, t.date DESC LIMIT 60""",
                          (c["id"],)).fetchall()
    reconciled = conn().execute("SELECT COUNT(*) c FROM bank_txns WHERE company_id=? AND status='reconciled'",
                                (c["id"],)).fetchone()["c"]
    unreconciled = conn().execute("SELECT COUNT(*) c FROM bank_txns WHERE company_id=? AND status='unreconciled'",
                                  (c["id"],)).fetchone()["c"]
    return render_template("banking.html", banks=banks, txns=txns, reconciled=reconciled,
                           unreconciled=unreconciled, title="Banking & Reconciliation")


@app.route("/banking/<int:tid>/toggle", methods=["POST"])
def banking_toggle(tid):
    c = company()
    row = conn().execute("SELECT * FROM bank_txns WHERE id=? AND company_id=?", (tid, c["id"])).fetchone()
    if row:
        new = "reconciled" if row["status"] == "unreconciled" else "unreconciled"
        conn().execute("UPDATE bank_txns SET status=? WHERE id=?", (new, tid))
        conn().commit()
    return redirect(request.referrer or url_for("banking"))


# ------------------------------------------------------------------ contacts
@app.route("/contacts")
def contacts():
    c = company()
    tab = request.args.get("tab", "customer")
    rows = A.contacts_with_balance(conn(), c["id"], tab)
    return render_template("contacts.html", rows=rows, tab=tab, title="Contacts")


@app.route("/contacts/new", methods=["GET", "POST"])
def contact_new():
    c = company()
    if request.method == "POST":
        f = request.form
        cur = conn().cursor()
        cur.execute("""INSERT INTO contacts(company_id,type,name,company,email,phone,address,tax_no,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (c["id"], f.get("type", "customer"), f.get("name"), f.get("company") or f.get("name"),
                     f.get("email"), f.get("phone"), f.get("address"), f.get("tax_no"), str(date.today())))
        conn().commit()
        flash(f"{f.get('name')} added to contacts.", "success")
        return redirect(url_for("contacts", tab=f.get("type", "customer")))
    return render_template("contact_new.html", title="New Contact", tab=request.args.get("type", "customer"))


@app.route("/contacts/<int:cid2>")
def contact_view(cid2):
    c = company()
    ct = conn().execute("SELECT * FROM contacts WHERE id=? AND company_id=?", (cid2, c["id"])).fetchone()
    if not ct:
        return redirect(url_for("contacts"))
    if ct["type"] == "customer":
        docs = conn().execute("SELECT * FROM invoices WHERE contact_id=? ORDER BY date DESC", (cid2,)).fetchall()
        total = sum(d["total"] for d in docs)
        balance = sum(d["total"] - d["amount_paid"] for d in docs)
        pays = conn().execute("SELECT * FROM payments WHERE contact_id=? ORDER BY date DESC", (cid2,)).fetchall()
    else:
        docs = conn().execute("SELECT * FROM bills WHERE vendor_id=? ORDER BY date DESC", (cid2,)).fetchall()
        total = sum(d["total"] for d in docs)
        balance = sum(d["total"] - d["amount_paid"] for d in docs)
        pays = conn().execute("SELECT * FROM payments WHERE contact_id=? ORDER BY date DESC", (cid2,)).fetchall()
    return render_template("contact_view.html", ct=ct, docs=docs, total=total, balance=balance, pays=pays,
                           title=ct["name"])


# ------------------------------------------------------------------ inventory / items
@app.route("/inventory")
def inventory():
    c = company()
    items = A.stock_summary(conn(), c["id"])
    accounts = conn().execute("SELECT * FROM accounts WHERE company_id=? AND type='income' ORDER BY code",
                              (c["id"],)).fetchall()
    total_value = sum(i["qty"] * i["cost"] for i in items)
    low = [i for i in items if i["qty"] <= i["reorder"]]
    return render_template("inventory.html", items=items, accounts=accounts, total_value=total_value, low=low,
                           title="Inventory & Items")


@app.route("/inventory/adjust", methods=["POST"])
def inventory_adjust():
    c = company()
    f = request.form
    it = conn().execute("SELECT * FROM items WHERE id=? AND company_id=?", (f.get("item_id"), c["id"])).fetchone()
    if not it:
        return redirect(url_for("inventory"))
    new_qty = float(f.get("new_qty") or 0)
    delta = new_qty - it["qty"]
    value = round(abs(delta) * (it["cost"] or 0), 2)
    conn().execute("UPDATE items SET qty=? WHERE id=?", (new_qty, it["id"]))
    conn().commit()
    if value > 0:
        if delta > 0:
            post_je(f.get("date") or str(date.today()), f"Stock adjustment - {it['name']}", "adjustment", it["sku"],
                    [("1200", value, 0, "Stock increase"), ("4200", 0, value, "Stock adjustment gain")])
        else:
            post_je(f.get("date") or str(date.today()), f"Stock adjustment - {it['name']}", "adjustment", it["sku"],
                    [("5230", value, 0, "Stock write-off"), ("1200", 0, value, "Stock decrease")])
    flash(f"Stock for {it['name']} adjusted to {new_qty:g}.", "success")
    return redirect(url_for("inventory"))


@app.route("/items/new", methods=["POST"])
def item_new():
    c = company()
    f = request.form
    rev = conn().execute("SELECT id FROM accounts WHERE company_id=? AND code=?", (c["id"], f.get("account_code") or "4000")).fetchone()
    cur = conn().cursor()
    n = conn().execute("SELECT COUNT(*) c FROM items WHERE company_id=?", (c["id"],)).fetchone()["c"]
    cur.execute("""INSERT INTO items(company_id,name,sku,kind,unit,price,cost,tax_rate,qty,reorder,tracked,account_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (c["id"], f.get("name"), f.get("sku") or f"ITM-{n+1:03d}", f.get("kind", "service"),
                 f.get("unit") or "unit", float(f.get("price") or 0), float(f.get("cost") or 0), 15,
                 float(f.get("qty") or 0), float(f.get("reorder") or 0),
                 1 if f.get("kind") == "goods" else 0, rev["id"] if rev else None))
    conn().commit()
    flash(f"Item {f.get('name')} added.", "success")
    return redirect(url_for("inventory"))


# ------------------------------------------------------------------ payroll
@app.route("/payroll")
def payroll():
    c = company()
    runs = A.payroll_runs(conn(), c["id"])
    employees = conn().execute("SELECT * FROM employees WHERE company_id=? ORDER BY gross DESC", (c["id"],)).fetchall()
    monthly = sum(e["gross"] for e in employees if e["status"] == "Active")
    return render_template("payroll.html", runs=runs, employees=employees, monthly=monthly, title="Payroll")


@app.route("/payroll/new", methods=["GET", "POST"])
def payroll_new():
    c = company()
    employees = conn().execute("SELECT * FROM employees WHERE company_id=? AND status='Active' ORDER BY name",
                               (c["id"],)).fetchall()
    if request.method == "POST":
        period = request.form.get("period") or date.today().strftime("%Y-%m")
        exists = conn().execute("SELECT id FROM payroll_runs WHERE company_id=? AND period=?", (c["id"], period)).fetchone()
        if exists:
            flash(f"Payroll for {period} already exists.", "error")
            return redirect(url_for("payroll"))
        when = request.form.get("date") or str(date.today())
        slips, gross_t, paye_t, aids_t, nssa_t, net_t, er_nssa = [], 0, 0, 0, 0, 0, 0
        for e in employees:
            gross = e["gross"]
            paye, aids, nssa = db.paye_zim(gross)
            net = round(gross - paye - aids - nssa, 2)
            slips.append((e["id"], gross, paye, aids, nssa, net))
            gross_t += gross; paye_t += paye; aids_t += aids; nssa_t += nssa; net_t += net
            er_nssa += round(min(gross, 700) * 0.045, 2)
        cur = conn().cursor()
        cur.execute("""INSERT INTO payroll_runs(company_id,period,date,gross,paye,nssa,net,status)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (c["id"], period, when, round(gross_t, 2), round(paye_t, 2), round(nssa_t + er_nssa, 2),
                     round(net_t, 2), "paid"))
        rid = cur.lastrowid
        for s in slips:
            cur.execute("INSERT INTO payslips(run_id,employee_id,gross,paye,aids,nssa,net) VALUES(?,?,?,?,?,?,?)", (rid,) + s)
        conn().commit()
        post_je(when, f"Payroll {period}", "payroll", period, [
            ("5100", gross_t, 0, "Gross salaries"), ("5110", er_nssa, 0, "Employer NSSA"),
            ("2200", 0, round(paye_t, 2), "PAYE payable"), ("2220", 0, round(aids_t, 2), "AIDS levy"),
            ("2210", 0, round(nssa_t + er_nssa, 2), "NSSA payable"), ("2300", 0, round(net_t, 2), "Net wages accrued")])
        post_je(when, f"Net pay transfer {period}", "payroll", period,
                [("2300", round(net_t, 2), 0, "Net wages paid"), ("1010", 0, round(net_t, 2), "Salaries transfer")])
        flash(f"Payroll {period} processed: {len(slips)} employees, net ${net_t:,.2f}.", "success")
        return redirect(url_for("payroll_view", rid=rid))
    next_period = date.today().strftime("%Y-%m")
    preview = []
    for e in employees:
        paye, aids, nssa = db.paye_zim(e["gross"])
        preview.append({**dict(e), "paye": paye, "aids": aids, "nssa": nssa, "net": round(e["gross"] - paye - aids - nssa, 2)})
    return render_template("payroll_new.html", employees=preview, period=next_period,
                           today=date.today().isoformat(), title="Run Payroll")


@app.route("/payroll/<int:rid>")
def payroll_view(rid):
    c = company()
    run = conn().execute("SELECT * FROM payroll_runs WHERE id=? AND company_id=?", (rid, c["id"])).fetchone()
    if not run:
        return redirect(url_for("payroll"))
    slips = conn().execute("""SELECT s.*, e.name, e.position FROM payslips s JOIN employees e ON e.id=s.employee_id
        WHERE s.run_id=? ORDER BY e.name""", (rid,)).fetchall()
    return render_template("payroll_view.html", run=run, slips=slips, title=f"Payroll {run['period']}")


# ------------------------------------------------------------------ assets
@app.route("/assets")
def assets():
    c = company()
    reg = A.asset_register(conn(), c["id"])
    totals = dict(cost=sum(a["cost"] for a in reg), dep=sum(a["accum_dep"] for a in reg),
                  nbv=sum(a["nbv"] for a in reg))
    return render_template("assets.html", rows=reg, totals=totals, title="Fixed Assets",
                           today=date.today().isoformat())


@app.route("/assets/new", methods=["POST"])
def asset_new():
    c = company()
    f = request.form
    cost = float(f.get("cost") or 0)
    life = float(f.get("life") or 5)
    exp = acct_id("5240"); acc = acct_id("1510"); ppe = acct_id("1500")
    cur = conn().cursor()
    cur.execute("""INSERT INTO fixed_assets(company_id,name,category,purchase_date,cost,salvage,life,accum_dep,
                   last_dep,exp_account_id,accum_account_id,status,location)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (c["id"], f.get("name"), f.get("category") or "Equipment", f.get("purchase_date") or str(date.today()),
                 cost, 0, life, 0, None, exp, acc, "In service", f.get("location") or "Harare"))
    conn().commit()
    post_je(f.get("purchase_date") or str(date.today()), f"Asset acquisition - {f.get('name')}", "asset",
            f.get("name"), [("1500", cost, 0, f.get("name")), ("1010", 0, cost, "Asset purchase")])
    flash(f"Asset {f.get('name')} capitalised.", "success")
    return redirect(url_for("assets"))


# ------------------------------------------------------------------ journal & accounts
@app.route("/journal")
def journal():
    c = company()
    rows = conn().execute("""SELECT je.*, COALESCE(SUM(jl.debit),0) total FROM journal_entries je
        LEFT JOIN journal_lines jl ON jl.entry_id=je.id WHERE je.company_id=?
        GROUP BY je.id ORDER BY je.date DESC, je.id DESC LIMIT 80""", (c["id"],)).fetchall()
    return render_template("journal.html", rows=rows, title="Journal Entries")


@app.route("/journal/<int:eid>")
def journal_view(eid):
    c = company()
    e = conn().execute("SELECT * FROM journal_entries WHERE id=? AND company_id=?", (eid, c["id"])).fetchone()
    lines = conn().execute("""SELECT jl.*, a.code, a.name account FROM journal_lines jl
        JOIN accounts a ON a.id=jl.account_id WHERE jl.entry_id=? ORDER BY jl.id""", (eid,)).fetchall()
    return render_template("journal_view.html", e=e, lines=lines, title=e["number"] if e else "Journal")


@app.route("/journal/new", methods=["GET", "POST"])
def journal_new():
    c = company()
    accounts = conn().execute("SELECT * FROM accounts WHERE company_id=? ORDER BY code", (c["id"],)).fetchall()
    if request.method == "POST":
        f = request.form
        lines = []
        dr_t = cr_t = 0.0
        for i, aid in enumerate(f.getlist("account_id")):
            if not aid:
                continue
            try:
                dr = float(f.getlist("debit")[i] or 0)
                cr = float(f.getlist("credit")[i] or 0)
            except Exception:
                continue
            if dr == 0 and cr == 0:
                continue
            a = conn().execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
            lines.append((a["code"], dr, cr, f.getlist("desc")[i] or a["name"]))
            dr_t += dr; cr_t += cr
        if not lines or abs(dr_t - cr_t) > 0.02 or dr_t == 0:
            flash(f"Entry must balance. Debits ${dr_t:,.2f} vs credits ${cr_t:,.2f}.", "error")
            return redirect(url_for("journal_new"))
        when = f.get("date") or str(date.today())
        post_je(when, f.get("memo") or "Manual journal", "manual", f.get("reference") or "", lines)
        flash("Journal posted.", "success")
        return redirect(url_for("journal"))
    return render_template("journal_new.html", accounts=accounts, title="New Journal Entry",
                           today=date.today().isoformat())


@app.route("/accounts")
def accounts_page():
    c = company()
    amap = A.acct_by_code(conn(), c["id"])
    bal = A.account_balances(conn(), c["id"])
    groups = {"asset": [], "liability": [], "equity": [], "income": [], "expense": []}
    for code, a in sorted(amap.items()):
        v = bal.get(a["id"], 0)
        natural = v if a["type"] in ("asset", "expense") else -v
        groups[a["type"]].append({**a, "balance": natural})
    labels = {"asset": "Assets", "liability": "Liabilities", "equity": "Equity",
              "income": "Income", "expense": "Expenses"}
    return render_template("accounts.html", groups=groups, labels=labels, title="Chart of Accounts")



# ------------------------------------------------------------------ credit notes (sales returns)
def _money(v):
    try:
        return round(float(v or 0), 2)
    except Exception:
        return 0.0


@app.route("/credit-notes")
def credit_notes():
    c = company()
    rows = conn().execute("""SELECT cn.*, ct.name party, i.number invoice_no FROM credit_notes cn
        LEFT JOIN contacts ct ON ct.id=cn.contact_id
        LEFT JOIN invoices i ON i.id=cn.invoice_id
        WHERE cn.company_id=? ORDER BY cn.date DESC, cn.id DESC""", (c["id"],)).fetchall()
    totals = {"total": sum(r["total"] for r in rows),
              "available": sum(max(r["total"] - r["applied"] - r["refunded"], 0) for r in rows)}
    return render_template("credit_notes.html", rows=rows, totals=totals, title="Credit Notes")


@app.route("/credit-notes/new", methods=["GET", "POST"])
def credit_note_new():
    c = company()
    contacts = conn().execute("SELECT * FROM contacts WHERE company_id=? AND type='customer' ORDER BY name",
                              (c["id"],)).fetchall()
    items = conn().execute("SELECT * FROM items WHERE company_id=? ORDER BY name", (c["id"],)).fetchall()
    open_invoices = conn().execute("""SELECT i.*, ct.name party FROM invoices i
        LEFT JOIN contacts ct ON ct.id=i.contact_id
        WHERE i.company_id=? AND i.total-i.amount_paid>0.01 ORDER BY i.date DESC""", (c["id"],)).fetchall()
    if request.method == "POST":
        f = request.form
        cust = f.get("contact_id")
        if not cust:
            flash("Choose the customer first.", "error")
            return redirect(url_for("credit_note_new"))
        when = f.get("date") or str(date.today())
        restock = bool(f.get("restock"))
        lines, subtotal, tax, cogs = [], 0.0, 0.0, 0.0
        for i, iid in enumerate(f.getlist("item_id")):
            if not iid:
                continue
            it = conn().execute("SELECT * FROM items WHERE id=? AND company_id=?", (iid, c["id"])).fetchone()
            if not it:
                continue
            try:
                qty = float(f.getlist("qty")[i] or 0)
            except Exception:
                qty = 0
            if qty <= 0:
                continue
            prices = f.getlist("price")
            price = float(prices[i]) if i < len(prices) and prices[i] else it["price"]
            desc = (f.getlist("desc")[i] if i < len(f.getlist("desc")) else "") or it["name"]
            amt = _money(qty * price)
            lines.append({"item": it, "qty": qty, "price": price, "desc": desc, "amt": amt})
            subtotal += amt
            tax += _money(amt * c["tax_rate"] / 100)
            if it["tracked"]:
                cogs += qty * (it["cost"] or 0)
        if not lines:
            flash("Add at least one line to credit.", "error")
            return redirect(url_for("credit_note_new"))
        subtotal, tax = _money(subtotal), _money(tax)
        total = _money(subtotal + tax)
        number = next_number("credit_notes", "CN")
        cur = conn().cursor()
        cur.execute("""INSERT INTO credit_notes(company_id,number,contact_id,invoice_id,date,reason,
                       subtotal,tax,total,applied,refunded,status,notes)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (c["id"], number, cust, f.get("invoice_id") or None, when, f.get("reason") or "Sales return",
                     subtotal, tax, total, 0, 0, "open", f.get("notes", "")))
        cnid = cur.lastrowid
        for l in lines:
            cur.execute("""INSERT INTO credit_note_lines(credit_note_id,item_id,description,qty,unit_price,
                           tax_rate,amount,unit_cost,restock) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (cnid, l["item"]["id"], l["desc"], l["qty"], l["price"], c["tax_rate"], l["amt"],
                         l["item"]["cost"] or 0, 1 if (restock and l["item"]["tracked"]) else 0))
            if restock and l["item"]["tracked"]:
                cur.execute("UPDATE items SET qty=qty+? WHERE id=?", (l["qty"], l["item"]["id"]))
        conn().commit()
        je = [("4900", subtotal, 0, f"Credit note {number}"),
              ("2100", tax, 0, f"VAT reversed on {number}"),
              ("1150", 0, total, f"Credit available {number}")]
        if restock and cogs:
            je += [("1200", _money(cogs), 0, "Goods returned to stock"),
                   ("5000", 0, _money(cogs), "Cost of sales reversed")]
        post_je(when, f"Credit note {number}", "credit_note", number, je)

        # auto-apply to the referenced invoice
        applied = 0.0
        inv_id = f.get("invoice_id")
        if inv_id:
            inv = conn().execute("SELECT * FROM invoices WHERE id=? AND company_id=?",
                                 (inv_id, c["id"])).fetchone()
            if inv:
                bal = _money(inv["total"] - inv["amount_paid"])
                applied = _money(min(total, max(bal, 0)))
                if applied > 0:
                    new_paid = _money(inv["amount_paid"] + applied)
                    conn().execute("UPDATE invoices SET amount_paid=?, status=? WHERE id=?",
                                   (new_paid, "paid" if new_paid >= inv["total"] - 0.011 else "partial", inv["id"]))
                    conn().execute("UPDATE credit_notes SET applied=?, status=? WHERE id=?",
                                   (applied, "applied" if applied >= total - 0.011 else "partial", cnid))
                    conn().commit()
                    post_je(when, f"Credit note {number} applied to {inv['number']}", "credit_note", number,
                            [("1150", applied, 0, f"Credit used on {inv['number']}"),
                             ("1100", 0, applied, f"Receivable reduced {inv['number']}")])
        flash(f"Credit note {number} issued for ${total:,.2f}"
              + (f" — ${applied:,.2f} applied to the invoice." if applied else "."), "success")
        return redirect(url_for("credit_notes"))
    pre_inv = request.args.get("invoice_id")
    return render_template("credit_note_new.html", contacts=contacts, items=items, invoices=open_invoices,
                           title="New Credit Note", today=date.today().isoformat(), pre_inv=pre_inv)


@app.route("/credit-notes/<int:cnid>")
def credit_note_view(cnid):
    c = company()
    cn = conn().execute("SELECT * FROM credit_notes WHERE id=? AND company_id=?", (cnid, c["id"])).fetchone()
    if not cn:
        return redirect(url_for("credit_notes"))
    lines = conn().execute("SELECT * FROM credit_note_lines WHERE credit_note_id=?", (cnid,)).fetchall()
    party = conn().execute("SELECT * FROM contacts WHERE id=?", (cn["contact_id"],)).fetchone()
    inv = conn().execute("SELECT number FROM invoices WHERE id=?", (cn["invoice_id"],)).fetchone() if cn["invoice_id"] else None
    invoices = conn().execute("""SELECT i.*, ct.name party FROM invoices i
        LEFT JOIN contacts ct ON ct.id=i.contact_id
        WHERE i.company_id=? AND i.total-i.amount_paid>0.01 ORDER BY i.date DESC""", (c["id"],)).fetchall()
    return render_template("credit_note_view.html", cn=cn, lines=lines, party=party,
                           inv_no=inv["number"] if inv else None, invoices=invoices,
                           title=cn["number"])


@app.route("/credit-notes/<int:cnid>/apply", methods=["POST"])
def credit_note_apply(cnid):
    c = company()
    cn = conn().execute("SELECT * FROM credit_notes WHERE id=? AND company_id=?", (cnid, c["id"])).fetchone()
    if not cn:
        return redirect(url_for("credit_notes"))
    available = _money(cn["total"] - cn["applied"] - cn["refunded"])
    inv = conn().execute("SELECT * FROM invoices WHERE id=? AND company_id=?",
                         (request.form.get("invoice_id"), c["id"])).fetchone()
    if not inv:
        flash("Choose an open invoice to apply this credit to.", "error")
        return redirect(url_for("credit_notes"))
    balance = _money(inv["total"] - inv["amount_paid"])
    amount = _money(min(_money(request.form.get("amount") or available), available, max(balance, 0)))
    if amount <= 0:
        flash("Nothing to apply — the invoice is already settled or the credit is used up.", "error")
        return redirect(url_for("credit_notes"))
    when = request.form.get("date") or str(date.today())
    new_paid = _money(inv["amount_paid"] + amount)
    conn().execute("UPDATE invoices SET amount_paid=?, status=? WHERE id=?",
                   (new_paid, "paid" if new_paid >= inv["total"] - 0.011 else "partial", inv["id"]))
    total_applied = _money(cn["applied"] + amount)
    conn().execute("UPDATE credit_notes SET applied=?, status=? WHERE id=?",
                   (total_applied, "applied" if total_applied + cn["refunded"] >= cn["total"] - 0.011 else "partial", cnid))
    conn().commit()
    post_je(when, f"Credit note {cn['number']} applied to {inv['number']}", "credit_note", cn["number"],
            [("1150", amount, 0, f"Credit used on {inv['number']}"),
             ("1100", 0, amount, f"Receivable reduced {inv['number']}")])
    flash(f"${amount:,.2f} of {cn['number']} applied to {inv['number']}.", "success")
    return redirect(url_for("credit_notes"))


@app.route("/credit-notes/<int:cnid>/refund", methods=["POST"])
def credit_note_refund(cnid):
    c = company()
    cn = conn().execute("SELECT * FROM credit_notes WHERE id=? AND company_id=?", (cnid, c["id"])).fetchone()
    if not cn:
        return redirect(url_for("credit_notes"))
    available = _money(cn["total"] - cn["applied"] - cn["refunded"])
    amount = _money(min(_money(request.form.get("amount") or available), available))
    if amount <= 0:
        flash("No refundable balance on this credit note.", "error")
        return redirect(url_for("credit_notes"))
    when = request.form.get("date") or str(date.today())
    conn().execute("UPDATE credit_notes SET refunded=?, status=? WHERE id=?",
                   (_money(cn["refunded"] + amount),
                    "refunded" if cn["applied"] + cn["refunded"] + amount >= cn["total"] - 0.011 else "partial", cnid))
    conn().commit()
    post_je(when, f"Refund of credit note {cn['number']}", "credit_note", cn["number"],
            [("1150", amount, 0, f"Credit refunded {cn['number']}"),
             ("1010", 0, amount, "Bank refund to customer")])
    flash(f"${amount:,.2f} refunded against {cn['number']}.", "success")
    return redirect(url_for("credit_notes"))


# ------------------------------------------------------------------ vendor credits
@app.route("/vendor-credits")
def vendor_credits():
    c = company()
    rows = conn().execute("""SELECT vc.*, ct.name party, b.number bill_no FROM vendor_credits vc
        LEFT JOIN contacts ct ON ct.id=vc.vendor_id
        LEFT JOIN bills b ON b.id=vc.bill_id
        WHERE vc.company_id=? ORDER BY vc.date DESC, vc.id DESC""", (c["id"],)).fetchall()
    totals = {"total": sum(r["total"] for r in rows),
              "available": sum(max(r["total"] - r["applied"], 0) for r in rows)}
    return render_template("vendor_credits.html", rows=rows, totals=totals, title="Vendor Credits")


@app.route("/vendor-credits/new", methods=["GET", "POST"])
def vendor_credit_new():
    c = company()
    vendors = conn().execute("SELECT * FROM contacts WHERE company_id=? AND type='vendor' ORDER BY name",
                             (c["id"],)).fetchall()
    accounts = conn().execute("SELECT * FROM accounts WHERE company_id=? AND type='expense' ORDER BY code",
                              (c["id"],)).fetchall()
    open_bills = conn().execute("""SELECT b.*, ct.name party FROM bills b
        LEFT JOIN contacts ct ON ct.id=b.vendor_id
        WHERE b.company_id=? AND b.total-b.amount_paid>0.01 ORDER BY b.date DESC""", (c["id"],)).fetchall()
    if request.method == "POST":
        f = request.form
        vendor = f.get("vendor_id")
        if not vendor:
            flash("Choose the supplier first.", "error")
            return redirect(url_for("vendor_credit_new"))
        when = f.get("date") or str(date.today())
        lines, subtotal, tax = [], 0.0, 0.0
        for i, aid in enumerate(f.getlist("account_id")):
            if not aid:
                continue
            try:
                qty = float(f.getlist("qty")[i] or 1)
                cost = float(f.getlist("unit_cost")[i] or 0)
            except Exception:
                continue
            if cost <= 0:
                continue
            desc = f.getlist("desc")[i] or ""
            amt = _money(qty * cost)
            acct = conn().execute("SELECT * FROM accounts WHERE id=? AND company_id=?", (aid, c["id"])).fetchone()
            lines.append({"account": acct, "desc": desc or acct["name"], "qty": qty,
                          "cost": cost, "amt": amt})
            subtotal += amt
            tax += _money(amt * c["tax_rate"] / 100)
        if not lines:
            flash("Add at least one line.", "error")
            return redirect(url_for("vendor_credit_new"))
        subtotal, tax = _money(subtotal), _money(tax)
        total = _money(subtotal + tax)
        number = next_number("vendor_credits", "VC")
        cur = conn().cursor()
        cur.execute("""INSERT INTO vendor_credits(company_id,number,vendor_id,bill_id,date,reason,
                       subtotal,tax,total,applied,status,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (c["id"], number, vendor, f.get("bill_id") or None, when,
                     f.get("reason") or "Supplier credit received", subtotal, tax, total, 0, "open",
                     f.get("notes", "")))
        vcid = cur.lastrowid
        for l in lines:
            cur.execute("""INSERT INTO vendor_credit_lines(vendor_credit_id,item_id,account_id,description,
                           qty,unit_cost,tax_rate,amount,restock) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (vcid, None, l["account"]["id"], l["desc"], l["qty"], l["cost"], c["tax_rate"], l["amt"], 0))
        conn().commit()
        post_je(when, f"Vendor credit {number}", "vendor_credit", number, [
            ("2000", total, 0, f"Payable reduced {number}"),
            ("1400", 0, tax, f"Input VAT reversed {number}"),
            ("2050", 0, subtotal, f"Supplier credit available {number}")])

        applied = 0.0
        if f.get("bill_id"):
            bill = conn().execute("SELECT * FROM bills WHERE id=? AND company_id=?",
                                  (f.get("bill_id"), c["id"])).fetchone()
            if bill:
                bal = _money(bill["total"] - bill["amount_paid"])
                applied = _money(min(total, max(bal, 0)))
                if applied > 0:
                    new_paid = _money(bill["amount_paid"] + applied)
                    conn().execute("UPDATE bills SET amount_paid=?, status=? WHERE id=?",
                                   (new_paid, "paid" if new_paid >= bill["total"] - 0.011 else "partial", bill["id"]))
                    conn().execute("UPDATE vendor_credits SET applied=?, status=? WHERE id=?",
                                   (applied, "applied" if applied >= total - 0.011 else "partial", vcid))
                    conn().commit()
                    post_je(when, f"Vendor credit {number} applied to {bill['number']}", "vendor_credit", number,
                            [("2050", applied, 0, f"Credit used on {bill['number']}"),
                             ("2000", 0, applied, f"Payable reduced {bill['number']}")])
        flash(f"Vendor credit {number} recorded for ${total:,.2f}"
              + (f" — ${applied:,.2f} applied to the bill." if applied else "."), "success")
        return redirect(url_for("vendor_credits"))
    pre_bill = request.args.get("bill_id")
    return render_template("vendor_credit_new.html", vendors=vendors, accounts=accounts, bills=open_bills,
                           title="New Vendor Credit", today=date.today().isoformat(), pre_bill=pre_bill)


@app.route("/vendor-credits/<int:vcid>/apply", methods=["POST"])
def vendor_credit_apply(vcid):
    c = company()
    vc = conn().execute("SELECT * FROM vendor_credits WHERE id=? AND company_id=?", (vcid, c["id"])).fetchone()
    if not vc:
        return redirect(url_for("vendor_credits"))
    available = _money(vc["total"] - vc["applied"])
    bill = conn().execute("SELECT * FROM bills WHERE id=? AND company_id=?",
                          (request.form.get("bill_id"), c["id"])).fetchone()
    if not bill:
        flash("Choose an open bill to apply this credit to.", "error")
        return redirect(url_for("vendor_credits"))
    balance = _money(bill["total"] - bill["amount_paid"])
    amount = _money(min(_money(request.form.get("amount") or available), available, max(balance, 0)))
    if amount <= 0:
        flash("Nothing to apply — the bill is settled or the credit is used up.", "error")
        return redirect(url_for("vendor_credits"))
    when = request.form.get("date") or str(date.today())
    new_paid = _money(bill["amount_paid"] + amount)
    conn().execute("UPDATE bills SET amount_paid=?, status=? WHERE id=?",
                   (new_paid, "paid" if new_paid >= bill["total"] - 0.011 else "partial", bill["id"]))
    total_applied = _money(vc["applied"] + amount)
    conn().execute("UPDATE vendor_credits SET applied=?, status=? WHERE id=?",
                   (total_applied, "applied" if total_applied >= vc["total"] - 0.011 else "partial", vcid))
    conn().commit()
    post_je(when, f"Vendor credit {vc['number']} applied to {bill['number']}", "vendor_credit", vc["number"],
            [("2050", amount, 0, f"Credit used on {bill['number']}"),
             ("2000", 0, amount, f"Payable reduced {bill['number']}")])
    flash(f"${amount:,.2f} of {vc['number']} applied to {bill['number']}.", "success")
    return redirect(url_for("vendor_credits"))


# ------------------------------------------------------------------ purchase orders
@app.route("/purchase-orders")
def purchase_orders():
    c = company()
    rows = conn().execute("""SELECT po.*, ct.name party FROM purchase_orders po
        LEFT JOIN contacts ct ON ct.id=po.vendor_id
        WHERE po.company_id=? ORDER BY po.date DESC, po.id DESC""", (c["id"],)).fetchall()
    return render_template("purchase_orders.html", rows=rows,
                           committed=sum(r["total"] for r in rows if r["status"] != "billed"),
                           title="Purchase Orders")


@app.route("/purchase-orders/new", methods=["GET", "POST"])
def purchase_order_new():
    c = company()
    vendors = conn().execute("SELECT * FROM contacts WHERE company_id=? AND type='vendor' ORDER BY name",
                             (c["id"],)).fetchall()
    accounts = conn().execute("SELECT * FROM accounts WHERE company_id=? AND type='expense' ORDER BY code",
                              (c["id"],)).fetchall()
    stock_items = conn().execute("SELECT * FROM items WHERE company_id=? AND tracked=1 ORDER BY name",
                                 (c["id"],)).fetchall()
    if request.method == "POST":
        f = request.form
        vendor = f.get("vendor_id")
        if not vendor:
            flash("Choose a supplier first.", "error")
            return redirect(url_for("purchase_order_new"))
        when = f.get("date") or str(date.today())
        amap = A.acct_by_code(conn(), c["id"])
        lines, subtotal, tax = [], 0.0, 0.0
        for i, target in enumerate(f.getlist("line_target")):
            if not target:
                continue
            try:
                qty = float(f.getlist("qty")[i] or 0)
                cost = float(f.getlist("unit_cost")[i] or 0)
            except Exception:
                continue
            if qty <= 0 or cost <= 0:
                continue
            desc = f.getlist("desc")[i] or ""
            amt = _money(qty * cost)
            if target.startswith("item:"):
                it = conn().execute("SELECT * FROM items WHERE id=?", (target.split(":")[1],)).fetchone()
                code, item_id, desc = "1200", it["id"], desc or it["name"]
            else:
                aid = int(target.split(":")[1])
                code = [k for k, v in amap.items() if v["id"] == aid][0]
                item_id, desc = None, desc or amap[code]["name"]
            lines.append({"code": code, "item_id": item_id, "desc": desc, "qty": qty,
                          "cost": cost, "amt": amt})
            subtotal += amt
            tax += _money(amt * c["tax_rate"] / 100)
        if not lines:
            flash("Add at least one line.", "error")
            return redirect(url_for("purchase_order_new"))
        subtotal, tax = _money(subtotal), _money(tax)
        total = _money(subtotal + tax)
        number = next_number("purchase_orders", "PO")
        cur = conn().cursor()
        cur.execute("""INSERT INTO purchase_orders(company_id,number,vendor_id,date,delivery_date,status,
                       subtotal,tax,total,notes) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (c["id"], number, vendor, when, f.get("delivery_date") or None, "sent",
                     subtotal, tax, total, f.get("notes", "")))
        poid = cur.lastrowid
        for l in lines:
            cur.execute("""INSERT INTO purchase_order_lines(purchase_order_id,item_id,account_id,description,
                           qty,unit_cost,tax_rate,amount,qty_received) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (poid, l["item_id"], amap[l["code"]]["id"], l["desc"], l["qty"], l["cost"],
                         c["tax_rate"], l["amt"], 0))
        conn().commit()
        flash(f"Purchase order {number} issued for ${total:,.2f} — a commitment, not yet a liability.", "success")
        return redirect(url_for("purchase_order_view", poid=poid))
    return render_template("purchase_order_new.html", vendors=vendors, accounts=accounts,
                           stock_items=stock_items, title="New Purchase Order",
                           today=date.today().isoformat())


@app.route("/purchase-orders/<int:poid>")
def purchase_order_view(poid):
    c = company()
    po = conn().execute("""SELECT po.*, ct.name party, ct.email, ct.phone FROM purchase_orders po
        LEFT JOIN contacts ct ON ct.id=po.vendor_id WHERE po.id=? AND po.company_id=?""",
                        (poid, c["id"])).fetchone()
    if not po:
        return redirect(url_for("purchase_orders"))
    lines = conn().execute("""SELECT pol.*, a.name account, i.name item FROM purchase_order_lines pol
        LEFT JOIN accounts a ON a.id=pol.account_id LEFT JOIN items i ON i.id=pol.item_id
        WHERE pol.purchase_order_id=?""", (poid,)).fetchall()
    bill = conn().execute("SELECT number, id FROM bills WHERE id=?", (po["bill_id"],)).fetchone() if po["bill_id"] else None
    return render_template("purchase_order_view.html", po=po, lines=lines, bill=bill, title=po["number"])


@app.route("/purchase-orders/<int:poid>/receive", methods=["POST"])
def purchase_order_receive(poid):
    c = company()
    po = conn().execute("SELECT * FROM purchase_orders WHERE id=? AND company_id=?", (poid, c["id"])).fetchone()
    if not po:
        return redirect(url_for("purchase_orders"))
    lines = conn().execute("SELECT * FROM purchase_order_lines WHERE purchase_order_id=?", (poid,)).fetchall()
    all_done = True
    for l in lines:
        try:
            qty = float(request.form.get(f"recv_{l['id']}") or 0)
        except Exception:
            qty = 0
        total_recv = min(_money(l["qty_received"] + qty), l["qty"])
        conn().execute("UPDATE purchase_order_lines SET qty_received=? WHERE id=?", (total_recv, l["id"]))
        if total_recv < l["qty"] - 0.001:
            all_done = False
    conn().execute("UPDATE purchase_orders SET status=?, received_at=? WHERE id=?",
                   ("received" if all_done else "partial", str(date.today()), poid))
    conn().commit()
    flash("Receipt recorded. Stock moves when the supplier bill is posted.", "success")
    return redirect(url_for("purchase_order_view", poid=poid))


@app.route("/purchase-orders/<int:poid>/bill", methods=["POST"])
def purchase_order_bill(poid):
    c = company()
    po = conn().execute("SELECT * FROM purchase_orders WHERE id=? AND company_id=?", (poid, c["id"])).fetchone()
    if not po:
        return redirect(url_for("purchase_orders"))
    if po["bill_id"]:
        flash("This purchase order is already billed.", "error")
        return redirect(url_for("purchase_order_view", poid=poid))
    lines = conn().execute("SELECT * FROM purchase_order_lines WHERE purchase_order_id=?", (poid,)).fetchall()
    if not lines:
        flash("Nothing to bill.", "error")
        return redirect(url_for("purchase_order_view", poid=poid))
    when = request.form.get("date") or str(date.today())
    due = request.form.get("due_date") or str(date.fromisoformat(when) + timedelta(days=30))
    subtotal = _money(sum(l["amount"] for l in lines))
    tax = _money(sum(l["amount"] * (l["tax_rate"] or c["tax_rate"]) / 100 for l in lines))
    total = _money(subtotal + tax)
    number = next_number("bills", "BILL")
    cur = conn().cursor()
    cur.execute("""INSERT INTO bills(company_id,number,vendor_id,date,due_date,status,subtotal,tax,total,
                   amount_paid,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (c["id"], number, po["vendor_id"], when, due, "open", subtotal, tax, total, 0,
                 f"From purchase order {po['number']}"))
    bid = cur.lastrowid
    amap = A.acct_by_code(conn(), c["id"])
    je = [("2000", 0, total, number), ("1400", tax, 0, "Input VAT " + number)]
    for l in lines:
        cur.execute("""INSERT INTO bill_lines(bill_id,item_id,account_id,description,qty,unit_cost,tax_rate,amount)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (bid, l["item_id"], l["account_id"], l["description"],
                     l["qty_received"] or l["qty"], l["unit_cost"], l["tax_rate"], l["amount"]))
        code = [k for k, v in amap.items() if v["id"] == l["account_id"]][0]
        je.append((code, l["amount"], 0, l["description"]))
        if l["item_id"]:
            cur.execute("UPDATE items SET qty=qty+?", ((l["qty_received"] or l["qty"]),))
            cur.execute("UPDATE items SET qty=qty WHERE id=?", (l["item_id"],))
    conn().execute("UPDATE purchase_orders SET bill_id=?, status='billed' WHERE id=?", (bid, poid))
    conn().commit()
    post_je(when, f"Vendor bill {number} from {po['number']}", "bill", number, je)
    flash(f"{po['number']} billed as {number}.", "success")
    return redirect(url_for("bill_view", bid=bid))


# ------------------------------------------------------------------ reports
@app.route("/reports")
def reports():
    return render_template("reports.html", title="Reports")


@app.route("/reports/<rtype>")
def report_view(rtype):
    c = company()
    cid = c["id"]
    t = date.today()
    start = pdate("start", A.fy_start(c))
    end = pdate("end", t)
    as_of = pdate("as_of", t)
    ctx = dict(rtype=rtype, start=start, end=end, as_of=as_of, title="Reports")
    if rtype == "pl":
        ctx["data"] = A.pnl_statement(conn(), cid, start, end)
        ctx["title"] = "Profit & Loss"
    elif rtype == "bs":
        ctx["data"] = A.balance_sheet(conn(), cid, as_of)
        ctx["title"] = "Balance Sheet"
    elif rtype == "tb":
        amap = A.acct_by_code(conn(), cid)
        rows = conn().execute("""SELECT jl.account_id, SUM(jl.debit) dr, SUM(jl.credit) cr FROM journal_lines jl
            JOIN journal_entries je ON je.id=jl.entry_id WHERE je.company_id=? AND je.date<=?
            GROUP BY jl.account_id ORDER BY jl.account_id""", (cid, str(as_of))).fetchall()
        data = []
        for r in rows:
            a = [v for v in amap.values() if v["id"] == r["account_id"]][0]
            net = (r["dr"] or 0) - (r["cr"] or 0)
            data.append({**a, "dr": r["dr"] or 0, "cr": r["cr"] or 0,
                         "bal_dr": max(net, 0), "bal_cr": max(-net, 0)})
        ctx["data"] = data
        ctx["totals"] = {"dr": sum(d["dr"] for d in data), "cr": sum(d["cr"] for d in data),
                         "bal_dr": sum(d["bal_dr"] for d in data), "bal_cr": sum(d["bal_cr"] for d in data)}
        ctx["title"] = "Trial Balance"
    elif rtype == "cf":
        ctx["data"] = A.cash_flow(conn(), cid, start, end)
        ctx["title"] = "Cash Flow Statement"
    elif rtype == "vat":
        ctx["data"] = A.vat_report(conn(), cid, start, end)
        ctx["title"] = "VAT Return (ZIMRA)"
    elif rtype == "aging":
        ar_b, ar_d = A.ar_aging(conn(), cid)
        ap_b, ap_d = A.ap_aging(conn(), cid)
        ctx.update(ar_b=ar_b, ar_d=ar_d, ap_b=ap_b, ap_d=ap_d, title="Aged Receivables & Payables")
    elif rtype == "gl":
        acc_id = request.args.get("account_id")
        accounts = conn().execute("SELECT * FROM accounts WHERE company_id=? ORDER BY code", (cid,)).fetchall()
        if not acc_id:
            acc_id = accounts[0]["id"]
        ctx["accounts"] = accounts
        ctx["sel"] = int(acc_id)
        ctx["data"] = A.general_ledger(conn(), cid, int(acc_id), start, end)
        ctx["title"] = "General Ledger"
    elif rtype == "sales-items":
        ctx["data"] = A.item_sales(conn(), cid, start, end)
        ctx["title"] = "Sales by Item"
    elif rtype == "stock":
        ctx["data"] = A.stock_summary(conn(), cid)
        ctx["totals"] = {"value": sum(i["qty"] * i["cost"] for i in ctx["data"])}
        ctx["title"] = "Inventory Valuation"
    elif rtype == "assets-register":
        ctx["data"] = A.asset_register(conn(), cid)
        ctx["title"] = "Fixed Asset Register"
    else:
        return redirect(url_for("reports"))
    return render_template("report_view.html", **ctx)


# ------------------------------------------------------------------ setup / settings
@app.route("/setup")
def setup():
    c = company()
    return render_template("setup.html", current=c["industry"], title="Industry Setup")


@app.route("/setup/apply", methods=["POST"])
def setup_apply():
    profile = request.form.get("profile", "mining")
    mode = request.form.get("mode", "demo")
    if profile not in db.PROFILES:
        profile = "mining"
    c = company()
    db.rebuild_tenant(conn(), c["id"], profile, demo=(mode == "demo"))
    # the rebuild recreates users, so re-sign the current person in
    if g.ident.get("role") != "demo":
        owner = conn().execute("""SELECT * FROM users WHERE company_id=? AND role='owner'
                                  ORDER BY id LIMIT 1""", (c["id"],)).fetchone()
        if owner:
            auth.sign_in(owner["id"], c["id"], c["name"])
    flash(f"{db.PROFILES[profile]['label']} template activated for this workspace "
          f"({'with demo data' if mode == 'demo' else 'clean start'}).", "success")
    return redirect(url_for("dashboard"))


@app.route("/settings", methods=["GET", "POST"])
def settings():
    c = company()
    if request.method == "POST":
        f = request.form
        conn().execute("""UPDATE companies SET name=?, email=?, phone=?, address=?, tax_name=?,
            tax_rate=?, fiscal_start=?, currency=?, symbol=? WHERE id=?""",
                       (f.get("name"), f.get("email"), f.get("phone"), f.get("address"), f.get("tax_name"),
                        float(f.get("tax_rate") or 15), f.get("fiscal_start"), f.get("currency") or "USD",
                        f.get("symbol") or "$", c["id"]))
        conn().commit()
        flash("Company settings saved.", "success")
        return redirect(url_for("settings"))
    users = conn().execute("SELECT * FROM users WHERE company_id=? ORDER BY id", (c["id"],)).fetchall()
    currencies = conn().execute("SELECT * FROM currencies ORDER BY code").fetchall()
    return render_template("settings.html", users=users, currencies=currencies, title="Settings")


@app.route("/settings/users", methods=["POST"])
def settings_user():
    c = company()
    f = request.form
    role = f.get("role") if f.get("role") in auth.ROLES else "accountant"
    email = (f.get("email") or "").strip().lower()
    if not email or not f.get("name"):
        flash("Name and email are required to invite a user.", "error")
        return redirect(url_for("settings"))
    if conn().execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
        flash("That email already has an account.", "error")
        return redirect(url_for("settings"))
    temp = secrets.token_urlsafe(6)
    conn().execute("""INSERT INTO users(company_id,name,email,role,status,password_hash,created_at)
                      VALUES(?,?,?,?,?,?,?)""",
                   (c["id"], f.get("name"), email, role, "Active",
                    auth.hash_password(temp), str(date.today())))
    conn().commit()
    flash(f"{f.get('name')} added as {auth.ROLES[role]}. Temporary password: {temp} "
          f"— share it securely, they can change it under Settings.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/users/<int:uid>/toggle", methods=["POST"])
def settings_user_toggle(uid):
    c = company()
    row = conn().execute("SELECT * FROM users WHERE id=? AND company_id=?", (uid, c["id"])).fetchone()
    if not row:
        return redirect(url_for("settings"))
    if row["id"] == g.ident.get("user_id"):
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("settings"))
    new = "Suspended" if row["status"] == "Active" else "Active"
    conn().execute("UPDATE users SET status=? WHERE id=?", (new, uid))
    conn().commit()
    flash(f"{row['name']} is now {new.lower()}.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/password", methods=["POST"])
def settings_password():
    f = request.form
    uid = g.ident.get("user_id")
    if not uid:
        flash("Demo visitors cannot change the shared password.", "error")
        return redirect(url_for("settings"))
    row = conn().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not auth.verify_password(row["password_hash"], f.get("current")):
        flash("Current password is incorrect.", "error")
        return redirect(url_for("settings"))
    newpw = f.get("new") or ""
    if len(newpw) < 8:
        flash("New password must be at least 8 characters.", "error")
        return redirect(url_for("settings"))
    if newpw != f.get("confirm"):
        flash("New passwords do not match.", "error")
        return redirect(url_for("settings"))
    conn().execute("UPDATE users SET password_hash=? WHERE id=?", (auth.hash_password(newpw), uid))
    conn().commit()
    flash("Password updated.", "success")
    return redirect(url_for("settings"))


@app.route("/reset-demo", methods=["POST"])
def reset_demo():
    c = company()
    db.rebuild_tenant(conn(), c["id"], c["industry"], demo=True)
    if g.ident.get("role") != "demo":
        owner = conn().execute("""SELECT * FROM users WHERE company_id=? AND role='owner'
                                  ORDER BY id LIMIT 1""", (c["id"],)).fetchone()
        if owner:
            auth.sign_in(owner["id"], c["id"], c["name"])
    flash("Demo data regenerated for this workspace.", "success")
    return redirect(url_for("dashboard"))


# ------------------------------------------------------------------ API for the AI panel
@app.route("/api/dashboard")
def api_dashboard():
    c = conn()
    d = A.dashboard(c, company())
    comp = dict(d["company"])
    return jsonify({
        "company": comp["name"], "industry": comp["industry"], "currency": comp["currency"],
        "today": str(date.today()),
        "revenue_ytd": round(d["pl_ytd"]["revenue"], 2),
        "expenses_ytd": round(d["pl_ytd"]["expense"], 2),
        "net_profit_ytd": round(d["pl_ytd"]["net"], 2),
        "net_margin_pct": round(d["pl_ytd"]["net_margin"], 1),
        "gross_margin_pct": round(d["pl_ytd"]["margin"], 1),
        "revenue_this_month": round(d["pl_month"]["revenue"], 2),
        "revenue_growth_pct": round(d["rev_growth"], 1),
        "cash": round(d["cash_total"], 2),
        "ar_outstanding": round(d["ar"], 2),
        "ap_outstanding": round(d["ap"], 2),
        "vat_payable": round(d["vat"]["payable"], 2),
        "overdue_invoices": d["overdue"]["c"], "overdue_value": round(d["overdue"]["v"], 2),
        "runway_months": round(d["runway"], 1),
        "health_score": d["health"], "current_ratio": round(d["current_ratio"], 2),
        "alerts": [{"title": a["title"], "detail": a["detail"]} for a in d["alerts"]],
        "top_customers": [{"name": r["name"], "value": round(r["v"], 2)} for r in d["top_customers"]],
        "monthly": [{k: v for k, v in s.items()} for s in d["series"]],
        "expense_mix": [{"name": m["name"], "value": m["value"], "pct": m["pct"]} for m in d["mix"]],
        "aging": {k: round(v, 2) for k, v in d["ar_buckets"].items()},
        "industry_metric": d["profile"]["metric"], "industry_value": round(d["tracked_sold"] or d["billed"], 0),
        "employees": d["employees"],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
