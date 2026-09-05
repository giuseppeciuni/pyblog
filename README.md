# PyBlog

**English · [Italiano](README.it.md)**

**A complete blog engine in pure Python. Zero dependencies, in-browser visual editor, AI translation and blazing-fast static HTML.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![No dependencies](https://img.shields.io/badge/dependencies-zero-green.svg)](#)

PyBlog is a static blog generator written in **pure Python**, with not one external dependency: it runs with `python3` alone. Write your articles with a WYSIWYG editor in the browser, hit save, and PyBlog generates lightweight static HTML ready for nginx. No database, no framework, no `pip install`.

> Built for people who want a fast blog, who want to own their code and data, and who don't want to depend on WordPress or third-party platforms.

---

## Why PyBlog

- **Zero dependencies.** A thin `pyblog.py` entry point plus a small `core/` package, with the HTML in `templates/` and the CSS/JS in `static/`. You can read it, understand it, modify it. Python standard library only.
- **Migrate from Hugo/Jekyll in one command.** `python3 pyblog.py import-md posts/` reads your Markdown files with front matter and imports them all. Export back to Markdown any time: no lock-in, in either direction.
- **Visual editor in the browser.** Write like in Word (Quill WYSIWYG): bold, resizable images, syntax-highlighted code blocks, tables, YouTube videos.
- **Blazing-fast static HTML.** Public pages are static files served by nginx in milliseconds. Python only runs the admin area and can stay off.
- **Bilingual with AI translation.** Write in one language, translate to the other with one click (DeepL, Google, Claude, OpenAI or DeepSeek). The site becomes bilingual with a language switcher and a per-article English preview.
- **Full SEO, including author E-E-A-T.** Meta description, canonical, hreflang, Open Graph, Twitter Card, JSON-LD with a full schema.org Person (photo, job title, `sameAs` profiles), sitemap.xml, robots.txt, RSS, and even llms.txt for AI crawlers.
- **A complete reader experience out of the box.** Pagination, per-year archive, table of contents, related articles, prev/next navigation, author box, auto-generated favicon, dark mode that follows the system preference, keyboard-accessible focus states.
- **Hardened by default.** PBKDF2 password hashing, CSRF tokens on every state-changing request, sessions that expire, login rate limiting, upload size limits with magic-byte and SVG checks, path-traversal protection, security headers with a Content-Security-Policy, editor bound to localhost, Secure session cookies behind HTTPS, API keys via environment variables. Docker and systemd examples included.
- **SEO & backlink analysis with AI.** One click in the editor returns keywords, suggested tags, title variants, backlink anchor texts, internal links, FAQ for AI answer engines and article-specific advice.
- **Built-in analytics.** Google Analytics 4 or self-hosted Umami (cookie-free), enabled from Settings; tutorial and docker-compose included.
- **Your data.** Articles are plain JSON files. No lock-in, one-click backup.

## Screenshots

<!--
  TODO: add real screenshots here (see SCREENSHOT.md for the list).
  Example:
  ![Homepage](screenshots/homepage.png)
  ![Editor](screenshots/editor.png)
-->

*(Screenshots coming soon — see `SCREENSHOT.md` for how to generate them.)*

## Quick install

```bash
git clone https://github.com/giuseppeciuni/pyblog.git
cd pyblog
./install.sh
```

The script checks Python, sets the admin password and generates the site. Then:

```bash
python3 pyblog.py serve
```

Open **http://localhost:8000/admin** and start writing. Every save regenerates the HTML automatically.

No `install.sh`? Just three commands:

```bash
python3 pyblog.py password   # set the admin password
python3 pyblog.py build      # generate the site
python3 pyblog.py serve      # start the editor on localhost:8000
```

## How it works

```
   YOU (browser)                     PyBlog                  output/
  ┌──────────────┐  save     ┌──────────────────┐  generate┌──────────┐
  │ Quill editor │ ───────▶  │ pyblog.py serve  │ ───────▶ │ *.html   │
  │  (WYSIWYG)   │   JSON     │ (local server)   │  static  │ rss.xml  │
  └──────────────┘            └──────────────────┘   HTML   └──────────┘
                                                                  │
                                                            nginx serves
                                                            these files
```

You write in the editor → PyBlog saves the article as JSON and regenerates all the static pages → nginx serves them to the public. The Python server runs **only** the editor; the public site is the static files in `output/`.

## Project structure

```
pyblog.py              entry point: argument parsing and dispatch only
core/
  config.py            CONFIG_DEFAULT, load/save of config.json, schema migration,
                       language layout (main language at the root, the other in a subfolder)
  i18n.py              UI_TRANSLATIONS and the T() lookup
  render.py            the template engine (string.Template) with a cache,
                       plus esc() for HTML and js() for JavaScript
  articles.py          slugs, articles on disk, uploads and their validation,
                       Markdown import/export
  ai.py                translation (DeepL, Google, Claude, OpenAI, DeepSeek),
                       SEO description and reader preview, SEO analysis
  auth.py              password (PBKDF2), sessions, CSRF tokens, login rate limiting
  build.py             generation of the whole static site
  server.py            the HTTP handler and the administration pages
templates/
  base.html            the shared layout of every public page
  public/*.html        article, homepage, archive, tag, card, 404, training rights
  admin/*.html         admin layout, dashboard, editor, settings, login, password
static/
  common.css           design tokens shared by the public site and the admin area
  style.css            the public site
  admin.css            the administration area
  site.js              theme and client-side search (copied into output/)
  admin.js             the whole editor: Quill, uploads, tables, SEO panel, fetch calls
posts/                 the articles, one JSON file each
output/                the generated static site (this is what nginx serves)
config.json            the site configuration (created on the first save)
admin_password.txt     the password digest, never the password
```

Two rules run through the whole codebase:

- a value that ends up in **HTML** goes through `html.escape()` (`render.esc`);
- a value that ends up inside **JavaScript** goes through `json.dumps()` (`render.js`).

No translated string is ever concatenated into a script. The admin JavaScript
receives everything it displays as `window.PB_I18N`, and the public search
receives its labels as `window.PB_SITE`, so an Italian apostrophe can never
break the syntax.

## Commands

```bash
python3 pyblog.py serve             # start the editor on http://localhost:8000
python3 pyblog.py serve 9000        # ...on another port
python3 pyblog.py serve 8000 0.0.0.0  # ...reachable from the network (behind a proxy only)
python3 pyblog.py build             # regenerate the whole static site into output/
python3 pyblog.py password          # set or change the admin password
python3 pyblog.py import-md posts/  # import Markdown files (a file or a folder)
python3 pyblog.py export-md out/    # export every article to Markdown with front matter
```

`build` is also run automatically after every save, so you rarely need it by
hand: it is there for scripts, for a first run, and for after you have edited
`config.json` or a template by hand.

## Full feature list

**Writing**
- WYSIWYG editor (Quill): fonts, sizes, colors, alignment
- Resizable images by dragging the corners; PNG/JPEG/SVG upload
- Syntax-highlighted code blocks (Python, JS and more)
- Tables (manual or paste from Word), YouTube videos and video upload
- Strikethrough, subscript/superscript, checklists, indentation
- Live preview with the real site styling

**Publishing & SEO**
- Static HTML: homepage, articles, tag pages, RSS feed
- SEO: meta description, canonical, Open Graph, Twitter Card, JSON-LD
- sitemap.xml, robots.txt, llms.txt (for AI crawlers: ChatGPT, Claude, Perplexity)
- SEO description and reader preview can be generated with AI
- Estimated reading time, table of contents, related articles

**Multilingual**
- Bilingual site (e.g. Italian/English) with a language switcher
- The main language is chosen in the configuration (the other goes in a subfolder)
- Automatic translation with 5 providers: DeepL, Google, Claude, OpenAI, DeepSeek
- Translations are reviewed and confirmed before publishing
- The entire admin interface can run in English or Italian

**Administration**
- Password-protected admin area (PBKDF2 hashing, expiring sessions, CSRF tokens)
- Dashboard with article list, status, search, edit, delete
- Editor with a sidebar, responsive and mobile friendly
- Advanced section to edit config.json directly, with validation
- One-click backup/export of all content as a ZIP

**Reading**
- Browser-side full-text search with snippets and highlighting
- Light/dark theme with saved preference
- Homepage with introduction, editorial cards (bio, projects) and article grid
- Comments via Giscus or Disqus, your choice

**Under the hood**
- Zero dependencies: just `python3`
- Articles as JSON files (no database)
- Minimal CSS, system fonts, light JavaScript
- Templates as plain `.html` files rendered with `string.Template`
- One stylesheet and one script per audience, shared design tokens in `common.css`

## Requirements

Only **Python 3.8 or higher**. No `pip install`, no virtualenv.

## Documentation

- **`GUIDA.md`** — step-by-step guide (in Italian): install, write, publish online
- **`DEPLOY-REMOTO.md`** — deploy on an Ubuntu server with nginx, systemd and HTTPS
- **`CONFIGURATION.md`** — reference for all configuration parameters
- **`config.example.json`** — configuration template with all fields

## Production deployment

PyBlog runs on an Ubuntu server with nginx as a "gatekeeper": it serves the static pages to the public and forwards only the admin area to Python. When you publish an article, the pages regenerate themselves — no rsync, no manual deploy. The full guide with systemd and certbot (HTTPS) is in `DEPLOY-REMOTO.md`.

## Comments

PyBlog supports three options, chosen from the Settings page: none, **Giscus** (uses GitHub Discussions, free and tracking-free, ideal for technical blogs) or **Disqus** (social login, easier for readers). Configuration details in `GUIDA.md`.

## License

MIT — see the [LICENSE](LICENSE) file. You can use, modify and distribute it freely.

## Contributing

PyBlog is deliberately simple. Issues and pull requests are welcome: if you propose a feature, keep the project's philosophy in mind (zero dependencies, standard library only, explicit and readable code, comments in English).
