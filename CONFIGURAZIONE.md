# Riferimento della configurazione di PyBlog

*In English: [CONFIGURATION.md](CONFIGURATION.md)*

Tutti i parametri del sito sono salvati in un unico file: **`config.json`**,
nella cartella principale del progetto.

- Il file viene creato in automatico la prima volta che salvi le impostazioni
  dall'area admin (pagina "Impostazioni").
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
| `home_intro_position` | Dove va la presentazione della homepage (`home_content`): `"sidebar"` (default) nel primo riquadro della barra laterale, cosi' gli articoli partono dall'alto; `"top"` sopra l'elenco degli articoli. Si imposta dalle Impostazioni, sezione "Home page". |
| `home_excerpt_words` | Quante parole dell'articolo mostrano gli elenchi (home, tag, archivio) quando non hai scritto un'anteprima (default `40`). L'estratto prende solo il testo, senza titoletti, e si ferma alla fine di una parola. |
| `home_order`  | Non piu' usato. Ordinava le sezioni della vecchia homepage a una colonna; con le due colonne gli articoli stanno a sinistra e il resto nella barra laterale, quindi non c'e' piu' un ordine da scegliere. Nei config vecchi resta e viene ignorato. |

## Contenuto della homepage

| Parametro        | Significato                                                      |
|------------------|-----------------------------------------------------------------|
| `home_content` | HTML della parte alta della homepage (biografia, presentazione). Si scrive con l'editor visuale, non a mano. |
| `home_cards_enabled` | Interruttore generale del blocco delle card (default `true`). Con `false` l'intero blocco sparisce dalla homepage, qualunque cosa dicano le singole card, e le loro pagine non vengono generate. Si imposta anche dalla pagina Impostazioni, sezione "Pagine". |
| `home_cards`      | Lista delle "card" editoriali (Biografia, Progetti, ecc.), elencate nel riquadro "Esplora" della barra laterale: ognuna ha la sua pagina. Ogni card ha `active` (true/false), `title` e `content`. Una card con `active` a `false`, o senza contenuto, non appare e non ha una sua pagina. |

## SEO e dati dell'autore (`seo`)

Questi dati alimentano i dati strutturati schema.org (Person, WebSite,
Article) e i meta tag social di tutte le pagine. Aiutano Google a
riconoscere l'autore come persona reale (segnali E-E-A-T) e a collegare
tra loro i suoi profili pubblici. Tutti i campi sono facoltativi e si
impostano anche dalla pagina Impostazioni, sezione "Sito e autore".

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

Se usi Google Analytics, PyBlog ha il suo banner: con il consenso acceso
(vedi [Consenso ai cookie](#consenso-ai-cookie-consent)) lo script di GA
parte solo dopo che il visitatore ha accettato le statistiche.

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

## Codici esterni e annunci (`custom_code`)

Pezzi di HTML o JavaScript inseriti nelle pagine pubbliche: Google
Analytics, AdSense, Tag Manager, pixel, widget di chat, embed. Si gestiscono
dalla pagina Impostazioni, sezione "Statistiche e annunci", e ogni pezzo
ha quattro scelte: dove va nella pagina, su quali pagine appare, se deve
aspettare il consenso del visitatore e il codice vero e proprio.

Il pulsante "Aggiungi codice" propone i servizi piu' comuni (Google
Analytics 4, Google Tag Manager, AdSense automatico o con un'unita'
pubblicitaria, Google Ads, Meta Pixel, Microsoft Clarity): basta scrivere
l'ID e il codice viene preparato con posizione, pagine e consenso adatti.
"Codice libero" e' la scheda vuota, per tutto il resto.

`custom_code` e' una lista; ogni elemento e' un oggetto con questi campi:

| Campo      | Significato                                                     |
|------------|-----------------------------------------------------------------|
| `id`       | Identificatore stabile (`snip-xxxxxxxx`), generato da solo. Gli articoli si riferiscono al codice con questo, non con il nome: rinominarlo non rompe niente. |
| `name`     | Il nome che vedi tu nelle Impostazioni. Non finisce nelle pagine. |
| `enabled`  | `true` o `false`. Spento vuol dire spento ovunque, senza cancellarlo. |
| `position` | Dove finisce nella pagina (vedi sotto).                          |
| `scope`    | Su quali pagine appare (vedi sotto).                             |
| `consent`  | Il consenso che aspetta: `necessary` (parte sempre, il default), `statistics` o `marketing` (pubblicita'). Conta solo con il banner del consenso acceso. |
| `code`     | Il codice, inserito **cosi' com'e'**, senza alcuna trasformazione. |

**Le posizioni (`position`)**

| Valore          | Dove finisce                                                  |
|-----------------|---------------------------------------------------------------|
| `head`          | Dentro `<head>`. Per meta tag e script che devono partire presto. |
| `body_start`    | Subito dopo `<body>`, prima dell'intestazione del sito.        |
| `body_end`      | In fondo alla pagina, dopo tutto il resto. Il posto giusto per gli script `defer` o `async`. |
| `after_header`  | Sotto l'intestazione, prima del contenuto. Si vede.            |
| `before_footer` | Dopo il contenuto, prima del pie' di pagina. Si vede.          |
| `article_end`   | In fondo al testo dell'articolo, prima della firma dell'autore. Esiste **solo negli articoli**: su qualunque altra pagina il codice non esce. |
| `nav`           | Nel menu dell'intestazione, dopo RSS e prima del cambio di lingua. Per una voce in piu', per esempio `<a href="#" data-vaitony-apri>Chiedi all'assistente</a>` che apre la chat di un widget: prende lo stile degli altri link del menu. |
| `sidebar`       | Nella barra laterale, dopo la presentazione: il posto di un annuncio 300x250 o di un widget. C'e' su homepage, articoli, tag, archivio e schede. |
| `home_feed`     | Tra gli articoli della homepage, dopo il terzo. Esiste **solo in homepage**. |
| `article_start` | All'inizio dell'articolo, dopo il titolo e la copertina, prima del testo. **Solo negli articoli**. |
| `article_middle`| A meta' dell'articolo, dopo il paragrafo piu' vicino alla meta' del testo: mai dentro una tabella o un elenco, mai fra un titoletto e il suo paragrafo. Un articolo troppo corto lo riceve in fondo al testo. **Solo negli articoli**. |

**Gli ambiti (`scope`)**

| Valore          | Su quali pagine                                               |
|-----------------|---------------------------------------------------------------|
| `home`          | Solo la homepage.                                             |
| `articles`      | Solo gli articoli, tutti.                                     |
| `home_articles` | La homepage e tutti gli articoli.                             |
| `optin`         | Solo gli articoli che lo spuntano nell'editor.                |
| `home_optin`    | La homepage, piu' gli articoli che lo spuntano nell'editor.   |
| `all`           | Tutto il sito: anche archivio, pagine dei tag, schede e 404.  |

**Le scelte del singolo articolo.** Nell'editor, il riquadro "Codici
esterni" elenca i codici del sito che possono uscire su quell'articolo:
quelli "da spuntare" (ambito `optin` o `home_optin`) escono solo con la
spunta; quelli "di serie" (tutti gli altri) escono finche' non togli la
spunta, e cosi' un articolo puo' fare a meno, per esempio, di un annuncio
che gli altri hanno. Sotto, "Solo per questo articolo" accoglie codice
che esce soltanto li': un annuncio dedicato, un embed. Nel JSON
dell'articolo:

| Campo                 | Significato                                           |
|-----------------------|-------------------------------------------------------|
| `custom_code_ids`     | Gli `id` dei codici "da spuntare" spuntati.           |
| `custom_code_off_ids` | Gli `id` dei codici "di serie" spenti su questo articolo. |
| `custom_code`         | I codici propri dell'articolo, con gli stessi campi di quelli del sito tranne `scope` (la loro unica pagina e' l'articolo); `id` comincia con `art-`. |

L'editor mostra solo i codici attivi, ma le scelte su quelli spenti
restano salvate: quando li riaccendi, ogni articolo li ritrova come li
aveva lasciati. Cancellare un codice dalle Impostazioni e' sicuro: l'`id`
rimasto negli articoli non corrisponde piu' a niente e viene ignorato.

**ads.txt (`ads_txt`).** Il testo del file `/ads.txt`, che dice chi puo'
vendere pubblicita' sul sito: AdSense lo cerca e limita gli annunci
finche' non lo trova. Il modello di AdSense ci aggiunge da solo la sua
riga (`google.com, pub-..., DIRECT, f08c47fec0942fa0`). Vuoto, il file
non viene pubblicato (e se c'era viene tolto).

**Una nota sulla fiducia.** Il codice viene scritto nella pagina senza
alcun controllo, perche' controllarlo vorrebbe dire impedirgli di
funzionare. Chi puo' entrare nell'area di amministrazione puo' quindi
eseguire qualunque JavaScript sul sito pubblico: incolla solo codice di
cui ti fidi, e tieni la password dell'amministrazione al sicuro.

## Consenso ai cookie (`consent`)

In Europa statistiche e pubblicita' che usano cookie possono partire solo
dopo il consenso del visitatore. PyBlog ha un banner suo: lo accendi dalle
Impostazioni, sezione "Cookie e privacy".

| Campo         | Significato                                                |
|---------------|------------------------------------------------------------|
| `enabled`     | `true` mostra il banner ai visitatori (default `false`).   |
| `text`        | Il testo del banner nella lingua principale. Vuoto = il testo predefinito. |
| `text_en`     | Il testo del banner nell'altra lingua del sito. Vuoto = il testo predefinito. |
| `privacy_url` | L'indirizzo dell'informativa privacy, linkata dal banner.  |
| `version`     | Un numero che cresce col pulsante "Chiedi di nuovo il consenso a tutti": chi ha scelto con un numero vecchio rivede il banner. Da usare quando aggiungi un servizio. |

**Come funziona.** Con il banner acceso, i codici segnati `statistics` o
`marketing` (e Google Analytics) arrivano nella pagina dentro un
`<template>`, che il browser non esegue: niente script, niente cookie,
niente richieste. Quando il visitatore accetta una categoria, `site.js`
li trasforma in codice vivo al loro posto. I tag di Google ricevono la
scelta tramite **Consent Mode** (tutto negato finche' il visitatore non
decide). La scelta resta nel browser del visitatore; il link "Preferenze
cookie" nel pie' di pagina riapre il banner, e ritirare un consenso
ricarica la pagina senza quel codice.

Il banner compare solo se qualche codice ne ha bisogno: con il consenso
acceso ma tutti i codici `necessary`, non esce niente.

**AdSense.** Per mostrare annunci in Europa Google chiede anche un CMP
certificato (TCF). Puoi accendere il messaggio gratuito di Google dal
pannello di AdSense ("Privacy e messaggi") e lasciare il codice di
AdSense su `necessary`, oppure usare il banner di PyBlog con AdSense su
`marketing`: in quel caso gli annunci partono solo dopo il consenso.

## Traduzione automatica (dalla lingua principale all'altra)

La traduzione va sempre dalla lingua principale del sito (`language`)
all'altra: dall'italiano all'inglese, o dall'inglese all'italiano se il
sito e' in inglese.

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
funziona normalmente nella sua lingua principale. Le chiavi restano sul server e non sono
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

**Un `config.json` illeggibile** (JSON rotto, per esempio dopo una modifica
a mano) non blocca piu' il sito: PyBlog avvisa sul terminale, ne mette una
copia in `config.broken.json` e parte con i valori predefiniti. Recupera i
tuoi dati dalla copia prima di salvare di nuovo le Impostazioni. I file
vengono sempre scritti "tutto o niente": un'interruzione a meta' lascia la
versione vecchia, mai un file a meta'.

## Diritti di addestramento AI (`ai_training`)

Dichiara se e a quali condizioni i contenuti del blog possono essere usati
per addestrare modelli di intelligenza artificiale. Si imposta dalla pagina
Impostazioni, sezione "Addestramento AI".

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
