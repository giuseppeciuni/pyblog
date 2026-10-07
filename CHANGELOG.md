# Changelog

All notable changes to PyBlog are documented in this file.

## Unreleased

### Bug fixes

- **Word import: lines, pictures and captions come out as they were.**
  Three things went wrong in an imported document. A line break inside a
  paragraph (Shift+Enter) was written as a `<br>`, which the editor
  deletes: "ciao mamma." and "Si sono qui!" came out glued together. Each
  line is now a paragraph of its own (a space in headings and list items).
  A picture was glued to its caption or to the text of its paragraph, a
  floating one landed inside the sentence it was anchored to, and a picture
  in a frame with its caption (LibreOffice's captions, Word's text boxes)
  came out twice, the second time with the size of the frame. Pictures now
  get a line of their own, floating ones go before or after their paragraph
  together with their caption, and one that went from margin to margin
  fills the column. A table that only laid out the page (a single row or a
  single column: a picture beside a text, a picture with its caption)
  became a real table, whose header row showed everything in bold and in a
  smaller size: it is now taken apart, as a table pasted from Word already
  was, and a notice says so. The paragraphs of a field that spans several
  (a bibliography) are no longer merged into one.
- **The administration no longer looks unstyled after an update.** Its
  stylesheets and script had fixed addresses, so a cache in between (the
  browser's, or a CDN such as Cloudflare) could keep serving the old files
  with the new pages. Their addresses now carry a fingerprint of the
  content (`admin.css?v=...`), as the public site's already did.
- **A missing page shows the site's 404 page.** The preview answered with
  Python's bare error page and `nginx.conf.example` with nginx's: now both
  answer with the site's own page, search and latest articles included.
- **The systemd service starts without `/etc/pyblog.env`.** The file of
  secret keys is now optional in `pyblog.service.example`.
- **The editor no longer looks shrunk on a phone.** The help bubbles of the
  buttons were always there, just invisible, and the ones near the right
  edge made the page wider than the screen: the browser shrank the whole
  editor to fit.
- **A new article no longer overwrites an existing one.** Saving a new
  article whose title matched an existing article replaced it, autosave
  included. A new article now takes a free address and the editor says
  so; renaming an article onto another's address is refused.
- **Safe writes.** `config.json` and the articles are written to a
  temporary file and renamed into place, so an interruption leaves the old
  version instead of half a file. An unreadable `config.json` is copied to
  `config.broken.json` and the site starts on the defaults instead of not
  starting at all.
- **The login can no longer be locked by anyone.** The lock after wrong
  passwords was global: anybody could keep the author out. It now applies
  to the address that keeps failing, grows with each failure and is
  forgotten after an hour. Behind nginx the address comes from
  `X-Real-IP`, which `nginx.conf.example` now sets.
- **English as the main language.** Translation went from Italian to
  English whatever the main language was, and comments, previews and the
  editor's labels assumed Italian. Everything now follows `language`.
- **The editor no longer looks modified as soon as it opens.** Quill
  reported the content it had just loaded as typed by the author, so an
  untouched article asked to confirm leaving and a draft got a pointless
  autosave.
- **Ticks on inactive snippets survive an article save.** The editor only
  lists active snippets, and saving an article dropped its choices about
  the others.

- **Fixed lost tags on legacy articles.** The automatic schema migration
  from the old Italian keys did not map `tag` to `tags`: articles written
  before the rename lost their tags on the public pages, in the search
  index and in the RSS keywords, and opening them in the editor crashed
  with a `KeyError`. The mapping is now complete and the editor is
  defensive about missing keys.
- **Fixed the publication date being reset on every save.** The editor
  never sends the `date` field, so each save (including the automatic
  save before the English preview) silently replaced the original
  publication date with "now", changing the article order and the SEO
  `datePublished`. The date of the article on disk is now preserved,
  also when the slug changes.
- **Fixed the unstyled site subtitle.** The header emitted
  `class="subtitle"` while the stylesheet targeted `.site-subtitle`:
  one half of a renaming pass. The two now agree.

- **Fixed a broken image-overlay reference** that made the whole admin
  editor unusable in some cases: a `ReferenceError` thrown while attaching
  the image resize overlay interrupted the rest of the page's script,
  which meant the advanced JSON config editor never got its content
  loaded and later initialisation code never ran. This was a leftover
  from an earlier renaming pass that missed function references passed
  as callbacks (not directly called with parentheses).
- **Fixed images overflowing the editor** when resized larger than the
  editing area: `blot-formatter` writes an inline `width` style when you
  drag-resize an image, which overrides a plain CSS `max-width` rule.
  Images are now always visually contained within the editor (and within
  published articles), regardless of the size chosen when resizing.

### New features

- **A newsletter inside PyBlog.** Readers subscribe from a form in the
  sidebar or at the end of the articles, confirm through an email (double
  opt-in, with a button rather than a bare link, which mail scanners would
  follow) and get an email the first time an article is published, in
  their language, with one-click unsubscribe. Subscribers live in
  `subscribers.json` on the server; emails leave through the SMTP account
  set in the new Settings section, which also sends a test email, lists the
  subscribers and exports them as CSV. A hidden field and a per-address
  limit keep robots out. The public routes `/iscriviti`, `/conferma`,
  `/disiscrivi` and the admin routes `/newsletter-prova`,
  `/newsletter-rimuovi`, `/newsletter-iscritti.csv` are new: they are in
  `nginx.conf.example`, with a request limit of their own.
- **Earlier versions of an article.** Every save keeps the version it
  replaces (autosaves closer than ten minutes are merged, a published
  version is always kept, 50 per article, in `posts/.history/`). In the
  editor, "Earlier versions" lists them, shows one and brings it back into
  the fields, to be saved like any edit. Versions follow a renamed article,
  go with a deleted one and are in the backup. The admin routes `/versioni`
  and `/versione` are new: nginx must pass them to Python (they are in
  `nginx.conf.example`).
- **Scheduled publishing.** A draft can be scheduled for a date and time:
  readers cannot see it until then, and it goes out by itself within a
  minute, dated at that moment. The editor checks every minute while it
  runs, and every `build` publishes what is due, so a site rebuilt by cron
  works too. The article can still be edited, rescheduled, published at
  once or put back to draft; the Articles page labels it, says when it goes
  out and has a filter for it.
- **Choose on the page where a piece of code goes.** Next to the fixed
  positions, an external code can go "at a point you choose on the page":
  a window shows the real page (the homepage or an article, generated
  without any code), the blocks light up under the mouse, a click picks one
  and "before" or "after" says on which side. The same blocks are in a
  list, for the keyboard and screen readers. The point is saved so that it
  holds for every page of that kind ("After · Paragraph 2 of the text");
  the published page carries the code inert and `site.js` moves it there,
  waiting for consent when it needs it. Article-only code can use it too.
  The admin route `/scegli-punto` is new: nginx must pass it to Python
  (it is in `nginx.conf.example`).
- **External code explained with examples.** Above the list, a guide with
  three real cases (analytics, an ad halfway through the articles, any
  widget) shows the code a service gives you and what to choose here; the
  help texts of position and consent say which to pick for the common
  services.
- **One look for the whole platform.** Buttons, fields and focus are one
  family shared by the public site and the administration, dark theme
  included: login, password pages and confirmation windows no longer use
  Bootstrap's own blue, the editor lost its grey, purple and bordered
  buttons, every AI action looks the same. Words are the same everywhere
  ("site", "page", "Save and update the site", "Address (slug)"), and the
  tools of the menu say what they do under their name.
- **Two documents instead of seven.** `TUTORIAL.md` takes an empty Ubuntu
  server to the site online with HTTPS, one checked step at a time;
  `MANUALE.md` holds everything else, from every setting to every
  `config.json` key. They replace `GUIDA.md`, `GUIDE.md`,
  `CONFIGURAZIONE.md`, `CONFIGURATION.md` and `DEPLOY-REMOTO.md`. Both
  exist in English too: `TUTORIAL.en.md` and `MANUAL.en.md`.
- **Biography and projects on the homepage.** Each has a section of its
  own in the Settings and goes where the author wants it: in the sidebar,
  above or below the articles. The biography shows the photo and its first
  lines, with "Read the biography" leading to a page with the whole text,
  translated too. The projects are cards with name, short description,
  link and an optional image, which can be hidden and reordered: a grid in
  the main column, a list in the sidebar. Both stay off until turned on,
  and the placeholder Biography and Projects cards are gone from the
  starting configuration, so they do not show twice.
- **A side menu for the administration.** The top bar put pages and rare
  tools on the same level, and the tools came back as buttons on the
  dashboard. A side menu now keeps the pages at the top (Articles with
  their count, New article, Settings) and tools and account at the bottom;
  on a phone it becomes a bar at the bottom of the screen with "More" for
  the rest. In the editor it shrinks to icons, and on a phone it gives way
  to the publishing panel, fixed at the bottom of the screen.
- **A lighter dashboard.** The count boxes became All / Published / Drafts
  filters, the search has a label, and each row keeps only Edit in sight:
  preview, publish or unpublish and delete are in a "⋯" menu that works
  from the keyboard too.
- **Settings split by task.** One long page on two columns became nine
  sections - Site and author, Homepage, Pages, Comments, Translation,
  Analytics and ads, Cookies and privacy, AI training, Advanced - one at a
  time, listed in the side menu and, on a phone, in a list to open them
  from. Every field has its label with the help under it, and the save bar
  says whether something is waiting to be saved, can discard it, and warns
  before leaving the page.
- **Accessible administration.** Every field has a linked label, editors
  included; focus is visible everywhere; help texts reach 4.5:1 contrast;
  buttons are 40px tall on a computer and 44px on a phone, and fields use
  16px text so phones do not zoom in on them.

- **The editor's buttons follow the state of the article.** "Save and
  generate HTML" and "Save and close", with the status in a dropdown further
  down, left the author guessing whether saving would change the live site.
  The top of the sidebar now says what the article is - a draft readers
  cannot see, or published, with a link to its page - and offers what makes
  sense in that state: Save draft, Preview and Publish for a draft; Update,
  Preview and Unpublish for a published article. Publishing and unpublishing
  ask for confirmation, a line under the buttons tells about unsaved
  changes, "All articles" replaces "Save and close", and deleting moved to
  the bottom of the sidebar.
- **A preview that saves nothing.** Preview opens the real page as it is in
  the editor, in a new tab, without writing anything. The preview of the
  translation used to save the article first, which on a published article
  put the half-done changes online.
- **Two-column layout.** The homepage lists the articles on the left, each
  with a thumbnail and a short preview, and keeps a sidebar on the right:
  the introduction, the search, the "Explore" box with the card pages, the
  topics and the author's profiles. On an article the sidebar carries the
  table of contents, which follows the reading. On a phone the sidebar
  moves below and the menu opens from a button. `home_intro_position`
  ("sidebar" or "top") and `home_excerpt_words` replace `home_order`,
  which is kept in old configurations and ignored.
- **External code: templates, ad positions, per-article code.** "Add code"
  offers Google Analytics 4, Google Tag Manager, AdSense (auto ads or an
  ad unit), Google Ads, Meta Pixel and Microsoft Clarity: type the id and
  the code is written with a suitable position, scope and consent, and
  AdSense adds its line to `ads.txt`, which the build publishes. Four new
  positions for ads: `article_start`, `article_middle`, `home_feed` and
  `sidebar`. Each card folds to one line saying where the code goes, on
  which pages and with which consent; the code is edited in CodeMirror,
  with the textarea as a fallback. An article can switch off a snippet
  that goes on every article (`custom_code_off_ids`) and carry code of
  its own (`custom_code`).
- **Cookie consent banner.** With `consent.enabled`, the snippets marked
  `statistics` or `marketing`, and Google Analytics, reach the page as
  inert `<template>` elements and come alive when the visitor accepts
  their category; Google's tags are told through Consent Mode. The choice
  is kept in the visitor's browser, a "Cookie preferences" link in the
  footer reopens the banner, and raising `consent.version` asks everyone
  again.
- **Word import rewritten.** Nested lists, fields with links, text boxes,
  footnotes, superscripts and subscripts, alternative text and merged
  table cells now survive the import; hidden text and Word's table of
  contents no longer reach the article. The subtitle becomes the
  description when that is empty, and the notices about what was skipped
  arrive in one message. An imported article can be edited and saved
  without losses.

- **Custom code in the header menu.** A new position, "In the header menu",
  puts a snippet among the menu links, after RSS and before the language
  switcher, with their style. Made for an extra entry such as an "Ask the
  assistant" link that opens a chat widget instead of its floating bubble.

- **Word paste: layout tables are unwrapped.** Word represents "text
  next to an image" as an HTML table on the clipboard; every pasted
  table used to become one atomic, non-editable block. Pasted tables are
  now classified: layout tables (single row, single column, or tables
  wrapping other tables) are unwrapped into ordinary editable text and
  images; real data tables are rebuilt clean, keeping the images inside
  their cells (they were previously dropped) and handling nested tables
  correctly. Cell text is escaped while rebuilding.
- **A small table editor.** Clicking an embedded table in the editor
  opens a window where every cell can be edited and rows/columns added
  or removed; saving rewrites the table into the article. This works
  around Quill's inability to manage table cells in its document model.
- **SEO and backlink analysis in the editor.** A new sidebar action asks
  the configured LLM for a full analysis of the article: primary and
  long-tail keywords, suggested tags (with one-click apply), SEO title
  variants, a review of the meta description, anchor-text proposals for
  backlinks from an external site (configurable as `seo.backlink_site`),
  internal-link suggestions towards the blog's other articles, FAQ
  blocks for AI answer engines and article-specific AI-SEO advice. Every
  result has a copy button; the article's canonical URL is shown as the
  backlink target.
- **API keys from environment variables.** Every translation/AI key can
  be provided as `PYBLOG_<NAME>` (e.g. `PYBLOG_LLM_API_KEY`), taking
  precedence over `config.json`. The Settings page only ever shows what
  is written in the file, so a key provided through the environment
  never appears in any page. Meant for internet-facing deployments,
  together with the new `pyblog.service.example` systemd unit (dedicated
  user, sandboxing options, the key in `Environment=`).
- **Secure session cookie behind HTTPS.** When the reverse proxy sets
  `X-Forwarded-Proto: https`, the session cookie gains the `Secure`
  flag; on plain local HTTP the flag is omitted so login keeps working.
- **Deployment examples refreshed.** `nginx.conf.example` now shows the
  full single-VPS architecture (static site plus proxied admin routes,
  `X-Forwarded-Proto`, longer timeouts for AI calls, rate limiting on
  `/login`); the deployment guide's embedded nginx snippet was still
  using pre-rename Italian route names and has been fixed.
- **Visit statistics.** Two independent, optional integrations injected
  into the public pages only (the editor is never tracked): Google
  Analytics 4 (`analytics_id`) and self-hosted Umami (`umami_url` +
  `umami_website_id`, cookie-free). Both configurable from the Settings
  page; values are validated before being emitted into the pages. A
  ready-to-use `umami-docker-compose.yml` ships with the repository and
  the configuration reference gained a step-by-step Umami tutorial.

- **Recovering images pasted from Word.** Copying text and images
  together from a Word document and pasting them into the editor used to
  drop every image silently (Word's clipboard HTML references images by
  a local file path the browser cannot read). The editor now also reads
  the real image data the clipboard provides alongside the HTML, uploads
  each one, and splices them back into the pasted content in place of the
  broken references — with a status message confirming how many images
  were recovered.

### Breaking changes

- **Public CSS classes and HTML ids are now in English.** Every class and id
  used in the generated site (article cards, author box, breadcrumbs,
  article navigation, archive list, search box, table of contents, and
  more) has been renamed from Italian to English — for example
  `.autore-box` is now `.author-box`, `.nav-articoli` is now `.article-nav`,
  `id="contenuto"` is now `id="content"`.

  **If you have customised `style.css` or written your own CSS overrides
  for a PyBlog site, those selectors will stop matching after upgrading.**
  To fix this:
  1. Update any custom CSS selectors to the new English class names (see
     the table below for the full mapping).
  2. Rebuild the site (`python3 pyblog.py build`) so the generated HTML
     uses the new class names consistently with your updated CSS.

  This does **not** affect `config.json` or the article JSON files: their
  schema was already migrated to English in an earlier release, with
  automatic, transparent migration on load. This change only touches the
  presentation layer (CSS classes and a couple of HTML ids), not your data.

#### Class/id mapping

| Old (Italian)              | New (English)          |
|-----------------------------|-------------------------|
| `autore-box` (+ its `-bio`, `-foto`, `-nome`, `-ruolo`, `-social`, `-etichetta` variants) | `author-box` (+ matching `-bio`, `-photo`, `-name`, `-role`, `-social`, `-label`) |
| `briciole`                 | `breadcrumbs`           |
| `card-articolo`            | `article-card`          |
| `card-data`                | `card-date`             |
| `card-estratto`            | `card-excerpt`          |
| `card-hero-titolo`         | `card-hero-title`       |
| `card-home` (+ `-griglia`, `-titolo`, `-estratto`, `-vai`) | `home-card` (+ `-grid`, `-title`, `-excerpt`, `-link`) |
| `card-leggi`               | `card-read-more`        |
| `card-pagina`               | `card-page`              |
| `card-titolo`              | `card-title`            |
| `contenuto-principale`     | `main-content`          |
| `correlati`                | `related-articles`      |
| `griglia-articoli`         | `articles-grid`         |
| `indice-contenuti` / `-titolo` | `table-of-contents` / `toc-title` |
| `nav-articoli` (+ `-destra`, `-etichetta`, `-link`, `-titolo`, `-vuoto`) | `article-nav` (+ `-right`, `-label`, `-link`, `-title`, `-empty`) |
| `nessun-articolo`          | `no-articles`           |
| `ricerca`                  | `search-box`            |
| `salta-contenuto`          | `skip-to-content`       |
| `selettore-lingua` (+ `-home`) | `language-switcher` (+ `-home`) |
| `sezione-articoli` (+ `-blocco`) | `articles-heading` (+ `articles-section`) |
| `sezione-card-blocco`      | `cards-section`         |
| `sito` / `sito-nav`        | `site` / `site-nav`     |
| `sottotitolo`              | `site-subtitle`         |
| `tabella-articolo`         | `article-table`         |
| `archivio-elenco` / `-anno` / `-data` | `archive-list` / `archive-year` / `archive-date` |
| `blocco-html`              | `raw-html-block`        |
| `id="contenuto"`           | `id="content"`          |
| `id="articoli"`            | `id="articles"`         |

### Internal (no user impact)

- All JavaScript function names in the admin editor and public search
  widget have been translated from Italian to English (e.g. `salvaConfig`
  → `saveConfig`, `eliminaArticolo` → `deleteArticle`).
- All remaining Italian identifiers, comments, and hardcoded user-facing
  strings in `pyblog.py` have been translated or routed through the
  existing bilingual `T()` system.
- `install.sh`, `Dockerfile`, `docker-compose.yml`, and
  `nginx.conf.example` are now fully in English.
