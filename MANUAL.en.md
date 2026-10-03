# PyBlog — Manual

*In italiano: [MANUALE.md](MANUALE.md)*

Everything about PyBlog: how it works, every way to install it, every page
of the administration, every setting and every `config.json` key.

To put a site online the first time, the shortest road is the
**[TUTORIAL.en.md](TUTORIAL.en.md)**: from an empty Ubuntu server to the site
with HTTPS, step by step. This manual is the reference to look things up
afterwards.

The labels quoted here are the ones of the administration in English; the
administration can be switched to Italian from its menu.

## Contents

1. [What PyBlog is and how it works](#1-what-pyblog-is-and-how-it-works)
2. [Installing and running](#2-installing-and-running)
3. [The administration](#3-the-administration)
4. [Writing an article: the editor](#4-writing-an-article-the-editor)
5. [The Settings, section by section](#5-the-settings-section-by-section)
6. [External code: analytics, ads, widgets](#6-external-code-analytics-ads-widgets)
7. [The cookie banner](#7-the-cookie-banner)
8. [Comments](#8-comments)
   - [8b. Newsletter](#8b-newsletter)
9. [Visit statistics](#9-visit-statistics)
10. [Two languages and automatic translation](#10-two-languages-and-automatic-translation)
11. [The public site: what gets generated](#11-the-public-site-what-gets-generated)
12. [Importing and exporting](#12-importing-and-exporting)
13. [config.json reference](#13-configjson-reference)
14. [Files, folders and the article format](#14-files-folders-and-the-article-format)
15. [Security](#15-security)
16. [Troubleshooting](#16-troubleshooting)
17. [For developers](#17-for-developers)

---

## 1. What PyBlog is and how it works

PyBlog is a blog engine written in pure Python, **with no external
dependency at all**: `python3` is enough, no database, no `pip install`. You
write the articles with a visual editor in the browser; when you save,
PyBlog generates the static HTML pages of the site.

They are **two different things**:

1. **The editor** (the `/admin` area): the Python program you start with
   `python3 pyblog.py serve`. It is password-protected and only for you.
2. **The site**: the `output/` folder, made of ready-made HTML files. It is
   what readers see and **it does not need Python**: a web server such as
   nginx serves it.

```
   You (browser)         PyBlog                      output/
  ┌─────────────┐ save  ┌──────────────────┐ build  ┌────────────┐
  │ editor      │ ────▶ │ pyblog.py serve  │ ─────▶ │ *.html     │ ──▶ nginx ──▶ readers
  │ (WYSIWYG)   │       │ (only for you)   │        │ rss, sitemap│
  └─────────────┘       └──────────────────┘        └────────────┘
```

Every time you save or delete an article in the administration, publish or
unpublish it, or save the Settings, PyBlog **regenerates every page** of
`output/` by itself. The `build` command (or "Rebuild the site" in the menu)
is only for special cases: the first time, after updating PyBlog, after
editing `config.json` or a template by hand.

**Requirements:** Python 3.8 or later. To publish online, a web server that
serves static files (nginx in the examples).

---

## 2. Installing and running

### 2.1 On your computer

```bash
git clone https://github.com/giuseppeciuni/pyblog.git
cd pyblog
./install.sh
```

The script checks Python, lets you choose the password and builds the site.
Without the script, three commands are enough:

```bash
python3 pyblog.py password   # the administration password
python3 pyblog.py build      # the first build of the site
python3 pyblog.py serve      # the editor on http://localhost:8000
```

Open **http://localhost:8000/admin**. The generated site is at
http://localhost:8000/. To stop the editor, Ctrl+C: the work is already
saved on disk.

For safety the editor listens on `localhost` only: no other device on the
network can reach it.

### 2.2 The commands

| Command | What it does |
|---|---|
| `python3 pyblog.py serve` | starts the editor on `localhost:8000` |
| `python3 pyblog.py serve 9000` | ...on another port |
| `python3 pyblog.py serve 8000 0.0.0.0` | ...reachable from the network: only behind a proxy with HTTPS |
| `python3 pyblog.py build` | regenerates the whole site into `output/` |
| `python3 pyblog.py password` | sets or changes the administration password |
| `python3 pyblog.py import-md <file or folder>` | imports Markdown articles (see [12.1](#121-markdown)) |
| `python3 pyblog.py import-docx <file or folder>` | imports Word documents as drafts (see [12.2](#122-word)) |
| `python3 pyblog.py export-md <folder>` | exports every article to Markdown |
| `python3 pyblog.py bundle` | builds `pyblog_standalone.py`, the single-file version |

### 2.3 With Docker

```bash
docker compose up -d
```

The editor is at `http://localhost:8000/admin`; `docker compose down` stops
it. The project folder is mounted in the container, so articles,
configuration, password and generated site stay on your disk.

The port is published on `127.0.0.1` only. Inside the container PyBlog
listens on `0.0.0.0` (otherwise it would be unreachable from the container
itself), but the container must not be exposed to the internet: online, nginx
serves the site from the `output/` folder. To update: replace the files and
`docker compose restart`.

### 2.4 The single-file version

`python3 pyblog.py bundle` writes **`pyblog_standalone.py`**: one script
holding the modules, the templates and the CSS/JavaScript. It is for people
who would rather download one file than a folder; it supports every command
except `bundle` and produces exactly the same site. It is a build product,
not a second codebase: changes are made in `core/` and then it is generated
again.

```bash
python3 pyblog_standalone.py serve
```

### 2.5 Online: three ways

| | **A. Write on your computer, upload the pages** | **B. Editor on the server, through an SSH tunnel** | **C. Editor online over HTTPS** (the tutorial) |
|---|---|---|---|
| Python on the server | no | yes | yes |
| Attack surface | minimal | small (SSH only) | the `/admin` area, behind HTTPS and limits |
| Writing from several devices | awkward | easy | easiest, phone included |
| To publish | `rsync` | nothing | nothing |

**A — Write locally, upload `output/`.** The server only has nginx.

```bash
python3 pyblog.py serve        # write, then Ctrl+C
rsync -avz --delete output/ user@yourdomain.com:/var/www/blog/
```

`--delete` removes from the server the files that no longer exist locally
(the deleted articles): the destination folder must hold the site only. On
nginx the "public site" part of `nginx.conf.example` is enough, with
`root /var/www/blog;`. It is worth putting the command in a `publish.sh`
script.

**B — Editor on the server, reached through an SSH tunnel.** The editor runs
on the server but is not visible from the internet:

```bash
# from your computer, leaving it open
ssh -L 8000:localhost:8000 user@yourdomain.com
```

and open `http://localhost:8000/admin` in your browser. When you save,
`output/` on the server is regenerated and nginx serves the pages right away.
For an editor that is always on, use the systemd service of 2.6; nginx only
serves `output/` (remove the administration blocks from the example file).

**C — Editor online over HTTPS.** It is the complete setup of the
**[TUTORIAL.en.md](TUTORIAL.en.md)**: nginx serves the site and passes only
the administration routes to PyBlog, with mandatory HTTPS and the limit on
login attempts.

### 2.6 The systemd service

`pyblog.service.example` is ready for `/opt/pyblog` and a `pyblog` user:

- `ExecStart=/usr/bin/python3 /opt/pyblog/pyblog.py serve 8000 127.0.0.1`:
  it listens on the machine only, nginx passes the requests to it;
- `Restart=on-failure`: it starts again if it stops;
- `EnvironmentFile=-/etc/pyblog.env`: the secret keys, in a file only root
  can read (optional, thanks to the leading dash);
- `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome` and
  `ReadWritePaths=/opt/pyblog`: the process gains no privileges, has a
  private `/tmp` and can write only in its own folder.

```bash
sudo useradd --system --home /opt/pyblog --shell /usr/sbin/nologin pyblog
sudo cp pyblog.service.example /etc/systemd/system/pyblog.service
sudo systemctl daemon-reload
sudo systemctl enable --now pyblog
systemctl status pyblog
journalctl -u pyblog -f        # the program's messages, live
```

### 2.7 nginx

`nginx.conf.example` is the complete configuration for way C. Block by
block:

- `limit_req_zone ... rate=1r/s`: at most one login attempt per second per
  address, with a small allowance;
- `root .../output;`: the public pages are static files;
- `location ~ ^/(admin|edit|config|login|...)$`: the administration routes go
  to PyBlog on `127.0.0.1:8000`, with the visitor's real address
  (`X-Real-IP`, which PyBlog uses to lock out only whoever gets the password
  wrong), the protocol (`X-Forwarded-Proto`, for the `Secure` cookie), a
  120-second wait for the AI features and uploads up to 100 MB;
- `location ^~ /admin-static/`: the administration's stylesheet and script,
  which live in `static/` and not in `output/`. The `^~` matters: without it,
  the rule for static files would look for them in `output/` and the
  administration would open with no styling;
- `location = /login`: the limit on attempts;
- `error_page 404 /404.html`: addresses that do not exist show the site's
  404 page, with the search and the latest articles;
- long caching for CSS, JS and images; the right types for `rss.xml` and
  `llms.txt`; `/media/` for uploaded files (nginx handles range requests,
  which let videos seek).

**When you update PyBlog**, if the list of administration routes changes, the
`location ~ ^/(...)$` line changes too: copy it into your nginx file,
otherwise the new feature answers 404 online. The CHANGELOG points it out.

### 2.8 HTTPS

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
sudo certbot renew --dry-run
```

Certbot adds HTTPS and the automatic switch from `http`, and renews the
certificate by itself. With the editor online (way C) HTTPS is a must: your
password travels from the administration.

### 2.9 Secret keys in environment variables

Every key of the `translation` section of `config.json` can come from an
environment variable, which takes precedence over the file and never shows
in the Settings page. The name is `PYBLOG_` plus the key's name in upper
case:

| Variable | Service |
|---|---|
| `PYBLOG_LLM_API_KEY` | Anthropic (Claude) or a compatible endpoint |
| `PYBLOG_OPENAI_API_KEY` | OpenAI |
| `PYBLOG_DEEPSEEK_API_KEY` | DeepSeek |
| `PYBLOG_DEEPL_API_KEY` | DeepL |
| `PYBLOG_GOOGLE_API_KEY` | Google Cloud Translation |

On the server they go in `/etc/pyblog.env` (permissions `600`, owned by
root), one per line (`PYBLOG_LLM_API_KEY=sk-...`), then `sudo systemctl
restart pyblog`. On your computer an `export` before starting is enough:

```bash
export PYBLOG_LLM_API_KEY="sk-ant-..."
python3 pyblog.py serve
```

Tip: a key just for the blog and a monthly spending cap in the service's
console. To check that it arrives: open an article and run **Analyze with
AI** in the SEO analysis box.

### 2.10 Updating PyBlog

```bash
cd /opt/pyblog
sudo -u pyblog git pull
sudo systemctl restart pyblog
sudo -u pyblog python3 pyblog.py build
```

Articles (`posts/`), `config.json` and the password are left untouched.
Files written by an old version (Italian keys such as `titolo_sito`) are
converted by themselves on the first start.

### 2.11 Backup and restore

What to save: `posts/`, `config.json`, `admin_password.txt`,
`subscribers.json` (the subscribers, if you use the newsletter) and
`output/media/` (the uploaded files). The rest of `output/` is regenerated
by `build`.

- **From the menu:** **Download the backup** downloads a `.zip` with
  articles (and their earlier versions), images, settings and newsletter
  subscribers.
- **Every night on the server**, with cron (`sudo crontab -e`):

  ```
  0 3 * * * tar -czf /var/backups/pyblog-$(date +\%F).tar.gz --ignore-failed-read -C /opt/pyblog posts config.json admin_password.txt subscribers.json output/media
  30 3 * * * find /var/backups -name 'pyblog-*.tar.gz' -mtime +30 -delete
  ```

- **Restoring:** stop the service, extract the archive into `/opt/pyblog`,
  `chown -R pyblog:pyblog /opt/pyblog`, `build`, start it again.

---

## 3. The administration

### 3.1 Login and password

- **The first time**, if there is no password yet, `/admin` offers to create
  one. Online it is better to create it from the terminal first
  (`python3 pyblog.py password`), so that nobody gets there before you.
- **Changing it:** menu → **Change password** (the current one is needed;
  you stay logged in, every other open session is closed).
- **Forgotten:** from the server's terminal, `python3 pyblog.py password`.
- After a few wrong attempts the **address** that keeps failing is stopped
  for a while, longer each time; after an hour without mistakes the count
  starts again. Other addresses are not affected.

### 3.2 The menu

On the left, always in sight:

- **Articles** (with how many there are), **New article**, **Settings** (on
  the Settings page it opens into its sections);
- **Tools:** **Rebuild the site** recreates every public page from articles
  and settings; **Download the backup** gives a `.zip` with articles, images
  and settings;
- **Open the site** (in a new tab), **Change password**, the language of the
  administration (Italiano or English), **Log out**.

In the editor the menu shrinks to a column of icons: hovering shows the
name. **On a phone** the menu becomes a bar at the bottom of the screen
(Articles, New, Settings, More); in the editor the bar gives way to the
publishing panel.

### 3.3 The Articles page

- At the top how many are published and how many drafts, and **New
  article**.
- The **All / Published / Drafts** filters, **search** by title and the
  **sort** order (newest first, oldest first, title, status).
- Each row: the status, the title (clickable, opens the editor), the date,
  the reading time and "also in Italian/English" when there is a
  translation; **Edit**, and the **⋯** button with the rarer actions:
  **Preview**, **Preview in ...** (when there is translated text),
  **Publish** or **Unpublish**, **Delete** (asks for confirmation). The ⋯
  menu works from the keyboard too: arrows to move, Esc to close.

---

## 4. Writing an article: the editor

### 4.1 The fields

- **Title.**
- **Address (slug):** the last part of the page's address, as in
  `/posts/how-it-works.html`. Left empty, it comes from the title. If
  another article already uses that address, the new one takes a free one
  (with "-2" at the end) and tells you: an article never overwrites another.
- **Tags**, comma separated: they become the `/tag/...` pages and the topics
  bar.
- **Cover image:** upload a file or paste an address. It shows in the
  homepage list, at the top of the article and in social previews.
- **Reader preview:** the text under the title in the lists; left empty, the
  first words of the article are used.
- **SEO description:** the sentence Google shows under the title, ideally
  120-160 characters; a counter guides you.

### 4.2 The text

The editor's toolbar has: font and size, bold, italic, underline,
strikethrough, text and background colour, subscript and superscript,
headings, bulleted, numbered and checkbox lists, indentation, alignment,
quotes, code blocks, links, images, videos. **Hover a button** and a bubble
says what it does.

Under the editor, **Insert:** **Upload image**, **Insert YouTube video**,
**Upload a video**, **Insert table**.

- **Images:** PNG, JPEG, GIF, WebP and SVG (SVGs stay sharp at any zoom:
  ideal for diagrams), up to 10 MB; JPEGs that are too large are scaled down
  in the browser before they leave. Click the image and drag the corners to
  resize it; the alignment buttons centre it or put it left or right, with
  the text around it.
- **Code:** the `<>` button creates a block; on the site the code is
  coloured according to the language and has a "Copy" button.
- **Tables:** **Insert table** asks for rows and columns; click a table to
  edit it in a window (cells, rows, columns). Tables pasted from Word stay
  tables; the ones Word used only for layout become ordinary text. On a phone
  wide tables scroll sideways.
- **Videos:** YouTube by pasting the link, or an MP4/WebM file up to 100 MB.
- **Pasting from Word:** text and images arrive together, and the images are
  uploaded by themselves; a message says how many.

### 4.3 Importing a Word document

**Import from Word (.docx)**, above the editor, loads a whole document (up to
30 MB): headings, bold and italics, alignments, nested lists, tables with
merged cells, images with their alternative text, footnotes, links,
superscripts and subscripts, text boxes. The document's title (Title or
Heading 1 style at the beginning) becomes the article's title and the
subtitle the description, if it is empty. Word's table of contents, hidden
text, WMF/EMF images (no browser shows them), linked rather than embedded
images, links that are not http, https or mailto, and equations are left
out: a notice says what was skipped. The imported article is **not saved
yet**: look it over, then save.

### 4.4 Status and publishing

At the top of the right-hand column there is the article's status and the
buttons that make sense in that status:

- **Draft** ("readers cannot see it"): **Save draft** (or Ctrl+S),
  **Preview**, **Publish**. Drafts are also saved by themselves every
  minute.
- **Published** (with the **View online** link): **Update the article** (or
  Ctrl+S) saves and puts it online right away; **Preview** shows the changes
  first; **Unpublish** takes the page off the site and the article goes back
  to draft.

**Scheduled** ("Scheduled · goes out on..."): the article goes out by itself
at a chosen time. From a draft, **Schedule publication…** opens a date and
time field (in your computer's time; it proposes tomorrow at 9) and
**Schedule** asks for confirmation. Until then readers cannot see it; then it
goes out within a minute, dated at the scheduled time, so it sits at the top
of the lists like a new article. Meanwhile you can correct it with **Save
changes**, **Change date and time…**, **Publish now** or **Cancel the
schedule** (back to draft). On the Articles page it has the "Scheduled"
label, says when it goes out and has a filter of its own.

The editor, while running, does the publishing: it checks every minute; every
`build` also publishes the articles whose time has come. If the editor does
not stay on (way A of chapter 2.5), a `cron` that rebuilds and uploads the
site does the same job, for example every five minutes:
`*/5 * * * * cd /path/to/pyblog && python3 pyblog.py build && rsync -az --delete output/ user@yourdomain.com:/var/www/blog/`.

**Preview** opens the real page, with the site's styling, as it is in the
editor at that moment, **without saving anything**. Publishing and
unpublishing ask for confirmation. Under the buttons a line says when there
are "Unsaved changes"; if you leave with something to save, the browser asks
you. **Delete article** is at the bottom of the column.

### 4.4b Earlier versions

Every save keeps the version it replaces. Under the publishing panel,
**Earlier versions** opens the list, newest first: for each, the moment, the
status, the words and the title. Choose one to see it; **Bring back into the
editor** puts that version's title, text, description, preview, tags, cover
and translation back in the fields. Nothing is saved until you save: save to
keep it, leave without saving to drop it. The address, the status and the
article's code stay as they are. If the editor has unsaved changes, it asks
for confirmation.

Autosave writes every minute, so a version is kept only if the last one is
more than ten minutes old; a **published** version is always kept, because
it is the one readers saw. The last 50 versions per article are kept, in
`posts/.history/<address>/`. Versions follow the article when its address
changes and go away when you delete it; the backup includes them.

### 4.5 The AI helpers

They use the service chosen in **Settings → Translation** (a key is needed,
see [2.9](#29-secret-keys-in-environment-variables)). The AI buttons all have
the same icon and the same purple colour.

- **Suggest with AI** next to the SEO description and **Generate with AI**
  next to the reader preview: a proposal based on the text, to touch up.
- **Analyze with AI**, in the SEO analysis box: main and long-tail keywords,
  suggested tags (with a button that applies them), title variants, an
  opinion on the description, anchor texts for backlinks from the outside
  site set in `seo.backlink_site`, internal links to the other articles,
  questions and answers (FAQ) for AI answer engines, and advice for the
  article. Every item has a Copy button. The article must have been saved at
  least once.

If a call fails, the message says why: wrong or missing key, credit used
up, model that does not exist.

### 4.6 External code on the article

In the right-hand column, **External code** lists the site's code that can
show on this article: the "tick to enable" ones show only when ticked, the
"by default" ones show until you untick them (for example, an article with
no advertising). Below, **For this article only** takes code that shows
there and nowhere else: a podcast player, a sign-up form, a dedicated ad.
This code too can go to a point chosen by clicking on the page (see
[6.4](#64-the-point-chosen-on-the-page)). See chapter
[6](#6-external-code-analytics-ads-widgets).

### 4.7 The version in the other language

At the bottom of the column, the translation section (see
[10](#10-two-languages-and-automatic-translation)): tick **Allow creating the
English version** (or Italian, on an English site), click **Translate
automatically** or write title, description, preview and text by hand, check
with **Preview the English page**, and when you are happy tick **Confirm the
translation and publish the English page** and save.

---

## 5. The Settings, section by section

The Settings are split into sections, one per job; one shows at a time. On a
computer the sections are in the menu on the left; on a phone the page opens
on a list, and the arrow at the top goes back to it. Every field has its help
underneath.

The bar at the bottom says **Unsaved changes** when there is something to
save. **Save and update the site** saves every section together and
regenerates the public site; **Discard changes** puts everything back as it
was last saved. If you leave with unsaved changes, the browser asks you.

### 5.1 Site and author

- **The site:** title, subtitle, **domain** (`https://yourdomain.com`, no
  trailing slash: the sitemap, canonical addresses and social previews come
  from here) and **main site language** (the one you write in: it sits at the
  root of the site, the translation goes in a subfolder).
- **Who writes:** name, job title, short bio, photo, personal page, public
  profiles (one per line: GitHub, LinkedIn, X...) and the site's X account.
  They go into the pages' structured data (schema.org) and social meta tags:
  they help Google recognise you as an author and connect your profiles. All
  optional.
- **Logo and icon:** the site's logo and a custom favicon (left empty, PyBlog
  generates one with the title's initial).

### 5.2 Homepage

- **Homepage introduction:** the free text of the homepage, with the visual
  editor (images, videos, alignments), and its version in the other language,
  with automatic translation. **Show/hide homepage preview** shows how it
  looks.
- **Layout:** the introduction **in the sidebar** (the articles start at the
  top) or **above the articles**; **highlight the latest article** (bigger,
  with its cover); the **excerpt length** for articles without a preview; how
  many **articles per page** (0 = all on one page).
- **Article page:** whether to show the cover at the top of the article.

### 5.3 Biography

Off until you tick **Show the biography**. Write the text with the editor,
choose a **photo** (left empty, the one from "Site and author" is used) and
**where it shows on the homepage**: in the sidebar, above or below the
articles. The homepage shows the photo and the first lines, with **Read the
biography** leading to the page with the whole text (`/pagine/biography.html`
on an English site, `/pagine/biografia.html` on an Italian one). Below is the
version in the other language, with automatic translation.

### 5.4 Projects

Off until you tick **Show the projects**. **Add a project** creates a card:
name, short description (also in the other language), link and an optional
image (cropped to 16:9). The arrows change the order, **Show this project**
hides it without deleting it. Above or below the articles the projects are a
grid of cards; in the sidebar a compact list. A project with no link leads
nowhere.

### 5.5 Pages

The pages of the **Explore** box in the sidebar: contacts, a gallery,
notices. Each has a title, a text written with the editor and an address of
its own (`/pagine/<title>.html`). **Show this page** puts it online; **Show
the Explore box** turns the whole box on or off (each page keeps its own
choice). A page with the same name as the biography is skipped while the
biography is on.

### 5.6 Comments

None, **Giscus** or **Disqus**: see [8](#8-comments).

### 5.6b Newsletter

The sign-up form, where it shows, its texts, the automatic sending on
publication, the SMTP account with the test email and the list of
subscribers: see [8b](#8b-newsletter).

### 5.7 Translation

The service (DeepL, Google Translate, Anthropic Claude, OpenAI, DeepSeek) and
its key, plus endpoint and model where needed. Without a key translation
stays off and the site works anyway. The same service also does the editor's
AI helpers. See [10](#10-two-languages-and-automatic-translation).

### 5.8 Analytics and ads

- **Analytics:** the Google Analytics 4 ID and the two Umami fields (see
  [9](#9-visit-statistics)).
- **External code and ads:** with the three-example guide; see
  [6](#6-external-code-analytics-ads-widgets).
- **ads.txt:** see [6.6](#66-adstxt).

### 5.9 Cookies and privacy

The consent banner: see [7](#7-the-cookie-banner).

### 5.10 AI training

Whether artificial intelligence services may use your writing:

- **Allowed:** no restriction;
- **Licensed only:** known AI crawlers are blocked in `robots.txt`, with an
  email to ask for a licence;
- **Disallowed:** blocked, no licence offered.

You can give the address of your own licence terms and a text of your own.
The choice ends up in `robots.txt`, `llms.txt`, `/.well-known/ai.txt`,
`/.well-known/tdmrep.json` (a good-faith attempt to follow the TDM
Reservation Protocol, a non-binding convention still evolving) and in the
public page `/training-rights.html`.

### 5.11 Advanced

Direct editing of `config.json`. The text is checked before saving: broken
JSON is refused with the line and column of the error, and the site stays as
it was. **Reset** goes back to the saved file. Use it only if you know what
you are doing; the reference is chapter [13](#13-configjson-reference).

---

## 6. External code: analytics, ads, widgets

An outside service gives you a piece of HTML or JavaScript to put in your
pages: Google Analytics, AdSense, Tag Manager, a pixel, a chat. There is no
need to touch the program's files: go to **Settings → Analytics and ads →
External code and ads**. A guide with three examples shows, for each, the
code the service gives and what to choose here.

### 6.1 Adding a piece of code

**Add code** asks what you want to add.

- **The most common services are ready:** Google Analytics 4, Google Tag
  Manager, AdSense (auto ads or an ad unit), Google Ads (conversion tag), Meta
  Pixel, Microsoft Clarity. Type only the ID (for example `G-AB12CD34EF`) and
  **Create**: the code is prepared with the right position, pages and
  consent, and if the ID has the wrong shape you are told first. With AdSense
  the `ads.txt` line is added too.
- **Your own code** for everything else: an empty card.

Each piece of code is a card, folded to a line that says where it goes, on
which pages and with which consent; click it to open it. Each card has:

1. **Active:** off means off everywhere, without deleting it.
2. **Name:** to find it again; it does not end up in the pages.
3. **Where it goes in the page** (see 6.2).
4. **On which pages** (see 6.3).
5. **Visitor consent** (see 6.5).
6. **Code:** pasted as it is; the box colours the code and numbers the
   lines.

### 6.2 The positions

*In the page code (invisible):*

| Position | Where | For |
|---|---|---|
| Page head (head) | inside `<head>` | analytics, Tag Manager, pixels, ownership checks |
| Start of the page | right after `<body>` | Tag Manager's `<noscript>` |
| End of the page | before `</body>` | chats and scripts that can wait (`defer`, `async`) |

*Visible in the page:*

| Position | Where | Exists on |
|---|---|---|
| In the header menu | next to Home, Articles, Archive | every page; for one more link, for example "Ask the assistant" that opens a chat |
| Below the site header | before the content | every page |
| In the sidebar | after the introduction: the place of a 300×250 ad | homepage, articles, tags, archive, pages |
| Between the homepage articles | after the third | the homepage only |
| At the start of the article | after title and cover | articles only |
| Halfway through the article | after the paragraph closest to the middle: never inside a table or a list, never between a subheading and its paragraph; a short article gets it at the end | articles only |
| At the end of the article text | before the author's signature | articles only |
| Before the footer | after the content | every page |
| **At a point you choose on the page…** | where you click it (see 6.4) | the pages that have that point |

On a page that does not have the chosen position, the code does not show.

### 6.3 The pages

**The whole site** (archive, tags, pages and 404 included), **homepage
only**, **articles only**, **homepage and all articles**, **selected
articles only**, **homepage and selected articles**. With "selected
articles" the code shows on an article only if you tick it in its editor;
with the others it shows everywhere, and in an article's editor you can turn
it off there alone.

### 6.4 The point chosen on the page

When the menu's positions are not enough (an ad after the second paragraph,
a widget before the comments, a banner under the biography), choose **At a
point you choose on the page…**: a window opens with the real page, generated
on the spot **without any external code**.

1. At the top choose which page: the homepage or one of the published
   articles (in an article's editor, that article; it must be saved first).
2. Move over the page: the blocks light up. **Click** the one next to which
   you want the code. The same blocks are listed in the **Block of the page**
   menu, for the keyboard and screen readers.
3. Choose whether the code goes **Before** or **After**. A dashed box shows
   where it will go.
4. **Put it here.** The card shows the point, for example "After · Paragraph
   2 of the text".

The point holds for **every page of the same kind**: chosen on an article,
"After · Paragraph 2 of the text" puts the code after the second paragraph of
every article that has one (together with the "On which pages" choice).
Where the point does not exist (an article with a single paragraph), the
code does not show. Technically the point is a CSS selector
(`div.post-content > p:nth-of-type(2)`) and a side; the published page
carries the code inert at the bottom and `site.js` moves it to the point and
starts it. If it waits for consent, it waits already in its place. If you
change position, the chosen point stays saved and you find it again by
going back to "At a point you choose".

### 6.5 Consent

It matters only with the cookie banner on (see [7](#7-the-cookie-banner)):

- **Necessary:** always runs. A widget that does not follow visitors.
- **Statistics:** Google Analytics, Clarity and the like.
- **Advertising:** AdSense, Google Ads, Meta Pixel.

### 6.6 ads.txt

It says who may sell advertising on the site: AdSense looks for it at
`/ads.txt` and limits the ads until it finds it. It is written in the
**ads.txt** field (the AdSense template adds its line); left empty, the file
is not published, and if it was there it is removed.

### 6.7 Trying it out, and trust

Try a piece of code **on the site or in an article's preview**, not in the
Settings: the administration blocks outside domains for safety, and a widget
would look broken there.

The code is inserted **as it is**, unchecked (checking it would mean
stopping it from working): whoever gets into the administration can run any
JavaScript on the public site. Paste only code from services you trust and
keep the password safe. Deleting a piece of code is safe: the articles that
had ticked it simply stop receiving it.

---

## 7. The cookie banner

In Europe, statistics and advertising that use cookies may start only after
the visitor's consent. In **Settings → Cookies and privacy** tick **Show the
consent banner to visitors**, give the address of your privacy policy and
save.

From then on:

- the "Statistics" and "Advertising" code, and Google Analytics, reach the
  page stopped (inside a `<template>`): no scripts, no cookies, no requests
  until the visitor accepts;
- the visitor can **accept all**, **refuse** or **choose**; refusing weighs
  as much as accepting (two equal buttons); the choice stays in their
  browser;
- Google's tags receive the choice through **Consent Mode** (everything
  denied until the visitor decides);
- at the bottom of every page **Cookie preferences** opens the banner again;
  withdrawing a consent reloads the page without that code.

The banner shows only when some code needs it. The text can be changed, in
the other language too (empty = the default one). When you add a new service,
**Ask everyone for consent again** and save: every visitor will see the
banner again.

**AdSense in Europe** also asks for a certified CMP (TCF): you can turn on
Google's free message from the AdSense panel ("Privacy & messaging") and
leave AdSense on "Necessary", or use this banner with AdSense on
"Advertising": the ads start after consent.

The banner is a tool, not legal advice: the privacy policy and the choice of
services remain yours.

---

## 8. Comments

A static site relies on an outside service for comments.

**Giscus** (free, no advertising, ideal for technical blogs): it uses the
Discussions of a GitHub repository.

1. Create a public repository on GitHub and in Settings → Features turn on
   **Discussions**.
2. Install the app: https://github.com/apps/giscus
3. On https://giscus.app enter the repository and copy the four values:
   repo, repo ID, category, category ID.
4. **Settings → Comments:** choose Giscus, paste the values (the theme is
   `light` or `dark`), save.

**Disqus** (login with social accounts, but with advertising): sign up at
https://disqus.com, create the site and get the **shortname**; in
**Settings → Comments** choose Disqus, type it and save.

---

## 8b. Newsletter

Readers subscribe from the site and get an email when you publish an
article. Everything stays on your server: the subscribers live in
`subscribers.json` (next to `config.json`, and just as private) and the
emails leave from your SMTP account, with no service in between.

**What it needs.** The editor online (way C of chapter 2.5, the tutorial's):
the sign-up form is on the static site but must reach PyBlog, and nginx
passes it `/iscriviti`, `/conferma` and `/disiscrivi` (with a request limit
of their own). And an **SMTP account**: your mail provider's or a service
such as Brevo, Mailgun or Amazon SES, which gives you server, port, username
and password.

**Turning it on.** In **Settings → Newsletter**: tick **Turn on the
newsletter**, choose where the form shows (in the sidebar, at the end of
every article), fill in **Sending the emails** and click **Send a test
email**: it goes to the sender address, with the values written there, even
before saving. Then **Save and update the site**. The SMTP password is
better kept in `/etc/pyblog.env` as `PYBLOG_SMTP_PASSWORD=...`: it takes
precedence and never shows in the page; an empty field keeps the saved one.

**Subscribing, with double opt-in.**

1. The reader types their address and clicks **Subscribe**: the page says
   "Check your inbox", whatever happened (so the form does not reveal who is
   already subscribed).
2. An email arrives with the confirmation link; asking again sends the link
   at most every ten minutes.
3. The link opens a page with the **Confirm my subscription** button: the
   link alone does not confirm, because mail scanners open every link.
   Without confirmation the address receives nothing else.

A hidden field stops the robots that fill in forms, and each internet
address can make at most five requests an hour.

**Sending.** When you publish an article for the **first time**, the
confirmed subscribers get an email with the title, the first lines and the
link, in their language if the article is translated. Scheduled articles too,
at the time they go out. Not sent: articles published before the newsletter
was turned on (even if you edit them later), the ones for which you untick
**Tell the subscribers when it is published** in the editor, and the same
article twice. With **Tell the subscribers when you publish an article** off,
nothing goes out. The emails leave from a thread of the editor, one at a
time; an article to send is written to disk, so a restart does not lose it,
and if the mail server does not answer it tries again every minute.

**Unsubscribing.** At the bottom of every email there is **Unsubscribe** (a
page with a button here too), and mail programs show their own one-click
unsubscribe button (`List-Unsubscribe-Post`). It works with the newsletter
off too.

**The subscribers.** In the same section you see how many are confirmed and
how many waiting, the list (with **Remove**), the result of the last sending
and **Download the list (CSV)**. The `.zip` backup contains them.

For privacy: only the address, the language and the dates are kept; say so
in your privacy policy, whose link shows under the form if you set it in
"Cookies and privacy".

## 9. Visit statistics

Statistics scripts go only into the public pages: the editor is never
tracked.

- **Umami** (recommended): installed on your server, **cookie-free**, so no
  banner; the data stays yours.
- **Google Analytics 4:** the ID (`G-XXXXXXXXXX`) is enough. It uses cookies:
  in Europe turn on the banner, and GA starts only after consent to
  statistics.
- **nginx logs**, with no script at all: `tail -f
  /var/log/nginx/blog-access.log` for live visits, or a dashboard with `sudo
  apt install goaccess` and `goaccess /var/log/nginx/blog-access.log`.

### Installing Umami with Docker

The project contains `umami-docker-compose.yml`.

1. Copy it to the server (for example `/opt/umami/docker-compose.yml`) and
   replace `CAMBIAMI_PASSWORD_DB` (in **two** places, identical) with a
   database password and `CAMBIAMI_SEGRETO_CASUALE` with the output of
   `openssl rand -base64 32`.
2. `docker compose up -d`. Umami listens only on `127.0.0.1:3000`, on
   purpose.
3. Expose it with nginx on a subdomain:

   ```nginx
   server {
       server_name stats.yourdomain.com;
       location / {
           proxy_pass http://127.0.0.1:3000;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   then `sudo certbot --nginx -d stats.yourdomain.com`.
4. First login at `https://stats.yourdomain.com` with `admin` / `umami`:
   **change the password right away** (Settings → Profile).
5. Settings → Websites → Add website, with the blog's domain: Umami shows the
   **Website ID**, the only thing you need.
6. In **Settings → Analytics and ads** type Umami's address and the Website
   ID, and save.

To check: open the blog in a private window and look at Umami's Realtime
view. Ad blockers block Umami too: the numbers are always a little below the
truth, as with any system. Include the `umami-db` Docker volume in your
backups.

---

## 10. Two languages and automatic translation

The site has a **main language** (Settings → Site and author), which sits at
the root (`/`), and the other one in a subfolder (`/en/` or `/it/`).
Translation always goes from the main language to the other.

For an article (see [4.7](#47-the-version-in-the-other-language)):

1. **Allow creating the English version.**
2. **Translate automatically**, or write title, description, preview and text
   by hand.
3. **Preview the English page**: the page as it is, without saving.
4. **Confirm the translation** and save: the article shows on the other
   language's homepage, in its archive, its feed and the sitemap.

Images, videos and embedded boxes are not sent to the service: they are kept
aside and return to their place. If the service loses an image's
placeholder, PyBlog puts the image back and tells you; check where it ended
up before confirming. Images' alternative text stays in the original
language.

With the site in English everything turns around: you write in English, the
section becomes the Italian version and the translated pages go in `/it/`.
Comments, dates, the banner and previews follow each page's language. The
**administration's language** is a separate choice: it is switched from the
menu.

The services: **DeepL**, **Google Cloud Translation**, **Anthropic Claude**,
**OpenAI**, **DeepSeek**. To try it locally with Anthropic: service
"Anthropic Claude", endpoint `https://api.anthropic.com/v1/messages`, a model
(for example `claude-sonnet-4-5`) and the key, in the Settings or with
`export PYBLOG_LLM_API_KEY=...`.

---

## 11. The public site: what gets generated

- **Two-column homepage:** the articles with thumbnail and opening lines (the
  most recent highlighted), the search, and the sidebar with introduction,
  biography and projects (if you put them there), the Explore box and
  "Follow". On a phone the sidebar moves below the articles and the menu
  opens from a button.
- **Pagination:** beyond the "articles per page", the following pages are
  `/pagina/2.html`, `/pagina/3.html`... (`/en/page/2.html` in English), with
  page numbers.
- **Archive:** every article by year (`/archivio.html`, `/en/archive.html`).
- **Tags:** one page per tag (`/tag/<tag>.html`) and the topics bar.
- **Article:** breadcrumbs, title, date and reading time, cover, table of
  contents (in the sidebar, following the reading; on a phone a collapsible
  menu), coloured code blocks with "Copy", a reading progress bar, the
  author's signature, previous and next article, related articles, comments.
- **Search** in the browser across every article (`search-index.json`), with
  excerpts and highlighting.
- **Light and dark theme**, following the system and remembering the choice.
- **404** with the search and the latest articles.
- **RSS feed** per language (`/rss.xml`, `/rss-en.xml` or `/rss-it.xml`).
- **SEO:** meta description, canonical, hreflang between the two languages,
  Open Graph, Twitter Card, JSON-LD structured data (WebSite, Person with
  photo, job title and profiles, Article), `sitemap.xml`, `robots.txt`,
  `llms.txt`.
- **Favicon** generated with the title's initial, unless you give one.

The pages are static HTML, with a single stylesheet (`style.css`, plus
`common.css` shared with the administration), system fonts and one light
script (`site.js`).

---

## 12. Importing and exporting

### 12.1 Markdown

```bash
python3 pyblog.py import-md folder-with-the-files/    # or a single file
python3 pyblog.py export-md destination-folder/
```

The import reads the "front matter" (the block between two `---` lines at the
top, the one of Hugo and Jekyll), with the fields in English or Italian:

```
---
title: My article              (also: titolo:)
date: 2025-03-15               (also: data:)
description: Line for Google   (also: descrizione:)
tags: [python, tutorial]       (or comma separated)
slug: my-article               (optional)
status: published              (also: stato: pubblicato / draft: false)
---
```

Without `status`, the article arrives as a **draft**; without a title, the
first `#` of the text or the file name is used. The converter covers
headings, bold, italic, code, links, images, lists, quotes and horizontal
rules; not Markdown tables and footnotes (for tables use the editor after the
import). With the editor running, restart it after the import.

The export writes one `.md` per article, with its front matter. It is a
simplified conversion: colours, alignments and sizes become plain text, and
numbered lists become bulleted ones.

### 12.2 Word

```bash
python3 pyblog.py import-docx document.docx      # or a folder
```

It imports as **drafts**, with the same rules as the editor's button (see
[4.3](#43-importing-a-word-document)); what is skipped is written on the
`warning:` lines.

### 12.3 The backup in one file

**Download the backup** in the menu: a `.zip` with articles, images and
settings. See also [2.11](#211-backup-and-restore).

---

## 13. config.json reference

All the settings live in **`config.json`**, in the project folder: it is
created on the first save of the Settings, contains secret keys and is
excluded from git. A template with every field is in `config.example.json`.
Normally it is edited from the Settings; by hand, remember to regenerate the
site (`build`) afterwards.

A missing field takes its default value: old files stay valid when new
fields arrive.

### 13.1 General

| Field | Meaning |
|---|---|
| `site_title` | The site's title. |
| `subtitle` | The line under the title. |
| `author` | The author's name (meta tags, footer, structured data). |
| `base_url` | The domain, with no trailing slash (`https://yourdomain.com`): sitemap, canonical, social. |
| `language` | The main language, `it` or `en`: it sits at the root, the other in a subfolder. |
| `admin_language` | The administration's language, `it` or `en`. |
| `articles_per_page` | Articles per homepage page (default `10`; `0` = all on one page). |
| `home_intro_position` | Where the introduction goes: `"sidebar"` (default) or `"top"`. |
| `home_excerpt_words` | Words of the excerpt in the lists, for articles without a preview (default `40`). |
| `home_featured` | `true` (default): the latest article highlighted at the top. |
| `article_cover` | `true` (default): the cover at the top of the article. |
| `home_order` | No longer used; ignored in old files. |

### 13.2 Homepage, biography, projects, pages

| Field | Meaning |
|---|---|
| `home_content`, `home_content_en` | The homepage introduction (the editor's HTML) and its translation; without a translation, the other language shows the main one. |
| `biography` | `enabled` (default `false`), `position` (`"sidebar"`, `"top"`, `"bottom"`; default `"sidebar"`), `photo` (empty = `seo.author_image`), `content`, `content_en`. |
| `projects` | `enabled` (default `false`), `position` (as above, default `"top"`), `items`: the list in the order of the page; each project has `name`, `description`, `description_en`, `url`, `image`, `visible`. Without a name or with `visible: false` it does not show; a `javascript:` link is discarded. |
| `home_cards_enabled` | Switch of the Explore box (default `true`); with `false` the pages are not generated. |
| `home_cards` | The pages of the Explore box: `active`, `title`, `content`. Off or empty, it has no page. |

### 13.3 SEO and author (`seo`)

| Field | Meaning |
|---|---|
| `author_url` | The personal or professional page. |
| `author_image` | The absolute address of the photo. |
| `author_role` | The job title (`jobTitle`). |
| `author_bio` | A short bio (`description` of Person). |
| `social_profiles` | List of profile addresses (`sameAs`): the strongest signal to connect them. |
| `logo` | The absolute address of the logo (publisher). |
| `twitter_site` | The site's X account, with the @. |
| `favicon` | A favicon of your own; empty, PyBlog generates `favicon.svg`. |
| `backlink_site` | The outside site that republishes the articles and hosts the backlinks: the SEO analysis suggests suitable anchor texts. |

### 13.3b Newsletter (`newsletter`)

| Field | Meaning |
|---|---|
| `enabled` | `true` turns on the form and the sending (default `false`). |
| `enabled_since` | When it was turned on (written by PyBlog): only articles published since then are sent. |
| `in_sidebar`, `after_article` | Where the form shows (default `true`). |
| `title`, `text` | Title and text of the form; empty, the default ones. |
| `send_on_publish` | `true` (default): an article published for the first time goes to the subscribers. |
| `sender_name`, `sender_email` | The sender (an empty name = the site title). |
| `smtp_host`, `smtp_port`, `smtp_security`, `smtp_user`, `smtp_password` | The SMTP account; `smtp_security` is `starttls` (default), `ssl` or `none`. The password can come from `PYBLOG_SMTP_PASSWORD`, which takes precedence. |

The subscribers are not here but in `subscribers.json`.

### 13.4 Comments

| Field | Meaning |
|---|---|
| `comments` | `none`, `giscus` or `disqus`. |
| `giscus` | `repo`, `repo_id`, `category`, `category_id`, `theme`. |
| `disqus` | `shortname`. |

### 13.5 Statistics

| Field | Meaning |
|---|---|
| `analytics_id` | The Google Analytics 4 ID (`G-XXXXXXXXXX`); empty = off. |
| `umami_url` | The address of your Umami instance, with no trailing slash. |
| `umami_website_id` | The Website ID; needed together with `umami_url`. |

### 13.6 External code (`custom_code`) and `ads_txt`

`custom_code` is a list; each piece of code has:

| Field | Meaning |
|---|---|
| `id` | Stable identifier (`snip-...`), generated by itself; articles refer to this, not to the name. |
| `name` | The name you see. |
| `enabled` | `true` or `false`. |
| `position` | `head`, `body_start`, `body_end`, `nav`, `after_header`, `sidebar`, `home_feed`, `article_start`, `article_middle`, `article_end`, `before_footer`, `anchor` (see [6.2](#62-the-positions)). An unknown one counts as `head`. |
| `anchor_selector`, `anchor_where`, `anchor_label`, `anchor_page` | For `anchor`: the block's CSS selector, `before` or `after`, the description shown and the kind of page it was chosen on (`home` or `article`). A selector containing `<` or a line break is discarded. |
| `scope` | `all`, `home`, `articles`, `home_articles`, `optin`, `home_optin` (see [6.3](#63-the-pages)). An unknown one counts as `home`. |
| `consent` | `necessary` (default), `statistics`, `marketing`. |
| `code` | The code, inserted as it is. |

`ads_txt` is the text of the `/ads.txt` file; empty, the file does not exist.

### 13.7 Consent (`consent`)

| Field | Meaning |
|---|---|
| `enabled` | `true` shows the banner (default `false`). |
| `text`, `text_en` | The text in the main language and in the other one; empty = the default. |
| `privacy_url` | The privacy policy. |
| `version` | Grows with "Ask everyone for consent again": whoever chose under an older number sees the banner again. |

### 13.8 Translation (`translation`)

| Field | Meaning |
|---|---|
| `service` | `deepl`, `google`, `llm` (Anthropic), `openai`, `deepseek`. |
| `deepl_api_key`, `google_api_key` | The DeepL and Google keys. |
| `llm_api_key`, `llm_endpoint`, `llm_model` | Anthropic: key, endpoint (normally unchanged), model. |
| `openai_api_key`, `openai_model` | OpenAI (for example `gpt-4o-mini`). |
| `deepseek_api_key`, `deepseek_model` | DeepSeek (for example `deepseek-chat`). |

Every key can come from an environment variable `PYBLOG_<KEY>`, which takes
precedence (see [2.9](#29-secret-keys-in-environment-variables)).

### 13.9 AI training (`ai_training`)

| Field | Meaning |
|---|---|
| `policy` | `"open"`, `"licensed"` or `"disallow"` (see [5.10](#510-ai-training)). |
| `contact_email` | The email for licences (only with `"licensed"`). |
| `license_url` | Your terms; empty, PyBlog's `/training-rights.html` page. |
| `statement` | A text of your own instead of the default one. |

### 13.10 If config.json breaks, and old versions

An unreadable `config.json` (JSON broken by a hand edit) does not stop the
site: PyBlog says so on the terminal, keeps a copy in `config.broken.json`
and starts with the default values. Recover your data from the copy
**before** saving the Settings again. Files are written "all or nothing": an
interruption halfway leaves the old version, never half a file.

Old versions used Italian keys (`titolo_sito`, `stato`, `contenuto`...): on
the first start PyBlog converts `config.json` and the articles by itself,
once.

---

## 14. Files, folders and the article format

```
pyblog.py              the entry point: reads the command and runs it
core/                  the program (configuration, texts, templates, articles,
                       AI, login, Word import, generation, server)
templates/             the HTML templates of the site (public/) and of the administration (admin/)
static/                common.css, style.css, site.js (site); admin.css, admin.js
posts/                 the articles, one JSON file each: your sources
posts/.history/        the earlier versions of every article
output/                the generated site: this is the folder that goes online
output/media/          the uploaded images and videos
config.json            the settings (excluded from git)
admin_password.txt     the password's fingerprint, never the password (excluded from git)
config.broken.json     the copy of a config.json that could not be read
subscribers.json       the newsletter's subscribers (excluded from git)
```

An article in `posts/<slug>.json`:

| Field | Meaning |
|---|---|
| `title`, `slug`, `date`, `date_modified` | Title, address, creation date and date of the last change. |
| `status` | `published`, `draft` or `scheduled`. |
| `publish_at` | For `scheduled`: the moment it goes out, in UTC (`2026-10-04T07:00:00+00:00`); empty in the other statuses. |
| `content` | The text, in HTML. |
| `description`, `preview` | The SEO description and the reader preview. |
| `tags` | The tags, comma separated. |
| `image` | The cover. |
| `title_en`, `description_en`, `preview_en`, `content_en` | The translation into the site's other language. |
| `translation_authorized`, `translation_confirmed` | Whether the translation is allowed and whether it is confirmed (published). |
| `custom_code_ids`, `custom_code_off_ids` | The site's code ticked ("tick to enable") and switched off ("by default") on this article. |
| `custom_code` | The code of this article only, with the same fields as the site's except `scope`; its `id` starts with `art-`. |
| `first_published` | When it was first published (written by PyBlog). |
| `notify_subscribers`, `newsletter_sent` | Whether to tell the subscribers on first publication, and whether it has been sent already. |

---

## 15. Security

- The password is stored as a salted PBKDF2 fingerprint, never in clear.
- Every administration page requires login; every action that changes
  something also requires a CSRF token.
- Sessions expire; the cookie is `HttpOnly`, and `Secure` behind HTTPS.
- Whoever gets the password wrong is stopped, per address and longer each
  time.
- Uploads have size limits and checks on the file's real type; SVGs are
  checked; no path can leave the intended folders.
- The administration sends security headers and a Content Security Policy;
  other sites cannot frame it.
- The editor listens on `localhost`; keys can live outside the project, in
  environment variables.
- The example systemd service runs as a user of its own, without privileges,
  and writes only in its own folder.

**Points to keep in mind:** HTTPS is a must if the editor is online;
`config.json` and `admin_password.txt` must not be published (they are
already excluded from git); external code is JavaScript running on your
site, so whoever gets into the administration can do a lot: keep the
password safe.

---

## 16. Troubleshooting

| What you see | Why | What to do |
|---|---|---|
| **502 Bad Gateway** on `/admin` | PyBlog is off | `sudo systemctl restart pyblog`; the messages with `journalctl -u pyblog -n 50` |
| **403 Forbidden** on the site | nginx cannot read `output/` | `sudo chmod 755 /opt/pyblog /opt/pyblog/output` |
| The administration with no styling | `/admin-static/` does not reach PyBlog | use the `location ^~ /admin-static/` block of `nginx.conf.example` |
| An administration page answers 404 online | the route is missing from nginx's `location ~ ^/(...)$` line | compare your file with `nginx.conf.example` |
| Port 8000 is taken | another program uses it | `python3 pyblog.py serve 9000` (and change `proxy_pass` in nginx) |
| Changes do not show on the site | the browser shows the old copy | Ctrl+F5; **Rebuild the site** from the menu |
| Google indexes nothing | the domain is still the example one | Settings → Site and author → Site domain |
| The AI features give an error | key missing, wrong or out of credit | the message says which; the key in `/etc/pyblog.env`, then restart |
| A widget does not start in the Settings | the administration blocks outside domains | try it on the site or in an article's preview |
| Code "at a chosen point" does not show | that page lacks the point, or is not among the chosen pages | reopen the point choice on a page of that kind |
| "Too many attempts" at login | protection against guessing | wait; it affects only your address |
| Forgotten password | — | `python3 pyblog.py password` on the server |
| `config.json` broken | a hand edit | the data is in `config.broken.json` (see [13.10](#1310-if-configjson-breaks-and-old-versions)) |
| Certbot fails | the domain does not point at the server | check the DNS records and try again |
| The newsletter form answers 404 | nginx does not pass `/iscriviti` to PyBlog, or the newsletter is off | the `location ~ ^/(iscriviti|conferma|disiscrivi)$` block of `nginx.conf.example`; the checkbox in the Settings |
| Emails do not go out | wrong SMTP values, or the provider refuses the sender | **Send a test email** says the error; the last failed sending is written in the Newsletter section |
| Emails end up in spam | the sender's domain does not authorise the mail server | set SPF and DKIM as your SMTP provider says |

---

## 17. For developers

- **No dependencies:** only Python's standard library. The browser libraries
  (Quill, highlight.js, CodeMirror, Bootstrap for the administration's
  windows and notifications) come from CDNs.
- **Two rules everywhere:** a value that ends up in HTML goes through
  `html.escape()` (`render.esc`), one that ends up in JavaScript through
  `json.dumps()` (`render.js`). No translated text is ever concatenated into
  a script: the administration receives everything in `window.PB_I18N`, the
  site in `window.PB_SITE`.
- **Templates** are `.html` files in `templates/`, rendered with
  `string.Template`.
- **Interface texts** are in `core/i18n.py`, in Italian and English.
- **A new setting** is added to `CONFIG_DEFAULT` (`core/config.py`): existing
  configurations receive it with its default value.
- **Tests** are run one by one: `python3 tests/test_<name>.py`; they print "N
  passed, M failed" and put back what they touch.
- **The single-file version** is generated again with `python3 pyblog.py
  bundle` after every change.
