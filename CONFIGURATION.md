# PyBlog configuration reference

*In italiano: [CONFIGURAZIONE.md](CONFIGURAZIONE.md)*

All site parameters are stored in a single file: **`config.json`**,
in the project's main folder.

- The file is created automatically the first time you save the settings
  from the admin area ("Settings" page).
- It contains secret API keys, so it is excluded from git (see `.gitignore`).
- You will find a complete template with every field in **`config.example.json`**.

Normally you do not need to edit it by hand: everything is set from the
Settings page. But if you want to understand it or edit it over SSH, here
is every parameter.

## General parameters

| Parameter      | Meaning                                                            |
|----------------|--------------------------------------------------------------------|
| `site_title`  | The blog title, shown in the header and on pages.                 |
| `subtitle`  | A short sentence below the title.                                 |
| `author`       | The author's name (appears in SEO meta tags and in the footer).   |
| `base_url`     | The site domain, without trailing slash (e.g. `https://mysite.com`). Used for canonical URLs, sitemap and social tags. |
| `language`       | **Main site language** (`it` or `en`). Decides which language sits at the root `/`; the other goes into a subfolder (`/en/` or `/it/`). |
| `admin_language` | Language of the administration interface (`it` or `en`). Can also be switched with the EN/IT button in the admin bar. |
| `articles_per_page` | How many articles to show on each homepage page (default `10`). The next pages are generated at `/pagina/2.html`, `/pagina/3.html`... (in English, `/en/page/2.html`). With `0`, pagination is disabled and all articles fit on one page. |
| `home_intro_position` | Where the homepage introduction (`home_content`) goes: `"sidebar"` (default) in the first box of the sidebar, so the articles start at the top; `"top"` above the list of articles. Set it from the Settings page, "Homepage" section. |
| `home_excerpt_words` | How many words of an article the lists show (homepage, tags, archive) when you have not written a preview (default `40`). The excerpt takes the text only, no headings, and stops at the end of a word. |
| `home_order`  | No longer used. It ordered the sections of the old one-column homepage; with two columns the articles sit on the left and the rest in the sidebar, so there is no order left to choose. Old configurations keep it and it is ignored. |

## Homepage content

| Parameter        | Meaning                                                          |
|------------------|-------------------------------------------------------------------|
| `home_content` | HTML of the top part of the homepage (biography, introduction). Written with the visual editor, not by hand. |
| `home_cards_enabled` | Master switch of the cards block (default `true`). With `false` the whole block disappears from the homepage, whatever each card says, and their pages are not generated. Can also be set from the Settings page, "Pages" section. |
| `home_cards`      | List of the editorial "cards" (Biography, Projects, etc.), listed in the "Explore" box of the sidebar: each one has a page of its own. Each card has `active` (true/false), `title` and `content`. A card with `active` set to `false`, or with no content, does not appear and has no page of its own. |

## SEO and author data (`seo`)

This data feeds the schema.org structured data (Person, WebSite, Article)
and the social meta tags of every page. It helps Google recognise the author
as a real person (E-E-A-T signals) and connect their public profiles
together. All fields are optional and can also be set from the Settings
page, "Site and author" section.

| Parameter         | Meaning                                                      |
|-------------------|---------------------------------------------------------------|
| `author_url`      | URL of the author's personal or professional page.           |
| `author_image` | Absolute URL of a photo of the author (Person schema).       |
| `author_role`    | Job title (e.g. "CTO and lecturer"), the `jobTitle` field.   |
| `author_bio`      | Short bio (1-2 sentences), the `description` field of Person. |
| `social_profiles`  | List of public profile URLs (GitHub, LinkedIn, X...). Becomes the `sameAs` field: the most important signal to connect profiles. |
| `logo`            | Absolute URL of the site logo (publisher schema).            |
| `twitter_site`    | The site's X/Twitter account, with the at sign (e.g. `@name`). |
| `favicon`         | URL of a custom favicon. If empty, PyBlog generates `favicon.svg` with the initial of the site title. |
| `backlink_site`   | External site that republishes the articles and hosts the backlinks towards the blog (e.g. `startupbusiness.it`). The editor's SEO analysis uses it to propose anchor texts that fit that editorial context. |

## Comments

| Parameter  | Meaning                                                                |
|------------|------------------------------------------------------------------------|
| `comments` | Comment system: `none` (none), `giscus` or `disqus`.               |
| `giscus`   | If you use Giscus: `repo`, `repo_id`, `category`, `category_id`, `theme`. |
| `disqus`   | If you use Disqus: `shortname`.                                        |

## Visit statistics (analytics)

PyBlog supports two statistics systems, independent of each other: you
can use one, both or neither. The scripts are only injected into the
public pages: the editor and the administration area are never tracked.
All the fields can also be set from the Settings page.

| Parameter          | Meaning                                                     |
|--------------------|-------------------------------------------------------------|
| `analytics_id`     | Google Analytics 4 measurement ID (format `G-XXXXXXXXXX`). Empty = GA disabled. |
| `umami_url`        | Base URL of your self-hosted Umami instance (e.g. `https://stats.mysite.com`), without a trailing slash. |
| `umami_website_id` | The website ID (a UUID) shown by Umami when you register the site. It works together with `umami_url`: if either is empty, Umami is disabled. |

**Which one to choose?** Google Analytics uses cookies and, in Europe,
requires a prior consent banner (GDPR). Umami uses no cookies: no
banner, the data stays on your server and the pages are faster. For a
personal blog it is the recommended choice.

If you use Google Analytics, PyBlog has a banner of its own: with consent
switched on (see [Cookie consent](#cookie-consent-consent)) the GA script
starts only after the visitor accepts the statistics.

### Tutorial: installing Umami with Docker

The repository ships a ready-to-use `umami-docker-compose.yml`.

1. Copy the file to your server (e.g. `/opt/umami/docker-compose.yml`)
   and open it: replace `CAMBIAMI_PASSWORD_DB` (in **two** places, it
   must be identical) with a database password of your choice, and
   `CAMBIAMI_SEGRETO_CASUALE` with a string generated by
   `openssl rand -base64 32`.
2. Start it: `docker compose up -d`. Umami listens on `127.0.0.1:3000`
   only, on purpose: it must not be exposed directly.
3. Expose it through your reverse proxy. nginx example for
   `stats.mysite.com`:

   ```nginx
   server {
       server_name stats.mysite.com;
       location / {
           proxy_pass http://127.0.0.1:3000;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   Then the certificate: `certbot --nginx -d stats.mysite.com`.
4. First login at `https://stats.mysite.com` with `admin` / `umami`:
   **change the password right away** (Settings -> Profile).
5. Register the blog: Settings -> Websites -> Add website, with the
   site's domain. Umami shows you the **Website ID** (a UUID): it is
   the only piece of data you need; the script tag Umami proposes can
   be ignored.
6. In PyBlog, Settings page: paste the instance URL and the Website ID
   into the two Umami fields and save. The site is rebuilt with the
   script in place.

To verify: open the blog in a private window and check Umami's
Realtime view: the visit shows up within seconds. Note that many ad
blockers block statistics scripts (Umami included): the numbers will
always be somewhat underestimated, whatever system you use.

Finally, remember backups: the `umami-db` Docker volume holds the whole
statistics history.

## External code and ads (`custom_code`)

Pieces of HTML or JavaScript injected into the public pages: Google
Analytics, AdSense, Tag Manager, pixels, chat widgets, embeds. They are
managed from the Settings page, "Analytics and ads" section, and each
piece has four choices: where it goes in the page, which pages it appears
on, whether it must wait for the visitor's consent, and the code itself.

The "Add code" button offers the most common services (Google Analytics 4,
Google Tag Manager, AdSense auto ads or a single ad unit, Google Ads, Meta
Pixel, Microsoft Clarity): type the id and the code is prepared with a
suitable position, pages and consent. "Your own code" is the empty card,
for everything else.

`custom_code` is a list; each item is an object with these fields:

| Field      | Meaning                                                         |
|------------|-----------------------------------------------------------------|
| `id`       | Stable identifier (`snip-xxxxxxxx`), generated on its own. Articles refer to a snippet by this, not by name: renaming one breaks nothing. |
| `name`     | The name you see in the Settings page. It never reaches the pages. |
| `enabled`  | `true` or `false`. Off means off everywhere, without deleting it. |
| `position` | Where it lands in the page (see below).                         |
| `scope`    | Which pages it appears on (see below).                          |
| `consent`  | The consent it waits for: `necessary` (always runs, the default), `statistics` or `marketing` (advertising). Only matters with the consent banner switched on. |
| `code`     | The code, injected **verbatim**, with no transformation at all.  |

**The positions (`position`)**

| Value           | Where it lands                                                |
|-----------------|---------------------------------------------------------------|
| `head`          | Inside `<head>`. For meta tags and scripts that must start early. |
| `body_start`    | Right after `<body>`, before the site header.                  |
| `body_end`      | At the end of the page, after everything else. The right place for `defer` or `async` scripts. |
| `after_header`  | Below the site header, before the content. Visible.            |
| `before_footer` | After the content, before the footer. Visible.                 |
| `article_end`   | At the end of the article text, before the author box. It exists **on articles only**: on any other page the code does not appear. |
| `nav`           | In the header menu, after RSS and before the language switcher. For an extra entry, such as `<a href="#" data-vaitony-apri>Ask the assistant</a>` opening a chat widget: it takes the style of the other menu links. |
| `sidebar`       | In the sidebar, after the introduction: the place for a 300x250 ad or a widget. It exists on the homepage, the articles, the tags, the archive and the cards. |
| `home_feed`     | Between the homepage articles, after the third. It exists **on the homepage only**. |
| `article_start` | At the start of the article, after the title and the cover, before the text. **Articles only**. |
| `article_middle`| Half way through the article, after the paragraph nearest the middle of the text: never inside a table or a list, never between a heading and its paragraph. An article too short to have a middle gets it at the end of the text. **Articles only**. |

**The scopes (`scope`)**

| Value           | Which pages                                                   |
|-----------------|---------------------------------------------------------------|
| `home`          | The homepage only.                                            |
| `articles`      | The articles only, all of them.                               |
| `home_articles` | The homepage and every article.                               |
| `optin`         | Only the articles that tick it in the editor.                 |
| `home_optin`    | The homepage, plus the articles that tick it in the editor.   |
| `all`           | The whole site: the archive, the tag pages, the cards and the 404 page included. |

**What a single article decides.** In the editor, the "External code"
box lists the site's snippets that may appear on that article: the "tick
to enable" ones (scope `optin` or `home_optin`) appear only when ticked;
the "by default" ones (every other scope) appear until you untick them,
which is how one article does without, say, an ad the others carry.
Below it, "For this article only" holds code that appears there and
nowhere else: a dedicated ad, an embed. In the article's JSON:

| Field                 | Meaning                                               |
|-----------------------|-------------------------------------------------------|
| `custom_code_ids`     | The `id` of the ticked "tick to enable" snippets.     |
| `custom_code_off_ids` | The `id` of the "by default" snippets switched off on this article. |
| `custom_code`         | The article's own snippets, with the same fields as the site's minus `scope` (their only page is the article); their `id` starts with `art-`. |

The editor only lists the active snippets, but the choices about the
inactive ones stay saved: switch one back on and every article finds it
the way it left it. Deleting a snippet from the Settings page is safe:
the id left behind in the articles no longer matches anything and is
ignored.

**ads.txt (`ads_txt`).** The text of the `/ads.txt` file, which says who
may sell advertising on the site: AdSense looks for it and limits the
ads until it finds it. The AdSense template adds its own line by itself
(`google.com, pub-..., DIRECT, f08c47fec0942fa0`). When empty, the file
is not published (and removed if it was there).

**A note on trust.** The code is written into the page with no checking
at all, because checking it would mean stopping it from working. Anyone
who can log into the administration area can therefore run any
JavaScript on the public site: only paste code you trust, and keep the
administration password safe.

## Cookie consent (`consent`)

In Europe, statistics and advertising that use cookies may start only
after the visitor consents. PyBlog has a banner of its own: switch it on
from the Settings page, "Cookies and privacy" section.

| Field         | Meaning                                                    |
|---------------|------------------------------------------------------------|
| `enabled`     | `true` shows the banner to visitors (default `false`).     |
| `text`        | The banner text in the main language. Empty = the default text. |
| `text_en`     | The banner text in the site's other language. Empty = the default text. |
| `privacy_url` | The address of the privacy policy, linked from the banner. |
| `version`     | A number raised by the "Ask everyone for consent again" button: whoever chose under an older number sees the banner again. Use it when you add a service. |

**How it works.** With the banner on, the snippets marked `statistics` or
`marketing` (and Google Analytics) reach the page inside a `<template>`,
which the browser does not run: no scripts, no cookies, no requests. When
the visitor accepts a category, `site.js` turns them into live code in
the very place they stand. Google's tags receive the choice through
**Consent Mode** (everything denied until the visitor decides). The choice
stays in the visitor's browser; the "Cookie preferences" link in the
footer reopens the banner, and withdrawing a consent reloads the page
without that code.

The banner appears only when some code needs it: with consent switched on
but every snippet `necessary`, nothing shows.

**AdSense.** To show ads in Europe Google also asks for a certified CMP
(TCF). You can switch on Google's free message from the AdSense dashboard
("Privacy & messaging") and leave the AdSense code on `necessary`, or use
PyBlog's banner with AdSense on `marketing`: the ads then start only after
consent.

## Automatic translation (from the main language to the other)

Translation always goes from the site's main language (`language`) to the
other one: from Italian to English, or from English to Italian when the
site is in English.

Inside the `translation` section:

| Parameter          | Meaning                                                      |
|--------------------|---------------------------------------------------------------|
| `service`         | Which service to use: `deepl`, `google`, `llm` (Anthropic), `openai` or `deepseek`. |
| `deepl_api_key`    | DeepL API key.                                                |
| `google_api_key`   | Google Cloud Translation API key.                            |
| `llm_api_key`      | Anthropic (Claude) API key.                                  |
| `llm_endpoint`     | Anthropic API endpoint (normally left unchanged).            |
| `llm_model`      | Claude model to use.                                          |
| `openai_api_key`   | OpenAI API key.                                               |
| `openai_model`   | OpenAI model (e.g. `gpt-4o-mini`).                            |
| `deepseek_api_key` | DeepSeek API key.                                             |
| `deepseek_model` | DeepSeek model (e.g. `deepseek-chat`).                        |

If you enter no key, translation stays disabled and the blog works normally
in the main language. Keys stay on the server and are never visible on
public pages.

### API keys from environment variables

On an internet-facing server it is better not to write the API keys in
`config.json`. Every key of the `translation` section can be provided
through an environment variable, which takes precedence over the file:
the name is `PYBLOG_` plus the parameter name in upper case. Examples:
`PYBLOG_LLM_API_KEY`, `PYBLOG_OPENAI_API_KEY`,
`PYBLOG_DEEPSEEK_API_KEY`, `PYBLOG_DEEPL_API_KEY`,
`PYBLOG_GOOGLE_API_KEY`. In production put the variable in `/etc/pyblog.env` with `600`
permissions, read by the systemd unit through `EnvironmentFile=` (see
`pyblog.service.example` and DEPLOY-REMOTO.md); locally an `export`
before starting the editor is enough: the key never touches the project folder,
never ends up in `config.json` backups and never appears in the
Settings page.

## Adding parameters in the future

The system is designed to grow: to add a new parameter, just put it in
`CONFIG_DEFAULT` inside `pyblog.py`. All existing articles and configurations
keep working, because new parameters receive their default value until you
set them.

## Migrating from earlier versions

Earlier versions used Italian keys (`titolo_sito`, `stato`, `contenuto`...).
**Nothing to do on your side**: on the first start PyBlog detects the old
format, converts `config.json` and the article files to the new English
schema and rewrites them on disk. The migration runs once and is automatic.

**An unreadable `config.json`** (broken JSON, say after a hand edit) no
longer stops the site: PyBlog warns on the terminal, keeps a copy in
`config.broken.json` and starts on the default values. Recover your data
from the copy before saving the Settings again. Files are always written
"all or nothing": an interruption half way leaves the old version, never
half a file.

## AI training rights (`ai_training`)

Declares whether and under what conditions the blog's content may be used
to train AI models. Set from the Settings page, "AI training" section.

| Parameter        | Meaning                                                          |
|------------------|--------------------------------------------------------------------|
| `policy`         | `"open"` (no restriction), `"licensed"` (requires a licence; known AI crawlers are blocked in robots.txt, with a contact to negotiate) or `"disallow"` (blocked, no licence offered). |
| `contact_email`  | Email for licensing inquiries (shown only with `"licensed"`).     |
| `license_url`    | URL of your own licence terms. If empty, PyBlog's own generated page is used (`/training-rights.html`). |
| `statement`      | Custom text replacing the default wording.                       |

The choice is reflected in `robots.txt` (blocking known AI crawlers), in
`llms.txt`, in `/.well-known/ai.txt` and `/.well-known/tdmrep.json` (a
good-faith attempt to follow the TDM Reservation Protocol, a non-binding,
still-evolving industry convention), and on the public
`/training-rights.html` page.
