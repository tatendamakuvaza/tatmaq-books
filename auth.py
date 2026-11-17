"""Tatmaq Books — authentication, sessions, roles and shareable demo links."""
import os
from functools import wraps

from flask import abort, flash, g, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from db import connect

SECRET = os.environ.get("TATMAQ_SECRET", "tatmaq-books-demo-key-change-in-production")
_serializer = URLSafeTimedSerializer(SECRET, salt="tatmaq-identity")

SESSION_TTL = 60 * 60 * 24 * 14        # 14 days
DEMO_TTL = 60 * 60 * 24 * 7            # 7-day shareable demo links

ROLES = {
    "owner": "Owner / Admin",
    "accountant": "Accountant",
    "sales": "Sales Clerk",
    "auditor": "Auditor (read-only)",
    "demo": "Demo visitor",
}

# who may POST (create/modify data)
WRITE_ROLES = {"owner", "accountant", "sales", "demo"}
# who may reach system settings / industry setup
SYSTEM_ROLES = {"owner", "accountant", "demo"}

# POST endpoints a sales clerk may not touch
SALES_BLOCKED = (
    "bill", "payroll", "asset", "journal", "setup", "settings", "reset",
    "inventory_adjust", "item_new", "accounts_page",
)


def hash_password(pw):
    return generate_password_hash(pw)


def verify_password(pw_hash, pw):
    try:
        return check_password_hash(pw_hash or "", pw or "")
    except Exception:
        return False


def make_token(company_id, user_id, role, kind="session", ttl=None, label=""):
    payload = {"cid": company_id, "uid": user_id, "role": role, "kind": kind, "label": label}
    return _serializer.dumps(payload)


def read_token(token, max_age=None):
    if not token:
        return None
    try:
        return _serializer.loads(token, max_age=max_age or SESSION_TTL)
    except SignatureExpired:
        return None
    except BadSignature:
        return None
    except Exception:
        return None


def make_demo_token(company_id):
    """Magic link that opens a seeded workspace read/write (demo data only)."""
    return make_token(company_id, None, "demo", kind="demo", ttl=DEMO_TTL)


def read_demo_token(token):
    payload = read_token(token, max_age=DEMO_TTL)
    if not payload or payload.get("kind") != "demo":
        return None
    return payload


def load_user(uid):
    if not uid:
        return None
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE id=? AND status='Active'", (uid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def resolve_identity():
    """Return (identity_dict, source) where source is 'session' or 'token'."""
    demo_cid = session.get("demo_cid")
    if demo_cid:
        conn = connect()
        try:
            comp = conn.execute("SELECT * FROM companies WHERE id=?", (demo_cid,)).fetchone()
        finally:
            conn.close()
        if comp:
            return ({"user_id": None, "company_id": comp["id"], "role": "demo",
                     "name": "Demo visitor", "email": "demo@tatmaqbooks.co.zw",
                     "source": "session", "company_name": comp["name"]}, "session")
        session.pop("demo_cid", None)

    uid = session.get("uid")
    if uid:
        u = load_user(uid)
        if u:
            return ({"user_id": u["id"], "company_id": u["company_id"], "role": u["role"],
                     "name": u["name"], "email": u["email"], "source": "session",
                     "company_name": session.get("company_name", "")}, "session")

    token = request.values.get("s") or request.headers.get("X-Tatmaq-Token")
    payload = read_token(token)
    if payload:
        if payload.get("kind") == "demo":
            conn = connect()
            try:
                comp = conn.execute("SELECT * FROM companies WHERE id=?",
                                    (payload.get("cid"),)).fetchone()
            finally:
                conn.close()
            if not comp:
                return (None, None)
            return ({"user_id": None, "company_id": comp["id"], "role": "demo",
                     "name": "Demo visitor", "email": "demo@tatmaqbooks.co.zw",
                     "source": "token", "company_name": comp["name"]}, "token")
        u = load_user(payload.get("uid"))
        if u:
            return ({"user_id": u["id"], "company_id": u["company_id"], "role": u["role"],
                     "name": u["name"], "email": u["email"], "source": "token",
                     "company_name": session.get("company_name", "")}, "token")
    return (None, None)


def sign_in(user_id, company_id, company_name="", remember=True):
    session.permanent = remember
    session["uid"] = user_id
    session["company_name"] = company_name


def sign_out():
    session.clear()


def permissions(role):
    return {
        "write": role in WRITE_ROLES,
        "system": role in SYSTEM_ROLES,
        "sales": role in {"owner", "accountant", "sales", "demo"},
        "purchases": role in {"owner", "accountant", "demo"},
        "operations": role in {"owner", "accountant", "demo"},
        "accounting": role in {"owner", "accountant", "auditor", "demo"},
        "role_label": ROLES.get(role, role),
        "is_demo": role == "demo",
        "full_view": role in {"owner", "accountant", "auditor", "demo"},
    }


def gate_post(role, endpoint):
    """Raise 403 when a role may not perform this POST."""
    if role not in WRITE_ROLES:
        return False
    if role == "sales" and endpoint and any(k in endpoint for k in SALES_BLOCKED):
        return False
    return True
