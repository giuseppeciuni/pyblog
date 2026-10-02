# PyBlog

**[English](README.md) · Italiano**

**Un motore di blog completo in un solo file Python. Zero dipendenze, editor visuale nel browser, traduzione AI e HTML statico velocissimo.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![No dependencies](https://img.shields.io/badge/dependencies-zero-green.svg)](#)

PyBlog è un generatore di blog statico scritto in **un singolo file Python**, senza una sola dipendenza esterna: gira con il solo `python3`. Scrivi gli articoli con un editor WYSIWYG nel browser, premi salva, e PyBlog genera HTML statico leggerissimo pronto per nginx. Niente database, niente framework, niente `pip install`.

> Pensato per chi vuole un blog veloce, possederne il codice e i dati, e non dipendere da WordPress o da piattaforme di terze parti.

---

## Perché PyBlog

- **Un file, zero dipendenze.** Tutto in `pyblog.py`. Lo leggi, lo capisci, lo modifichi. Solo libreria standard di Python.
- **Migra da Hugo/Jekyll con un comando.** `python3 pyblog.py import-md posts/` legge i tuoi file Markdown con front matter e li importa tutti. E puoi esportare in Markdown quando vuoi: nessun lock-in, in nessuna direzione.
- **Editor visuale nel browser.** Scrivi come su Word (Quill WYSIWYG): grassetto, immagini ridimensionabili, blocchi di codice con evidenziazione, tabelle, video YouTube.
- **HTML statico velocissimo.** Le pagine pubbliche sono file statici serviti da nginx in pochi millisecondi. Python gira solo per l'area admin e può stare spento.
- **Bilingue con traduzione AI.** Scrivi in italiano, traduci in inglese con un click (DeepL, Google, Claude, OpenAI o DeepSeek). Il sito diventa bilingue con selettore di lingua e anteprima inglese per ogni articolo.
- **SEO completo, autore incluso (E-E-A-T).** Meta description, canonical, hreflang, Open Graph, Twitter Card, JSON-LD con schema.org Person completo (foto, ruolo, profili `sameAs`), sitemap.xml, robots.txt, RSS, e perfino llms.txt per i crawler AI.
- **Esperienza di lettura completa, di serie.** Paginazione, archivio per anno, indice dei contenuti, articoli correlati, navigazione precedente/successivo, box autore, favicon generata automaticamente, tema scuro che segue la preferenza di sistema, focus visibile per chi naviga da tastiera.
- **Sicuro di default.** Password con PBKDF2, blocco anti brute-force sul login, protezione dal path traversal, editor in ascolto solo su localhost, cookie di sessione Secure dietro HTTPS, chiavi API da variabili d'ambiente. Esempi Docker e systemd inclusi.
- **Analisi SEO e backlink con AI.** Un click nell'editor e ottieni keyword, tag consigliati, varianti di titolo, anchor text per i backlink, link interni, FAQ per i motori AI e consigli specifici per l'articolo.
- **Statistiche integrate.** Google Analytics 4 o Umami self-hosted (senza cookie), attivabili dalle Impostazioni; tutorial e docker-compose inclusi.
- **Tuoi i dati.** Gli articoli sono semplici file JSON. Nessun lock-in, backup in un click.

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

## Funzionalità complete

**Scrittura**
- Editor WYSIWYG (Quill): font, dimensioni, colori, allineamento
- Pulsanti che seguono lo stato dell'articolo: Salva bozza e Pubblica per una bozza, Aggiorna e Ritira per un articolo pubblicato; anteprima della pagina vera senza salvare; salvataggio automatico delle bozze, Ctrl+S, avviso per le modifiche non salvate
- Immagini ridimensionabili trascinando gli angoli; upload PNG/JPEG/SVG
- Blocchi di codice con evidenziazione sintassi (Python, JS e altri)
- Tabelle (manuali o copia-incolla da Word), video YouTube e upload video
- Import di documenti Word (.docx): titoli, elenchi annidati, tabelle con celle unite, immagini con testo alternativo, note, link
- Anteprima dal vivo con la grafica del sito vero

**Pubblicazione e SEO**
- HTML statico: homepage, articoli, pagine tag, feed RSS
- SEO: meta description, canonical, Open Graph, Twitter Card, JSON-LD
- sitemap.xml, robots.txt, llms.txt (per crawler AI: ChatGPT, Claude, Perplexity)
- Descrizione SEO e anteprima per i lettori generabili con l'AI
- Tempo di lettura stimato, indice dei contenuti, articoli correlati

**Multilingua**
- Sito bilingue IT/EN con selettore di lingua
- La lingua principale si sceglie in configurazione (l'altra va in sottocartella): con l'inglese, la traduzione va verso l'italiano
- Traduzione automatica con 5 provider: DeepL, Google, Claude, OpenAI, DeepSeek
- Le traduzioni si rivedono e confermano prima di pubblicarle

**Amministrazione**
- Area admin protetta da password (hash PBKDF2, sessioni che scadono, token CSRF); chi sbaglia la password blocca solo il proprio indirizzo
- Dashboard con elenco articoli, stato, ricerca, modifica, elimina
- Editor con barra laterale, responsive e mobile friendly
- Interfaccia admin in italiano o inglese
- Codici esterni e annunci: modelli pronti per Google Analytics, Tag Manager, AdSense, Google Ads, Meta Pixel e Clarity; posizioni per gli annunci (barra laterale, inizio e metà dell'articolo, tra gli articoli); scelta articolo per articolo e codice proprio del singolo articolo; ads.txt
- Banner dei cookie integrato: statistiche e pubblicità partono solo dopo il consenso, con Consent Mode di Google
- Backup/export di tutti i contenuti in un ZIP

**Lettura**
- Ricerca full-text lato browser con snippet ed evidenziazione (IT ed EN)
- Tema chiaro/scuro con preferenza salvata
- Homepage a due colonne: articoli con miniatura e anteprima, barra laterale con presentazione, ricerca, pagine e argomenti
- Nell'articolo, l'indice nella barra laterale segue la lettura; sul telefono, menu a scomparsa
- Commenti via Giscus o Disqus, a scelta

**Sotto il cofano**
- Zero dipendenze: solo `python3`
- Articoli come file JSON (niente database)
- CSS minimale, font di sistema, JavaScript leggero

## Requisiti

Solo **Python 3.8 o superiore**. Niente `pip install`, niente virtualenv.

## Documentazione

- **`GUIDA.md`** — guida passo-passo: installazione, scrittura, pubblicazione online
- **`DEPLOY-REMOTO.md`** — deploy su server Ubuntu con nginx, systemd e HTTPS
- **`CONFIGURAZIONE.md`** — riferimento di tutti i parametri di configurazione
- **`config.example.json`** — modello di configurazione con tutti i campi

## Deploy in produzione

PyBlog gira su un server Ubuntu con nginx come "portinaio": serve le pagine statiche al pubblico e inoltra a Python solo l'area admin. Quando pubblichi un articolo, le pagine si rigenerano da sole — nessun rsync, nessun deploy manuale. La guida completa con systemd e certbot (HTTPS) è in `DEPLOY-REMOTO.md`.

## I commenti

PyBlog supporta tre opzioni, scelte dalla pagina Impostazioni: nessuno, **Giscus** (usa le GitHub Discussions, gratuito e senza tracciamento, ideale per blog tecnici) o **Disqus** (login social, più facile per i lettori). Dettagli di configurazione in `GUIDA.md`.

## Licenza

MIT — vedi il file [LICENSE](LICENSE). Puoi usarlo, modificarlo e distribuirlo liberamente.

## Contribuire

PyBlog nasce come progetto a file singolo, volutamente semplice. Issue e pull request sono benvenute: se proponi una feature, tieni presente la filosofia del progetto (zero dipendenze, un solo file, codice leggibile).
