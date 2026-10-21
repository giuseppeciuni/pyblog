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
  You      ──https──▶  nginx  ──▶  PyBlog (Python) on 127.0.0.1:8000  →  the administration
```

- Readers receive ready-made HTML pages, served by nginx: fast, and no
  program for anyone to attack.
- You log into the administration with your password, write and save:
  PyBlog regenerates the pages and nginx shows them right away.

**One address or two: choose now**

The administration can live in one of two places. The tutorial follows both;
where they differ, the steps say **Variant A** or **Variant B**.

| | Variant A: one address | Variant B: administration on its own address |
|---|---|---|
| Public site | `https://yourdomain.com` | `https://yourdomain.com` |
| Administration | `https://yourdomain.com/admin` | `https://admin.yourdomain.com` |
| DNS records | `@` and `www` | `@`, `www` and `admin` |
| nginx file | `nginx.conf.example` | `nginx.separate-admin.conf.example` |
| Good for | starting quickly, a site with no outside code | a site with analytics, ads or chat widgets (**recommended**) |

Why Variant B is safer: the code of outside services on the public pages
(Google Analytics, AdSense, a chat widget) runs on the site's address. If
the administration answers on that same address, that code could read what
you see while logged in, API keys included. On two addresses the browser
keeps them apart. You can start with A and move to B later (step 7.4).

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
| A | `admin` (**Variant B only**) | the server's IP address |

If the server also has an IPv6 address, add the same records as `AAAA`.

**Check** (it can take a few minutes, sometimes a few hours):

```bash
$ getent hosts yourdomain.com www.yourdomain.com
$ getent hosts admin.yourdomain.com     # Variant B only
```

Your server's IP must appear for every name.

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

The project contains both nginx configurations, ready to use: they only need
your domain and the site's folder. Follow **4.1 or 4.2**, not both.

### 4.1 Variant A: one address

```bash
$ sudo cp /opt/pyblog/nginx.conf.example /etc/nginx/sites-available/pyblog
$ sudo sed -i 's/mysite\.com/yourdomain.com/g; s#/path/to/pyblog/output#/opt/pyblog/output#' \
      /etc/nginx/sites-available/pyblog
$ sudo ln -s /etc/nginx/sites-available/pyblog /etc/nginx/sites-enabled/pyblog
$ sudo rm -f /etc/nginx/sites-enabled/default
$ sudo nginx -t && sudo systemctl reload nginx
```

What this configuration does: it serves the pages of `output/` directly,
passes only the administration routes (`/admin`, `/login`, `/config`,
`/edit`, `/media-library`...) to PyBlog, allows one login attempt per second and
shows the site's 404 page for addresses that do not exist.

### 4.2 Variant B: the administration at admin.yourdomain.com

```bash
$ sudo cp /opt/pyblog/nginx.separate-admin.conf.example /etc/nginx/sites-available/pyblog
$ sudo sed -i 's/mysite\.com/yourdomain.com/g; s#/path/to/pyblog/output#/opt/pyblog/output#' \
      /etc/nginx/sites-available/pyblog
$ sudo ln -s /etc/nginx/sites-available/pyblog /etc/nginx/sites-enabled/pyblog
$ sudo rm -f /etc/nginx/sites-enabled/default
$ sudo nginx -t && sudo systemctl reload nginx
```

The same `sed` also turns `admin.mysite.com` into `admin.yourdomain.com`.
The file has two blocks:

- **the public site** (`yourdomain.com`, `www.yourdomain.com`): only the
  static pages and the newsletter forms. The old addresses of the
  administration (`/admin`, `/login`...) are sent on to the new one;
- **the administration** (`admin.yourdomain.com`): everything goes to
  PyBlog, with the limit on login attempts. There is no list of routes to
  keep up to date: a new page of the administration works without touching
  nginx.

The separation is switched on in step 6.2, from the Settings. Until then the
administration answers on both addresses, so the order of the steps cannot
lock you out.

**Check (both variants):** `nginx -t` says `syntax is ok` and
`test is successful`. Open `http://yourdomain.com` in the browser: you see
the example site.

---

## Part 5 — Turn on HTTPS

Your password travels from the administration: HTTPS is a must.

**Variant A:**

```bash
$ sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

**Variant B** (one certificate for all three names):

```bash
$ sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com -d admin.yourdomain.com
```

Certbot asks for an email (for expiry notices), gets Let's Encrypt's free
certificate, adds HTTPS to the nginx configuration and the automatic switch
from `http` to `https`. Renewal is automatic.

> **Behind Cloudflare** (orange cloud) certbot cannot validate the domain
> this way. Use a Cloudflare *Origin Certificate* instead and point
> `ssl_certificate` / `ssl_certificate_key` at it in both server blocks; set
> the SSL mode to *Full (strict)*.

**Check:**

```bash
$ sudo certbot renew --dry-run
```

must end with `Congratulations, all simulated renewals succeeded`. Then open
`https://yourdomain.com`: the padlock is there.

---

## Part 6 — First login and first settings

### 6.1 Log in

Open **`https://yourdomain.com/admin`** (Variant A) or
**`https://admin.yourdomain.com/admin`** (Variant B) and enter the password
of step 2.3.
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

**Variant B only — switch on the separate address.** Still in **Site and
author**, write `https://admin.yourdomain.com` in **Address of the
administration** and save. Before saving, PyBlog checks that the address
really leads to it (if nginx or the certificate is not ready yet, it says so
and saves nothing); then it takes you to the new address, where you log in
again. From now on:

- `https://yourdomain.com/admin` sends you on to `https://admin.yourdomain.com`;
- the administration's address does not show the site's pages.

If you ever lock yourself out, the administration always answers on the
server itself: from your computer `ssh -L 8000:127.0.0.1:8000 user@SERVER-IP`,
then open `http://localhost:8000/admin` and empty the field.

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
   written, use **Import from Word (.docx)**: headings, lists, tables and
   pictures arrive in the editor, and the editor shows the same spacing the
   page will have.
3. Pictures: click one to resize it, align it, or give it an **alternative
   text and caption** (the button appears on the picture). The alternative
   text is what Google Images reads.
4. **Details** opens the panel with the description, tags, series, cover and
   translation. **Widen** gives the text the whole width of the screen.
5. In the strip at the top: **Save draft** to keep it to yourself,
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

then `sudo systemctl restart pyblog`. In **Settings → Automatic translation** choose
the service and leave the key field empty. Tip: a key used only for the
blog, with a monthly spending cap set in the service's console.

### 6.6 (Recommended) Email and password recovery

If you forget your password, PyBlog can send you a link to choose a new
one. It needs an SMTP account (your mail provider's, or Brevo, Mailgun,
Amazon SES). In **Settings → Email and password recovery**:

- in **Mail server** fill in sender, SMTP server, port, security and
  username, then click **Send a test email**;
- in **Password recovery** write the **password recovery email**: the link
  goes there.

Put the SMTP password in `/etc/pyblog.env` as `PYBLOG_SMTP_PASSWORD=...`
(then `sudo systemctl restart pyblog`). The same mail server also serves
the newsletter.

**Check:** log out, click **Forgot your password?** on the login page and
type the recovery email: the link arrives in a few seconds.

### 6.7 (Optional) The newsletter

To let readers subscribe and send them an email for every new article you
need the mail server of step 6.6. In **Settings → Newsletter** tick **Turn
on the newsletter**, choose where the form shows and save. The nginx configuration of step 4.1 or 4.2 already
passes the form to PyBlog. All the details in chapter 8b of the manual.

---

## Part 7 — Keep it healthy

### 7.1 Backups

From the menu, **Download the backup** gives you a `.zip` file with
articles, images and settings; **Restore a backup** puts one back (it checks
the whole file first and saves the current state, so you can change your
mind). PyBlog also keeps a few automatic backups, made before every
restore and every update. For an automatic backup every night on the
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

**From the menu (easiest):** **Updates** shows the installed version and
what is new. **Update now** saves an automatic backup, downloads the new
code, tries it in a separate process (and goes back by itself if it does
not start), restarts PyBlog and rebuilds the site. Then you log in again.

**By hand:**

```bash
$ cd /opt/pyblog
$ sudo -u pyblog git pull
$ sudo systemctl restart pyblog
$ sudo -u pyblog python3 pyblog.py build
```

All three commands, in this order. **The restart is not optional:** PyBlog
keeps the pages of the administration in memory, while the CSS is read from
disk. After a `git pull` without a restart the administration mixes old
pages with the new style and looks completely wrong.

Articles, settings and password are left untouched. If a new version changes
`nginx.conf.example` or `nginx.separate-admin.conf.example`, compare it with
your file in `/etc/nginx/sites-available/pyblog` (the CHANGELOG says so).

### 7.3 If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| **502 Bad Gateway** on `/admin` | PyBlog is off | `sudo systemctl restart pyblog`, then `sudo journalctl -u pyblog -n 50 --no-pager` |
| **403 Forbidden** on the site | nginx cannot read `output/` | `sudo chmod 755 /opt/pyblog /opt/pyblog/output` |
| The administration with no colours or buttons | nginx does not pass `/admin-static/` to PyBlog | redo step 4.1 or 4.2 with the new configuration |
| After an update the administration looks completely wrong | PyBlog was not restarted after `git pull` | `sudo systemctl restart pyblog` |
| Variant B: "does not answer as PyBlog" when saving the address | nginx or the certificate for `admin.` is not ready | check steps 1.2, 4.2 and 5, then save again |
| Variant B: locked out of the administration | the address saved is wrong | `ssh -L 8000:127.0.0.1:8000 user@SERVER-IP`, open `http://localhost:8000/admin`, empty **Address of the administration** |
| An administration page answers 404 | a new route is missing from the nginx configuration | compare `/etc/nginx/sites-available/pyblog` with `nginx.conf.example` |
| Certbot fails | the domain does not point at the server yet | redo the check of step 1.2 and try again |
| "Too many attempts" at login | protection against password guessing | wait: the lock affects only your address and grows with each mistake |
| Forgotten password | — | **Forgot your password?** on the login page sends a link to the recovery email (Settings → Email and password recovery, step 6.6). Without it: `cd /opt/pyblog && sudo -u pyblog python3 pyblog.py password` |
| Changes do not show | the browser shows the old copy | hard reload (Ctrl+F5); from the menu **Rebuild the site** recreates every page |

### 7.4 Moving from one address to two

Started with Variant A and now the site has analytics or ads? Moving costs
five minutes and nothing is lost:

1. DNS: add the `admin` record of step 1.2 and wait for the check.
2. nginx: do step 4.2 (it replaces the file of 4.1).
3. HTTPS: run the Variant B command of Part 5; certbot adds `admin.` to the
   certificate.
4. Settings: the Variant B paragraph of step 6.2.

Old bookmarks of the administration keep working: they are sent on to the
new address.

---

## What next?

The **[MANUAL.en.md](MANUAL.en.md)** has everything else: every section of the
Settings, external code (Analytics, AdSense, widgets) with the point chosen
by clicking on the page, the cookie banner, comments, analytics with Umami,
translation, importing from Word and Markdown, the other installations (on
your computer, with Docker, without Python on the server), every
`config.json` key and troubleshooting.
