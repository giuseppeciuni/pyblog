# Deploy online su un server (es. www.ciunix.com)

Questa guida spiega come far girare PyBlog su un server remoto, cosi' da poter
scrivere e pubblicare articoli da qualsiasi browser, senza usare rsync dal PC.

## L'architettura

Sul server girano due cose insieme:

1. **nginx**: serve il blog pubblico (le pagine statiche in `output/`) sul dominio,
   e fa da "portinaio" inoltrando le richieste dell'area admin al programma Python.
2. **Il programma Python (pyblog.py serve)**: gira sempre, come servizio, e
   fornisce l'area di amministrazione protetta da password.

```
   Visitatore  --->  nginx  --->  file statici in output/  (blog pubblico)
   Tu (admin)  --->  nginx  --->  Python su 127.0.0.1:8000  (area riservata)
```

L'area admin (/admin, /login, /edit, /config...) viene gestita da Python.
Le pagine pubbliche (/, /posts/, /style.css...) sono file statici.

## Passo 1 — Carica PyBlog sul server

Copia la cartella del progetto sul server, ad esempio in /opt/pyblog:

    scp -r pyblog utente@www.ciunix.com:/opt/

Collegati in SSH:

    ssh utente@www.ciunix.com
    cd /opt/pyblog

## Passo 2 — Imposta la password di amministrazione

    python3 pyblog.py password

Ti chiede una nuova password e la salva (come hash, mai in chiaro) nel file
`admin_password.txt`. Se in futuro la dimentichi, ripeti questo comando via SSH
per reimpostarla.

## Passo 3 — Genera il sito una prima volta

    python3 pyblog.py build

## Passo 4 — Fai girare Python come servizio permanente

Crea un servizio systemd cosi' il programma riparte da solo dopo un riavvio.
Crea il file `/etc/systemd/system/pyblog.service`:

    [Unit]
    Description=PyBlog admin
    After=network.target

    [Service]
    Type=simple
    User=pyblog
    WorkingDirectory=/opt/pyblog
    ExecStart=/usr/bin/python3 /opt/pyblog/pyblog.py serve 8000 127.0.0.1
    Restart=on-failure
    # La chiave API del servizio AI (traduzioni, analisi SEO) viene letta
    # da un file separato, leggibile solo da root: vedi subito sotto.
    EnvironmentFile=/etc/pyblog.env

    [Install]
    WantedBy=multi-user.target

### Dove mettere la chiave API (es. Anthropic)

La chiave non va in `config.json` (finirebbe nei backup e sarebbe
visibile nella pagina Impostazioni a chiunque acceda all'admin). Va in
un file di ambiente che solo root puo' leggere:

    sudo nano /etc/pyblog.env

con dentro una riga cosi' (usa la variabile del tuo provider:
`PYBLOG_LLM_API_KEY` per Anthropic o endpoint personalizzati,
`PYBLOG_OPENAI_API_KEY`, `PYBLOG_DEEPSEEK_API_KEY`,
`PYBLOG_DEEPL_API_KEY`, `PYBLOG_GOOGLE_API_KEY`):

    PYBLOG_LLM_API_KEY=sk-ant-api03-...la-tua-chiave...

Poi blinda i permessi e riavvia il servizio:

    sudo chmod 600 /etc/pyblog.env
    sudo chown root:root /etc/pyblog.env
    sudo systemctl daemon-reload
    sudo systemctl restart pyblog

Nelle Impostazioni del blog lascia vuoto il campo della chiave: la
variabile d'ambiente ha la precedenza e non compare mai nella pagina.
Due buone abitudini: usa una chiave dedicata al blog (non riusarla in
altri progetti) e imposta un tetto di spesa mensile nella console del
provider, cosi' il danno massimo in caso di furto e' il tetto scelto.

Per verificare che la chiave arrivi al servizio: apri un articolo
nell'editor e lancia "Analisi SEO e backlink". Se risponde, tutto e'
collegato.

Nel repository trovi `pyblog.service.example` con la stessa unit piu' le
opzioni di isolamento (ProtectSystem, PrivateTmp...): usa quella come
base. Crea prima l'utente dedicato:

    sudo useradd --system --home /opt/pyblog --shell /usr/sbin/nologin pyblog

Poi attivalo:

    sudo systemctl daemon-reload
    sudo systemctl enable pyblog
    sudo systemctl start pyblog

Ora Python ascolta su 127.0.0.1:8000 (solo locale: nginx lo espone in sicurezza).

## Passo 5 — Configura nginx

Crea `/etc/nginx/sites-available/ciunix`:

    server {
        listen 80;
        server_name www.ciunix.com ciunix.com;

        # Le pagine pubbliche del blog sono file statici.
        root /opt/pyblog/output;
        index index.html;

        access_log /var/log/nginx/blog-access.log;

        # L'area di amministrazione viene gestita dal programma Python.
        # Inoltriamo a Python tutte le rotte riservate.
        location ~ ^/(admin|login|logout|set-password|change-password|edit|config|preview|save|delete|save-config|save-config-raw|rebuild|toggle-status|export|upload|translate|generate-description|generate-preview|analyze-seo|admin-language)$ {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            # PyBlog aggiunge il flag Secure al cookie di sessione
            # quando vede che la richiesta e' arrivata in HTTPS.
            proxy_set_header X-Forwarded-Proto $scheme;
            # L'analisi SEO e le traduzioni possono durare fino a un minuto.
            proxy_read_timeout 120s;
            client_max_body_size 50m;
        }

        # Tutto il resto: prima prova i file statici, poi passa a Python.
        location / {
            try_files $uri $uri/ @python;
        }
        location @python {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Pagina 404 personalizzata.
        error_page 404 /404.html;

        location /media/ {
            add_header Cache-Control "public, max-age=2592000";
        }
    }

Attiva e ricarica:

    sudo ln -s /etc/nginx/sites-available/ciunix /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl reload nginx

## Passo 6 — HTTPS obbligatorio (l'area admin invia password)

Dato che fai il login da remoto, l'HTTPS non e' opzionale: protegge la password
in transito. Attivalo con Let's Encrypt:

    sudo apt install certbot python3-certbot-nginx
    sudo certbot --nginx -d www.ciunix.com -d ciunix.com

Certbot aggiorna nginx per l'HTTPS e rinnova il certificato da solo.

## Come si usa, una volta online

- Blog pubblico:    https://www.ciunix.com/
- Area riservata:   https://www.ciunix.com/admin
  (la prima volta ti chiede di creare la password, se non l'hai gia' fatta via SSH)

Scrivi un articolo dall'area admin, lo salvi: il programma genera subito l'HTML
nella cartella output/, e nginx lo serve immediatamente al pubblico. Nessun
rsync, nessun passaggio dal PC.

## Come funziona la generazione automatica delle pagine

Questo e' il punto piu' importante da capire: **non devi mai rigenerare il sito
a mano.** Il programma Python lo fa da solo.

Ogni volta che, dall'area admin, esegui una di queste azioni:

- salvi un articolo (nuovo o modificato),
- elimini un articolo,
- pubblichi o metti in bozza un articolo,
- cambi le impostazioni o la homepage,

il programma **rigenera automaticamente tutte le pagine HTML statiche** nella
cartella `output/`. nginx, che serve proprio quella cartella, mostra subito le
pagine aggiornate ai visitatori.

In pratica il flusso e':

    Scrivi nell'editor  ->  Salva  ->  Python rigenera output/  ->  nginx serve le nuove pagine

Nessun comando manuale, nessun rsync, nessun deploy dal PC. Scrivi dal browser
e il sito pubblico e' aggiornato in tempo reale.

Il comando `python3 pyblog.py build` serve solo per la **prima** generazione (o
se vuoi forzare una rigenerazione da SSH). Durante l'uso normale non ti serve.

## Quando aggiorni il codice di pyblog.py

Se in futuro aggiorni `pyblog.py` con una nuova versione, sul server basta:

    sudo systemctl restart pyblog      # riavvia il programma con il nuovo codice
    python3 pyblog.py build            # rigenera le pagine con le nuove funzioni

I tuoi articoli (in `posts/`) e la configurazione (`config.json`) non vengono
toccati: restano dove sono.

## Cambiare la password

- Da loggato nell'area admin: pulsante "Cambia password".
- Se la dimentichi: collegati in SSH ed esegui `python3 pyblog.py password`.

## Sicurezza: cosa e' protetto

- La password e' salvata solo come hash con sale (mai in chiaro).
- Le pagine admin e tutte le azioni di scrittura richiedono il login.
- Il cookie di sessione e' HttpOnly (non leggibile da script).
- Con HTTPS attivo, la password viaggia cifrata.
- Consiglio: tieni `admin_password.txt` e `config.json` fuori da git
  (sono gia' nel .gitignore).

## Avvio con Docker (alternativa)

Se sul server (o sul tuo computer) hai Docker, puoi avviare PyBlog senza
installare Python:

```bash
docker compose up -d
```

L'editor sara' su `http://localhost:8000/admin`. La cartella del progetto
viene montata dentro il container, quindi articoli, configurazione e sito
generato restano sul tuo disco.

Due note importanti:

1. La porta 8000 e' esposta solo su localhost (vedi `docker-compose.yml`).
   In produzione non serve tenere il container attivo: PyBlog genera un
   sito statico, quindi basta far servire la cartella `output/` a nginx
   come descritto sopra.
2. Per aggiornare PyBlog basta sostituire `pyblog.py` e riavviare:
   `docker compose restart`.
