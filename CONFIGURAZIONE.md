# Riferimento della configurazione di PyBlog

*In English: [CONFIGURATION.md](CONFIGURATION.md)*

Tutti i parametri del sito sono salvati in un unico file: **`config.json`**,
nella cartella principale del progetto.

- Il file viene creato in automatico la prima volta che salvi le impostazioni
  dall'area admin (pagina "Impostazioni e homepage").
- Contiene chiavi API segrete, quindi e' escluso da git (vedi `.gitignore`).
- Trovi un modello completo con tutti i campi in **`config.example.json`**.

Normalmente non serve modificarlo a mano: tutto si imposta dalla pagina
Impostazioni. Ma se vuoi capirlo o modificarlo via SSH, ecco ogni parametro.

## Parametri generali

| Parametro      | Significato                                                        |
|----------------|-------------------------------------------------------------------|
| `site_title`  | Il titolo del blog, mostrato nell'intestazione e nelle pagine.    |
| `subtitle`  | Una frase breve sotto il titolo.                                  |
| `author`       | Il nome dell'autore (appare nei meta tag SEO e nel footer).       |
| `base_url`     | Il dominio del sito, senza slash finale (es. `https://miosito.it`). Serve per URL canonici, sitemap e social. |
| `language`       | **Lingua principale del sito** (`it` o `en`). Decide quale lingua sta alla radice `/`; l'altra va in una sottocartella (`/en/` o `/it/`). |
| `admin_language` | Lingua dell'interfaccia di amministrazione (`it` o `en`). Si cambia anche col pulsante EN/IT nella barra admin. |
| `articles_per_page` | Quanti articoli mostrare in ogni pagina della homepage (default `10`). Le pagine successive vengono generate in `/pagina/2.html`, `/pagina/3.html`... (in inglese `/en/page/2.html`). Con `0` la paginazione e' disattivata e tutti gli articoli stanno in una pagina. |
| `home_order`  | Ordine delle sezioni della homepage, dall'alto in basso. Lista di tre valori tra `"intro"` (presentazione), `"articles"` e `"cards"`. Default: `["intro", "cards", "articles"]` (presentazione, poi le card, poi gli articoli). Si imposta anche dalla pagina Impostazioni, sezione "Struttura della homepage". |

## Contenuto della homepage

| Parametro        | Significato                                                      |
|------------------|-----------------------------------------------------------------|
| `home_content` | HTML della parte alta della homepage (biografia, presentazione). Si scrive con l'editor visuale, non a mano. |
| `home_cards`      | Lista delle "card" editoriali sotto la presentazione (Biografia, Progetti, ecc.). Ogni card ha `active` (true/false), `title` e `content`. |

## SEO e dati dell'autore (`seo`)

Questi dati alimentano i dati strutturati schema.org (Person, WebSite,
Article) e i meta tag social di tutte le pagine. Aiutano Google a
riconoscere l'autore come persona reale (segnali E-E-A-T) e a collegare
tra loro i suoi profili pubblici. Tutti i campi sono facoltativi e si
impostano anche dalla pagina Impostazioni, sezione "SEO e dati dell'autore".

| Parametro         | Significato                                                  |
|-------------------|--------------------------------------------------------------|
| `author_url`      | URL della pagina personale o professionale dell'autore.     |
| `author_image` | URL assoluto di una foto dell'autore (schema Person).       |
| `author_role`    | Ruolo professionale (es. "CTO e docente"), campo `jobTitle`. |
| `author_bio`      | Breve biografia (1-2 frasi), campo `description` di Person. |
| `social_profiles`  | Lista di URL dei profili pubblici (GitHub, LinkedIn, X...). Diventa il campo `sameAs`: e' il segnale piu' importante per collegare i profili. |
| `logo`            | URL assoluto del logo del sito (schema publisher).          |
| `twitter_site`    | Account X/Twitter del sito, con la chiocciola (es. `@nome`). |
| `favicon`         | URL di una favicon personalizzata. Se vuoto, PyBlog genera `favicon.svg` con l'iniziale del titolo del sito. |
| `backlink_site`   | Sito esterno che ripubblica gli articoli e ospita i backlink verso il blog (es. `startupbusiness.it`). Lo usa l'analisi SEO dell'editor per proporre anchor text adatti a quel contesto editoriale. |

## Commenti

| Parametro  | Significato                                                            |
|------------|-----------------------------------------------------------------------|
| `comments` | Sistema di commenti: `none`, `giscus` o `disqus`.                  |
| `giscus`   | Se usi Giscus: `repo`, `repo_id`, `category`, `category_id`, `theme`. |
| `disqus`   | Se usi Disqus: `shortname`.                                           |

## Statistiche di visita (analytics)

PyBlog supporta due sistemi di statistiche, indipendenti tra loro: puoi
usarne uno, entrambi o nessuno. Gli script vengono inseriti solo nelle
pagine pubbliche: l'editor e l'area di amministrazione non vengono mai
tracciati. Tutti i campi si impostano anche dalla pagina Impostazioni.

| Parametro          | Significato                                                 |
|--------------------|-------------------------------------------------------------|
| `analytics_id`     | ID misurazione di Google Analytics 4 (formato `G-XXXXXXXXXX`). Vuoto = GA disattivato. |
| `umami_url`        | URL base della tua istanza Umami self-hosted (es. `https://stats.miosito.it`), senza slash finale. |
| `umami_website_id` | L'ID del sito (UUID) mostrato da Umami quando registri il sito. Serve insieme a `umami_url`: se uno dei due e' vuoto, Umami e' disattivato. |

**Quale scegliere?** Google Analytics usa cookie e in Europa richiede un
banner di consenso preventivo (GDPR). Umami non usa cookie: niente
banner, i dati restano sul tuo server e le pagine sono piu' veloci. Per
un blog personale e' la scelta consigliata.

### Tutorial: installare Umami con Docker

Nel repository trovi `umami-docker-compose.yml` pronto all'uso.

1. Copia il file sul tuo server (es. in `/opt/umami/docker-compose.yml`)
   e apri il file: sostituisci `CAMBIAMI_PASSWORD_DB` (in **due** punti,
   deve essere identica) con una password per il database, e
   `CAMBIAMI_SEGRETO_CASUALE` con una stringa generata da
   `openssl rand -base64 32`.
2. Avvia: `docker compose up -d`. Umami ascolta solo su
   `127.0.0.1:3000`, di proposito: non va esposto direttamente.
3. Esponilo con il tuo reverse proxy. Esempio nginx per
   `stats.miosito.it`:

   ```nginx
   server {
       server_name stats.miosito.it;
       location / {
           proxy_pass http://127.0.0.1:3000;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   Poi il certificato: `certbot --nginx -d stats.miosito.it`.
4. Primo accesso su `https://stats.miosito.it` con `admin` / `umami`:
   **cambia subito la password** (Settings -> Profile).
5. Registra il blog: Settings -> Websites -> Add website, con il dominio
   del sito. Umami ti mostra il **Website ID** (un UUID): e' l'unico
   dato che ti serve, il tag script proposto da Umami puoi ignorarlo.
6. In PyBlog, pagina Impostazioni: incolla URL dell'istanza e Website ID
   nei due campi Umami e salva. Il sito viene rigenerato con lo script.

Per verificare: apri il blog in navigazione anonima e controlla la vista
Realtime di Umami: la visita compare in pochi secondi. Nota che molti
adblocker bloccano gli script di statistica (Umami compreso): i numeri
saranno sempre un po' sottostimati, e vale per qualunque sistema.

Ricorda infine il backup: il volume Docker `umami-db` contiene tutto lo
storico delle statistiche.

## Traduzione automatica (Italiano -> Inglese)

Dentro la sezione `translation`:

| Parametro          | Significato                                                  |
|--------------------|-------------------------------------------------------------|
| `service`         | Quale servizio usare: `deepl`, `google`, `llm` (Anthropic), `openai` o `deepseek`. |
| `deepl_api_key`    | Chiave API DeepL.                                            |
| `google_api_key`   | Chiave API Google Cloud Translation.                        |
| `llm_api_key`      | Chiave API Anthropic (Claude).                              |
| `llm_endpoint`     | Endpoint dell'API Anthropic (di norma non si cambia).       |
| `llm_model`      | Modello Claude da usare.                                     |
| `openai_api_key`   | Chiave API OpenAI.                                           |
| `openai_model`   | Modello OpenAI (es. `gpt-4o-mini`).                          |
| `deepseek_api_key` | Chiave API DeepSeek.                                         |
| `deepseek_model` | Modello DeepSeek (es. `deepseek-chat`).                      |

Se non inserisci nessuna chiave, la traduzione resta disattivata e il blog
funziona normalmente in italiano. Le chiavi restano sul server e non sono
mai visibili nelle pagine pubbliche.

### Chiavi API da variabile d'ambiente

Su un server esposto a internet e' preferibile non scrivere le chiavi
API in `config.json`. Ogni chiave della sezione `translation` puo'
essere fornita con una variabile d'ambiente, che ha la precedenza sul
file: il nome e' `PYBLOG_` piu' il nome del parametro in maiuscolo.
Esempi: `PYBLOG_LLM_API_KEY`, `PYBLOG_OPENAI_API_KEY`,
`PYBLOG_DEEPSEEK_API_KEY`, `PYBLOG_DEEPL_API_KEY`,
`PYBLOG_GOOGLE_API_KEY`. In produzione la variabile si mette in `/etc/pyblog.env` con permessi
`600`, letto dalla unit systemd tramite `EnvironmentFile=` (vedi
`pyblog.service.example` e DEPLOY-REMOTO.md); in locale basta un
`export` prima di avviare l'editor: cosi' la chiave non tocca il disco del
progetto, non finisce nei backup di `config.json` e non compare mai
nella pagina Impostazioni.

## Aggiungere parametri in futuro

Il sistema e' pensato per crescere: per aggiungere un nuovo parametro basta
inserirlo in `CONFIG_DEFAULT` dentro `pyblog.py`. Tutti gli articoli e le
configurazioni esistenti continuano a funzionare, perche' i parametri nuovi
ricevono il loro valore di default finche' non li imposti.

## Migrazione dalle versioni precedenti

Le versioni precedenti usavano chiavi italiane (`titolo_sito`, `stato`,
`contenuto`...). **Non serve fare nulla**: al primo avvio PyBlog riconosce
il vecchio formato, converte `config.json` e i file degli articoli al nuovo
schema inglese e li riscrive su disco. La migrazione avviene una sola volta
ed e' automatica.

## Diritti di addestramento AI (`ai_training`)

Dichiara se e a quali condizioni i contenuti del blog possono essere usati
per addestrare modelli di intelligenza artificiale. Si imposta dalla pagina
Impostazioni, sezione "Diritti di addestramento AI".

| Parametro        | Significato                                                      |
|------------------|--------------------------------------------------------------------|
| `policy`         | `"open"` (nessuna restrizione), `"licensed"` (richiede una licenza; i crawler AI noti vengono bloccati in robots.txt, con un contatto per negoziare) o `"disallow"` (bloccati, nessuna licenza offerta). |
| `contact_email`  | Email per le richieste di licenza (mostrata solo con `"licensed"`). |
| `license_url`    | URL dei propri termini di licenza. Se vuoto, si usa la pagina generata da PyBlog (`/training-rights.html`). |
| `statement`      | Testo personalizzato che sostituisce quello predefinito.          |

La scelta si riflette in `robots.txt` (blocco dei crawler AI noti), in
`llms.txt`, in `/.well-known/ai.txt` e `/.well-known/tdmrep.json` (un
tentativo in buona fede di seguire il TDM Reservation Protocol, una
convenzione di settore non vincolante e ancora in evoluzione), e nella
pagina pubblica `/training-rights.html`.
