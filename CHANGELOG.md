# Changelog

All notable changes to PyBlog are documented in this file.

## Unreleased

### Bug fixes

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
