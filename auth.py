"""
auth.py — Simple login gate for Project Goldstein dashboard.

Sits in front of the Dash app via Flask routes.
Buyers get a username + API key. Keys are set via environment variables.

Usage: imported by dashboard.py — no changes needed to Dash layout.

Env vars:
    GOLDSTEIN_USERS = "buyer1:key_abc123,buyer2:key_xyz789"
    GOLDSTEIN_SECRET = "any-long-random-string-for-session-signing"
"""

import os
import hashlib
from functools import wraps
from flask import request, session, redirect, url_for, Response

# ── Load users from env ───────────────────────────────────────────────────────

def _load_users():
    raw = os.getenv("GOLDSTEIN_USERS", "admin:goldstein2026")
    users = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            u, k = entry.split(":", 1)
            users[u.strip()] = k.strip()
    return users

USERS = _load_users()

# ── Login page HTML ───────────────────────────────────────────────────────────

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Project Goldstein — Access</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #07071a;
    font-family: Inter, Arial, sans-serif;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .card {
    background: #0e0e28;
    border: 1px solid #1e1e42;
    border-top: 3px solid #58A6FF;
    border-radius: 12px;
    padding: 40px 44px;
    width: 380px;
  }
  .logo {
    color: #58A6FF;
    font-size: 11px;
    letter-spacing: 3px;
    font-weight: 600;
    margin-bottom: 6px;
  }
  h1 {
    color: #e8e8f0;
    font-size: 20px;
    font-weight: 600;
    margin-bottom: 4px;
  }
  .sub {
    color: #6b6b8a;
    font-size: 11px;
    margin-bottom: 28px;
    letter-spacing: 0.3px;
  }
  label {
    color: #6b6b8a;
    font-size: 10px;
    letter-spacing: 1.2px;
    display: block;
    margin-bottom: 6px;
    text-transform: uppercase;
  }
  input {
    width: 100%;
    background: #12122e;
    border: 1px solid #1e1e42;
    border-radius: 6px;
    color: #e8e8f0;
    font-family: Inter, Arial, sans-serif;
    font-size: 13px;
    padding: 10px 14px;
    margin-bottom: 16px;
    outline: none;
    transition: border 0.15s;
  }
  input:focus { border-color: #58A6FF; }
  button {
    width: 100%;
    background: #1e1e50;
    border: 1px solid #58A6FF;
    border-radius: 6px;
    color: #58A6FF;
    font-family: Inter, Arial, sans-serif;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 11px;
    cursor: pointer;
    transition: all 0.15s;
    margin-top: 4px;
  }
  button:hover { background: #252560; }
  .error {
    color: #F85149;
    font-size: 11px;
    margin-top: 12px;
    text-align: center;
  }
  .footer {
    color: #3a3a5a;
    font-size: 9px;
    text-align: center;
    margin-top: 24px;
    letter-spacing: 0.5px;
  }
</style>
</head>
<body>
<div class="card">
  <div class="logo">◈ PROJECT GOLDSTEIN</div>
  <h1>Signal Access</h1>
  <p class="sub">Geopolitical Risk Premium Score Engine</p>
  <form method="POST" action="/login">
    <label>Username</label>
    <input type="text" name="username" autocomplete="username" required>
    <label>API Key</label>
    <input type="password" name="apikey" autocomplete="current-password" required>
    <button type="submit">ACCESS DASHBOARD →</button>
    {error}
  </form>
  <div class="footer">Project Goldstein · Confidential · Not for redistribution</div>
</div>
</body>
</html>
"""

# ── Flask route registration ──────────────────────────────────────────────────

def register_auth(server, secret_key=None):
    """
    Call this with the Flask server underlying the Dash app.
    Adds /login and /logout routes and protects all other routes.
    """
    server.secret_key = secret_key or os.getenv(
        "GOLDSTEIN_SECRET", "goldstein-default-secret-change-in-prod"
    )

    @server.route("/login", methods=["GET", "POST"])
    def login():
        error = ""
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            apikey   = request.form.get("apikey", "").strip()
            if USERS.get(username) == apikey:
                session["authenticated"] = True
                session["user"] = username
                return redirect("/")
            error = '<p class="error">Invalid credentials. Contact pns5158@psu.edu</p>'
        return LOGIN_HTML.format(error=error)

    @server.route("/logout")
    def logout():
        session.clear()
        return redirect("/login")

    @server.before_request
    def require_login():
        # Allow login page and static assets through without auth
        if request.path.startswith("/login"):
            return None
        if request.path.startswith("/_dash") or request.path.startswith("/assets"):
            return None
        if not session.get("authenticated"):
            return redirect("/login")
        return None
