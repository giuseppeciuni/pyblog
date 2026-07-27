# Guida all'uso di PyBlog — passo per passo

*In English: [GUIDE.md](GUIDE.md)*

Questa guida ti accompagna dall'installazione alla pubblicazione online,
spiegando ogni singolo passaggio. Non serve esperienza: segui l'ordine.

---

## Cos'e' PyBlog, in due righe

PyBlog e' un programma in un solo file Python che ti dà un editor visuale
(come Word) per scrivere articoli e configurare la homepage. Quando salvi,
genera pagine HTML statiche, cioe' file già pronti, leggerissimi e velocissimi.
Quei file li mette online un server web (nginx). Il programma Python serve solo
a te per scrivere: il sito pubblico funziona da solo, anche con il programma spento.

Pensa a due mondi separati:
- Il tuo "studio di redazione" privato (il programma Python, sul tuo computer).
- Il "giornale stampato" pubblico (i file HTML, serviti da nginx online).

---

## PARTE 1 — Installazione

### Passo 1.1 — Verifica di avere Python

Apri il terminale e scrivi:

    python3 --version

Se vedi un numero tipo "Python 3.10" o superiore, sei a posto. PyBlog non ha
bisogno di nient'altro: niente database, niente librerie da installare.

### Passo 1.2 — Scompatta il programma

Metti il file zip in una cartella a tua scelta e scompattalo:

    unzip pyblog.zip
    cd pyblog

Dentro trovi il programma (`pyblog.py`), questa guida e alcune cartelle che
si riempiranno mentre lavori.

---

## PARTE 2 — Avviare l'editor e scrivere

### Passo 2.1 — Accendi l'editor

Dalla cartella `pyblog`, scrivi:

    python3 pyblog.py serve

Vedrai un messaggio che dice di aprire `http://localhost:8000`. Lascia questo
terminale aperto: e' il programma in funzione. Per fermarlo, premerai Ctrl+C.

Per sicurezza l'editor ascolta solo sul tuo computer (localhost): nessun
altro dispositivo della rete puo' raggiungerlo. Se la porta 8000 e' occupata
puoi sceglierne un'altra:

    python3 pyblog.py serve 9000

Se ti serve davvero raggiungere l'editor da un altro dispositivo (sconsigliato,
meglio farlo dietro un reverse proxy con HTTPS), puoi indicare anche l'host:

    python3 pyblog.py serve 8000 0.0.0.0

In alternativa, se hai Docker, puoi avviare tutto con `docker compose up -d`
(vedi DEPLOY-REMOTO.md).

### Passo 2.2 — Apri la redazione nel browser

Apri il browser (Chrome, Firefox...) e vai su:

    http://localhost:8000

Questa e' la tua redazione. Vedrai i pulsanti: "Nuovo articolo",
"Impostazioni e homepage", "Rigenera sito", "Vedi blog", e la lista
degli articoli (per ora vuota).

### Passo 2.3 — Configura prima la homepage e il sito

Clicca su "Impostazioni e homepage". Qui imposti tutto senza toccare codice.

1. Nella parte alta c'e' un editor visuale per la HOME: scrivi qui la tua
   presentazione o biografia. Puoi mettere in grassetto, fare titoli, elenchi.
2. Per aggiungere un'immagine: clicca l'icona immagine nella barra dell'editor.
   Per posizionarla a sinistra o a destra del testo, clicca sull'immagine e poi
   usa i pulsanti di allineamento (le righe a sinistra/destra) nella barra: il
   testo le scorrera' intorno.
3. Puoi anche inserire un video YouTube (pulsante "Inserisci video YouTube",
   incolli il link) o caricare un video dal computer ("Carica un video").
4. Clicca "Mostra/nascondi anteprima homepage" per vedere subito come verra'.
5. Più sotto, compila le "Impostazioni generali": titolo del sito, sottotitolo,
   il tuo nome, il dominio (es. https://miosito.it) e la lingua.
6. Nella sezione "Struttura della homepage" decidi l'ordine delle tre sezioni
   della home (Presentazione, Articoli, Card): di default le card con
   biografia e progetti stanno subito dopo la presentazione, ma puoi
   spostarle dove preferisci. Qui imposti anche
   quanti articoli mostrare per pagina (vedi "Paginazione e archivio" più sotto).
7. Nella sezione "SEO e dati dell'autore" inserisci i tuoi dati professionali:
   pagina personale, foto, ruolo, breve biografia e soprattutto i tuoi profili
   pubblici (GitHub, LinkedIn...), uno per riga. Questi dati finiscono nei
   "dati strutturati" delle pagine e aiutano Google a riconoscerti come autore
   reale e a collegare tra loro i tuoi profili. Tutti i campi sono facoltativi.
   Qui puoi anche indicare un logo, l'account X/Twitter del sito e una favicon
   personalizzata (se non ne metti una, PyBlog ne genera una in automatico con
   l'iniziale del titolo del sito).
8. Nella sezione "Commenti" scegli se usare Giscus, Disqus o nessuno
   (vedi la PARTE 5 per come ottenere i dati).
9. Clicca "Salva e rigenera sito". Fatto: la configurazione e' salvata.

### Passo 2.4 — Scrivi il tuo primo articolo

Torna alla redazione (link in alto) e clicca "Nuovo articolo".

1. Scrivi il Titolo.
2. Lo Slug (la parte finale dell'indirizzo web) si genera da solo: lascialo vuoto.
3. Scrivi la Descrizione SEO: una frase breve che riassume l'articolo. Comparira'
   nei risultati di Google, quindi rendila invitante (max 160 caratteri).
4. Scrivi il Contenuto nell'editor visuale. **Se non ricordi a cosa serve un
   pulsante, passaci sopra il mouse**: compare una nuvoletta che lo spiega.
   Nella barra dell'editor hai:
   - scelta del font e della dimensione del testo;
   - grassetto, corsivo, sottolineato;
   - colore del testo e colore di sfondo (le due icone con la "A" e il secchiello);
   - titoli, elenchi puntati e numerati, allineamento;
   - citazioni e blocchi di codice;
   - inserimento di link e immagini.
5. Per inserire un'immagine hai due strade: il pulsante "Carica immagine"
   (carica un file PNG, JPEG o SVG dal tuo computer) oppure l'icona immagine
   nella barra dell'editor. Consiglio: per i diagrammi con testo usa il
   formato SVG, che resta nitido a qualsiasi ingrandimento e non sgrana mai.
   Per le foto vanno bene PNG e JPEG.
6. Dopo aver inserito un'immagine, puoi ridimensionarla: cliccaci sopra e
   trascina le maniglie quadrate che compaiono ai bordi (funzionano in tutte
   le direzioni). Per centrarla o spostarla a sinistra/destra, con l'immagine
   selezionata usa i pulsanti di allineamento nella barra dell'editor.
7. Per inserire codice (Python o altri linguaggi): clicca il pulsante del
   blocco di codice nella barra (l'icona <>), poi incolla o scrivi il codice.
   Nelle pagine pubblicate il codice viene colorato automaticamente in base
   al linguaggio (syntax highlighting), perfetto per articoli tecnici.
8. Per inserire una tabella: usa il pulsante "Inserisci tabella" (ti chiede
   righe e colonne) oppure copia direttamente una tabella da Word e incollala
   nell'editor. La struttura viene mantenuta e adattata alla grafica del blog;
   su mobile le tabelle larghe scorrono in orizzontale.
8b. Se incolli un intero documento Word (testo e immagini insieme), le
   immagini vengono recuperate e caricate automaticamente: il copia-incolla
   di Word mette a disposizione i dati veri delle immagini insieme al testo
   (che da solo non basterebbe), e l'editor li usa per inserire le immagini
   vere nei punti giusti. Un messaggio ti conferma quante immagini sono
   state recuperate.
9. Puoi inserire video YouTube o caricare video dal computer con i pulsanti
   sotto l'editor.
10. Clicca "Mostra/nascondi anteprima" per vedere come apparira' l'articolo
   pubblicato, con la stessa grafica del sito vero. L'anteprima si aggiorna
   mentre scrivi.
8. Aggiungi i Tag separati da virgola (es. "Python, tutorial").
9. Lo stato: "Bozza" se non vuoi ancora pubblicarlo, "Pubblicato" per renderlo
   visibile sul sito.
10. Clicca "Salva e genera HTML".

### Passo 2.5 — Gestire e aggiornare gli articoli dalla dashboard

La pagina principale (http://localhost:8000) e' la tua dashboard di
amministrazione. Da qui vedi:

- In alto, tre contatori: articoli totali, pubblicati e bozze.
- Una barra di ricerca per filtrare gli articoli per titolo (utile quando ne hai
  tanti): scrivi e l'elenco si restringe in tempo reale.
- L'elenco di tutti gli articoli, ognuno con il suo stato (Pubblicato o Bozza),
  la data e la descrizione.

Per ogni articolo hai queste azioni rapide:
- "Modifica": apre l'articolo nell'editor. Fai le tue modifiche e clicca
  "Salva e genera HTML": l'articolo viene aggiornato e la pagina rigenerata.
- "Anteprima": apre la pagina pubblicata in una nuova scheda.
- "Anteprima EN": compare solo se l'articolo ha del contenuto inglese, e apre
  la pagina inglese. Utile per controllare la traduzione prima di confermarla.
- "Elimina": rimuove l'articolo (chiede conferma prima).

### Passo 2.6 — Controlla il risultato

Dalla redazione clicca "Vedi blog", oppure apri `http://localhost:8000/posts/`.
Vedrai la tua homepage con la presentazione in alto e gli articoli sotto.

### Passo 2.7 — La versione inglese di un articolo

Nell'editor, in fondo alla colonna laterale, c'e' la sezione "Versione inglese":

1. Spunta "Autorizza la creazione della versione inglese".
2. Clicca "Traduci automaticamente" (serve una chiave API nelle Impostazioni,
   sezione Traduzione) oppure scrivi la traduzione a mano nei campi EN.
3. Clicca "Anteprima pagina inglese": l'articolo viene salvato e la pagina
   inglese si apre in una nuova scheda, esattamente come la vedranno i lettori.
4. Quando la traduzione ti convince, spunta "Conferma la traduzione e pubblica
   la pagina inglese" e salva. Da quel momento l'articolo compare anche nella
   home inglese (`/en/`), nell'archivio inglese e nella sitemap.

### Passo 2.8 — Paginazione, archivio e favicon (tutto automatico)

Tre cose che PyBlog fa da solo, senza che tu debba fare nulla:

- **Paginazione.** Quando gli articoli superano il numero impostato in
  "Articoli per pagina" (10 se non lo tocchi), la homepage mostra solo i più
  recenti e in fondo compare la navigazione "Più recenti / Meno recenti".
  Le pagine successive vivono in `/pagina/2.html`, `/pagina/3.html`... (in
  inglese `/en/page/2.html`). Se preferisci tutti gli articoli in una sola
  pagina, imposta il valore a 0.
- **Archivio.** La voce "Archivio" nella barra del sito porta a una pagina
  con TUTTI gli articoli raggruppati per anno, in un elenco compatto con data
  e titolo. Esiste in entrambe le lingue (`/archivio.html` e `/en/archive.html`)
  e si aggiorna a ogni salvataggio. La ricerca nella homepage, invece, cerca
  sempre su tutti gli articoli, non solo su quelli della pagina corrente.
- **Favicon.** L'iconcina che appare nella linguetta del browser viene generata
  automaticamente con l'iniziale del titolo del sito. Se ne vuoi una tua,
  indica il suo URL nel campo "Favicon personalizzata" delle Impostazioni.

---

### Passo 2.9 — Gli aiuti AI nella barra laterale e le tabelle

Nella barra laterale dell'editor trovi tre aiuti basati sul servizio
AI configurato nelle Impostazioni (sezione Traduzione):

- **Suggerisci con AI** accanto alla descrizione SEO e all'anteprima
  per i lettori: genera una proposta a partire dal contenuto, che poi
  puoi ritoccare.
- **Analisi SEO e backlink**: analizza l'articolo e ti restituisce
  keyword principali e long-tail, tag consigliati (con un pulsante che
  li applica), varianti di titolo, un giudizio sulla meta description,
  gli anchor text da usare nei backlink dal sito esterno configurato
  (`seo.backlink_site` in CONFIGURAZIONE.md), i link interni verso gli
  altri articoli del blog, blocchi FAQ pensati per i motori AI e
  consigli specifici per l'articolo. Ogni voce ha il pulsante Copia.
  Serve che l'articolo abbia gia' uno slug (salvalo prima, se nuovo).

Sulle **tabelle**: incollando da Word, le tabelle usate solo per
impaginare (testo accanto a un'immagine) vengono sciolte in normale
testo modificabile, mentre le vere tabelle dati restano tabelle. Per
modificarne il contenuto, **clicca sulla tabella**: si apre una
finestra dove cambi le celle e aggiungi o togli righe e colonne.

### Passo 2.10 — Provare le funzioni AI in locale (ambiente di test)

Per provare in locale tutto cio' che usa l'AI (traduzione, suggerimenti,
analisi SEO) serve una chiave API del provider scelto. In locale la
strada semplice e' la pagina Impostazioni, sezione Traduzione:

1. Scegli il servizio. Con Anthropic: servizio `llm`, endpoint
   `https://api.anthropic.com/v1/messages`, modello ad esempio
   `claude-sonnet-4-5`, e la tua chiave (`sk-ant-...`) nel campo
   dedicato. Con OpenAI o DeepSeek basta la chiave nel loro campo.
2. Salva: la chiave finisce in `config.json`, che resta solo sul tuo
   computer (`.gitignore` lo esclude gia' da git).

In alternativa, se preferisci non scriverla nemmeno li', avviala come
variabile d'ambiente: ha la precedenza sul file e non compare mai
nella pagina Impostazioni.

    export PYBLOG_LLM_API_KEY="sk-ant-...la-tua-chiave..."
    python3 pyblog.py serve

Poi il giro di prova completo, su un articolo con un po' di contenuto:

1. **Suggerisci con AI** accanto alla descrizione SEO: deve comparire
   una proposta nel campo.
2. **Suggerisci con AI** sull'anteprima per i lettori: idem.
3. **Analisi SEO e backlink**: salva prima l'articolo (serve lo slug),
   poi lancia l'analisi; in meno di un minuto compare il pannello con
   keyword, anchor text, link interni e FAQ.
4. **Traduzione inglese**: autorizza la traduzione nell'articolo e
   clicca "Traduci automaticamente"; controlla i campi EN compilati.

Se una chiamata fallisce, il messaggio di errore dice il perche':
chiave sbagliata o mancante, credito esaurito, o modello inesistente.
Consiglio: usa una chiave dedicata alle prove con un tetto di spesa
basso impostato nella console del provider.

## PARTE 3 — Dove finiscono le cose (per capire, non e' obbligatorio)

- `posts/` : gli articoli che scrivi, salvati come file di testo (in formato JSON).
  Sono le tue "fonti". Conviene fare un backup di questa cartella ogni tanto.
- `config.json` : le impostazioni del sito e il contenuto della homepage.
- `output/` : i file HTML generati, cioe' il sito vero e proprio.
  Questa e' la cartella che andrà online.
- `output/media/` : i video che carichi.

Ogni volta che salvi un articolo o le impostazioni, la cartella `output/`
viene rigenerata automaticamente.

---

## PARTE 4 — Far girare PyBlog: in locale e in produzione

Prima dei comandi, il concetto che evita il 90% degli errori.

PyBlog è **due cose diverse** dentro un solo file:

1. **L'editor** — il programma Python che avvii con `serve`. Gira *per te*,
   protetto da password. Serve solo a scrivere.
2. **Il sito** — la cartella `output/`, cioè file HTML statici. È questo che
   vedono i lettori, e per funzionare **non ha bisogno di Python**.

> **Regola d'oro: l'editor non va mai esposto su internet.** È l'area di
> amministrazione del tuo blog. In produzione i lettori devono raggiungere
> solo `output/`, servita da nginx. Per questo, di default, `serve` ascolta
> unicamente su `localhost`.

### Come si esegue in locale (sul tuo computer)

    cd pyblog
    python3 pyblog.py serve

Apri `http://localhost:8000`, scrivi, salva. A ogni salvataggio la cartella
`output/` viene rigenerata. Quando hai finito, chiudi con Ctrl+C: il lavoro è
già salvato su disco, non serve tenere il programma acceso.

Comandi utili in locale:

    python3 pyblog.py serve 9000        # se la porta 8000 è occupata
    python3 pyblog.py build             # rigenera output/ senza aprire l'editor
    python3 pyblog.py password          # imposta o cambia la password

Il comando `build` da solo serve quando hai modificato i file a mano (per
esempio dopo un `import-md`) e vuoi rigenerare il sito senza aprire il browser.

### In produzione, scenario A — scrivi in locale, pubblichi sul server (consigliato)

È il modo più semplice e più sicuro: **sul server non gira nessun Python**.
Nessuna area di amministrazione raggiungibile, nessun processo da tenere vivo.

Sul tuo computer:

    python3 pyblog.py serve             # scrivi i tuoi articoli
    # Ctrl+C quando hai finito
    rsync -avz --delete output/ utente@miosito.it:/var/www/blog/

Sul server: solo nginx che serve `/var/www/blog` (vedi PARTE 4B).

L'opzione `--delete` cancella dal server i file che in locale non esistono
più: è ciò che vuoi quando elimini un articolo. Attenzione: la cartella di
destinazione deve contenere *solo* il sito generato, altrimenti `--delete`
rimuoverebbe anche gli altri file presenti.

Suggerimento: metti il comando in uno script `pubblica.sh`, così pubblichi
sempre allo stesso modo senza rischiare di sbagliare percorso.

### In produzione, scenario B — scrivi direttamente sul server (tunnel SSH)

Utile se vuoi scrivere da più computer, o dal tablet, senza sincronizzare
niente. L'editor gira sul server ma **resta invisibile da internet**: ci
arrivi solo attraverso SSH.

Sul server:

    cd /home/blog/pyblog
    python3 pyblog.py serve             # ascolta solo sul localhost del server

Dal tuo computer apri un tunnel SSH e lascialo aperto:

    ssh -L 8000:localhost:8000 utente@miosito.it

Ora apri `http://localhost:8000` nel **tuo** browser: stai parlando con
l'editor del server attraverso il tunnel, cifrato da SSH. Nessuno da fuori
può raggiungere quella porta. Quando salvi, `output/` sul server si rigenera
da sola e nginx serve subito le pagine aggiornate: niente rsync.

Per non riavviare l'editor a mano dopo ogni riavvio del server, puoi farlo
gestire da systemd. Crea `/etc/systemd/system/pyblog.service`:

    [Unit]
    Description=PyBlog editor
    After=network.target

    [Service]
    Type=simple
    User=blog
    WorkingDirectory=/home/blog/pyblog
    ExecStart=/usr/bin/python3 /home/blog/pyblog/pyblog.py serve
    Restart=on-failure

    [Install]
    WantedBy=multi-user.target

Poi attivalo:

    sudo systemctl daemon-reload
    sudo systemctl enable --now pyblog
    sudo systemctl status pyblog

In questo scenario nginx punta alla cartella `output/` dov'è: nel file di
configurazione la riga `root` diventa `root /home/blog/pyblog/output;`
(vedi Passo 4.3 e i permessi al Passo 4.4).

### Quale scegliere

| | Scenario A (locale → rsync) | Scenario B (tunnel SSH) |
|---|---|---|
| Python sul server | no | sì |
| Superficie d'attacco | minima | piccola (solo via SSH) |
| Scrivere da più dispositivi | scomodo | comodo |
| Passaggio di pubblicazione | `rsync` | nessuno |

Se hai un dubbio, usa lo scenario A.

### E con Docker?

`docker compose up -d` è l'equivalente dello scenario B in locale: dentro il
container il server ascolta su `0.0.0.0` (altrimenti sarebbe irraggiungibile
dal container stesso), ma la porta è pubblicata solo su `127.0.0.1:8000` del
tuo computer. Anche qui, in produzione il sito lo serve nginx dalla cartella
`output/`: il container non deve restare esposto.

---

## PARTE 4B — Configurare nginx passo per passo

Questi passi si fanno una volta sola e valgono per entrambi gli scenari.

### Passo 4.1 — Installa nginx (sul server)

    sudo apt update
    sudo apt install nginx

### Passo 4.2 — Porta la cartella output sul server

Se scrivi sul tuo computer e il server e' un'altra macchina (es. un VPS),
copia la cartella `output/` sul server con rsync:

    rsync -a output/ utente@indirizzo-server:/var/www/blog/

Ripeterai questo comando ogni volta che pubblichi qualcosa di nuovo.
Se invece scrivi direttamente sul server, ti basta puntare nginx alla
cartella `output/` dove si trova.

### Passo 4.3 — Configura nginx

Usa il file `nginx.conf.example` incluso come modello. Copialo:

    sudo cp nginx.conf.example /etc/nginx/sites-available/blog

Aprilo e modifica due cose: il nome del dominio e il percorso della cartella
(la riga `root`):

    sudo nano /etc/nginx/sites-available/blog

Poi attiva il sito e ricarica nginx:

    sudo ln -s /etc/nginx/sites-available/blog /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl reload nginx

`nginx -t` controlla che la configurazione sia corretta prima di applicarla.

### Passo 4.4 — Permessi (se le pagine non si vedono)

Se nginx dà errore "403 Forbidden", probabilmente non puo' leggere la cartella.
Dai il permesso di lettura:

    chmod -R o+rX /var/www/blog

### Passo 4.5 — Attiva HTTPS (il lucchetto verde), gratis

Dopo aver puntato il tuo dominio all'indirizzo del server:

    sudo apt install certbot python3-certbot-nginx
    sudo certbot --nginx -d tuodominio.com

Certbot configura il certificato da solo e lo rinnova automaticamente.

---

## PARTE 5 — Attivare i commenti

I commenti su un sito statico si appoggiano a un servizio esterno. Hai due scelte.

### Giscus (consigliato: gratis, niente pubblicita')

Usa le Discussioni di un repository GitHub come archivio dei commenti.

1. Crea un repository pubblico su GitHub.
2. Nel repo: Settings -> Features -> spunta "Discussions".
3. Installa l'app Giscus: https://github.com/apps/giscus
4. Vai su https://giscus.app, inserisci il nome del repo e copia i quattro
   valori che ti mostra (repo, repo id, category, category id).
5. Incollali nella pagina "Impostazioni e homepage", scegli "Giscus", salva.

### Disqus (piu' facile per chi commenta, ma con pubblicita')

1. Registrati su https://disqus.com e scegli di installarlo sul tuo sito.
2. Ti verra' assegnato uno "shortname" (un nome breve).
3. Inseriscilo nella pagina Impostazioni, scegli "Disqus", salva.

---

## PARTE 6 — Vedere chi visita il sito (statistiche)

PyBlog ha il supporto integrato per due sistemi di statistiche, da
attivare dalla pagina Impostazioni (vengono inseriti solo nelle pagine
pubbliche, mai nell'editor):

- **Umami** (consigliato): self-hosted, senza cookie, quindi senza
  banner di consenso. In CONFIGURAZIONE.md trovi il tutorial completo
  per installarlo con Docker; nel repository c'e' anche il file
  `umami-docker-compose.yml` pronto all'uso.
- **Google Analytics 4**: basta incollare l'ID misurazione
  (`G-XXXXXXXXXX`) nel campo dedicato. Ricorda che in Europa GA
  richiede un banner di consenso cookie.

In alternativa (o in aggiunta), nginx registra comunque ogni visita nel
file `/var/log/nginx/blog-access.log`, senza script nelle pagine.

Per vedere le visite dal vivo:

    tail -f /var/log/nginx/blog-access.log

Per un cruscotto con grafici (pagine piu' viste, visitatori, paesi):

    sudo apt install goaccess
    goaccess /var/log/nginx/blog-access.log

---

## PARTE 7 — Importare ed esportare articoli in Markdown

Se arrivi da Hugo, Jekyll o hai articoli scritti in Markdown, puoi importarli
tutti con un comando (l'editor deve essere spento, o riavvialo dopo):

    python3 pyblog.py import-md cartella-con-i-file/

Puoi anche importare un singolo file:

    python3 pyblog.py import-md articolo.md

PyBlog legge il "front matter" (il blocco tra due righe `---` all'inizio del
file, quello usato da Hugo e Jekyll) e riconosce questi campi, in italiano o
in inglese:

    ---
    title: Il mio articolo         (accettato anche: titolo:)
    date: 2025-03-15               (accettato anche: data:)
    description: Frase per Google  (accettato anche: descrizione:)
    tags: [python, tutorial]       (oppure una semplice lista separata da virgole)
    slug: il-mio-articolo          (facoltativo: si genera dal titolo)
    status: published              (accettati anche: stato: pubblicato / draft: false)
    ---

Regole prudenti: se lo status non e' indicato, l'articolo viene importato come
**bozza**, cosi' puoi rivederlo nell'editor prima di pubblicarlo. Se manca il
titolo, viene usato il primo titolo `#` del testo o il nome del file.

Il convertitore Markdown copre titoli, grassetto, corsivo, codice inline e a
blocchi, link, immagini, elenchi puntati e numerati, citazioni e righe
orizzontali. Non copre tabelle Markdown e note a pie' di pagina: per le
tabelle usa l'editor visuale dopo l'import.

Per il percorso inverso (backup o migrazione verso un altro sistema):

    python3 pyblog.py export-md cartella-di-destinazione/

Ogni articolo diventa un file `.md` con il suo front matter. L'export e' una
conversione semplificata: la formattazione avanzata dell'editor (colori,
allineamenti, dimensioni dei caratteri) diventa testo semplice e gli elenchi
numerati diventano puntati.

---

## Riepilogo del lavoro di tutti i giorni

Scenario A (scrivi in locale, pubblichi sul server):

1. Accendi l'editor:        python3 pyblog.py serve
2. Apri:                    http://localhost:8000
3. Scrivi o modifica un articolo, usa l'anteprima, salva.
4. Spegni l'editor (Ctrl+C) e pubblica:
                            rsync -avz --delete output/ utente@miosito.it:/var/www/blog/

Scenario B (editor sul server, tunnel SSH):

1. Apri il tunnel:          ssh -L 8000:localhost:8000 utente@miosito.it
2. Apri:                    http://localhost:8000
3. Scrivi, salva. Fatto: nginx serve già le pagine aggiornate, niente rsync.

Buona scrittura.
