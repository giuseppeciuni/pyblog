# PyBlog user guide — step by step

*In italiano: [GUIDA.md](GUIDA.md)*

This guide takes you from installation to publishing online, explaining
every single step. No experience needed: just follow the order.

---

## What PyBlog is, in two lines

PyBlog is a single-file Python program that gives you a visual editor
(like Word) to write articles and configure your homepage. When you save,
it generates static HTML pages: ready-made, lightweight, lightning-fast files.
A web server (nginx) puts those files online. The Python program is only for
you, for writing: the public site works on its own, even with the program off.

Think of two separate worlds:
- Your private "newsroom" (the Python program, on your computer).
- The public "printed newspaper" (the HTML files, served by nginx online).

---

## PART 1 — Installation

### Step 1.1 — Check that you have Python

Open the terminal and type:

    python3 --version

If you see a number like "Python 3.10" or higher, you are set. PyBlog needs
nothing else: no database, no libraries to install.

### Step 1.2 — Unpack the program

Put the zip file in a folder of your choice and unpack it:

    unzip pyblog.zip
    cd pyblog

Inside you will find the program (`pyblog.py`), this guide and a few folders
that will fill up as you work.

---

## PART 2 — Starting the editor and writing

### Step 2.1 — Turn on the editor

From the `pyblog` folder, type:

    python3 pyblog.py serve

You will see a message telling you to open `http://localhost:8000`. Keep this
terminal open: it is the running program. To stop it, press Ctrl+C.

For safety, the editor listens only on your computer (localhost): no other
device on the network can reach it. If port 8000 is busy you can pick
another one:

    python3 pyblog.py serve 9000

If you really need to reach the editor from another device (not recommended;
better to do it behind a reverse proxy with HTTPS), you can also set the host:

    python3 pyblog.py serve 8000 0.0.0.0

Alternatively, if you have Docker, you can start everything with
`docker compose up -d` (see DEPLOY-REMOTO.md).

### Step 2.2 — Open the newsroom in the browser

Open your browser (Chrome, Firefox...) and go to:

    http://localhost:8000

This is your newsroom. You will see the buttons: "New article",
"Settings and homepage", "Rebuild site", "View blog", and the article
list (empty for now).

### Step 2.3 — Configure the homepage and the site first

Click "Settings and homepage". Here you set everything without touching code.

The homepage has two columns: on the left the articles, each with its
thumbnail and a few lines of preview; on the right a sidebar with your
introduction, the search, the "Explore" box with your pages, the topics and
your profiles. On a phone the sidebar moves below the articles and the menu
opens from a button.

1. At the top there is a visual editor for the HOME: write your introduction
   or biography here. You can use bold, headings, lists.
2. To add an image: click the image icon in the editor toolbar. To place it
   left or right of the text, click the image and then use the alignment
   buttons (the left/right lines) in the toolbar: text will flow around it.
3. You can also embed a YouTube video ("Insert YouTube video" button, paste
   the link) or upload a video from your computer ("Upload a video").
4. Click "Show/hide homepage preview" to see right away how it will look.
5. In the "Homepage cards" section, decide which pages to list in the
   "Explore" box of the sidebar. Each card (Biography, Projects,
   Highlights, Service notices) has its own "Show this card" checkbox:
   checked, it appears in "Explore" and gets a page of its own; unchecked,
   it disappears.
   The checkbox at the top, "Show the cards section", covers the whole
   block: uncheck it and they all go at once, and when you check it again
   every card comes back the way you left it.
6. Further down, fill in the "General settings": site title, subtitle,
   your name, the domain (e.g. https://mysite.com) and the language.
7. In the "Homepage" section, choose where the introduction goes: in the
   sidebar (so the articles start at the top) or above the articles. Here
   you also set how many words to show for the articles without a preview,
   whether to highlight the latest article and how many articles to show
   per page (see "Pagination and archive" below).
8. In the "SEO and author data" section, enter your professional details:
   personal page, photo, job title, short bio and above all your public
   profiles (GitHub, LinkedIn...), one per line. This data goes into the
   pages' "structured data" and helps Google recognise you as a real author
   and connect your profiles together. All fields are optional. Here you can
   also set a logo, the site's X/Twitter account and a custom favicon (if
   you leave it empty, PyBlog generates one automatically with the initial
   of the site title).
9. In the "Comments" section, choose Giscus, Disqus or none
   (see PART 5 for how to get the values).
10. Click "Save and rebuild site". Done: the configuration is saved.

### Step 2.4 — Write your first article

Go back to the newsroom (link at the top) and click "New article".

1. Write the Title.
2. The Slug (the final part of the web address) is generated automatically:
   leave it empty. If another article already uses that address, the new
   one takes a free one (with "-2" at the end, for instance) and a message
   tells you so: an article never overwrites another.
3. Write the SEO Description: a short sentence summarising the article. It
   will appear in Google results, so make it inviting (max 160 characters).
4. Write the Content in the visual editor. **If you cannot remember what a
   button does, hover over it**: a small bubble explains it. In the toolbar
   you have:
   - font and text size selection;
   - bold, italic, underline;
   - text colour and background colour (the "A" and bucket icons);
   - headings, bulleted and numbered lists, alignment;
   - quotes and code blocks;
   - link and image insertion.
5. To insert an image you have two ways: the "Upload image" button (uploads
   a PNG, JPEG or SVG file from your computer) or the image icon in the
   toolbar. Tip: for diagrams with text use the SVG format, which stays
   sharp at any zoom and never pixelates. PNG and JPEG are fine for photos.
6. After inserting an image, you can resize it: click on it and drag the
   square handles that appear on the edges (they work in every direction).
   To centre it or move it left/right, with the image selected use the
   alignment buttons in the toolbar.
7. To insert code (Python or other languages): click the code block button
   in the toolbar (the <> icon), then paste or type the code. On published
   pages the code is automatically colour-highlighted based on the language
   (syntax highlighting), perfect for technical articles.
8. To insert a table: use the "Insert table" button (it asks for rows and
   columns) or copy a table straight from Word and paste it into the editor.
   The structure is kept and adapted to the blog's design; on mobile, wide
   tables scroll horizontally.
8b. If you paste a whole Word document (text and images together), the
   images are automatically recovered and uploaded: Word's clipboard puts
   the real image data alongside the (unusable) text, and the editor picks
   it up and inserts proper images in the right places. A status message
   confirms how many images were recovered.
8c. If the article already exists as a Word document, the "Import from
   Word (.docx)" button above the editor loads all of it: headings, lists
   (nested ones too), tables with merged cells, images with their
   alternative text, footnotes, links, superscripts and subscripts, text
   boxes. The document's title (Title or Heading 1 style at the start)
   becomes the article's title, and the subtitle becomes the description
   when that is empty. Word's table of contents and hidden text stay out,
   and a notice tells you what was skipped (an equation, say, to write
   again). The imported article is not saved yet: review it, then edit and
   save it like any other.
9. You can embed YouTube videos or upload videos from your computer with
   the buttons below the editor.
10. Add Tags separated by commas (e.g. "Python, tutorial").
11. At the top of the right column you see the state of the article. While
   it is a **draft** ("readers cannot see it") you have three buttons:
   - **Save draft** (or Ctrl+S): saves without publishing. Drafts also save
     themselves, every minute;
   - **Preview**: opens the page as it is now in a new tab, with the real
     site's design, without saving anything;
   - **Publish**: after a confirmation, puts the article on the site, on the
     homepage, in the archive and in the RSS feed.
12. Once the article is **published**, "View online" appears at the top and
   the buttons change: **Update the article** (or Ctrl+S) saves and puts
   the changes online right away; **Preview** shows the changes before you
   do; **Unpublish** takes the page off the site and the article becomes a
   draft again. Under the buttons a line tells you about "Unsaved changes".
   To go back to the list use "All articles" at the top: if something is
   still to be saved, the browser reminds you.

### Step 2.5 — Managing and updating articles from the dashboard

The main page (http://localhost:8000) is your administration dashboard.
From here you see:

- At the top, three counters: total, published and draft articles.
- A search bar to filter articles by title (useful when you have many):
  type and the list narrows in real time.
- The list of all articles, each with its status (Published or Draft),
  date and description.

For each article you have these quick actions:
- "Edit": opens the article in the editor. Make your changes and click
  "Update the article" (or "Save draft", if it is not published yet).
- "Publish" / "Unpublish": changes the state of the article without
  opening it, with the same words as the editor's buttons.
- "Preview": opens the published page in a new tab.
- "Preview EN": appears only if the article has English content, and opens
  the English page. Useful to check the translation before confirming it.
- "Delete": removes the article (asks for confirmation first).

### Step 2.6 — Check the result

From the newsroom click "View blog", or open `http://localhost:8000/posts/`.
You will see your homepage with the introduction at the top and the
articles below.

### Step 2.7 — The English version of an article

In the editor, at the bottom of the sidebar, there is the "English version"
section:

1. Tick "Allow creating the English version".
2. Click "Translate automatically" (an API key is needed in Settings,
   Translation section) or write the translation by hand in the EN fields.
3. Click "Preview the English page": the English page opens in a new tab,
   exactly as readers will see it, without saving anything.
4. When you are happy with the translation, tick "Confirm the translation
   and publish the English page" and save. From that moment the article also
   appears on the English homepage (`/en/`), in the English archive and in
   the sitemap.

Images, videos and embeds are not sent to the translation service: they are
kept aside and put back once the translation is in. Nothing to do, it is
automatic. If the service loses an image's marker along the way, PyBlog puts
the image back anyway and says so ("check they are where they belong"): look
at where it landed before you confirm. The images' alt text stays in Italian,
because it lives inside the tag that never leaves.

**If your site is in English** (General settings, "Main site language":
English) everything turns around: you write the articles in English, the
section becomes "Italian version", translation goes from English to Italian
and the translated pages live under `/it/`. Comments, dates, the cookie
banner and the previews follow the language of each page.

### Step 2.8 — Pagination, archive and favicon (all automatic)

Three things PyBlog does by itself, with nothing to do on your side:

- **Pagination.** When articles exceed the number set in "Articles per page"
  (10 if you leave it untouched), the homepage shows only the most recent
  ones and a "Newer / Older" navigation appears at the bottom. The next
  pages live at `/pagina/2.html`, `/pagina/3.html`... (in English,
  `/en/page/2.html`). If you prefer all articles on a single page, set the
  value to 0.
- **Archive.** The "Archive" item in the site bar leads to a page with ALL
  articles grouped by year, in a compact list with date and title. It exists
  in both languages (`/archivio.html` and `/en/archive.html`) and updates on
  every save. The homepage search, on the other hand, always searches all
  articles, not just those on the current page.
- **Favicon.** The little icon in the browser tab is generated automatically
  with the initial of the site title. If you want your own, put its URL in
  the "Custom favicon" field in Settings.

---

### Step 2.9 — The AI helpers in the sidebar, and tables

The editor sidebar offers three helpers based on the AI service
configured in Settings (Translation section):

- **Suggest with AI** next to the SEO description and the reader
  preview: it drafts a proposal from the content, which you can then
  adjust.
- **SEO & backlink analysis**: it analyses the article and returns
  primary and long-tail keywords, suggested tags (with a one-click
  apply button), title variants, a review of the meta description, the
  anchor texts to use in backlinks from the configured external site
  (`seo.backlink_site` in CONFIGURATION.md), internal links towards
  the blog's other articles, FAQ blocks meant for AI answer engines
  and article-specific advice. Every item has a Copy button. The
  article needs a slug (save it first, if new).

About **tables**: when pasting from Word, tables used purely for page
layout (text next to an image) are unwrapped into ordinary editable
text, while real data tables stay tables. To edit their content,
**click the table**: a window opens where you change the cells and add
or remove rows and columns.

### Step 2.10 — Trying the AI features locally (test environment)

To try everything AI-based locally (translation, suggestions, SEO
analysis) you need an API key for the provider of your choice. Locally
the simple way is the Settings page, Translation section:

1. Pick the service. With Anthropic: service `llm`, endpoint
   `https://api.anthropic.com/v1/messages`, model e.g.
   `claude-sonnet-4-5`, and your key (`sk-ant-...`) in the dedicated
   field. With OpenAI or DeepSeek the key in their field is enough.
2. Save: the key goes into `config.json`, which stays on your computer
   only (`.gitignore` already keeps it out of git).

Alternatively, if you prefer not to write it even there, start the
editor with an environment variable: it takes precedence over the file
and never appears in the Settings page.

    export PYBLOG_LLM_API_KEY="sk-ant-...your-key..."
    python3 pyblog.py serve

Then the full test round, on an article with some content:

1. **Suggest with AI** next to the SEO description: a proposal must
   appear in the field.
2. **Suggest with AI** on the reader preview: same.
3. **SEO & backlink analysis**: save the article first (the slug is
   needed), then run the analysis; within a minute the panel appears
   with keywords, anchor texts, internal links and FAQ.
4. **English translation**: authorise the translation in the article
   and click "Translate automatically"; check the filled EN fields.

If a call fails, the error message says why: wrong or missing key,
no credit left, or a non-existent model. Tip: use a key dedicated to
testing, with a low spending cap set in the provider's console.

### Step 2.11 — Putting a third-party service's code into your pages

Sooner or later a service will hand you a line to paste into your site:
Google Analytics, AdSense, a support widget, a chat, a tracking pixel.
Something like this:

```html
<script src="https://example.com/widget/loader.js" data-widget-id="a7ddc6ff" defer></script>
```

You do not need to touch the program's files. Go to **Settings**, scroll
down to **External code and ads** and click **Add code**: you are asked
what you want to add.

**The most common services are ready.** Pick Google Analytics 4, Google
Tag Manager, AdSense (auto ads or a single ad unit), Google Ads, Meta
Pixel or Microsoft Clarity from the list, type the id the service gave
you (for instance `G-ABC123DEF4` for Analytics) and click **Create**. The
code is prepared with a suitable position, pages and consent; an id of
the wrong shape is caught first. With AdSense the line of the `ads.txt`
file is added too (see below). You can change everything afterwards.

**For everything else there is "Your own code"**: an empty card to fill in.

1. **Name**: whatever you want to call it, so you can find it again.
   E.g. "Support widget".
2. **Where it goes in the page**: the entries are split into two groups.
   The ones *in the page code* (`head`, start, end) are invisible and suit
   scripts and pixels: for the example above, pick **the end of the
   page**. The *visible* ones are for code that must show up in a precise
   spot: in the header menu, below the site header, in the sidebar (the
   place for a 300x250 ad), between the homepage articles, at the start,
   half way or at the end of the article text, before the footer. **In
   the header menu** is for one more entry next to Home, Articles and
   Archive: for instance an "Ask the assistant" link that opens a chat
   widget.
3. **On which pages**: the whole site, the homepage only, the articles
   only, homepage and articles, or **selected articles only**: with the
   last one the code stays off until you switch it on, article by article.
4. **Visitor consent**: "Necessary" if the code sets no cookies (a widget,
   an embed), "Statistics" for Analytics, Clarity and the like,
   "Advertising" for AdSense, Google Ads and pixels. It only matters with
   the cookie banner switched on (step 2.12).
5. **Code**: paste what the service gave you, unchanged. The box colours
   the code and numbers the lines, like a programmer's editor.

Save, and the site is rebuilt. When you come back to the page each piece
of code is folded to a single line that says where it goes, on which pages
and with which consent: click the line to open it.

**Code on a single article.** Open the article in the editor: in the right
column, under **External code**, you find the site's code that may appear
on that article, with a checkbox each. The "tick to enable" ones (scope
"selected articles") appear only when ticked; the "by default" ones appear
on every article, and unticking one switches it off on this article only:
useful, for instance, for an article that must carry no ads. Below it,
**For this article only** holds code that appears there and nowhere else:
a dedicated ad, an embed, a widget. Save the article and that is it.

**ads.txt.** It is a file that says who may sell advertising on your site:
AdSense looks for it at `/ads.txt` and limits the ads until it finds it.
Write it in the **ads.txt** field under the code (the AdSense template
already puts its line there); when empty, the file is not published.

**To actually try it**, use the article preview, not the Settings page:
the administration area blocks external domains for security, so the
widget would not start there and would look broken. In the preview, and
on the published site, it works normally.

**Two warnings.** The code is injected into the page as it is, with no
checking: only paste code you trust, because it can do anything on your
site. And if you delete a snippet from the Settings page, the articles
that had ticked it do not break: they simply stop receiving it.

### Step 2.12 — The cookie banner

In Europe, statistics and advertising that use cookies may start only
after the visitor consents. PyBlog has a banner of its own: in
**Settings**, section **Cookie consent**, tick "Show the consent banner to
visitors", enter the address of your privacy policy and save.

From then on:

- the code marked "Statistics" or "Advertising", and Google Analytics,
  reaches the page on hold: it does not start, sets no cookies and calls
  nobody until the visitor accepts;
- the visitor can accept everything, refuse everything or choose, and the
  two buttons weigh the same; the choice stays in their browser and is not
  asked again on every page;
- Google's tags receive the choice through Consent Mode;
- a "Cookie preferences" link at the bottom of every page lets the visitor
  change their mind.

The banner appears only when some code needs it. You can change its text
(empty = the default one), for the version in the other language too.
When you add a new service, click **Ask everyone for consent again** and
save: every visitor will see the banner again.

**AdSense in Europe** also asks for a "certified CMP". You have two roads:
switch on Google's free message from the AdSense dashboard ("Privacy &
messaging") and leave the AdSense code on "Necessary"; or use this banner
with AdSense on "Advertising": the ads start after consent.

The banner is a tool, not legal advice: the privacy policy and the choice
of which services to use remain yours.

## PART 3 — Where things end up (to understand; not mandatory)

- `posts/` : the articles you write, saved as text files (JSON format).
  They are your "sources". It is wise to back up this folder now and then.
- `config.json` : the site settings and the homepage content.
  It also holds the keys of the translation services, which is why it
  stays out of git. Should it ever become unreadable, PyBlog keeps a copy
  in `config.broken.json` and starts again on the default values.
- `output/` : the generated HTML files, i.e. the actual site.
  This is the folder that goes online.
- `output/media/` : the videos you upload.

Every time you save an article or the settings, the `output/` folder is
regenerated automatically.

---

## PART 4 — Running PyBlog: locally and in production

Before the commands, the concept that prevents 90% of the mistakes.

PyBlog is **two different things** inside a single file:

1. **The editor** — the Python program you start with `serve`. It runs *for
   you*, protected by a password. It is only for writing.
2. **The site** — the `output/` folder, i.e. static HTML files. This is what
   readers see, and it **does not need Python** to work.

> **Golden rule: never expose the editor to the internet.** It is your blog's
> admin area. In production, readers must only reach `output/`, served by
> nginx. That is why, by default, `serve` listens on `localhost` only.

### Running locally (on your computer)

    cd pyblog
    python3 pyblog.py serve

Open `http://localhost:8000`, write, save. On every save the `output/` folder
is regenerated. When you are done, stop it with Ctrl+C: your work is already
on disk, there is no need to keep the program running.

Useful local commands:

    python3 pyblog.py serve 9000        # if port 8000 is busy
    python3 pyblog.py build             # rebuild output/ without the editor
    python3 pyblog.py password          # set or change the password

The `build` command on its own is what you want when you have changed files
by hand (for example after an `import-md`) and want to rebuild the site
without opening the browser.

### Production, scenario A — write locally, publish to the server (recommended)

The simplest and safest way: **no Python runs on the server**. No reachable
admin area, no process to keep alive.

On your computer:

    python3 pyblog.py serve             # write your articles
    # Ctrl+C when you are done
    rsync -avz --delete output/ user@mysite.com:/var/www/blog/

On the server: just nginx serving `/var/www/blog` (see PART 4B).

The `--delete` option removes files from the server that no longer exist
locally: that is exactly what you want when you delete an article. Careful:
the destination folder must contain *only* the generated site, otherwise
`--delete` would remove the other files too.

Tip: put the command in a `publish.sh` script, so you always publish the same
way without risking a wrong path.

### Production, scenario B — write directly on the server (SSH tunnel)

Useful if you want to write from several computers, or from a tablet, with
nothing to sync. The editor runs on the server but **stays invisible from the
internet**: you only reach it through SSH.

On the server:

    cd /home/blog/pyblog
    python3 pyblog.py serve             # listens on the server's localhost only

From your computer, open an SSH tunnel and leave it open:

    ssh -L 8000:localhost:8000 user@mysite.com

Now open `http://localhost:8000` in **your** browser: you are talking to the
server's editor through the tunnel, encrypted by SSH. Nobody from outside can
reach that port. When you save, `output/` on the server is regenerated by
itself and nginx immediately serves the updated pages: no rsync needed.

To avoid restarting the editor by hand after every server reboot, let systemd
manage it. Create `/etc/systemd/system/pyblog.service`:

    [Unit]
    Description=PyBlog editor
    After=network.target

    [Service]
    Type=simple
    User=blog
    WorkingDirectory=/home/blog/pyblog
    ExecStart=/usr/bin/python3 /home/blog/pyblog/pyblog.py serve
    Restart=on-failure

    [Install]
    WantedBy=multi-user.target

Then enable it:

    sudo systemctl daemon-reload
    sudo systemctl enable --now pyblog
    sudo systemctl status pyblog

In this scenario nginx points at the `output/` folder where it lives: in the
configuration file the `root` line becomes `root /home/blog/pyblog/output;`
(see Step 4.3 and the permissions in Step 4.4).

### Which one to choose

| | Scenario A (local → rsync) | Scenario B (SSH tunnel) |
|---|---|---|
| Python on the server | no | yes |
| Attack surface | minimal | small (SSH only) |
| Writing from several devices | awkward | convenient |
| Publishing step | `rsync` | none |

If in doubt, use scenario A.

### What about Docker?

`docker compose up -d` is the local equivalent of scenario B: inside the
container the server listens on `0.0.0.0` (otherwise it would be unreachable
from the container itself), but the port is published only on your computer's
`127.0.0.1:8000`. Here too, in production the site is served by nginx from the
`output/` folder: the container should not stay exposed.

---

## PART 4B — Configuring nginx step by step

These steps are done only once and apply to both scenarios.

### Step 4.1 — Install nginx (on the server)

    sudo apt update
    sudo apt install nginx

### Step 4.2 — Bring the output folder to the server

If you write on your computer and the server is another machine (e.g. a VPS),
copy the `output/` folder to the server with rsync:

    rsync -a output/ user@server-address:/var/www/blog/

You will repeat this command every time you publish something new.
If instead you write directly on the server, just point nginx to the
`output/` folder where it lives.

### Step 4.3 — Configure nginx

Use the included `nginx.conf.example` file as a template. Copy it:

    sudo cp nginx.conf.example /etc/nginx/sites-available/blog

Open it and change two things: the domain name and the folder path
(the `root` line):

    sudo nano /etc/nginx/sites-available/blog

Then enable the site and reload nginx:

    sudo ln -s /etc/nginx/sites-available/blog /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl reload nginx

`nginx -t` checks that the configuration is correct before applying it.

### Step 4.4 — Permissions (if pages do not show)

If nginx returns "403 Forbidden", it probably cannot read the folder.
Grant read permission:

    chmod -R o+rX /var/www/blog

### Step 4.5 — Enable HTTPS (the green padlock), for free

After pointing your domain to the server address:

    sudo apt install certbot python3-certbot-nginx
    sudo certbot --nginx -d yourdomain.com

Certbot configures the certificate by itself and renews it automatically.

---

## PART 5 — Enabling comments

Comments on a static site rely on an external service. You have two choices.

### Giscus (recommended: free, no ads)

Uses the Discussions of a GitHub repository as the comment store.

1. Create a public repository on GitHub.
2. In the repo: Settings -> Features -> tick "Discussions".
3. Install the Giscus app: https://github.com/apps/giscus
4. Go to https://giscus.app, enter the repo name and copy the four values
   it shows (repo, repo id, category, category id).
5. Paste them in the "Settings and homepage" page, choose "Giscus", save.

### Disqus (easier for commenters, but with ads)

1. Sign up at https://disqus.com and choose to install it on your site.
2. You will be assigned a "shortname".
3. Enter it in the Settings page, choose "Disqus", save.

---

## PART 6 — Seeing who visits the site (statistics)

PyBlog ships built-in support for two statistics systems, enabled from
the Settings page (injected into the public pages only, never into the
editor):

- **Umami** (recommended): self-hosted, cookie-free, so no consent
  banner is needed. CONFIGURATION.md has the full tutorial to install
  it with Docker; the repository also ships a ready-to-use
  `umami-docker-compose.yml`.
- **Google Analytics 4**: just paste the measurement ID
  (`G-XXXXXXXXXX`) into the dedicated field. Remember that in Europe
  GA requires cookie consent: switch on PyBlog's banner (step 2.12) and
  GA starts only after the visitor accepts.

Alternatively (or additionally), nginx still records every visit in
`/var/log/nginx/blog-access.log`, with no script in the pages.

To watch visits live:

    tail -f /var/log/nginx/blog-access.log

For a dashboard with charts (most viewed pages, visitors, countries):

    sudo apt install goaccess
    goaccess /var/log/nginx/blog-access.log

---

## PART 7 — Importing and exporting articles in Markdown

If you come from Hugo, Jekyll, or have articles written in Markdown, you can
import them all with one command (the editor must be off, or restart it after):

    python3 pyblog.py import-md folder-with-files/

You can also import a single file:

    python3 pyblog.py import-md article.md

PyBlog reads the "front matter" (the block between two `---` lines at the
start of the file, the one used by Hugo and Jekyll) and recognises these
fields, in Italian or in English:

    ---
    title: My article              (legacy titolo: also accepted)
    date: 2025-03-15               (legacy data: also accepted)
    description: A line for Google (legacy descrizione: also accepted)
    tags: [python, tutorial]       (or a simple comma-separated list)
    slug: my-article               (optional: generated from the title)
    status: published              (also accepted: stato: pubblicato / draft: false)
    ---

Prudent rules: if the status is not given, the article is imported as a
**draft**, so you can review it in the editor before publishing. If the
title is missing, the first `#` heading in the text or the file name is used.

The Markdown converter covers headings, bold, italic, inline and block code,
links, images, bulleted and numbered lists, quotes and horizontal rules. It
does not cover Markdown tables and footnotes: for tables, use the visual
editor after the import.

For the reverse path (backup or migration to another system):

    python3 pyblog.py export-md destination-folder/

Each article becomes a `.md` file with its front matter. The export is a
simplified conversion: the editor's advanced formatting (colours, alignment,
font sizes) becomes plain text, and numbered lists become bulleted.

---

## Day-to-day work summary

Scenario A (write locally, publish to the server):

1. Turn on the editor:      python3 pyblog.py serve
2. Open:                    http://localhost:8000
3. Write or edit an article, use the preview, save.
4. Stop the editor (Ctrl+C) and publish:
                            rsync -avz --delete output/ user@mysite.com:/var/www/blog/

Scenario B (editor on the server, SSH tunnel):

1. Open the tunnel:         ssh -L 8000:localhost:8000 user@mysite.com
2. Open:                    http://localhost:8000
3. Write, save. Done: nginx already serves the updated pages, no rsync.

Happy writing.
