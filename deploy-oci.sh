#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  Tatmaq Books — one-command installer for a fresh Linux server
#  Tested against Oracle Linux 9 (Oracle Cloud Always Free) and Ubuntu 22/24.
#
#  Run it from inside the project folder:
#      bash deploy-oci.sh
#      bash deploy-oci.sh --with-https      # add free HTTPS via caddy + sslip.io
#
#  It is safe to run again: it repairs rather than duplicates.
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8000}"
WITH_HTTPS=0
[[ "${1:-}" == "--with-https" ]] && WITH_HTTPS=1

say()  { printf "\n\033[1;34m▸ %s\033[0m\n" "$1"; }
ok()   { printf "   \033[32m✓\033[0m %s\n" "$1"; }
die()  { printf "\n\033[31m✗ %s\033[0m\n" "$1" >&2; exit 1; }

[[ -f "$APP_DIR/app.py" ]] || die "app.py not found — run this from inside the project folder"

say "Tatmaq Books installer"
echo "   project : $APP_DIR"
echo "   app port: 127.0.0.1:$PORT (private — a web server or proxy faces the internet)"

# ---------------------------------------------------------------- 1. packages
say "Installing system packages"
SUDO=""
[[ $EUID -ne 0 ]] && SUDO="sudo"

if command -v dnf >/dev/null 2>&1; then
  $SUDO dnf install -y python3 python3-pip >/dev/null
  ok "python3 via dnf"
elif command -v apt-get >/dev/null 2>&1; then
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq python3 python3-venv python3-pip curl >/dev/null
  ok "python3 via apt"
else
  die "Neither dnf nor apt-get found — unsupported distribution"
fi

PYV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
echo "   python $PYV"
python3 -c 'import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)' \
  || die "Python 3.9 or newer is required (this server has $PYV)"

# ---------------------------------------------------------------- 2. virtualenv
say "Creating the Python environment"
cd "$APP_DIR"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv 2>/dev/null || {
    # Oracle Linux 9 sometimes ships python3 without ensurepip
    python3 -m venv --without-pip .venv
    curl -fsSL --max-time 60 https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    ./.venv/bin/python /tmp/get-pip.py -q
    rm -f /tmp/get-pip.py
  }
  ok "virtual environment created"
else
  ok "virtual environment already present"
fi
if [[ ! -x .venv/bin/pip ]]; then
  die "pip is missing from the virtual environment — run: sudo dnf install -y python3-pip, then re-run this script"
fi
./.venv/bin/pip install --upgrade pip -q
./.venv/bin/pip install -r requirements.txt -q
ok "Flask $(./.venv/bin/pip show flask | awk '/^Version/{print $2}') and gunicorn installed"

# ---------------------------------------------------------------- 3. secret
say "Generating the secret key"
mkdir -p "$APP_DIR/data"
SECRET_FILE="$APP_DIR/data/secret.key"
if [[ ! -f "$SECRET_FILE" ]]; then
  ./.venv/bin/python -c "import secrets;print(secrets.token_urlsafe(48))" > "$SECRET_FILE"
  chmod 600 "$SECRET_FILE"
  ok "new secret written to data/secret.key (chmod 600)"
else
  ok "keeping the existing secret"
fi
SECRET="$(cat "$SECRET_FILE")"

# ---------------------------------------------------------------- 4. database
say "Preparing the database"
export TATMAQ_DB="$APP_DIR/data/tatmaq.db"
if [[ ! -f "$TATMAQ_DB" ]]; then
  ./.venv/bin/python db.py
  ok "database created and seeded"
else
  ok "database already exists — left untouched"
fi
echo "   $TATMAQ_DB ($(du -h "$TATMAQ_DB" | cut -f1))"

# ---------------------------------------------------------------- 5. service
say "Installing the systemd service"
$SUDO tee /etc/systemd/system/tatmaq.service >/dev/null <<EOF
[Unit]
Description=Tatmaq Books — industry-adaptive accounting
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment="TATMAQ_SECRET=$SECRET"
Environment="TATMAQ_DB=$TATMAQ_DB"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$APP_DIR/.venv/bin/gunicorn app:app \\
    --bind 127.0.0.1:$PORT \\
    --workers 2 --threads 4 \\
    --timeout 60 --graceful-timeout 30 \\
    --access-logfile - --error-logfile -
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now tatmaq >/dev/null 2>&1 || $SUDO systemctl restart tatmaq
sleep 2
systemctl is-active --quiet tatmaq && ok "tatmaq.service is running" || {
  echo; $SUDO journalctl -u tatmaq -n 25 --no-pager
  die "the service failed to start — output above"
}

# ---------------------------------------------------------------- 6. health check
say "Checking the application answers"
for i in $(seq 1 15); do
  if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    ok "/healthz returned 200"
    break
  fi
  [[ $i -eq 15 ]] && { $SUDO journalctl -u tatmaq -n 25 --no-pager; die "no answer on port $PORT"; }
  sleep 1
done

# ---------------------------------------------------------------- 7. firewall
say "Opening the firewall"
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
  $SUDO firewall-cmd --permanent --add-service=http  >/dev/null 2>&1 || true
  $SUDO firewall-cmd --permanent --add-service=https >/dev/null 2>&1 || true
  $SUDO firewall-cmd --reload >/dev/null 2>&1 || true
  ok "firewalld: http and https opened"
else
  ok "firewalld not active — nothing to open here"
fi

# ---------------------------------------------------------------- 8. https
PUBLIC_IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
HTTPS_HOST=""
if [[ $WITH_HTTPS -eq 1 && -n "$PUBLIC_IP" ]]; then
  say "Setting up free HTTPS"
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64)  CADDY_ARCH=amd64 ;;
    aarch64) CADDY_ARCH=arm64 ;;
    *)       CADDY_ARCH="" ;;
  esac
  if [[ -z "$CADDY_ARCH" ]]; then
    echo "   unsupported architecture $ARCH — skipping HTTPS"
  elif ! command -v caddy >/dev/null 2>&1; then
    CADDY_VER="2.10.2"
    TMP="$(mktemp -d)"
    if curl -fsSL --max-time 90 -o "$TMP/caddy.tar.gz" \
        "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VER}/caddy_${CADDY_VER}_linux_${CADDY_ARCH}.tar.gz"; then
      tar -xzf "$TMP/caddy.tar.gz" -C "$TMP" caddy
      $SUDO install -m 755 "$TMP/caddy" /usr/local/bin/caddy
      ok "caddy ${CADDY_VER} installed"
    else
      echo "   could not download caddy — skipping HTTPS"
      CADDY_ARCH=""
    fi
    rm -rf "$TMP"
  fi

  # sslip.io turns 203-0-113-7.sslip.io into 203.0.113.7 — a real hostname,
  # so Let's Encrypt will issue a certificate, with no domain to buy.
  if [[ -n "$CADDY_ARCH" ]] && command -v caddy >/dev/null 2>&1; then
    HTTPS_HOST="$(echo "$PUBLIC_IP" | tr '.' '-').sslip.io"
    $SUDO mkdir -p /etc/caddy /var/lib/caddy
    $SUDO tee /etc/caddy/Caddyfile >/dev/null <<EOF
$HTTPS_HOST {
    encode gzip
    reverse_proxy 127.0.0.1:$PORT
}

http://$HTTPS_HOST {
    redir https://$HTTPS_HOST{uri} permanent
}
EOF
    $SUDO tee /etc/systemd/system/caddy.service >/dev/null <<'EOF'
[Unit]
Description=Caddy web server
After=network-online.target
Wants=network-online.target

[Service]
User=root
ExecStart=/usr/local/bin/caddy run --config /etc/caddy/Caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile
Restart=on-failure
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now caddy >/dev/null 2>&1 || $SUDO systemctl restart caddy
    sleep 3
    if systemctl is-active --quiet caddy; then
      ok "HTTPS enabled on https://$HTTPS_HOST"
    else
      echo "   caddy did not start — run: sudo journalctl -u caddy -n 30"
    fi
  fi
fi

# ---------------------------------------------------------------- 9. summary
PUBLIC_IP="${PUBLIC_IP:-$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo '<server-ip>')}"
cat <<EOF

  ════════════════════════════════════════════════════════════
   Tatmaq Books is installed and running
  ════════════════════════════════════════════════════════════

   Service      sudo systemctl status tatmaq
   Logs         sudo journalctl -u tatmaq -f
   Restart      sudo systemctl restart tatmaq
   Database     $TATMAQ_DB
   Secret       $SECRET_FILE

EOF

if [[ -n "$HTTPS_HOST" ]]; then
  echo "   Open         https://$HTTPS_HOST"
  echo "   First step   https://$HTTPS_HOST/register"
else
  echo "   Open         http://$PUBLIC_IP:$PORT   (only if the cloud firewall allows $PORT)"
  echo "   Tip          re-run with --with-https for a real certificate"
fi

cat <<'EOF'

   Reminder — the cloud's own firewall is separate from the
   server's. In the Oracle console open:
     Networking → VCN → Security Lists → Default Security List
     Add Ingress Rule: source 0.0.0.0/0, TCP, ports 80,443

EOF
