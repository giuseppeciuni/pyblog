# PyBlog

**[English](README.md) · Italiano**

**Un motore di blog completo in Python puro. Zero dipendenze, editor visuale nel browser, traduzione AI e HTML statico velocissimo.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![No dependencies](https://img.shields.io/badge/dependencies-zero-green.svg)](#)

PyBlog è un generatore di blog statico scritto in **Python puro**, senza una sola dipendenza esterna: gira con il solo `python3`. Scrivi gli articoli con un editor WYSIWYG nel browser, premi salva, e PyBlog genera HTML statico leggerissimo pronto per nginx. Niente database, niente framework, niente `pip install`.

> Pensato per chi vuole un blog veloce, possederne il codice e i dati, e non dipendere da WordPress o da piattaforme di terze parti.

---

## Perché PyBlog

- **Zero dipendenze.** Un `pyblog.py` sottile come punto di ingresso e un piccolo pacchetto `core/`, con l'HTML in `templates/` e CSS/JS in `static/`. Lo leggi, lo capisci, lo modifichi. Solo libreria standard di Python.
- **Migra da Hugo/Jekyll con un comando.** `python3 pyblog.py import-md posts/` legge i tuoi file Markdown con front matter e li importa tutti. E puoi esportare in Markdown quando vuoi: nessun lock-in, in nessuna direzione.
- **Scrivi in Word, pubblica qui.** Trascini un `.docx` nell'editor e arriva con titoli, elenchi, tabelle e immagini. Fatto con `zipfile` e `xml.etree`, come tutto il resto: niente `python-docx`.
- **Editor visuale nel browser.** Scrivi come su Word (Quill WYSIWYG): grassetto, immagini ridimensionabili, blocchi di codice con evidenziazione, tabelle, video YouTube.
- **HTML statico velocissimo.** Le pagine pubbliche sono file statici serviti da nginx in pochi millisecondi. Python gira solo per l'area admin e può stare spento.
- **Bilingue con traduzione AI.** Scrivi in una lingua, traduci nell'altra con un clic (DeepL, Google, Claude, OpenAI o DeepSeek). Il sito diventa bilingue con selettore di lingua e anteprima della traduzione per ogni articolo.
- **SEO completo, autore incluso (E-E-A-T).** Meta description, canonical, hreflang, Open Graph, Twitter Card, JSON-LD con schema.org Person completo (foto, ruolo, profili `sameAs`), sitemap.xml, robots.txt, RSS, e perfino llms.txt per i crawler AI.
- **Esperienza di lettura completa, di serie.** Paginazione, archivio per anno, indice dei contenuti, articoli correlati, navigazione precedente/successivo, box autore, favicon generata automaticamente, tema scuro che segue la preferenza di sistema, focus visibile per chi naviga da tastiera.
- **Sicuro di default.** L'amministrazione può stare su un indirizzo suo (`admin.tuodominio.it`), separata dal codice esterno delle pagine pubbliche. Password con PBKDF2, token CSRF su ogni richiesta che cambia qualcosa, sessioni che scadono, blocco dei tentativi di accesso, limiti e controlli sui file caricati (contenuto vero e SVG), protezione dal path traversal, intestazioni di sicurezza con Content-Security-Policy, editor in ascolto solo su localhost, cookie di sessione Secure dietro HTTPS, chiavi API da variabili d'ambiente. Esempi Docker e systemd inclusi.
- **Analisi SEO e backlink con AI.** Un clic nell'editor e ottieni keyword, tag consigliati, varianti di titolo, anchor text per i backlink, link interni, FAQ per i motori AI e consigli specifici per l'articolo.
- **Statistiche integrate.** Google Analytics 4 o Umami self-hosted (senza cookie), attivabili dalle Impostazioni; tutorial e docker-compose inclusi.
- **Si gestisce da solo.** Una libreria dei media, backup e ripristino dal menu con un clic, e aggiornamenti con un clic che provano la versione nuova prima di passarci.
- **Tuoi i dati.** Gli articoli sono semplici file JSON. Nessun lock-in, backup in un clic.

## Screenshot

<!--
  TODO: aggiungi qui gli screenshot reali (vedi SCREENSHOT.md per la lista).
  Esempio:
  ![Homepage](screenshots/homepage.png)
  ![Editor](screenshots/editor.png)
-->

*(Screenshot in arrivo — vedi `SCREENSHOT.md` per come generarli.)*

## Installazione rapida

```bash
git clone https://github.com/giuseppeciuni/pyblog.git
cd pyblog
./install.sh
```

Lo script verifica Python, imposta la password di amministrazione e genera il sito. Poi:

```bash
python3 pyblog.py serve
```

Apri **http://localhost:8000/admin** e inizia a scrivere. Ogni salvataggio rigenera l'HTML automaticamente.

Niente `install.sh`? Bastano tre comandi:

```bash
python3 pyblog.py password   # imposta la password admin
python3 pyblog.py build      # genera il sito
python3 pyblog.py serve      # avvia l'editor su localhost:8000
```

**Su un server** segui il [`TUTORIAL.md`](TUTORIAL.md): da un server Ubuntu
vuoto al sito online con HTTPS, con nginx in una delle sue due forme —
l'amministrazione su `tuodominio.it/admin`, oppure su un indirizzo suo,
`admin.tuodominio.it`.

## Come funziona

```
   TU (browser)                      PyBlog                  output/
  ┌──────────────┐  salva    ┌──────────────────┐  genera  ┌──────────┐
  │ editor Quill │ ───────▶  │ pyblog.py serve  │ ───────▶ │ *.html   │
  │  (WYSIWYG)   │   JSON     │ (server locale)  │  HTML    │ rss.xml  │
  └──────────────┘            └──────────────────┘  statico └──────────┘
                                                                  │
                                                           nginx serve
                                                           questi file
```

Scrivi nell'editor → PyBlog salva l'articolo come JSON e rigenera tutte le pagine statiche → nginx le serve al pubblico. Il server Python serve **solo** l'editor; il sito pubblico sono i file statici in `output/`.

## Struttura del progetto

```
pyblog.py              punto di ingresso: solo lettura degli argomenti e smistamento
core/
  config.py            CONFIG_DEFAULT, lettura/scrittura di config.json, migrazione
                       delle impostazioni vecchie, lingue (la principale alla radice)
  i18n.py              i testi dell'interfaccia in italiano e inglese, e T()
  render.py            il motore dei modelli (string.Template) con cache,
                       più esc() per l'HTML e js() per il JavaScript
  articles.py          slug, articoli su disco, versioni, caricamenti e loro
                       controllo, import/export Markdown
  images.py            controllo e ottimizzazione delle immagini caricate
  media_library.py     la pagina Media: ogni file caricato e dove è usato
  docx_import.py       Word .docx -> HTML, fatto con zipfile e xml.etree
  ai.py                traduzione (DeepL, Google, Claude, OpenAI, DeepSeek),
                       descrizione SEO e anteprima per i lettori, analisi SEO
  newsletter.py        iscrizioni con doppia conferma, email via SMTP
  auth.py              password (PBKDF2), sessioni, token CSRF, limite ai tentativi
  build.py             generazione dell'intero sito statico
  settings_panel.py    il pannello Impostazioni: sezioni, gruppi, cosa manca
  backup.py            backup da scaricare, ripristino, backup automatici
  updates.py           controllo e installazione di una versione nuova (git)
  legacy_names.py      i vecchi nomi delle classi, per aggiornare i selettori salvati
  server.py            il gestore HTTP e le pagine dell'amministrazione
  bundle.py            costruisce la versione in un solo file
templates/
  base.html            l'impaginazione comune di ogni pagina pubblica
  public/*.html        articolo, home, archivio, tag, serie, lab, pagine,
                       newsletter, 404...
  admin/*.html         elenco, editor, impostazioni, media, ripristino, aggiornamenti, accesso...
static/
  common.css           i valori di design comuni a sito pubblico e amministrazione
  style.css            il sito pubblico
  admin.css            l'amministrazione
  site.js              tema, ricerca, banner del consenso (copiato in output/)
  admin.js             tutto l'editor: Quill, caricamenti, tabelle, pannello SEO, chiamate
tests/                 i test, un file per area (python3 tests/test_x.py)
test_docx/             documenti .docx di prova e i test dell'import da Word
nginx.conf.example     nginx con l'amministrazione su tuodominio.it/admin
nginx.separate-admin.conf.example
                       nginx con l'amministrazione su admin.tuodominio.it
pyblog.service.example il servizio systemd
posts/                 gli articoli, un file JSON ciascuno
output/                il sito statico generato (è quello che serve nginx)
config.json            la configurazione del sito (creata al primo salvataggio)
admin_password.txt     l'impronta della password, mai la password
```

Due regole valgono in tutto il codice:

- un valore che finisce nell'**HTML** passa da `html.escape()` (`render.esc`);
- un valore che finisce dentro il **JavaScript** passa da `json.dumps()` (`render.js`).

Nessun testo tradotto viene mai incollato dentro uno script. Il JavaScript
dell'amministrazione riceve tutto ciò che mostra come `window.PB_I18N`, e la
ricerca pubblica riceve le sue etichette come `window.PB_SITE`: un apostrofo
italiano non può mai rompere la sintassi.

## Comandi

```bash
python3 pyblog.py serve             # avvia l'editor su http://localhost:8000
python3 pyblog.py serve 9000        # ...su un'altra porta
python3 pyblog.py serve 8000 0.0.0.0  # ...raggiungibile dalla rete (solo dietro un proxy)
python3 pyblog.py build             # rigenera tutto il sito statico in output/
python3 pyblog.py password          # imposta o cambia la password admin
python3 pyblog.py import-md posts/  # importa file Markdown (un file o una cartella)
python3 pyblog.py import-docx doc/  # importa documenti Word come bozze (un file o una cartella)
python3 pyblog.py export-md out/    # esporta ogni articolo in Markdown con front matter
python3 pyblog.py bundle            # crea pyblog_standalone.py, la versione in un solo file
```

`build` parte da solo dopo ogni salvataggio, quindi a mano serve di rado: è
lì per gli script, per il primo avvio e per quando hai modificato a mano
`config.json` o un modello.

### La versione in un solo file

`python3 pyblog.py bundle` scrive **`pyblog_standalone.py`**: un unico script
con tutti i moduli, tutti i modelli e il CSS/JavaScript incorporati come
stringhe, per chi preferisce scaricare un file invece di una cartella.
Supporta tutti i comandi tranne `bundle` stesso, e produce lo stesso
identico sito.

```bash
python3 pyblog.py bundle          # da una copia del progetto, scrive pyblog_standalone.py
python3 pyblog_standalone.py serve  # altrove: non serve altro
```

È un prodotto della costruzione, non un secondo codice: le correzioni si
fanno in `core/` e poi lo si genera di nuovo.

## Import da Word

`python3 pyblog.py import-docx documento.docx`, oppure il pulsante **Importa
da Word (.docx)** nell'editor, trasforma un documento Word in un articolo. Il
pulsante mette il risultato nell'editor senza salvarlo, così lo rivedi prima;
la riga di comando importa come bozze, per lo stesso motivo.

Un `.docx` è uno ZIP di parti XML, quindi PyBlog lo legge con `zipfile` e
`xml.etree` — niente `python-docx`, niente `mammoth`, nessuna dipendenza.

**Cosa viene convertito**

| Word | Diventa |
|---|---|
| Titoli (anche con gli stili localizzati, es. `Titolo 2`) | `<h2>`-`<h6>`: il livello più alto usato diventa `<h2>` |
| Grassetto, corsivo, sottolineato, barrato | `<strong> <em> <u> <s>` |
| Formattazione portata da uno stile di paragrafo o di carattere | gli stessi tag |
| Allineamento centrato / a destra / giustificato | le classi `ql-align-*` dell'editor |
| Elenchi puntati e numerati, anche annidati | `<ul>` / `<ol>` |
| Tabelle | `<table class="article-table">`, prima riga come intestazione |
| Immagini incorporate (PNG, JPEG, GIF, WebP) | salvate in `media/`, `<img loading="lazy">`, con il loro testo alternativo |
| Una didascalia sotto un'immagine ("Inserisci didascalia") | `<figure>` con `<figcaption>` |
| A capo dentro un paragrafo | righe separate, come le scrive l'editor |
| Inserimenti con revisioni attive | testo normale |

Il Titolo del documento (o il suo primo Titolo 1) diventa il titolo
dell'articolo e viene tolto dal testo, perché diventa l'`<h1>` della pagina.
Se manca, si usa il nome del file.

**Cosa viene scartato, e perché**

- **Immagini WMF ed EMF.** Word le incorpora volentieri e nessun browser le
  mostra. Vengono rifiutate con un avviso che nomina il file.
- **Immagini collegate (non incorporate).** I byte stanno sul disco
  dell'autore, non nel documento: non c'è niente da estrarre.
- **Link che non sono http, https o mailto.** Un `javascript:` o un `file:`
  non ha posto in una pagina pubblicata. Il testo del link resta.
- **Una tabella dentro una tabella.** Word le usa per impaginare; quella
  interna viene ridotta al suo testo.
- **Cancellazioni con revisioni, commenti, intestazioni e piè di pagina,
  equazioni, campi, font, colori, dimensioni, interruzioni di pagina e
  impostazioni di sezione.** Un articolo di blog non li porta.

Ogni conversione dice cosa ha scartato: con dei messaggi nell'editor, con
righe `warning:` sulla riga di comando. Altri due limiti da sapere: senza
`numbering.xml` ogni elenco diventa puntato (un pallino al posto di un
numero è una piccola perdita; numeri inventati sarebbero sbagliati), e il
caricamento si ferma a 30 MB.

## Funzionalità complete

**Scrittura**
- Editor WYSIWYG (Quill): font, dimensioni, colori, allineamento
- Import da Word (.docx): titoli, formattazione, elenchi annidati, tabelle con celle unite, immagini con testo alternativo e didascalia, note, link, caselle di testo
- Pulsanti che seguono lo stato dell'articolo: Salva bozza e Pubblica per una bozza, Aggiorna e Ritira per un articolo pubblicato; anteprima della pagina vera senza salvare; salvataggio automatico delle bozze, Ctrl+S, avviso per le modifiche non salvate
- Immagini ridimensionabili trascinando gli angoli; caricamento PNG/JPEG/GIF/WebP/SVG, oppure scelta di una già presente nei Media
- Testo alternativo e didascalia per ogni immagine (anche da Word), con il conto delle immagini che ancora non ce l'hanno
- L'editor cresce con il testo e mostra gli stessi spazi della pagina; **Allarga** gli dà tutto lo schermo
- Blocchi di codice con evidenziazione sintassi (Python, JS e altri)
- Tabelle (manuali o copia-incolla da Word), video YouTube e caricamento video
- Barrato, pedice/apice, liste di controllo, rientri
- Anteprima dal vivo con la grafica del sito vero
- Serie di articoli e "lab" (il lato pratico di un articolo, con il suo repository)

**Pubblicazione e SEO**
- HTML statico: home, articoli, pagine dei tag, feed RSS
- SEO: meta description, canonical, Open Graph, Twitter Card, JSON-LD
- sitemap.xml, robots.txt, llms.txt (per i crawler AI: ChatGPT, Claude, Perplexity)
- Descrizione SEO e anteprima per i lettori generabili con l'AI
- Tempo di lettura stimato, indice dei contenuti, articoli correlati

**Multilingua**
- Sito bilingue (es. italiano/inglese) con selettore di lingua
- La lingua principale si sceglie in configurazione (l'altra va in sottocartella): con l'inglese, la traduzione va verso l'italiano
- Traduzione automatica con 5 servizi: DeepL, Google, Claude, OpenAI, DeepSeek
- Le traduzioni si rivedono e si confermano prima di pubblicarle
- Tutta l'amministrazione può essere in italiano o in inglese

**Amministrazione**
- Area admin protetta da password (hash PBKDF2, sessioni che scadono, token CSRF); chi sbaglia la password blocca solo il proprio indirizzo
- Elenco degli articoli con stato, ricerca, modifica, eliminazione; pubblicazione programmata e cronologia delle versioni di ogni articolo
- Impostazioni raccolte in un pannello che mostra cosa è compilato e cosa manca
- Libreria dei media: ogni file caricato, dove è usato, e pulizia di quelli non usati
- Sezione avanzata per modificare direttamente config.json, con controllo
- Codici esterni e annunci: modelli pronti per Google Analytics, Tag Manager, AdSense, Google Ads, Meta Pixel e Clarity; posizioni per gli annunci (barra laterale, inizio e metà dell'articolo, tra gli articoli); scelta articolo per articolo e codice proprio del singolo articolo; ads.txt
- Banner dei cookie integrato: statistiche e pubblicità partono solo dopo il consenso, con il Consent Mode di Google
- Backup/export di tutti i contenuti in uno ZIP con un clic, e ripristino dal menu (prima viene salvato lo stato attuale)
- Aggiornamenti con un clic: la versione nuova viene provata in un processo a parte prima di passarci
- L'amministrazione su un indirizzo suo (`admin.tuodominio.it`), controllato prima di salvarlo
- Newsletter: iscrizioni con doppia conferma e un'email per ogni nuovo articolo

**Lettura**
- Ricerca a testo pieno nel browser, con estratti ed evidenziazione
- Pulsante per copiare i blocchi di codice e barra di avanzamento della lettura
- Una pagina 404 che aiuta: casella di ricerca più gli ultimi articoli
- Tema chiaro/scuro con preferenza salvata
- Home a due colonne: articoli con miniatura e anteprima, barra laterale con presentazione, ricerca, pagine e argomenti
- Nell'articolo, l'indice nella barra laterale segue la lettura; sul telefono, un menu a scomparsa
- Commenti via Giscus o Disqus, a scelta

**Sotto il cofano**
- Zero dipendenze: solo `python3`
- Articoli come file JSON (niente database)
- CSS minimale, font di sistema, JavaScript leggero
- Modelli come semplici file `.html` riempiti con `string.Template`
- Un foglio di stile e uno script per pubblico, valori di design comuni in `common.css`

## Requisiti

Solo **Python 3.8 o superiore**. Niente `pip install`, niente virtualenv.

## Documentazione

La documentazione sta in due file, in italiano e in inglese:

- **[`TUTORIAL.md`](TUTORIAL.md)** ([English](TUTORIAL.en.md)) — passo per passo, da un server Ubuntu vuoto al sito online con HTTPS: installazione, nginx con l'amministrazione su `/admin` o su `admin.tuodominio.it`, primo articolo, backup e aggiornamenti
- **[`MANUALE.md`](MANUALE.md)** ([English](MANUAL.en.md)) — il manuale completo: ogni modo di installarlo, ogni pagina dell'amministrazione, ogni impostazione e ogni chiave di `config.json`, codici esterni, banner dei cookie, commenti, statistiche, traduzione, import/export, sicurezza e soluzione dei problemi
- **`config.example.json`** — modello di configurazione con tutti i campi
- **`nginx.conf.example`** e **`nginx.separate-admin.conf.example`** — le due configurazioni di nginx, pronte da copiare
- **[`CHANGELOG.md`](CHANGELOG.md)** — cosa è cambiato in ogni versione, e cosa controllare quando aggiorni

## Messa in produzione

PyBlog gira su un server Ubuntu con nginx come "portinaio": serve le pagine statiche al pubblico e inoltra a Python solo l'area admin. Quando pubblichi un articolo, le pagine si rigenerano da sole — nessun rsync, nessun deploy a mano.

Le configurazioni di nginx pronte sono due:

| | Amministrazione su | File |
|---|---|---|
| **A — un indirizzo** | `https://tuodominio.it/admin` | `nginx.conf.example` |
| **B — un indirizzo suo** (consigliata con statistiche, pubblicità o widget) | `https://admin.tuodominio.it` | `nginx.separate-admin.conf.example` |

La guida passo per passo per tutte e due, con systemd e certbot (HTTPS), è il [`TUTORIAL.md`](TUTORIAL.md).

Dopo un aggiornamento con `git pull` riavvia PyBlog (`sudo systemctl restart pyblog`): tiene in memoria le pagine dell'amministrazione. La voce **Aggiornamenti** del menu fa tutto da sola.

## I commenti

PyBlog supporta tre opzioni, scelte dalla pagina Impostazioni: nessuno, **Giscus** (usa le GitHub Discussions, gratuito e senza tracciamento, ideale per blog tecnici) o **Disqus** (accesso con i social, più facile per i lettori). Dettagli di configurazione nel [`MANUALE.md`](MANUALE.md).

## Licenza

MIT — vedi il file [LICENSE](LICENSE). Puoi usarlo, modificarlo e distribuirlo liberamente.

## Contribuire

PyBlog è volutamente semplice. Issue e pull request sono benvenute: se proponi una funzione, tieni presente la filosofia del progetto (zero dipendenze, solo libreria standard, codice esplicito e leggibile, commenti in inglese).
