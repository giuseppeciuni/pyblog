# PyBlog — Tutorial: from an empty server to a site online

*In italiano: [TUTORIAL.md](TUTORIAL.md)*

This tutorial takes you, one command at a time, from a freshly created
Ubuntu server to a blog online with HTTPS, which you write from the browser.
Follow the steps in order: after each one a **Check** tells you whether it
all went well.

Everything you do not need to get started (the other ways to install it,
every setting, every `config.json` key) is in the **[MANUAL.en.md](MANUAL.en.md)**.

---

## Before you start

**What you get at the end**

```
  Readers  ──https──▶  nginx  ──▶  static pages in /opt/pyblog/output
  You      ──https──▶  nginx  ──▶  PyBlog (Python) on 127.0.0.1:8000  →  /admin
```

- Readers receive ready-made HTML pages, served by nginx: fast, and no
  program for anyone to attack.
- You log into `https://yourdomain.com/admin` with your password, write and
  save: PyBlog regenerates the pages and nginx shows them right away.

**What you need**

- A server with **Ubuntu 22.04 or 24.04** (the smallest VPS will do: 1 CPU,
  1 GB of RAM) and a user with `sudo`.
- A **domain** (in this tutorial `yourdomain.com`) whose DNS records you can
  edit.
- About half an hour.

> In every command replace **`yourdomain.com`** with your domain. Lines
> starting with `$` are commands to type (without the `$`).

---

## Part 1 — Prepare the server

### 1.1 Connect and update

From your computer:

```bash
$ ssh user@SERVER-IP-ADDRESS
```

Then, on the server:

```bash
$ sudo apt update && sudo apt upgrade -y
```

### 1.2 Point the domain at the server

In your registrar's panel (where you bought the domain) create two DNS
records:

| Type | Name | Value |
|---|---|---|
| A | `@` (that is `yourdomain.com`) | the server's IP address |
| A | `www` | the server's IP address |

If the server also has an IPv6 address, add two identical `AAAA` records.

**Check** (it can take a few minutes, sometimes a few hours):

```bash
$ getent hosts yourdomain.com www.yourdomain.com
```

Your server's IP must appear, twice.

### 1.3 Turn on the firewall

```bash
$ sudo apt install -y ufw
$ sudo ufw allow OpenSSH
$ sudo ufw allow 80/tcp
$ sudo ufw allow 443/tcp
$ sudo ufw enable
```

**Check:** `sudo ufw status` shows `22`, `80` and `443` as `ALLOW`. PyBlog's
port 8000 must **not** be opened: only nginx talks to it, from inside.

### 1.4 Install the programs

```bash
$ sudo apt install -y python3 git nginx certbot python3-certbot-nginx
```

PyBlog needs nothing else: no database, no `pip install`.

**Check:** `python3 --version` must say 3.8 or later (Ubuntu 22.04 has 3.10,
24.04 has 3.12).

---

## Part 2 — Install PyBlog

### 2.1 Create the blog's user

PyBlog runs as a user of its own, which can do nothing else on the server:

```bash
$ sudo useradd --system --home /opt/pyblog --shell /usr/sbin/nologin pyblog
```

### 2.2 Download PyBlog

```bash
$ sudo git clone https://github.com/giuseppeciuni/pyblog.git /opt/pyblog
$ sudo chown -R pyblog:pyblog /opt/pyblog
```

If you have PyBlog in a folder on your computer rather than on GitHub, copy
it to the server and then give it to the `pyblog` user:

```bash
# on your computer
$ rsync -a --exclude output/ pyblog/ user@SERVER-IP:/tmp/pyblog/
# on the server
$ sudo mv /tmp/pyblog /opt/pyblog && sudo chown -R pyblog:pyblog /opt/pyblog
```

**Check:** `ls /opt/pyblog` shows `pyblog.py`, `core`, `templates`, `static`.

### 2.3 Choose the administration password

```bash
$ cd /opt/pyblog
$ sudo -u pyblog python3 pyblog.py password
$ sudo chmod 600 /opt/pyblog/admin_password.txt
```

The program asks for it twice and stores it hashed (only its "fingerprint",
never the password). Make it long: a sentence works well.

> Do it now, from the terminal. If you open the site before there is a
> password, the `/admin` page offers to create one to whoever gets there
> first.

### 2.4 Build the site for the first time

```bash
$ sudo -u pyblog python3 pyblog.py build
```

**Check:** `ls /opt/pyblog/output` shows `index.html`, `posts`,
`sitemap.xml`, `404.html` and the other files of the site.

---

## Part 3 — Run the editor as a service

The editor (the `/admin` area) is a Python program that must stay on and
start again by itself after a server reboot: we hand it to `systemd`.

### 3.1 Prepare the file of secret keys

The keys of the AI and translation services, if you ever use them, go in a
file only root can read, not in the project. Create it empty:

```bash
$ sudo install -m 600 -o root -g root /dev/null /etc/pyblog.env
```

### 3.2 Install and start the service

```bash
$ sudo cp /opt/pyblog/pyblog.service.example /etc/systemd/system/pyblog.service
$ sudo systemctl daemon-reload
$ sudo systemctl enable --now pyblog
```

The example file is already set for `/opt/pyblog` and the `pyblog` user; it
makes PyBlog listen **only** on `127.0.0.1:8000` and lets it write only in
its own folder.

**Check:**

```bash
$ systemctl status pyblog --no-pager
$ curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/login
```

The first must say `active (running)`, the second `200`. If not, see why
with `sudo journalctl -u pyblog -n 50 --no-pager`.

---

## Part 4 — Publish the site with nginx

### 4.1 Install PyBlog's configuration

The project contains a ready-made nginx configuration: it only needs your
domain and the site's folder.

```bash
$ sudo cp /opt/pyblog/nginx.conf.example /etc/nginx/sites-available/pyblog
$ sudo sed -i 's/mysite\.com/yourdomain.com/g; s#/path/to/pyblog/output#/opt/pyblog/output#' \
      /etc/nginx/sites-available/pyblog
$ sudo ln -s /etc/nginx/sites-available/pyblog /etc/nginx/sites-enabled/pyblog
$ sudo rm -f /etc/nginx/sites-enabled/default
$ sudo nginx -t && sudo systemctl reload nginx
```

What this configuration does: it serves the pages of `output/` directly,
passes only the administration routes (`/admin`, `/login`, `/config`...) to
PyBlog, allows one login attempt per second and shows the site's 404 page
for addresses that do not exist.

**Check:** `nginx -t` says `syntax is ok` and `test is successful`. Open
`http://yourdomain.com` in the browser: you see the example site.

---

## Part 5 — Turn on HTTPS

Your password travels from the administration: HTTPS is a must.

```bash
$ sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Certbot asks for an email (for expiry notices), gets Let's Encrypt's free
certificate, adds HTTPS to the nginx configuration and the automatic switch
from `http` to `https`. Renewal is automatic.

**Check:**

```bash
$ sudo certbot renew --dry-run
```

must end with `Congratulations, all simulated renewals succeeded`. Then open
`https://yourdomain.com`: the padlock is there.

---

## Part 6 — First login and first settings

### 6.1 Log in

Open **`https://yourdomain.com/admin`** and enter the password of step 2.3.
On the left is the menu: Articles, New article, Settings, and at the bottom
the tools and your account. On a phone the menu is a bar at the bottom of
the screen. The administration speaks Italian or English: the language item
in the menu switches it.

### 6.2 The site and the domain (important)

Go to **Settings → Site and author** and fill in:

- **Site title** and **Subtitle**;
- **Site domain**: `https://yourdomain.com`, with no trailing slash. The
  sitemap, the canonical addresses and the social previews come from here:
  left at the example value, Google indexes nothing;
- **Main site language**: the language you write in;
- in **Who writes**: your name and, if you like, job title, a short bio and
  your profiles (GitHub, LinkedIn...), one per line.

Click **Save and update the site** at the bottom of the page.

### 6.3 The first page

- **Homepage**: write the introduction with the visual editor and choose
  whether it goes in the sidebar or above the articles.
- **Biography** and **Projects** (optional): turn them on with their
  checkbox, write the biography, add a card per project and choose for each
  where it shows on the homepage.

Every section is saved with the same button at the bottom; if you leave with
unsaved changes, the browser asks you first.

### 6.4 The first article

1. **New article** in the menu.
2. Write the title and the text. For a Word document that is already
   written, use **Import from Word (.docx)**.
3. In the right-hand column: **Save draft** to keep it to yourself,
   **Preview** to see it as it is, **Publish** to put it online.

**Check:** open `https://yourdomain.com`: the article is there, at the top of
the list.

### 6.5 (Optional) The AI features

Automatic translation, suggestions for the description and the preview, SEO
analysis: they need the key of a service (Anthropic, OpenAI, DeepSeek, DeepL
or Google). Put it in the file of step 3.1, not in the Settings:

```bash
$ sudo nano /etc/pyblog.env
```

with a line like this one (the name depends on the service:
`PYBLOG_LLM_API_KEY` for Anthropic, `PYBLOG_OPENAI_API_KEY`,
`PYBLOG_DEEPSEEK_API_KEY`, `PYBLOG_DEEPL_API_KEY`, `PYBLOG_GOOGLE_API_KEY`):

```
PYBLOG_LLM_API_KEY=sk-ant-...
```

then `sudo systemctl restart pyblog`. In **Settings → Translation** choose
the service and leave the key field empty. Tip: a key used only for the
blog, with a monthly spending cap set in the service's console.

### 6.6 (Optional) The newsletter

To let readers subscribe and send them an email for every new article you
need an SMTP account (your mail provider's, or Brevo, Mailgun, Amazon SES).
In **Settings → Newsletter** tick **Turn on the newsletter**, fill in
**Sending the emails**, click **Send a test email** and save. Put the SMTP
password in `/etc/pyblog.env` as `PYBLOG_SMTP_PASSWORD=...` (then `sudo
systemctl restart pyblog`). The nginx configuration of step 4.1 already
passes the form to PyBlog. All the details in chapter 8b of the manual.

---

## Part 7 — Keep it healthy

### 7.1 Backups

From the menu, **Download the backup** gives you a `.zip` file with
articles, images and settings. For an automatic backup every night on the
server:

```bash
$ sudo crontab -e
```

and add these two lines:

```
0 3 * * * tar -czf /var/backups/pyblog-$(date +\%F).tar.gz --ignore-failed-read -C /opt/pyblog posts config.json admin_password.txt subscribers.json output/media
30 3 * * * find /var/backups -name 'pyblog-*.tar.gz' -mtime +30 -delete
```

Every night at 3 a dated archive; the ones older than 30 days go away. Now
and then copy an archive off the server too.

**Restoring** an archive:

```bash
$ sudo systemctl stop pyblog
$ sudo tar -xzf /var/backups/pyblog-YYYY-MM-DD.tar.gz -C /opt/pyblog
$ sudo chown -R pyblog:pyblog /opt/pyblog
$ cd /opt/pyblog && sudo -u pyblog python3 pyblog.py build
$ sudo systemctl start pyblog
```

### 7.2 Updating PyBlog

```bash
$ cd /opt/pyblog
$ sudo -u pyblog git pull
$ sudo systemctl restart pyblog
$ sudo -u pyblog python3 pyblog.py build
```

Articles, settings and password are left untouched. If a new version changes
`nginx.conf.example`, compare it with your file in
`/etc/nginx/sites-available/pyblog` (the CHANGELOG says so).

### 7.3 If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| **502 Bad Gateway** on `/admin` | PyBlog is off | `sudo systemctl restart pyblog`, then `sudo journalctl -u pyblog -n 50 --no-pager` |
| **403 Forbidden** on the site | nginx cannot read `output/` | `sudo chmod 755 /opt/pyblog /opt/pyblog/output` |
| The administration with no colours or buttons | nginx does not pass `/admin-static/` to PyBlog | redo step 4.1 with the new configuration |
| An administration page answers 404 | a new route is missing from the nginx configuration | compare `/etc/nginx/sites-available/pyblog` with `nginx.conf.example` |
| Certbot fails | the domain does not point at the server yet | redo the check of step 1.2 and try again |
| "Too many attempts" at login | protection against password guessing | wait: the lock affects only your address and grows with each mistake |
| Forgotten password | — | `cd /opt/pyblog && sudo -u pyblog python3 pyblog.py password` |
| Changes do not show | the browser shows the old copy | hard reload (Ctrl+F5); from the menu **Rebuild the site** recreates every page |

---

## What next?

The **[MANUAL.en.md](MANUAL.en.md)** has everything else: every section of the
Settings, external code (Analytics, AdSense, widgets) with the point chosen
by clicking on the page, the cookie banner, comments, analytics with Umami,
translation, importing from Word and Markdown, the other installations (on
your computer, with Docker, without Python on the server), every
`config.json` key and troubleshooting.
