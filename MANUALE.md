# PyBlog — Manuale

*In English: [MANUAL.en.md](MANUAL.en.md)*

Tutto su PyBlog: come funziona, ogni modo di installarlo, ogni pagina
dell'amministrazione, ogni impostazione e ogni chiave di `config.json`.

Per mettere online un sito la prima volta, la strada più breve è il
**[TUTORIAL.md](TUTORIAL.md)**: da un server Ubuntu vuoto al sito con HTTPS,
passo per passo. Questo manuale è il riferimento da consultare dopo.

## Indice

1. [Cos'è PyBlog e come funziona](#1-cosè-pyblog-e-come-funziona)
2. [Installare e avviare](#2-installare-e-avviare)
3. [L'amministrazione](#3-lamministrazione)
4. [Scrivere un articolo: l'editor](#4-scrivere-un-articolo-leditor)
5. [Le Impostazioni, sezione per sezione](#5-le-impostazioni-sezione-per-sezione)
6. [Codici esterni: statistiche, annunci, widget](#6-codici-esterni-statistiche-annunci-widget)
7. [Il banner dei cookie](#7-il-banner-dei-cookie)
8. [Commenti](#8-commenti)
   - [8b. Newsletter](#8b-newsletter)
9. [Statistiche delle visite](#9-statistiche-delle-visite)
10. [Due lingue e traduzione automatica](#10-due-lingue-e-traduzione-automatica)
11. [Il sito pubblico: cosa viene generato](#11-il-sito-pubblico-cosa-viene-generato)
12. [Importare ed esportare](#12-importare-ed-esportare)
13. [Riferimento di config.json](#13-riferimento-di-configjson)
14. [File, cartelle e formato degli articoli](#14-file-cartelle-e-formato-degli-articoli)
15. [Sicurezza](#15-sicurezza)
16. [Problemi e soluzioni](#16-problemi-e-soluzioni)
17. [Per chi sviluppa](#17-per-chi-sviluppa)

---

## 1. Cos'è PyBlog e come funziona

PyBlog è un motore per blog scritto in Python puro, **senza nessuna
dipendenza esterna**: basta `python3`, niente database, niente `pip install`.
Scrivi gli articoli con un editor visuale nel browser; quando salvi, PyBlog
genera le pagine HTML statiche del sito.

Sono **due cose diverse**:

1. **L'editor** (l'area `/admin`): il programma Python che avvii con
   `python3 pyblog.py serve`. È protetto da password e serve solo a te.
2. **Il sito**: la cartella `output/`, fatta di file HTML già pronti. È
   quello che vedono i lettori e **non ha bisogno di Python**: lo serve un
   server web come nginx.

```
   Tu (browser)          PyBlog                      output/
  ┌─────────────┐ salva ┌──────────────────┐ genera ┌────────────┐
  │ editor      │ ────▶ │ pyblog.py serve  │ ─────▶ │ *.html     │ ──▶ nginx ──▶ lettori
  │ (WYSIWYG)   │       │ (solo per te)    │        │ rss, sitemap│
  └─────────────┘       └──────────────────┘        └────────────┘
```

Ogni volta che dall'amministrazione salvi o elimini un articolo, lo
pubblichi o lo ritiri, o salvi le Impostazioni, PyBlog **rigenera da solo**
tutte le pagine di `output/`. Il comando `build` (o "Rigenera il sito" nel
menu) serve solo nei casi particolari: la prima volta, dopo un
aggiornamento di PyBlog, dopo aver modificato a mano `config.json` o un
modello.

**Requisiti:** Python 3.8 o più recente. Per pubblicare online, un server
web che serva file statici (nginx negli esempi).

---

## 2. Installare e avviare

### 2.1 Sul tuo computer

```bash
git clone https://github.com/giuseppeciuni/pyblog.git
cd pyblog
./install.sh
```

Lo script controlla Python, ti fa scegliere la password e genera il sito.
Senza lo script bastano tre comandi:

```bash
python3 pyblog.py password   # la password dell'amministrazione
python3 pyblog.py build      # la prima generazione del sito
python3 pyblog.py serve      # l'editor su http://localhost:8000
```

Apri **http://localhost:8000/admin**. Il sito generato è su
http://localhost:8000/. Per fermare l'editor, Ctrl+C: il lavoro è già
salvato su disco.

Per sicurezza l'editor ascolta solo su `localhost`: nessun altro
dispositivo della rete lo raggiunge.

### 2.2 I comandi

| Comando | Cosa fa |
|---|---|
| `python3 pyblog.py serve` | avvia l'editor su `localhost:8000` |
| `python3 pyblog.py serve 9000` | ...su un'altra porta |
| `python3 pyblog.py serve 8000 0.0.0.0` | ...raggiungibile dalla rete: solo dietro un proxy con HTTPS |
| `python3 pyblog.py build` | rigenera tutto il sito in `output/` |
| `python3 pyblog.py password` | sceglie o cambia la password dell'amministrazione |
| `python3 pyblog.py import-md <file o cartella>` | importa articoli Markdown (vedi [12.1](#121-markdown)) |
| `python3 pyblog.py import-docx <file o cartella>` | importa documenti Word come bozze (vedi [12.2](#122-word)) |
| `python3 pyblog.py export-md <cartella>` | esporta ogni articolo in Markdown |
| `python3 pyblog.py bundle` | crea `pyblog_standalone.py`, la versione a file unico |

### 2.3 Con Docker

```bash
docker compose up -d
```

L'editor è su `http://localhost:8000/admin`; `docker compose down` lo ferma.
La cartella del progetto è montata nel container, quindi articoli,
configurazione, password e sito generato restano sul tuo disco.

La porta è pubblicata solo su `127.0.0.1`. Dentro il container PyBlog
ascolta su `0.0.0.0` (altrimenti sarebbe irraggiungibile dal container
stesso), ma il container non va esposto su internet: online il sito lo
serve nginx dalla cartella `output/`. Per aggiornare: sostituisci i file e
`docker compose restart`.

### 2.4 La versione a file unico

`python3 pyblog.py bundle` scrive **`pyblog_standalone.py`**: un solo script
con dentro i moduli, i modelli e CSS/JavaScript. Serve a chi preferisce
scaricare un file invece di una cartella; supporta tutti i comandi tranne
`bundle` e produce esattamente lo stesso sito. È un prodotto della build,
non un secondo codice: le modifiche si fanno in `core/` e poi si rigenera.

```bash
python3 pyblog_standalone.py serve
```

### 2.5 Online: tre modi

| | **A. Scrivi sul tuo computer, carichi le pagine** | **B. Editor sul server, via tunnel SSH** | **C. Editor online in HTTPS** (il tutorial) |
|---|---|---|---|
| Python sul server | no | sì | sì |
| Superficie d'attacco | minima | piccola (solo SSH) | l'area `/admin`, dietro HTTPS e limiti |
| Scrivere da più dispositivi | scomodo | comodo | comodissimo, anche dal telefono |
| Per pubblicare | `rsync` | niente | niente |

**A — Scrivi in locale, carichi `output/`.** Sul server c'è solo nginx.

```bash
python3 pyblog.py serve        # scrivi, poi Ctrl+C
rsync -avz --delete output/ utente@tuodominio.it:/var/www/blog/
```

`--delete` toglie dal server i file che in locale non ci sono più (gli
articoli eliminati): la cartella di destinazione deve contenere solo il
sito. Su nginx basta la parte "sito pubblico" di `nginx.conf.example`, con
`root /var/www/blog;`. Conviene mettere il comando in uno script
`pubblica.sh`.

**B — Editor sul server, raggiunto con un tunnel SSH.** L'editor gira sul
server ma non è visibile da internet:

```bash
# dal tuo computer, lasciandolo aperto
ssh -L 8000:localhost:8000 utente@tuodominio.it
```

e apri `http://localhost:8000/admin` nel tuo browser. Salvando, `output/`
sul server si rigenera e nginx serve subito le pagine. Per l'editor sempre
acceso usa il servizio systemd del punto 2.6; nginx serve solo `output/`
(togli dal file di esempio i blocchi dell'amministrazione).

**C — Editor online in HTTPS.** È la configurazione completa del
**[TUTORIAL.md](TUTORIAL.md)**: nginx serve il sito e passa a PyBlog solo
le rotte dell'amministrazione, con HTTPS obbligatorio e il limite ai
tentativi di accesso.

### 2.6 Il servizio systemd

`pyblog.service.example` è pronto per `/opt/pyblog` e un utente `pyblog`:

- `ExecStart=/usr/bin/python3 /opt/pyblog/pyblog.py serve 8000 127.0.0.1`:
  ascolta solo sulla macchina, nginx gli passa le richieste;
- `Restart=on-failure`: riparte se si ferma;
- `EnvironmentFile=-/etc/pyblog.env`: le chiavi segrete, in un file
  leggibile solo da root (facoltativo, per il trattino davanti);
- `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome` e
  `ReadWritePaths=/opt/pyblog`: il processo non acquista privilegi, ha una
  `/tmp` sua e può scrivere solo nella sua cartella.

```bash
sudo useradd --system --home /opt/pyblog --shell /usr/sbin/nologin pyblog
sudo cp pyblog.service.example /etc/systemd/system/pyblog.service
sudo systemctl daemon-reload
sudo systemctl enable --now pyblog
systemctl status pyblog
journalctl -u pyblog -f        # i messaggi del programma, dal vivo
```

### 2.7 nginx

`nginx.conf.example` è la configurazione completa per il modo C. Blocco per
blocco:

- `limit_req_zone ... rate=1r/s`: al massimo un tentativo di accesso al
  secondo per indirizzo, con una piccola tolleranza;
- `root .../output;`: le pagine pubbliche sono file statici;
- `location ~ ^/(admin|edit|config|login|...)$`: le rotte
  dell'amministrazione vanno a PyBlog su `127.0.0.1:8000`, con l'indirizzo
  vero del visitatore (`X-Real-IP`, che PyBlog usa per bloccare solo chi
  sbaglia la password), il protocollo (`X-Forwarded-Proto`, per il cookie
  `Secure`), 120 secondi di attesa per le funzioni di AI e caricamenti
  fino a 100 MB;
- `location ^~ /admin-static/`: lo stile e lo script dell'amministrazione,
  che stanno in `static/` e non in `output/`. Il `^~` serve: senza, la
  regola dei file statici li cercherebbe in `output/` e l'amministrazione
  si aprirebbe senza grafica;
- `location = /login`: il limite ai tentativi;
- `error_page 404 /404.html`: gli indirizzi che non esistono mostrano la
  pagina 404 del sito, con la ricerca e gli ultimi articoli;
- cache lunga per CSS, JS e immagini; tipi giusti per `rss.xml` e
  `llms.txt`; `/media/` per i file caricati (nginx gestisce le richieste
  parziali, che servono a far scorrere i video).

**Quando aggiorni PyBlog**, se cambia l'elenco delle rotte
dell'amministrazione cambia anche la riga `location ~ ^/(...)$`: va copiata
nel tuo file di nginx, altrimenti la funzione nuova risponde 404 online.
Il CHANGELOG lo segnala.

### 2.8 HTTPS

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d tuodominio.it -d www.tuodominio.it
sudo certbot renew --dry-run
```

Certbot aggiunge l'HTTPS e il passaggio automatico da `http`, e rinnova il
certificato da solo. Con l'editor online (modo C) l'HTTPS è obbligatorio:
dall'amministrazione passa la tua password.

### 2.9 Chiavi segrete con le variabili d'ambiente

Ogni chiave della sezione `translation` di `config.json` può arrivare da
una variabile d'ambiente, che ha la precedenza sul file e non compare mai
nella pagina Impostazioni. Il nome è `PYBLOG_` più il nome della chiave in
maiuscolo:

| Variabile | Servizio |
|---|---|
| `PYBLOG_LLM_API_KEY` | Anthropic (Claude) o un endpoint compatibile |
| `PYBLOG_OPENAI_API_KEY` | OpenAI |
| `PYBLOG_DEEPSEEK_API_KEY` | DeepSeek |
| `PYBLOG_DEEPL_API_KEY` | DeepL |
| `PYBLOG_GOOGLE_API_KEY` | Google Cloud Translation |

Sul server vanno in `/etc/pyblog.env` (permessi `600`, proprietario root),
una per riga (`PYBLOG_LLM_API_KEY=sk-...`), poi `sudo systemctl restart
pyblog`. Sul tuo computer basta un `export` prima di avviare:

```bash
export PYBLOG_LLM_API_KEY="sk-ant-..."
python3 pyblog.py serve
```

Consiglio: una chiave dedicata al blog e un tetto di spesa mensile nella
console del servizio. Per verificare che arrivi: apri un articolo e lancia
**Analizza con AI** nel riquadro dell'analisi SEO.

### 2.10 Aggiornare PyBlog

```bash
cd /opt/pyblog
sudo -u pyblog git pull
sudo systemctl restart pyblog
sudo -u pyblog python3 pyblog.py build
```

Articoli (`posts/`), `config.json` e password non vengono toccati. I file
scritti con una versione vecchia (chiavi italiane come `titolo_sito`)
vengono convertiti da soli al primo avvio.

### 2.11 Backup e ripristino

Da salvare: `posts/`, `config.json`, `admin_password.txt`,
`subscribers.json` (gli iscritti, se usi la newsletter) e `output/media/`
(i file caricati). Tutto il resto di `output/` si rigenera con `build`.

- **Dal menu:** **Scarica il backup** scarica uno `.zip` con articoli (e
  le loro versioni precedenti), immagini, impostazioni e iscritti alla
  newsletter.
- **Ogni notte sul server**, con cron (`sudo crontab -e`):

  ```
  0 3 * * * tar -czf /var/backups/pyblog-$(date +\%F).tar.gz --ignore-failed-read -C /opt/pyblog posts config.json admin_password.txt subscribers.json output/media
  30 3 * * * find /var/backups -name 'pyblog-*.tar.gz' -mtime +30 -delete
  ```

- **Ripristino:** ferma il servizio, scompatta l'archivio in `/opt/pyblog`,
  `chown -R pyblog:pyblog /opt/pyblog`, `build`, riavvia.

---

## 3. L'amministrazione

### 3.1 Accesso e password

- **La prima volta**, se non c'è ancora una password, `/admin` propone di
  crearla. Online conviene crearla prima dal terminale
  (`python3 pyblog.py password`), così nessuno arriva prima di te.
- **Cambiarla:** menu → **Cambia password** (serve quella attuale; restano
  aperte solo le tue sessioni di quel momento, le altre si chiudono).
- **Dimenticata:** dal terminale del server, `python3 pyblog.py password`.
- Dopo alcuni tentativi sbagliati, l'**indirizzo** che sbaglia viene
  fermato per un po', sempre più a lungo; dopo un'ora senza errori il
  conteggio riparte. Gli altri indirizzi non sono toccati.

### 3.2 Il menu

A sinistra, sempre a vista:

- **Articoli** (con quanti sono), **Nuovo articolo**, **Impostazioni** (sulla
  pagina delle Impostazioni si apre nelle sue sezioni);
- **Strumenti:** **Rigenera il sito** ricrea tutte le pagine pubbliche da
  articoli e impostazioni; **Scarica il backup** dà un `.zip` con articoli,
  immagini e impostazioni;
- **Apri il sito** (in una nuova scheda), **Cambia password**, la lingua
  dell'amministrazione (italiano o inglese), **Esci**.

Nell'editor il menu si stringe a una colonna di icone: passandoci sopra
compare il nome. **Sul telefono** il menu diventa una barra in fondo allo
schermo (Articoli, Nuovo, Impostazioni, Altro); nell'editor la barra lascia
il posto al pannello di pubblicazione.

### 3.3 La pagina Articoli

- In alto quanti sono pubblicati e quante bozze, e **Nuovo articolo**.
- I filtri **Tutti / Pubblicati / Bozze**, la **ricerca** per titolo e
  l'**ordine** (più recenti, più vecchi, titolo, stato).
- Ogni riga: lo stato, il titolo (cliccabile, apre l'editor), la data, il
  tempo di lettura e "anche in inglese" se c'è la traduzione;
  **Modifica**, e il pulsante **⋯** con le azioni più rare: **Anteprima**,
  **Anteprima in inglese** (se c'è testo tradotto), **Pubblica** o **Ritira
  dalla pubblicazione**, **Elimina** (chiede conferma). Il menu ⋯ si usa
  anche da tastiera: frecce per muoversi, Esc per chiudere.

---

## 4. Scrivere un articolo: l'editor

### 4.1 I campi

La pagina ha una sola colonna, con il titolo e il testo. Sopra ci sono le
**parti del tema** come schede: **Teoria**, **In pratica** e **Lab**,
ognuna con il suo stato (bozza, pubblicato). Un clic porta da un articolo
all'altro; **+ Lab** e **+ In pratica** ne creano uno nuovo già legato alla
teoria, con i suoi tag. I pulsanti per salvare e pubblicare stanno in una
barra in alto (in basso sul telefono). In un lab, sopra il titolo, c'è il
riquadro del progetto: indirizzo su GitHub, con cosa è fatto, i comandi
per eseguirlo.

Tutto il resto si apre dal pulsante **Dettagli**: un pannello (a tutto
schermo sul telefono) con cinque gruppi che si aprono e si chiudono:
**Indirizzo, tag e copertina**, **Serie e tipo**, **Anteprima e ricerca**
(anteprima per i lettori, descrizione, analisi SEO), la **versione
tradotta** e **Avanzate** (pubblicato in origine, codici esterni, versioni
precedenti). Un gruppo chiuso dice in una riga cosa contiene, e il browser
ricorda quali hai lasciato aperti. Si chiude con **Chiudi** o con Esc.

- **Titolo.**
- **Indirizzo (slug):** la parte finale dell'indirizzo della pagina, come
  in `/posts/come-funziona.html`. Vuoto, nasce dal titolo. Se un altro
  articolo usa già quell'indirizzo, il nuovo ne prende uno libero (con
  "-2" in fondo) e te lo dice: un articolo non ne sovrascrive mai un altro.
- **Tag**, separati da virgola: diventano le pagine `/tag/...` e la barra
  degli argomenti.
- **Serie** e **Parte n.:** se l'articolo fa parte di una serie, scrivi il
  nome della serie (uguale su tutte le parti; il campo propone quelle che
  esistono) e il numero della parte. Sul sito ogni parte si apre con un
  riquadro che dice la serie, "parte 3 di 7" e l'elenco di tutte le parti;
  in fondo porta alla parte precedente e alla successiva invece che agli
  articoli vicini per data. La serie ha una pagina sua,
  `/serie/<nome>.html`, con le parti dalla prima all'ultima. Le parti senza
  numero seguono quelle numerate, in ordine di data. Finché la serie ha una
  sola parte online non si vede nulla.
- **Pubblicato in origine su:** se l'articolo è uscito prima su un altro
  sito, incolla l'indirizzo di quella pagina: sotto il titolo compare
  "Pubblicato in origine su" con il nome del sito e il link. La spunta
  **Indica ai motori di ricerca che l'originale è quello** va messa solo
  se qui il testo è identico: Google mostrerà l'altro sito e non questa
  pagina. Se qui l'articolo è più ampio, lasciala vuota.
- **Tipo di articolo:** uno stesso tema può avere tre articoli. L'**Articolo**
  è l'idea; **In pratica** è la versione per chi decide (una startup, un
  CTO); il **Lab** è la parte con il codice. Gli ultimi due indicano
  l'**articolo di riferimento** da cui partono: si aprono con un riquadro
  che lo dice e, in fondo al testo, ognuno dei tre porta agli altri due.
  Negli elenchi hanno l'etichetta "In pratica" o "Lab". Un lab ha in più
  l'**indirizzo del progetto** (per esempio il repository su GitHub),
  **Fatto con** (linguaggi e librerie) e **Per eseguirlo** (i comandi, uno
  per riga), che compaiono nel riquadro in cima. Quando c'è almeno un lab
  online compaiono la pagina `/labs.html`, che li elenca tutti, la voce
  **Labs** nel menu e, in cima alla home, la sezione **Labs** con gli
  ultimi tre. Per scrivere il lab di un articolo che esiste già usa **Crea
  il lab di questo articolo**, nell'editor dell'articolo o nel suo menu
  nell'elenco: si apre un articolo nuovo già impostato come lab e legato a
  quello.
- **Immagine di copertina:** carichi un file o incolli un indirizzo. Appare
  nell'elenco della home, in cima all'articolo e nelle anteprime social.
- **Anteprima per i lettori:** il testo sotto il titolo negli elenchi; vuoto,
  si usano le prime parole dell'articolo.
- **Descrizione SEO:** la frase che Google mostra sotto il titolo, ideale
  120-160 caratteri; un contatore ti guida.

### 4.2 Il testo

La barra dell'editor ha: carattere e dimensione, grassetto, corsivo,
sottolineato, barrato, colore del testo e dello sfondo, pedice e apice,
titoli, elenchi puntati, numerati e con caselle, rientri, allineamento,
citazioni, blocchi di codice, link, immagini, video. **Passa il mouse su un
pulsante** e una nuvoletta dice cosa fa.

Sotto l'editor, **Inserisci:** **Carica immagine**, **Inserisci video
YouTube**, **Carica un video**, **Inserisci tabella**.

- **Immagini:** PNG, JPEG, GIF, WebP e SVG (le SVG restano nitide a ogni
  ingrandimento: ideali per i diagrammi), fino a 10 MB; le JPEG troppo
  grandi vengono ridotte nel browser prima di partire. Clicca l'immagine e
  trascina gli angoli per ridimensionarla; i pulsanti di allineamento la
  centrano o la mettono a sinistra o a destra, con il testo intorno.
- **Codice:** il pulsante `<>` crea un blocco; sul sito il codice viene
  colorato secondo il linguaggio e ha un pulsante "Copia".
- **Tabelle:** **Inserisci tabella** chiede righe e colonne; clicca una
  tabella per modificarla in una finestra (celle, righe, colonne). Le
  tabelle incollate da Word restano tabelle; quelle che in Word servivano
  solo a impaginare diventano testo normale. Sul telefono le tabelle larghe
  scorrono di lato.
- **Video:** YouTube incollando il link, o un file MP4/WebM fino a 100 MB.
- **Incollare da Word:** testo e immagini arrivano insieme, e le immagini
  vengono caricate da sole; un messaggio dice quante.

### 4.3 Importare un documento Word

**Importa da Word (.docx)**, sopra l'editor, carica un documento intero
(fino a 30 MB): titoli, grassetti e corsivi, allineamenti, elenchi anche
annidati, tabelle con le celle unite, immagini con il loro testo
alternativo, note a piè di pagina, link, apici e pedici, caselle di testo. Il
titolo del documento (stile Titolo o Titolo 1 all'inizio) diventa il titolo
dell'articolo e il sottotitolo la descrizione, se è vuota. Restano fuori il
sommario di Word, il testo nascosto, le immagini WMF/EMF (che nessun browser
mostra), le immagini collegate e non incorporate, i link che non sono http,
https o mailto, le equazioni: un avviso dice cosa è stato saltato.

Tre cose di Word non hanno un equivalente nell'editor e vengono adattate:

- **A capo dentro un paragrafo** (Maiusc+Invio): ogni riga diventa un
  paragrafo, con lo stesso allineamento. Nei titoli e nelle voci d'elenco
  l'a capo diventa uno spazio; nelle celle delle tabelle resta.
- **Immagini:** un'immagine seguita dalla sua didascalia, o da un testo
  sulla stessa riga, va su una riga sua e il testo su quella dopo. Resta
  nella frase solo se ha testo da tutte e due le parti, o se è un'icona.
  Un'immagine "flottante", con il testo che le gira intorno, va prima del
  paragrafo a cui è ancorata (dopo, se in Word stava più in basso) insieme
  alla sua didascalia. Ogni immagine tiene la larghezza che aveva nel
  documento; se andava da margine a margine riempie la colonna
  dell'articolo.
- **Tabelle usate per impaginare:** una tabella con una sola riga o una
  sola colonna (un'immagine accanto a un testo, un'immagine con la sua
  didascalia) viene sciolta e il suo contenuto diventa testo normale, come
  quando si incolla da Word; un avviso lo segnala. Le tabelle vere, con più
  righe e più colonne, restano tabelle.

L'articolo importato **non è ancora salvato**: rivedilo, poi salva.

### 4.4 Stato e pubblicazione

In cima alla colonna di destra c'è lo stato dell'articolo e i pulsanti che
hanno senso in quello stato:

- **Bozza** ("i lettori non la vedono"): **Salva bozza** (o Ctrl+S),
  **Anteprima**, **Pubblica**. Le bozze si salvano anche da sole ogni
  minuto.
- **Pubblicato** (con il link **Vedi online**): **Aggiorna l'articolo** (o
  Ctrl+S) salva e mette subito online; **Anteprima** fa vedere le modifiche
  prima; **Ritira dalla pubblicazione** toglie la pagina dal sito e
  l'articolo torna bozza.

**Programmata** ("Programmato · esce il..."): l'articolo esce da solo a
un'ora scelta. Da una bozza, **Programma la pubblicazione…** apre un campo
con data e ora (nell'ora del tuo computer; la proposta è domani alle 9) e
**Programma** chiede conferma. Fino a quel momento i lettori non lo vedono;
poi esce entro un minuto, datato all'ora programmata, così sta in cima agli
elenchi come un articolo nuovo. Intanto puoi correggerlo con **Salva le
modifiche**, **Cambia data e ora…**, **Pubblica ora** o **Annulla la
programmazione** (torna bozza). Nella pagina Articoli ha l'etichetta
"Programmato", dice quando esce e ha un suo filtro.

L'uscita la fa l'editor acceso, che controlla ogni minuto; anche ogni
`build` pubblica gli articoli arrivati alla loro ora. Se l'editor non resta
acceso (il modo A del capitolo 2.5), un `cron` che rigenera e carica il sito
fa lo stesso lavoro, per esempio ogni cinque minuti:
`*/5 * * * * cd /percorso/pyblog && python3 pyblog.py build && rsync -az --delete output/ utente@tuodominio.it:/var/www/blog/`.

**Anteprima** apre la pagina vera, con la grafica del sito, così com'è in
quel momento nell'editor, **senza salvare niente**. Pubblicare e ritirare
chiedono conferma. Sotto i pulsanti una riga dice se ci sono "Modifiche non
salvate"; se esci con qualcosa da salvare, il browser te lo chiede.
**Elimina l'articolo** è in fondo alla colonna.

### 4.4b Le versioni precedenti

Ogni salvataggio tiene la versione che sostituisce. Sotto il pannello di
pubblicazione, **Versioni precedenti** apre l'elenco, dalla più recente: per
ognuna il momento, lo stato, le parole e il titolo. Scegline una per
vederla; **Riporta nell'editor** rimette nei campi titolo, testo,
descrizione, anteprima, tag, copertina e traduzione di quella versione.
Niente è salvato finché non salvi: per tenerla salva, per lasciar perdere
esci senza salvare. L'indirizzo, lo stato e i codici dell'articolo restano
come sono. Se nell'editor ci sono modifiche non salvate, chiede conferma.

L'autosalvataggio scrive ogni minuto, quindi una versione viene tenuta solo
se l'ultima ha più di dieci minuti; una versione **pubblicata** si tiene
sempre, perché è quella che hanno letto i lettori. Si tengono le ultime 50
versioni per articolo, in `posts/.history/<indirizzo>/`. Le versioni seguono
l'articolo quando cambia indirizzo e se ne vanno quando lo elimini; il
backup le contiene.

### 4.5 Gli aiuti di AI

Usano il servizio scelto in **Impostazioni → Traduzione** (serve una
chiave, vedi [2.9](#29-chiavi-segrete-con-le-variabili-dambiente)). I
pulsanti di AI hanno tutti la stessa icona e lo stesso colore viola.

- **Suggerisci con AI** accanto alla descrizione SEO e **Genera con AI**
  accanto all'anteprima per i lettori: una proposta a partire dal testo, da
  ritoccare.
- **Analizza con AI**, nel riquadro dell'analisi SEO: keyword principali e a coda lunga, tag consigliati (con
  un pulsante che li applica), varianti di titolo, un giudizio sulla
  descrizione, gli anchor text per i backlink dal sito esterno indicato in
  `seo.backlink_site`, i link interni verso gli altri articoli, domande e
  risposte (FAQ) per i motori di AI e consigli per l'articolo. Ogni voce ha
  il pulsante Copia. Serve l'articolo salvato almeno una volta.

Se una chiamata fallisce, il messaggio dice il perché: chiave sbagliata o
mancante, credito esaurito, modello inesistente.

### 4.6 Codici esterni sull'articolo

Nella colonna di destra, **Codici esterni** elenca i codici del sito che
possono uscire su questo articolo: quelli "da spuntare" escono solo con la
spunta, quelli "di serie" escono finché non la togli (per esempio, un
articolo senza pubblicità). Sotto, **Solo per questo articolo** accoglie
codice che esce soltanto lì: un lettore di podcast, un modulo d'iscrizione,
un annuncio dedicato. Anche questo codice può andare in un punto scelto
cliccando sulla pagina (vedi [6.4](#64-il-punto-scelto-sulla-pagina)). Vedi
il capitolo [6](#6-codici-esterni-statistiche-annunci-widget).

### 4.7 La versione nell'altra lingua

In fondo alla colonna, la sezione della traduzione (vedi
[10](#10-due-lingue-e-traduzione-automatica)): spunti **Autorizza la
creazione della versione inglese**, clicchi **Traduci automaticamente** o
scrivi a mano titolo, descrizione, anteprima e testo, controlli con
**Anteprima della pagina in inglese**, e quando sei convinto spunti
**Conferma la traduzione** e salvi.

---

## 5. Le Impostazioni, sezione per sezione

Le Impostazioni sono divise in sezioni, una per cosa da fare; se ne vede una
alla volta. Sul computer le sezioni sono nel menu a sinistra; sul telefono
la pagina si apre su un elenco, e la freccia in alto torna all'elenco. Ogni
campo ha l'aiuto sotto.

La barra in fondo dice **Modifiche non salvate** quando c'è qualcosa da
salvare. **Salva e aggiorna il sito** salva tutte le sezioni insieme e
rigenera il sito pubblico; **Annulla le modifiche** riporta tutto
all'ultimo salvataggio. Se esci con modifiche non salvate, il browser te lo
chiede.

### 5.1 Sito e autore

- **Il sito:** titolo, sottotitolo, **dominio** (`https://tuodominio.it`,
  senza barra finale: da qui nascono sitemap, indirizzi canonici e
  anteprime social) e **lingua principale** (quella in cui scrivi: sta alla
  radice del sito, la traduzione va in una sottocartella).
- **Chi scrive:** nome, ruolo, breve biografia, foto, pagina personale,
  profili pubblici (uno per riga: GitHub, LinkedIn, X...) e account X del
  sito. Finiscono nei dati strutturati delle pagine (schema.org) e nei meta
  tag social: aiutano Google a riconoscerti come autore e a collegare i tuoi
  profili. Tutti facoltativi.
- **Logo e icona:** il logo del sito e una favicon personalizzata (vuota,
  PyBlog ne genera una con l'iniziale del titolo).

### 5.2 Home page

- **Presentazione:** il testo libero della home, con l'editor visuale
  (immagini, video, allineamenti), e la sua versione nell'altra lingua, con
  la traduzione automatica. **Mostra/nascondi anteprima homepage** fa vedere
  com'è.
- **Disposizione:** la presentazione **nella barra laterale** (gli articoli
  partono dall'alto) o **sopra gli articoli**; **metti in evidenza l'ultimo
  articolo** (più grande, con la copertina); quante **parole di anteprima**
  per gli articoli senza anteprima; quanti **articoli per pagina** (0 =
  tutti in una pagina).
- **Pagina dell'articolo:** mostrare o no la copertina in cima
  all'articolo.

### 5.3 Biografia

Spenta finché non spunti **Mostra la biografia**. Scrivi il testo con
l'editor, scegli una **foto** (vuota, si usa quella di "Sito e autore") e
**dove compare in home**: nella barra laterale, sopra o sotto gli articoli.
In home si vedono la foto e le prime righe, con **Leggi la biografia** che
porta alla pagina con tutto il testo (`/pagine/biografia.html`, o
`/pagine/biography.html` se il sito è in inglese). Sotto c'è la versione
nell'altra lingua, con la traduzione automatica.

### 5.4 Progetti

Spenti finché non spunti **Mostra i progetti**. **Aggiungi un progetto** crea
una scheda: nome, descrizione breve (anche nell'altra lingua), link e
un'immagine facoltativa (ritagliata in 16:9). Le frecce cambiano l'ordine,
**Mostra questo progetto** lo nasconde senza cancellarlo. Sopra o sotto gli
articoli i progetti sono una griglia di schede; nella barra laterale un
elenco compatto. Un progetto senza link non porta da nessuna parte.

### 5.5 Pagine

Le pagine del riquadro **Esplora** della barra laterale: contatti, una
galleria, avvisi. Ognuna ha un titolo, un testo scritto con l'editor e un
suo indirizzo (`/pagine/<titolo>.html`). **Mostra questa pagina** la mette
online; **Mostra il riquadro Esplora** accende o spegne tutto il riquadro
(ogni pagina ricorda la sua scelta). Una pagina con lo stesso nome della
biografia viene saltata finché la biografia è accesa.

In cima alla sezione c'è il **pulsante "Lavora con me"**: acceso, chiude il
menu di ogni pagina con un pulsante in evidenza e mette un invito alla fine
di ogni articolo. In **Dove porta** scrivi la destinazione: una pagina del
sito (creala qui sotto, per esempio "Lavora con me", e incolla
`/pagine/lavora-con-me.html`), un indirizzo email (`mailto:...`) o un
profilo. Scritta del pulsante e frase dell'invito si possono cambiare, in
italiano e in inglese; vuote, usano quelle predefinite.

### 5.6 Commenti

Nessuno, **Giscus** o **Disqus**: vedi [8](#8-commenti).

### 5.6b Newsletter

Il modulo d'iscrizione, dove compare, i suoi testi, l'invio automatico alla
pubblicazione, l'account SMTP con l'email di prova e l'elenco degli
iscritti: vedi [8b](#8b-newsletter).

### 5.7 Traduzione

Il servizio (DeepL, Google Translate, Anthropic Claude, OpenAI, DeepSeek) e
la sua chiave, più endpoint e modello dove servono. Senza chiave la
traduzione resta spenta e il sito funziona lo stesso. Lo stesso servizio fa
anche gli aiuti di AI dell'editor. Vedi [10](#10-due-lingue-e-traduzione-automatica).

### 5.8 Statistiche e annunci

- **Statistiche:** l'ID di Google Analytics 4 e i due campi di Umami (vedi
  [9](#9-statistiche-delle-visite)).
- **Codici esterni e annunci:** con la guida a tre esempi; vedi
  [6](#6-codici-esterni-statistiche-annunci-widget).
- **ads.txt:** vedi [6.6](#66-adstxt).

### 5.9 Cookie e privacy

Il banner del consenso: vedi [7](#7-il-banner-dei-cookie).

### 5.10 Addestramento AI

Se i servizi di intelligenza artificiale possono usare i tuoi testi:

- **Consentito:** nessuna restrizione;
- **Solo su licenza:** i crawler di AI noti vengono bloccati in
  `robots.txt`, con un'email per chiedere una licenza;
- **Non consentito:** bloccati, nessuna licenza offerta.

Puoi indicare un indirizzo dei tuoi termini di licenza e un testo tuo. La
scelta finisce in `robots.txt`, `llms.txt`, `/.well-known/ai.txt`,
`/.well-known/tdmrep.json` (un tentativo in buona fede di seguire il TDM
Reservation Protocol, una convenzione non vincolante e ancora in
evoluzione) e nella pagina pubblica `/training-rights.html`.

### 5.11 Avanzate

Modifica diretta di `config.json`. Il testo viene controllato prima del
salvataggio: un JSON rotto viene rifiutato con la riga e la colonna
dell'errore, e il sito resta com'era. **Ripristina** torna al file salvato.
Da usare solo se sai cosa stai facendo; il riferimento è al capitolo
[13](#13-riferimento-di-configjson).

---

## 6. Codici esterni: statistiche, annunci, widget

Un servizio esterno ti dà un pezzo di HTML o JavaScript da mettere nelle tue
pagine: Google Analytics, AdSense, Tag Manager, un pixel, una chat. Non
serve toccare i file del programma: vai in **Impostazioni → Statistiche e
annunci → Codici esterni e annunci**. Una guida con tre esempi mostra, per
ognuno, il codice che dà il servizio e cosa scegliere qui.

### 6.1 Aggiungere un codice

**Aggiungi codice** chiede che cosa vuoi aggiungere.

- **I servizi più comuni sono pronti:** Google Analytics 4, Google Tag
  Manager, AdSense (annunci automatici o un'unità pubblicitaria), Google Ads
  (tag delle conversioni), Meta Pixel, Microsoft Clarity. Scrivi solo l'ID
  (per esempio `G-AB12CD34EF`) e **Crea**: il codice viene preparato con la
  posizione, le pagine e il consenso adatti, e se l'ID ha una forma
  sbagliata te lo dice prima. Con AdSense viene aggiunta anche la riga di
  `ads.txt`.
- **Codice libero** per tutto il resto: una scheda vuota.

Ogni codice è una scheda, chiusa su una riga che dice dove va, su quali
pagine e con quale consenso; cliccala per aprirla. Ogni scheda ha:

1. **Attivo:** spento vuol dire spento ovunque, senza cancellarlo.
2. **Nome:** per ritrovarlo, non finisce nelle pagine.
3. **Dove va nella pagina** (vedi 6.2).
4. **Su quali pagine** (vedi 6.3).
5. **Consenso del visitatore** (vedi 6.5).
6. **Codice:** incollato così com'è; il riquadro colora il codice e numera
   le righe.

### 6.2 Le posizioni

*Nel codice della pagina (non si vede):*

| Posizione | Dove | Per |
|---|---|---|
| Intestazione della pagina (head) | dentro `<head>` | statistiche, Tag Manager, pixel, verifiche di proprietà |
| Inizio della pagina | subito dopo `<body>` | il `<noscript>` di Tag Manager |
| Fondo della pagina | prima di `</body>` | chat e script che possono aspettare (`defer`, `async`) |

*Visibile nella pagina:*

| Posizione | Dove | Esiste su |
|---|---|---|
| Nel menu dell'intestazione | accanto a Home, Articoli, Archivio | tutte le pagine; per un link in più, per esempio "Chiedi all'assistente" che apre una chat |
| Sotto l'intestazione | prima del contenuto | tutte |
| Nella barra laterale | dopo la presentazione: il posto di un annuncio 300×250 | home, articoli, tag, archivio, pagine |
| Tra gli articoli della home | dopo il terzo | solo la home |
| All'inizio dell'articolo | dopo titolo e copertina | solo gli articoli |
| A metà dell'articolo | dopo il paragrafo più vicino alla metà: mai dentro una tabella o un elenco, mai fra un titoletto e il suo paragrafo; un articolo corto lo riceve in fondo | solo gli articoli |
| In fondo al testo dell'articolo | prima della firma dell'autore | solo gli articoli |
| Prima del piè di pagina | dopo il contenuto | tutte |
| **In un punto che scegli sulla pagina…** | dove lo clicchi tu (vedi 6.4) | le pagine che hanno quel punto |

Su una pagina che non ha la posizione scelta, il codice non esce.

### 6.3 Le pagine

**Tutto il sito** (anche archivio, tag, pagine e 404), **solo la
homepage**, **solo gli articoli**, **homepage e tutti gli articoli**,
**solo gli articoli scelti**, **homepage e articoli scelti**. Con "articoli
scelti" il codice esce su un articolo solo se lo spunti nel suo editor; con
le altre esce ovunque, e nell'editor di un articolo puoi spegnerlo solo lì.

### 6.4 Il punto scelto sulla pagina

Quando le posizioni del menu non bastano (un annuncio dopo il secondo
paragrafo, un widget prima dei commenti, un banner sotto la biografia),
scegli **In un punto che scegli sulla pagina…**: si apre una finestra con la
pagina vera, generata al momento **senza nessun codice esterno**.

1. In alto scegli su quale pagina: la home o uno degli articoli pubblicati
   (nell'editor di un articolo, quell'articolo; va salvato prima).
2. Passa sopra la pagina: i blocchi si colorano. **Clicca** quello vicino al
   quale vuoi il codice. Lo stesso elenco di blocchi è nel menu **Blocco
   della pagina**, per chi usa la tastiera o un lettore di schermo.
3. Scegli se il codice va **Prima** o **Dopo**. Un riquadro tratteggiato
   mostra dove andrà.
4. **Metti qui.** La scheda dice il punto, per esempio "Dopo · Paragrafo 2
   del testo".

Il punto vale per **tutte le pagine dello stesso tipo**: scelto su un
articolo, "Dopo · Paragrafo 2 del testo" mette il codice dopo il secondo
paragrafo di ogni articolo che ce l'ha (insieme alla scelta "Su quali
pagine"). Dove il punto non c'è (un articolo con un paragrafo solo), il
codice non compare. Tecnicamente il punto è un selettore CSS
(`div.post-content > p:nth-of-type(2)`) e un lato; la pagina pubblicata
porta il codice inerte in fondo e `site.js` lo sposta nel punto e lo fa
partire. Se aspetta il consenso, aspetta già al suo posto. Se cambi
posizione, il punto scelto resta salvato e lo ritrovi tornando a "In un
punto che scegli".

### 6.5 Il consenso

Conta solo con il banner dei cookie acceso (vedi
[7](#7-il-banner-dei-cookie)):

- **Necessario:** parte sempre. Un widget che non segue i visitatori.
- **Statistiche:** Google Analytics, Clarity e simili.
- **Pubblicità:** AdSense, Google Ads, Meta Pixel.

### 6.6 ads.txt

Dice chi può vendere pubblicità sul sito: AdSense lo cerca all'indirizzo
`/ads.txt` e limita gli annunci finché non lo trova. Si scrive nel campo
**ads.txt** (il modello di AdSense ci aggiunge la sua riga); vuoto, il file
non viene pubblicato, e se c'era viene tolto.

### 6.7 Per provarlo, e la fiducia

Prova un codice **sul sito o nell'anteprima di un articolo**, non nelle
Impostazioni: l'amministrazione blocca i domini esterni per sicurezza, e lì
il widget sembrerebbe rotto.

Il codice viene inserito **così com'è**, senza controlli (controllarlo
vorrebbe dire impedirgli di funzionare): chi entra nell'amministrazione può
eseguire qualunque JavaScript sul sito pubblico. Incolla solo codice di
servizi di cui ti fidi e tieni la password al sicuro. Cancellare un codice
è sicuro: gli articoli che lo avevano spuntato semplicemente non lo
ricevono più.

---

## 7. Il banner dei cookie

In Europa statistiche e pubblicità che usano cookie possono partire solo
dopo il consenso del visitatore. In **Impostazioni → Cookie e privacy**
spunta **Mostra il banner del consenso ai visitatori**, indica l'indirizzo della tua informativa
privacy e salva.

Da quel momento:

- i codici "Statistiche" e "Pubblicità", e Google Analytics, arrivano nella
  pagina fermi (dentro un `<template>`): niente script, niente cookie,
  niente richieste finché il visitatore non accetta;
- il visitatore può **accettare tutto**, **rifiutare** o **scegliere**;
  rifiutare pesa quanto accettare (due pulsanti uguali); la scelta resta nel
  suo browser;
- i tag di Google ricevono la scelta tramite **Consent Mode** (tutto negato
  finché il visitatore non decide);
- in fondo a ogni pagina **Preferenze cookie** riapre il banner; ritirare un
  consenso ricarica la pagina senza quel codice.

Il banner compare solo se qualche codice ne ha bisogno. Il testo si può
cambiare, anche nell'altra lingua (vuoto = quello predefinito). Quando
aggiungi un servizio nuovo, **Chiedi di nuovo il consenso a tutti** e salva:
ogni visitatore rivedrà il banner.

**AdSense in Europa** chiede anche un CMP certificato (TCF): puoi accendere
il messaggio gratuito di Google dal pannello di AdSense ("Privacy e
messaggi") e lasciare AdSense su "Necessario", oppure usare questo banner
con AdSense su "Pubblicità": gli annunci partono dopo il consenso.

Il banner è uno strumento, non una consulenza legale: l'informativa e la
scelta dei servizi restano tue.

---

## 8. Commenti

Un sito statico appoggia i commenti a un servizio esterno.

**Giscus** (gratis, senza pubblicità, ideale per blog tecnici): usa le
Discussioni di un repository GitHub.

1. Crea un repository pubblico su GitHub e in Settings → Features accendi
   **Discussions**.
2. Installa l'app: https://github.com/apps/giscus
3. Su https://giscus.app inserisci il repository e copia i quattro valori:
   repo, repo ID, category, category ID.
4. **Impostazioni → Commenti:** scegli Giscus, incolla i valori (il tema è
   `light` o `dark`), salva.

**Disqus** (accesso con i social, ma con pubblicità): registrati su
https://disqus.com, crea il sito e ottieni lo **shortname**; in
**Impostazioni → Commenti** scegli Disqus, scrivilo e salva.

---

## 8b. Newsletter

I lettori si iscrivono dal sito e ricevono un'email quando pubblichi un
articolo. Tutto resta sul tuo server: gli iscritti stanno in
`subscribers.json` (accanto a `config.json`, privato come lui) e le email
partono dal tuo account SMTP, senza servizi in mezzo.

**Cosa serve.** L'editor online (il modo C del capitolo 2.5, quello del
tutorial): il modulo d'iscrizione è sul sito statico ma deve raggiungere
PyBlog, e nginx gli passa `/iscriviti`, `/conferma` e `/disiscrivi` (con un
limite di richieste suo). E un **account SMTP**: quello del tuo provider di
posta o di un servizio come Brevo, Mailgun o Amazon SES, che ti dà server,
porta, utente e password.

**Accenderla.** In **Impostazioni → Newsletter**: spunta **Attiva la
newsletter**, scegli dove compare il modulo (nella barra laterale, in fondo
a ogni articolo), compila **Spedizione delle email** e clicca **Manda
un'email di prova**: arriva all'indirizzo del mittente, con i dati scritti,
anche prima di salvare. Poi **Salva e aggiorna il sito**. La password SMTP è
meglio in `/etc/pyblog.env` come `PYBLOG_SMTP_PASSWORD=...`: ha la
precedenza e non compare mai nella pagina; il campo vuoto tiene quella
salvata.

**L'iscrizione, con doppio consenso.**

1. Il lettore scrive il suo indirizzo e clicca **Iscriviti**: la pagina dice
   "Controlla la posta", qualunque cosa sia successo (così il modulo non
   rivela chi è già iscritto).
2. Gli arriva un'email con il link di conferma; se lo chiede di nuovo, il
   link riparte al massimo ogni dieci minuti.
3. Il link apre una pagina con il pulsante **Confermo l'iscrizione**: il
   link da solo non conferma, perché i programmi antivirus della posta
   aprono tutti i link. Senza conferma l'indirizzo non riceve nient'altro.

Un campo nascosto ferma i robot che compilano i moduli, e ogni indirizzo
internet può fare al massimo cinque richieste all'ora.

**Gli invii.** Quando pubblichi un articolo per la **prima volta**, gli
iscritti confermati ricevono un'email con il titolo, le prime righe e il
link, nella loro lingua se l'articolo è tradotto. Vale anche per gli
articoli programmati, all'ora in cui escono. Non vengono mandati gli
articoli pubblicati prima di accendere la newsletter (anche se li correggi
dopo), né quelli per cui nell'editor togli la spunta **Avvisa gli iscritti
quando lo pubblichi**, né lo stesso articolo due volte. Con **Avvisa gli
iscritti quando pubblichi un articolo** spenta, non parte niente. Le email
partono da un thread dell'editor, una alla volta; un articolo da mandare è
scritto su disco, quindi un riavvio non lo perde, e se il server di posta
non risponde si riprova ogni minuto.

**Disiscriversi.** In fondo a ogni email c'è **Disiscriviti** (anche qui una
pagina con un pulsante), e i programmi di posta mostrano il loro pulsante di
disiscrizione con un clic (`List-Unsubscribe-Post`). Funziona anche con la
newsletter spenta.

**Gli iscritti.** Nella stessa sezione vedi quanti sono confermati e quanti
in attesa, l'elenco (con **Rimuovi**), l'esito dell'ultimo invio e **Scarica
l'elenco (CSV)**. Il backup `.zip` li contiene.

Per la privacy: tieni solo l'indirizzo, la lingua e le date; dillo
nell'informativa, il cui link compare sotto il modulo se l'hai indicato in
"Cookie e privacy".

## 9. Statistiche delle visite

Gli script di statistica vanno solo nelle pagine pubbliche: l'editor non
viene mai tracciato.

- **Umami** (consigliato): installato sul tuo server, **senza cookie**,
  quindi senza banner; i dati restano tuoi.
- **Google Analytics 4:** basta l'ID (`G-XXXXXXXXXX`). Usa cookie: in Europa
  accendi il banner, e GA parte solo dopo il consenso alle statistiche.
- **I log di nginx**, senza nessuno script: `tail -f
  /var/log/nginx/blog-access.log` per le visite dal vivo, oppure un
  cruscotto con `sudo apt install goaccess` e `goaccess
  /var/log/nginx/blog-access.log`.

### Installare Umami con Docker

Nel progetto c'è `umami-docker-compose.yml`.

1. Copialo sul server (per esempio `/opt/umami/docker-compose.yml`) e
   sostituisci `CAMBIAMI_PASSWORD_DB` (in **due** punti, identica) con una
   password per il database e `CAMBIAMI_SEGRETO_CASUALE` con il risultato di
   `openssl rand -base64 32`.
2. `docker compose up -d`. Umami ascolta solo su `127.0.0.1:3000`, di
   proposito.
3. Esponilo con nginx su un sottodominio:

   ```nginx
   server {
       server_name stats.tuodominio.it;
       location / {
           proxy_pass http://127.0.0.1:3000;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   poi `sudo certbot --nginx -d stats.tuodominio.it`.
4. Primo accesso su `https://stats.tuodominio.it` con `admin` / `umami`:
   **cambia subito la password** (Settings → Profile).
5. Settings → Websites → Add website, con il dominio del blog: Umami mostra
   il **Website ID**, l'unico dato che serve.
6. In **Impostazioni → Statistiche e annunci** scrivi l'indirizzo di Umami e
   il Website ID, e salva.

Per verificare: apri il blog in una finestra anonima e guarda la vista
Realtime di Umami. Gli adblocker bloccano anche Umami: i numeri sono sempre
un po' più bassi del vero, come per qualunque sistema. Nel backup includi il
volume Docker `umami-db`.

---

## 10. Due lingue e traduzione automatica

Il sito ha una **lingua principale** (Impostazioni → Sito e autore), che sta
alla radice (`/`), e l'altra in una sottocartella (`/en/` o `/it/`). La
traduzione va sempre dalla principale all'altra.

Per un articolo (vedi [4.7](#47-la-versione-nellaltra-lingua)):

1. **Autorizza la creazione della versione inglese.**
2. **Traduci automaticamente**, o scrivi a mano titolo, descrizione,
   anteprima e testo.
3. **Anteprima della pagina in inglese**: la pagina com'è, senza salvare.
4. **Conferma la traduzione** e salva: l'articolo compare nella home
   dell'altra lingua, nel suo archivio, nel suo feed e nella sitemap.

Immagini, video e riquadri incorporati non vengono mandati al servizio:
restano da parte e tornano al loro posto. Se il servizio perde il
segnaposto di un'immagine, PyBlog la rimette e te lo dice; controlla dov'è
finita prima di confermare. Il testo alternativo delle immagini resta nella
lingua originale.

Con il sito in inglese tutto si rovescia: scrivi in inglese, la sezione
diventa "Versione in italiano" e le pagine tradotte vanno in `/it/`.
Commenti, date, banner e anteprime seguono la lingua di ciascuna pagina.
L'**interfaccia dell'amministrazione** ha una lingua sua, indipendente: si
cambia dal menu.

I servizi: **DeepL**, **Google Cloud Translation**, **Anthropic Claude**,
**OpenAI**, **DeepSeek**. Per provare in locale con Anthropic: servizio
"Anthropic Claude", endpoint `https://api.anthropic.com/v1/messages`, un
modello (per esempio `claude-sonnet-4-5`) e la chiave, nelle Impostazioni o
con `export PYBLOG_LLM_API_KEY=...`.

---

## 11. Il sito pubblico: cosa viene generato

- **Home a due colonne:** gli articoli con miniatura e prime righe (il più
  recente in evidenza), la ricerca, e la barra laterale con presentazione,
  biografia e progetti (se li metti lì), il riquadro Esplora e "Seguimi".
  Sul telefono la barra scende sotto gli articoli e il menu si apre da un
  pulsante.
- **Paginazione:** oltre gli "articoli per pagina", le pagine successive
  sono `/pagina/2.html`, `/pagina/3.html`... (`/en/page/2.html` in inglese),
  con i numeri di pagina.
- **Archivio:** tutti gli articoli per anno (`/archivio.html`,
  `/en/archive.html`).
- **Tag:** una pagina per tag (`/tag/<tag>.html`) e la barra degli argomenti.
- **Articolo:** percorso, titolo, data e tempo di lettura, copertina, indice
  (nella barra laterale, che segue la lettura; sul telefono un menu
  richiudibile), blocchi di codice colorati con "Copia", barra di
  avanzamento della lettura, firma dell'autore, articolo precedente e
  successivo, articoli correlati, commenti.
- **Ricerca** nel browser su tutti gli articoli (`search-index.json`), con
  estratti ed evidenziazione.
- **Tema chiaro e scuro**, che segue il sistema e ricorda la scelta.
- **404** con la ricerca e gli ultimi articoli.
- **Feed RSS** per lingua (`/rss.xml`, `/rss-en.xml` o `/rss-it.xml`).
- **SEO:** meta description, canonical, hreflang tra le due lingue, Open
  Graph, Twitter Card, dati strutturati JSON-LD (WebSite, Person con foto,
  ruolo e profili, Article), `sitemap.xml`, `robots.txt`, `llms.txt`.
- **Favicon** generata con l'iniziale del titolo, se non ne indichi una.

Le pagine sono HTML statico, con un solo foglio di stile (`style.css`, più
`common.css` condiviso con l'amministrazione), font di sistema e un solo
script leggero (`site.js`).

---

## 12. Importare ed esportare

### 12.1 Markdown

```bash
python3 pyblog.py import-md cartella-con-i-file/    # o un file solo
python3 pyblog.py export-md cartella-di-destinazione/
```

L'import legge il "front matter" (il blocco tra due righe `---` in cima,
quello di Hugo e Jekyll), con i campi in italiano o in inglese:

```
---
title: Il mio articolo         (anche: titolo:)
date: 2025-03-15               (anche: data:)
description: Frase per Google  (anche: descrizione:)
tags: [python, tutorial]       (oppure separati da virgole)
slug: il-mio-articolo          (facoltativo)
status: published              (anche: stato: pubblicato / draft: false)
---
```

Senza `status`, l'articolo arriva come **bozza**; senza titolo, si usa il
primo `#` del testo o il nome del file. Il convertitore copre titoli,
grassetto, corsivo, codice, link, immagini, elenchi, citazioni e righe
orizzontali; non le tabelle Markdown e le note (per le tabelle usa l'editor
dopo l'import). Con l'editor acceso, riavvialo dopo l'import.

L'export scrive un `.md` per articolo, con il suo front matter. È una
conversione semplificata: colori, allineamenti e dimensioni diventano testo
semplice, e gli elenchi numerati diventano puntati.

### 12.2 Word

```bash
python3 pyblog.py import-docx documento.docx      # o una cartella
```

Importa come **bozze**, con le stesse regole del pulsante dell'editor (vedi
[4.3](#43-importare-un-documento-word)); quello che viene saltato è scritto
nelle righe `warning:`.

### 12.3 Il backup in un file

**Scarica il backup** nel menu: uno `.zip` con articoli, immagini e
impostazioni. Vedi anche [2.11](#211-backup-e-ripristino).

---

## 13. Riferimento di config.json

Tutte le impostazioni stanno in **`config.json`**, nella cartella del
progetto: si crea al primo salvataggio delle Impostazioni, contiene chiavi
segrete ed è escluso da git. Un modello con tutti i campi è in
`config.example.json`. Di norma si modifica dalle Impostazioni; a mano,
ricordati di rigenerare il sito (`build`) dopo.

Un campo che manca prende il valore predefinito: i file vecchi restano
validi quando arrivano campi nuovi.

### 13.1 Generali

| Campo | Significato |
|---|---|
| `site_title` | Il titolo del sito. |
| `subtitle` | La frase sotto il titolo. |
| `author` | Il nome dell'autore (meta tag, piè di pagina, dati strutturati). |
| `base_url` | Il dominio, senza barra finale (`https://tuodominio.it`): sitemap, canonical, social. |
| `language` | La lingua principale, `it` o `en`: sta alla radice, l'altra in una sottocartella. |
| `admin_language` | La lingua dell'amministrazione, `it` o `en`. |
| `articles_per_page` | Articoli per pagina della home (predefinito `10`; `0` = tutti in una pagina). |
| `home_intro_position` | Dove va la presentazione: `"sidebar"` (predefinito) o `"top"`. |
| `home_excerpt_words` | Parole dell'estratto negli elenchi, per gli articoli senza anteprima (predefinito `40`). |
| `share_buttons` | `true` (predefinito) mostra a fine articolo il pulsante **Copia il link**; `false` lo toglie. La condivisione su LinkedIn, Hacker News, Reddit e X si fa dall'editor: su un articolo pubblicato, **Condividi l'articolo** apre la pagina di quel sito già compilata. |
| `home_featured` | `true` (predefinito): l'ultimo articolo in evidenza in cima. |
| `article_cover` | `true` (predefinito): la copertina in cima all'articolo. |
| `home_order` | Non più usato; nei file vecchi viene ignorato. |

### 13.2 Home, biografia, progetti, pagine

| Campo | Significato |
|---|---|
| `home_content`, `home_content_en` | La presentazione della home (HTML dell'editor) e la sua traduzione; senza traduzione, l'altra lingua mostra la principale. |
| `biography` | `enabled` (predefinito `false`), `position` (`"sidebar"`, `"top"`, `"bottom"`; predefinito `"sidebar"`), `photo` (vuota = `seo.author_image`), `content`, `content_en`. |
| `projects` | `enabled` (predefinito `false`), `position` (come sopra, predefinito `"top"`), `items`: la lista nell'ordine della pagina; ogni progetto ha `name`, `description`, `description_en`, `url`, `image`, `visible`. Senza nome o con `visible: false` non compare; un link `javascript:` viene scartato. |
| `home_cards_enabled` | Interruttore del riquadro Esplora (predefinito `true`); con `false` le pagine non vengono generate. |
| `home_cards` | Le pagine del riquadro Esplora: `active`, `title`, `content`. Spenta o vuota, non ha pagina. |

### 13.3 SEO e autore (`seo`)

| Campo | Significato |
|---|---|
| `author_url` | La pagina personale o professionale. |
| `author_image` | L'indirizzo assoluto della foto. |
| `author_role` | Il ruolo (`jobTitle`). |
| `author_bio` | Una breve biografia (`description` di Person). |
| `social_profiles` | Lista di indirizzi dei profili (`sameAs`): il segnale più importante per collegarli. |
| `logo` | L'indirizzo assoluto del logo (publisher). |
| `twitter_site` | L'account X del sito, con la chiocciola. |
| `favicon` | Una favicon tua; vuota, PyBlog genera `favicon.svg`. |
| `backlink_site` | Il sito esterno che ripubblica gli articoli e ospita i backlink: l'Analisi SEO propone anchor text adatti. |

### 13.3b Newsletter (`newsletter`)

| Campo | Significato |
|---|---|
| `enabled` | `true` accende il modulo e gli invii (predefinito `false`). |
| `enabled_since` | Quando è stata accesa (lo scrive PyBlog): si mandano solo gli articoli pubblicati da allora. |
| `in_sidebar`, `after_article` | Dove compare il modulo (predefiniti `true`). |
| `title`, `text` | Titolo e testo del modulo; vuoti, quelli predefiniti. |
| `send_on_publish` | `true` (predefinito): un articolo pubblicato per la prima volta va agli iscritti. |
| `sender_name`, `sender_email` | Il mittente (il nome vuoto = il titolo del sito). |
| `smtp_host`, `smtp_port`, `smtp_security`, `smtp_user`, `smtp_password` | L'account SMTP; `smtp_security` è `starttls` (predefinito), `ssl` o `none`. La password può venire da `PYBLOG_SMTP_PASSWORD`, che ha la precedenza. |

Gli iscritti non stanno qui ma in `subscribers.json`.

### 13.4 Commenti

| Campo | Significato |
|---|---|
| `comments` | `none`, `giscus` o `disqus`. |
| `giscus` | `repo`, `repo_id`, `category`, `category_id`, `theme`. |
| `disqus` | `shortname`. |

### 13.5 Statistiche

| Campo | Significato |
|---|---|
| `analytics_id` | L'ID di Google Analytics 4 (`G-XXXXXXXXXX`); vuoto = spento. |
| `umami_url` | L'indirizzo della tua istanza Umami, senza barra finale. |
| `umami_website_id` | Il Website ID; serve insieme a `umami_url`. |

### 13.6 Codici esterni (`custom_code`) e `ads_txt`

`custom_code` è una lista; ogni codice ha:

| Campo | Significato |
|---|---|
| `id` | Identificatore stabile (`snip-...`), generato da solo; gli articoli si riferiscono a questo, non al nome. |
| `name` | Il nome che vedi tu. |
| `enabled` | `true` o `false`. |
| `position` | `head`, `body_start`, `body_end`, `nav`, `after_header`, `sidebar`, `home_feed`, `article_start`, `article_middle`, `article_end`, `before_footer`, `anchor` (vedi [6.2](#62-le-posizioni)). Una sconosciuta vale `head`. |
| `anchor_selector`, `anchor_where`, `anchor_label`, `anchor_page` | Per `anchor`: il selettore CSS del blocco, `before` o `after`, la descrizione mostrata e il tipo di pagina su cui è stato scelto (`home` o `article`). Un selettore con `<` o un a capo viene scartato. |
| `scope` | `all`, `home`, `articles`, `home_articles`, `optin`, `home_optin` (vedi [6.3](#63-le-pagine)). Uno sconosciuto vale `home`. |
| `consent` | `necessary` (predefinito), `statistics`, `marketing`. |
| `code` | Il codice, inserito così com'è. |

`ads_txt` è il testo del file `/ads.txt`; vuoto, il file non esiste.

### 13.7 Consenso (`consent`)

| Campo | Significato |
|---|---|
| `enabled` | `true` mostra il banner (predefinito `false`). |
| `text`, `text_en` | Il testo nella lingua principale e nell'altra; vuoto = quello predefinito. |
| `privacy_url` | L'informativa privacy. |
| `version` | Cresce con "Chiedi di nuovo il consenso a tutti": chi ha scelto con un numero vecchio rivede il banner. |

### 13.8 Traduzione (`translation`)

| Campo | Significato |
|---|---|
| `service` | `deepl`, `google`, `llm` (Anthropic), `openai`, `deepseek`. |
| `deepl_api_key`, `google_api_key` | Le chiavi di DeepL e Google. |
| `llm_api_key`, `llm_endpoint`, `llm_model` | Anthropic: chiave, endpoint (di norma non si cambia), modello. |
| `openai_api_key`, `openai_model` | OpenAI (per esempio `gpt-4o-mini`). |
| `deepseek_api_key`, `deepseek_model` | DeepSeek (per esempio `deepseek-chat`). |

Ogni chiave può venire da una variabile d'ambiente `PYBLOG_<CHIAVE>`, che ha
la precedenza (vedi [2.9](#29-chiavi-segrete-con-le-variabili-dambiente)).

### 13.9 Addestramento AI (`ai_training`)

| Campo | Significato |
|---|---|
| `policy` | `"open"`, `"licensed"` o `"disallow"` (vedi [5.10](#510-addestramento-ai)). |
| `contact_email` | L'email per le licenze (solo con `"licensed"`). |
| `license_url` | I tuoi termini; vuoto, la pagina `/training-rights.html` di PyBlog. |
| `statement` | Un testo tuo al posto di quello predefinito. |

### 13.10 Se config.json si rompe, e le versioni vecchie

Un `config.json` illeggibile (JSON rotto da una modifica a mano) non ferma il
sito: PyBlog lo avvisa sul terminale, ne mette una copia in
`config.broken.json` e parte con i valori predefiniti. Recupera i dati dalla
copia **prima** di salvare di nuovo le Impostazioni. I file vengono scritti
"tutto o niente": un'interruzione a metà lascia la versione vecchia, mai un
file a metà.

Le versioni vecchie usavano chiavi italiane (`titolo_sito`, `stato`,
`contenuto`...): al primo avvio PyBlog converte da solo `config.json` e gli
articoli, una volta sola.

---

## 14. File, cartelle e formato degli articoli

```
pyblog.py              il punto d'ingresso: legge il comando e lo esegue
core/                  il programma (configurazione, testi, modelli, articoli,
                       AI, accesso, import da Word, generazione, server)
templates/             i modelli HTML del sito (public/) e dell'amministrazione (admin/)
static/                common.css, style.css, site.js (sito); admin.css, admin.js
posts/                 gli articoli, un file JSON ciascuno: le tue fonti
posts/.history/        le versioni precedenti di ogni articolo
output/                il sito generato: è questa la cartella che va online
output/media/          le immagini e i video caricati
config.json            le impostazioni (escluso da git)
admin_password.txt     l'impronta della password, mai la password (escluso da git)
config.broken.json     la copia di un config.json che non si leggeva
subscribers.json       gli iscritti alla newsletter (escluso da git)
```

Un articolo in `posts/<slug>.json`:

| Campo | Significato |
|---|---|
| `title`, `slug`, `date`, `date_modified` | Titolo, indirizzo, data di creazione e dell'ultima modifica. |
| `status` | `published`, `draft` o `scheduled`. |
| `publish_at` | Per `scheduled`: il momento in cui esce, in UTC (`2026-10-04T07:00:00+00:00`); vuoto negli altri stati. |
| `content` | Il testo, in HTML. |
| `description`, `preview` | La descrizione SEO e l'anteprima per i lettori. |
| `tags` | I tag, separati da virgola. |
| `image` | La copertina. |
| `title_en`, `description_en`, `preview_en`, `content_en` | La traduzione nell'altra lingua del sito. |
| `translation_authorized`, `translation_confirmed` | Se la traduzione è permessa e se è confermata (pubblicata). |
| `custom_code_ids`, `custom_code_off_ids` | I codici del sito spuntati ("da spuntare") e spenti ("di serie") su questo articolo. |
| `custom_code` | I codici solo di questo articolo, con gli stessi campi di quelli del sito tranne `scope`; il loro `id` comincia con `art-`. |
| `first_published` | Quando è stato pubblicato la prima volta (lo scrive PyBlog). |
| `notify_subscribers`, `newsletter_sent` | Se avvisare gli iscritti alla prima pubblicazione, e se è già stato mandato. |

---

## 15. Sicurezza

- La password è salvata come impronta PBKDF2 con sale, mai in chiaro.
- Ogni pagina dell'amministrazione chiede l'accesso; ogni azione che cambia
  qualcosa chiede anche un token CSRF.
- Le sessioni scadono; il cookie è `HttpOnly`, e `Secure` dietro HTTPS.
- Chi sbaglia la password viene fermato, per indirizzo e sempre più a lungo.
- I caricamenti hanno limiti di dimensione e controlli sul tipo vero del
  file; le SVG vengono controllate; nessun percorso può uscire dalle
  cartelle previste.
- L'amministrazione manda intestazioni di sicurezza e una Content Security
  Policy; non può essere incorniciata da altri siti.
- L'editor ascolta su `localhost`; le chiavi possono stare fuori dal
  progetto, in variabili d'ambiente.
- Il servizio systemd di esempio gira con un utente suo, senza privilegi, e
  scrive solo nella sua cartella.

**I punti da tenere a mente:** l'HTTPS è obbligatorio se l'editor è online;
`config.json` e `admin_password.txt` non vanno pubblicati (sono già esclusi
da git); i codici esterni sono JavaScript che gira sul tuo sito, quindi chi
entra nell'amministrazione può fare molto: tieni la password al sicuro.

---

## 16. Problemi e soluzioni

| Cosa vedi | Perché | Cosa fare |
|---|---|---|
| **502 Bad Gateway** su `/admin` | PyBlog è spento | `sudo systemctl restart pyblog`; i messaggi con `journalctl -u pyblog -n 50` |
| **403 Forbidden** sul sito | nginx non può leggere `output/` | `sudo chmod 755 /opt/pyblog /opt/pyblog/output` |
| L'amministrazione senza grafica | `/admin-static/` non arriva a PyBlog | usa il blocco `location ^~ /admin-static/` di `nginx.conf.example` |
| Una pagina dell'amministrazione dà 404 online | la rotta non è nella riga `location ~ ^/(...)$` di nginx | confronta il tuo file con `nginx.conf.example` |
| La porta 8000 è occupata | un altro programma la usa | `python3 pyblog.py serve 9000` (e cambia `proxy_pass` in nginx) |
| Le modifiche non si vedono sul sito | il browser mostra la copia vecchia | Ctrl+F5; **Rigenera il sito** dal menu |
| Google non indicizza niente | il dominio è ancora quello d'esempio | Impostazioni → Sito e autore → Dominio |
| Le funzioni di AI danno errore | chiave mancante, sbagliata o senza credito | il messaggio dice quale; la chiave in `/etc/pyblog.env`, poi riavvia |
| Un widget non parte nelle Impostazioni | l'amministrazione blocca i domini esterni | provalo sul sito o nell'anteprima di un articolo |
| Un codice "in un punto scelto" non compare | quella pagina non ha il punto, o non è tra le pagine scelte | riapri la scelta del punto su una pagina di quel tipo |
| "Troppi tentativi" al login | protezione contro chi indovina | aspetta; riguarda solo il tuo indirizzo |
| Password dimenticata | — | `python3 pyblog.py password` sul server |
| `config.json` rotto | una modifica a mano | i dati sono in `config.broken.json` (vedi [13.10](#1310-se-configjson-si-rompe-e-le-versioni-vecchie)) |
| Certbot fallisce | il dominio non punta al server | controlla i record DNS e riprova |
| Il modulo della newsletter risponde 404 | nginx non passa `/iscriviti` a PyBlog, o la newsletter è spenta | il blocco `location ~ ^/(iscriviti|conferma|disiscrivi)$` di `nginx.conf.example`; la spunta nelle Impostazioni |
| Le email non partono | dati SMTP sbagliati, o il provider rifiuta il mittente | **Manda un'email di prova** dice l'errore; l'ultimo invio fallito è scritto nella sezione Newsletter |
| Le email finiscono nella posta indesiderata | il dominio del mittente non autorizza il server di posta | imposta SPF e DKIM come dice il tuo provider SMTP |

---

## 17. Per chi sviluppa

- **Nessuna dipendenza:** solo la libreria standard di Python. Le librerie
  del browser (Quill, highlight.js, CodeMirror, Bootstrap per finestre e
  avvisi dell'amministrazione) arrivano da CDN.
- **Due regole ovunque:** un valore che finisce in HTML passa da
  `html.escape()` (`render.esc`), uno che finisce in JavaScript da
  `json.dumps()` (`render.js`). Nessun testo tradotto viene concatenato in
  uno script: l'amministrazione riceve tutto in `window.PB_I18N`, il sito in
  `window.PB_SITE`.
- **I modelli** sono file `.html` in `templates/`, resi con
  `string.Template`.
- **I testi dell'interfaccia** sono in `core/i18n.py`, in italiano e inglese.
- **Un parametro nuovo** si aggiunge in `CONFIG_DEFAULT` (`core/config.py`):
  le configurazioni esistenti lo ricevono con il valore predefinito.
- **I test** si lanciano uno per uno: `python3 tests/test_<nome>.py`;
  stampano "N passed, M failed" e rimettono a posto ciò che toccano.
- **La versione a file unico** si rigenera con `python3 pyblog.py bundle`
  dopo ogni modifica.
