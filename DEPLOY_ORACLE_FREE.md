# Deploying Tatmaq Books on Oracle Cloud — free, permanently

Oracle's **Always Free** tier is the only major cloud that gives you a real
server that never expires. No credit card charge, no 30-day trial, no sleeping
container. What you are configuring is exactly right:

| Setting | Your value | Good? |
|---|---|---|
| Shape | `VM.Standard.A1.Flex` | ✅ ARM, always-free eligible |
| Size | 1 OCPU, 6 GB RAM | ✅ More than enough; the free allowance is 4 OCPU / 24 GB total |
| OS | Oracle Linux 9 | ✅ Supported by `deploy-oci.sh` |

This guide takes you from that console page to a live HTTPS site.

---

## Part 1 — finish the four console steps

### Step 1 · Basic information

- **Name** — `tatmaq-books`
- **Create in compartment** — leave as your root compartment
- **Availability domain** — AD-1 is fine

### Step 2 · Security

Leave the defaults. Shielded instances are optional and can slow the boot for
no benefit here.

### Step 3 · Networking  ← this is where people go wrong

- **Virtual cloud network** — `Create new virtual cloud network`
- **Subnet** — `Create new public subnet`
- **Assign a public IPv4 address** — **must be `Yes`** (it is the default when
  you chose a *public* subnet). Without it the server is unreachable.

### Step 4 · Storage

- **Boot volume** — leave `Specify a custom boot volume size` **unticked**.
  The default 50 GB is inside the free allowance, and the whole app plus a
  year of bookkeeping fits in under 1 GB.
- **Encryption** — leave default.

### Then press **Create**

While it provisions, the console shows **"Save private key"** — **download
that file**. It is shown once and cannot be recovered. If you lose it you must
destroy the instance and start again.

Provisioning takes 1–3 minutes. When the instance shows **Running**, copy its
**Public IP address** from the instance page.

---

## Part 2 — open the cloud firewall

Oracle blocks everything except SSH by default. This trips up nearly everyone.

1. **Networking → Virtual Cloud Networks →** your VCN
2. **Security Lists → Default Security List**
3. **Add Ingress Rules** and add one rule:

| Field | Value |
|---|---|
| Stateless | **No** (unticked) |
| Source Type | CIDR |
| Source CIDR | `0.0.0.0/0` |
| IP Protocol | **TCP** |
| Destination Port Range | `80,443` |

Save. This is separate from the server's own firewall, which the installer
handles for you.

---

## Part 3 — connect from Windows

Windows 10 and 11 already include `ssh`. Open **Command Prompt**.

First, lock down the key file's permissions — Windows refuses to use a key that
other users could read:

```cmd
icacls "%USERPROFILE%\Downloads\ssh-key-2026-11-16.key" /inheritance:r
icacls "%USERPROFILE%\Downloads\ssh-key-2026-11-16.key" /grant:r "%USERNAME%:R"
```

(Adjust the filename to the key you downloaded.)

Then connect — `opc` is the default user on Oracle Linux:

```cmd
ssh -i "%USERPROFILE%\Downloads\ssh-key-2026-11-16.key" opc@YOUR-PUBLIC-IP
```

Type `yes` when asked about the host fingerprint. You are in when the prompt
becomes `[opc@tatmaq-books ~]$`.

---

## Part 4 — copy the project up

On your **Windows** machine, in a *second* Command Prompt window (leave the SSH
session open):

```cmd
cd /d "%USERPROFILE%\Downloads"
scp -i "%USERPROFILE%\Downloads\ssh-key-2026-11-16.key" tatmaq-upload-ready.zip opc@YOUR-PUBLIC-IP:~/
```

That uploads the whole project — 157 KB, a few seconds.

Back in the **SSH window**:

```bash
sudo dnf install -y unzip
unzip -q tatmaq-upload-ready.zip
cd tatmaq-books
```

---

## Part 5 — install

```bash
bash deploy-oci.sh --with-https
```

The `--with-https` flag is worth using. It gives you a genuine
Let's Encrypt certificate on an address like
`https://129-213-45-7.sslip.io` — that is the server's IP with dashes,
because `sslip.io` is a free DNS service that resolves any such name straight
back to that IP. **No domain to buy, no certificate warnings.**

The script performs, in order:

1. Installs Python 3 and its tooling
2. Creates a virtual environment and installs Flask + gunicorn
3. Generates a random `TATMAQ_SECRET` into `data/secret.key` (mode 600)
4. Creates and seeds `data/tatmaq.db`
5. Installs `tatmaq.service` so the app starts on boot and restarts on crash
6. Waits for `/healthz` to answer, and stops with the log if it does not
7. Opens ports 80 and 443 on the server firewall
8. Installs Caddy and obtains the certificate

It is safe to run again — it repairs rather than duplicating.

---

## Part 6 — first run

Open the HTTPS address the script prints at the end.

1. Click **Create workspace** (`/register`)
2. Register your own company — this is a real, empty workspace
3. Sign in and you land on the Executive Dashboard

The demo accounts (`owner@tatmaqbooks.co.zw` / `demo1234`) exist on the same
install because the database seeds itself. **Before showing real clients,
remove the demo line from the sign-in page** — it is the link that fills the
form. Say the word and I will put it behind an environment variable.

---

## Day-to-day

```bash
sudo systemctl status tatmaq          # is it running?
sudo journalctl -u tatmaq -f          # live logs
sudo systemctl restart tatmaq         # after an update
```

### Updating the app

```bash
cd ~/tatmaq-books
# replace the changed files, then:
sudo systemctl restart tatmaq
```

### Backing up — do this weekly

```bash
sudo systemctl stop tatmaq
cp data/tatmaq.db ~/backup-$(date +%F).db
sudo systemctl start tatmaq
```

Then pull the copy down to your PC:

```cmd
scp -i "C:\Users\Admin\Downloads\ssh-key.key" opc@YOUR-PUBLIC-IP:~/backup-*.db .
```

A single file holds the entire business. Treat it like the till.

---

## Why this beats the paid options

| | Oracle Always Free | Railway Hobby |
|---|---|---|
| Cost | **$0 forever** | $5/month |
| Credit card | Required for verification, **never charged** | Charged monthly |
| Sleeps when idle | No | No |
| RAM | **6 GB** | 512 MB |
| Certificate | Free via Caddy | Included |

Oracle requires a card to verify you are a real person, and takes about $1 as a
temporary hold. That is the only money involved.

The 6 GB shape is generous — every industry tenant you sell can share this one
machine for a long time. When you outgrow it, the same `deploy-oci.sh` runs on
any Linux box.

---

## If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Site does not load at all | Security list rule missing | Part 2, ports `80,443` |
| `ssh` warns "permissions too open" | Windows ACL not tightened | Run the two `icacls` lines |
| `Permission denied (publickey)` | Wrong user | Use `opc@`, not `root@` |
| Service keeps restarting | Python error | `sudo journalctl -u tatmaq -n 50` |
| HTTPS never issues | Port 80 blocked | Open it in the security list, then `sudo systemctl restart caddy` |
| Forgot the secret | — | `cat ~/tatmaq-books/data/secret.key` |

---

*Written for Tatmaq Books v1.2 · Oracle Linux 9 · A1.Flex Always Free*
