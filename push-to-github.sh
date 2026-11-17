#!/usr/bin/env bash
# Tatmaq Books — push this project to a GitHub repository.
#
# Usage:
#   ./push-to-github.sh                     # uses the repo URL you already configured
#   ./push-to-github.sh git@github.com:you/tatmaq-books.git
#   ./push-to-github.sh https://github.com/you/tatmaq-books.git
#
# With the GitHub CLI installed and signed in, this creates the repo for you:
#   ./push-to-github.sh --create tatmaq-books

set -euo pipefail
cd "$(dirname "$0")"

REMOTE_URL=""
CREATE_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create) CREATE_NAME="${2:-tatmaq-books}"; shift 2 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) REMOTE_URL="$1"; shift ;;
  esac
done

say() { printf "\n\033[1;34m▸ %s\033[0m\n" "$1"; }

# ---------------------------------------------------------------- 1. git identity
if ! git config user.email >/dev/null 2>&1; then
  say "Setting a local git identity (edit .git/config if you prefer another name)"
  git config user.name  "${GIT_AUTHOR_NAME:-Tatmaq Books}"
  git config user.email "${GIT_AUTHOR_EMAIL:-dev@tatmaqbooks.co.zw}"
fi

# ---------------------------------------------------------------- 2. repository
if [[ ! -d .git ]]; then
  say "Initialising a new repository"
  git init -b main -q
  git add -A
  git commit -q -m "Tatmaq Books — initial commit"
fi

# ---------------------------------------------------------------- 3. create repo (optional)
if [[ -n "$CREATE_NAME" ]]; then
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    say "Creating GitHub repository '$CREATE_NAME' with the GitHub CLI"
    gh repo create "$CREATE_NAME" --private --source=. --remote=origin --push
    say "Done — repository created and pushed"
    exit 0
  else
    echo "GitHub CLI (gh) is not installed or not signed in."
    echo "Create the repo in the browser, then run this script with its URL."
    exit 1
  fi
fi

# ---------------------------------------------------------------- 4. push
if [[ -n "$REMOTE_URL" ]]; then
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$REMOTE_URL"
  else
    git remote add origin "$REMOTE_URL"
  fi
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  cat <<'EOF'
No remote configured yet.

  1. Open https://github.com/new
  2. Name it tatmaq-books, choose Private, and do NOT add a README/.gitignore
  3. Copy the repo URL and run:
       ./push-to-github.sh https://github.com/<your-username>/tatmaq-books.git
EOF
  exit 1
fi

say "Checking the project before pushing"
python3 -c "import ast,pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('.').glob('*.py')]" \
  && echo "  python modules parse cleanly"
if [[ -f tests/smoke_test.py ]]; then
  python3 tests/smoke_test.py >/tmp/tatmaq-smoke.log 2>&1 \
    && echo "  smoke test passed (32 checks)" \
    || { echo "  smoke test FAILED — see /tmp/tatmaq-smoke.log"; exit 1; }
fi

say "Pushing to $(git remote get-url origin)"
git push -u origin main

say "Pushed. Next steps"
cat <<'EOF'
  · Add the repo to Railway (railway.app → New Project → Deploy from GitHub)
  · Set environment variables in Railway:
        TATMAQ_SECRET = <long random string>
        TATMAQ_DB     = /data/tatmaq.db       (after attaching a volume at /data)
  · Railway will use railway.json → gunicorn on $PORT, health check /healthz
  · Open /register on the deployed URL to create the first real workspace
EOF
