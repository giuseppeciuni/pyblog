# PyBlog

**English · [Italiano](README.it.md)**

**A complete blog engine in a single Python file. Zero dependencies, in-browser visual editor, AI translation and blazing-fast static HTML.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![No dependencies](https://img.shields.io/badge/dependencies-zero-green.svg)](#)

PyBlog is a static blog generator written in **a single Python file**, with not one external dependency: it runs with `python3` alone. Write your articles with a WYSIWYG editor in the browser, hit save, and PyBlog generates lightweight static HTML ready for nginx. No database, no framework, no `pip install`.

> Built for people who want a fast blog, who want to own their code and data, and who don't want to depend on WordPress or third-party platforms.

---

## Why PyBlog

- **One file, zero dependencies.** Everything lives in `pyblog.py`. You can read it, understand it, modify it. Python standard library only.
- **Migrate from Hugo/Jekyll in one command.** `python3 pyblog.py import-md posts/` reads your Markdown files with front matter and imports them all. Export back to Markdown any time: no lock-in, in either direction.
- **Visual editor in the browser.** Write like in Word (Quill WYSIWYG): bold, resizable images, syntax-highlighted code blocks, tables, YouTube videos.
- **Blazing-fast static HTML.** Public pages are static files served by nginx in milliseconds. Python only runs the admin area and can stay off.
- **Bilingual with AI translation.** Write in one language, translate to the other with one click (DeepL, Google, Claude, OpenAI or DeepSeek). The site becomes bilingual with a language switcher and a per-article English preview.
- **Full SEO, including author E-E-A-T.** Meta description, canonical, hreflang, Open Graph, Twitter Card, JSON-LD with a full schema.org Person (photo, job title, `sameAs` profiles), sitemap.xml, robots.txt, RSS, and even llms.txt for AI crawlers.
- **A complete reader experience out of the box.** Pagination, per-year archive, table of contents, related articles, prev/next navigation, author box, auto-generated favicon, dark mode that follows the system preference, keyboard-accessible focus states.
- **Hardened by default.** PBKDF2 password hashing, login rate limiting, path-traversal protection, editor bound to localhost, Secure session cookies behind HTTPS, API keys via environment variables. Docker and systemd examples included.
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
- Password-protected admin area (SHA-256 hashing with salt, cookie sessions)
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

PyBlog is designed as a single-file project, deliberately simple. Issues and pull requests are welcome: if you propose a feature, keep the project's philosophy in mind (zero dependencies, single file, readable code).
