# PyBlog — Tutorial: dal server vuoto al sito online

Questo tutorial ti porta, un comando alla volta, da un server Ubuntu appena
creato a un blog online con HTTPS, che scrivi dal browser. Segui i passi in
ordine: dopo ognuno c'è un **Controllo** che ti dice se è andato tutto bene.

Tutto ciò che non serve per partire (le altre installazioni, ogni
impostazione, ogni chiave di `config.json`) è nel **[MANUALE.md](MANUALE.md)**.

---

## Prima di cominciare

**Cosa ottieni alla fine**

```
  Lettori  ──https──▶  nginx  ──▶  pagine statiche in /opt/pyblog/output
  Tu       ──https──▶  nginx  ──▶  PyBlog (Python) su 127.0.0.1:8000  →  /admin
```

- I lettori ricevono pagine HTML già pronte, servite da nginx: veloci, e
  nessun programma da attaccare.
- Tu entri in `https://tuodominio.it/admin` con la tua password, scrivi e
  salvi: PyBlog rigenera le pagine e nginx le mostra subito.

**Cosa ti serve**

- Un server con **Ubuntu 22.04 o 24.04** (va bene il VPS più piccolo: 1 CPU,
  1 GB di RAM) e un utente con `sudo`.
- Un **dominio** (in questo tutorial `tuodominio.it`) di cui puoi modificare
  i record DNS.
- Circa mezz'ora.

> In tutti i comandi sostituisci **`tuodominio.it`** con il tuo dominio. Le
> righe che iniziano con `$` sono comandi da scrivere (senza il `$`).

---

## Parte 1 — Prepara il server

### 1.1 Collegati e aggiorna

Dal tuo computer:

```bash
$ ssh utente@INDIRIZZO-IP-DEL-SERVER
```

Poi, sul server:

```bash
$ sudo apt update && sudo apt upgrade -y
```

### 1.2 Punta il dominio al server

Nel pannello del tuo registrar (dove hai comprato il dominio) crea due
record DNS:

| Tipo | Nome | Valore |
|---|---|---|
| A | `@` (cioè `tuodominio.it`) | l'indirizzo IP del server |
| A | `www` | l'indirizzo IP del server |

Se il server ha anche un indirizzo IPv6, aggiungi due record `AAAA` uguali.

**Controllo** (può servire qualche minuto, a volte qualche ora):

```bash
$ getent hosts tuodominio.it www.tuodominio.it
```

Devono comparire l'IP del tuo server, due volte.

### 1.3 Accendi il firewall

```bash
$ sudo apt install -y ufw
$ sudo ufw allow OpenSSH
$ sudo ufw allow 80/tcp
$ sudo ufw allow 443/tcp
$ sudo ufw enable
```

**Controllo:** `sudo ufw status` mostra `22`, `80` e `443` come `ALLOW`. La
porta 8000 di PyBlog **non** va aperta: ci parla solo nginx, dall'interno.

### 1.4 Installa i programmi

```bash
$ sudo apt install -y python3 git nginx certbot python3-certbot-nginx
```

PyBlog non ha bisogno d'altro: niente database, niente `pip install`.

**Controllo:** `python3 --version` deve dire 3.8 o più (Ubuntu 22.04 ha la
3.10, la 24.04 la 3.12).

---

## Parte 2 — Installa PyBlog

### 2.1 Crea l'utente del blog

PyBlog gira con un utente tutto suo, che non può fare altro sul server:

```bash
$ sudo useradd --system --home /opt/pyblog --shell /usr/sbin/nologin pyblog
```

### 2.2 Scarica PyBlog

```bash
$ sudo git clone https://github.com/giuseppeciuni/pyblog.git /opt/pyblog
$ sudo chown -R pyblog:pyblog /opt/pyblog
```

Se hai PyBlog in una cartella sul tuo computer invece che su GitHub,
copiala sul server e poi dai la proprietà all'utente `pyblog`:

```bash
# sul tuo computer
$ rsync -a --exclude output/ pyblog/ utente@INDIRIZZO-IP:/tmp/pyblog/
# sul server
$ sudo mv /tmp/pyblog /opt/pyblog && sudo chown -R pyblog:pyblog /opt/pyblog
```

**Controllo:** `ls /opt/pyblog` mostra `pyblog.py`, `core`, `templates`,
`static`.

### 2.3 Scegli la password dell'amministrazione

```bash
$ cd /opt/pyblog
$ sudo -u pyblog python3 pyblog.py password
$ sudo chmod 600 /opt/pyblog/admin_password.txt
```

Il programma la chiede due volte e la salva cifrata (solo l'"impronta",
mai la password). Sceglila lunga: una frase va benissimo.

> Fallo adesso, dal terminale. Se apri il sito prima di avere una password,
> la pagina `/admin` propone di crearla a chi arriva per primo.

### 2.4 Genera il sito la prima volta

```bash
$ sudo -u pyblog python3 pyblog.py build
```

**Controllo:** `ls /opt/pyblog/output` mostra `index.html`, `posts`,
`sitemap.xml`, `404.html` e gli altri file del sito.

---

## Parte 3 — Fai partire l'editor come servizio

L'editor (l'area `/admin`) è un programma Python che deve restare acceso e
ripartire da solo dopo un riavvio del server: lo affidiamo a `systemd`.

### 3.1 Prepara il file delle chiavi segrete

Le chiavi dei servizi di AI e di traduzione, se un giorno le userai, vanno
in un file leggibile solo da root, non nel progetto. Crealo vuoto:

```bash
$ sudo install -m 600 -o root -g root /dev/null /etc/pyblog.env
```

### 3.2 Installa e accendi il servizio

```bash
$ sudo cp /opt/pyblog/pyblog.service.example /etc/systemd/system/pyblog.service
$ sudo systemctl daemon-reload
$ sudo systemctl enable --now pyblog
```

Il file di esempio è già pronto per `/opt/pyblog` e l'utente `pyblog`; fa
ascoltare PyBlog **solo** su `127.0.0.1:8000` e gli permette di scrivere
soltanto nella sua cartella.

**Controllo:**

```bash
$ systemctl status pyblog --no-pager
$ curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/login
```

Il primo deve dire `active (running)`, il secondo `200`. Se no, guarda il
perché con `sudo journalctl -u pyblog -n 50 --no-pager`.

---

## Parte 4 — Pubblica il sito con nginx

### 4.1 Installa la configurazione di PyBlog

Il progetto contiene una configurazione di nginx già pronta: va solo
adattata al tuo dominio e alla cartella del sito.

```bash
$ sudo cp /opt/pyblog/nginx.conf.example /etc/nginx/sites-available/pyblog
$ sudo sed -i 's/mysite\.com/tuodominio.it/g; s#/path/to/pyblog/output#/opt/pyblog/output#' \
      /etc/nginx/sites-available/pyblog
$ sudo ln -s /etc/nginx/sites-available/pyblog /etc/nginx/sites-enabled/pyblog
$ sudo rm -f /etc/nginx/sites-enabled/default
$ sudo nginx -t && sudo systemctl reload nginx
```

Cosa fa questa configurazione: serve le pagine di `output/` direttamente,
manda a PyBlog solo le rotte dell'amministrazione (`/admin`, `/login`,
`/config`...), limita i tentativi di accesso a uno al secondo e mostra la
pagina 404 del sito per gli indirizzi che non esistono.

**Controllo:** `nginx -t` dice `syntax is ok` e `test is successful`. Apri
`http://tuodominio.it` nel browser: vedi il sito di esempio.

---

## Parte 5 — Attiva HTTPS

Dall'amministrazione viaggia la tua password: l'HTTPS è obbligatorio.

```bash
$ sudo certbot --nginx -d tuodominio.it -d www.tuodominio.it
```

Certbot ti chiede un'email (per gli avvisi di scadenza), ottiene il
certificato gratuito di Let's Encrypt, aggiunge l'HTTPS alla configurazione
di nginx e il passaggio automatico da `http` a `https`. Il rinnovo è
automatico.

**Controllo:**

```bash
$ sudo certbot renew --dry-run
```

deve finire con `Congratulations, all simulated renewals succeeded`. Poi apri
`https://tuodominio.it`: il lucchetto c'è.

---

## Parte 6 — Primo accesso e prime impostazioni

### 6.1 Entra

Apri **`https://tuodominio.it/admin`** e inserisci la password del passo
2.3. A sinistra c'è il menu: Articoli, Nuovo articolo, Impostazioni, e in
basso gli strumenti e il tuo account. Sul telefono il menu è una barra in
fondo allo schermo.

### 6.2 Il sito e il dominio (importante)

Vai in **Impostazioni → Sito e autore** e compila:

- **Titolo del sito** e **Sottotitolo**;
- **Dominio del sito**: `https://tuodominio.it`, senza barra finale. Da qui
  nascono la sitemap, gli indirizzi canonici e le anteprime sui social: se
  resta l'esempio, Google non indicizza niente;
- **Lingua principale del sito**: la lingua in cui scrivi;
- in **Chi scrive**: il tuo nome e, se vuoi, ruolo, una breve biografia e i
  tuoi profili (GitHub, LinkedIn...), uno per riga.

Clicca **Salva e aggiorna il sito** in fondo alla pagina.

### 6.3 La prima pagina

- **Home page**: scrivi la presentazione con l'editor visuale e scegli se
  va nella barra laterale o sopra gli articoli.
- **Biografia** e **Progetti** (facoltativi): accendili con la loro spunta,
  scrivi la biografia, aggiungi una scheda per progetto e scegli per
  ciascuno dove compare in home.

Ogni sezione si salva con lo stesso pulsante in fondo; se esci con
modifiche non salvate, il browser te lo chiede.

### 6.4 Il primo articolo

1. **Nuovo articolo** nel menu.
2. Scrivi il titolo e il testo. Per un documento Word già pronto usa
   **Importa da Word (.docx)**.
3. Nella colonna di destra: **Salva bozza** per tenerlo per te,
   **Anteprima** per vederlo com'è, **Pubblica** per metterlo online.

**Controllo:** apri `https://tuodominio.it`: l'articolo c'è, in cima
all'elenco.

### 6.5 (Facoltativo) Le funzioni di AI

Traduzione automatica, suggerimenti per descrizione e anteprima, analisi
SEO: servono la chiave di un servizio (Anthropic, OpenAI, DeepSeek, DeepL o
Google). Mettila nel file del passo 3.1, non nelle Impostazioni:

```bash
$ sudo nano /etc/pyblog.env
```

con una riga come questa (il nome dipende dal servizio: `PYBLOG_LLM_API_KEY`
per Anthropic, `PYBLOG_OPENAI_API_KEY`, `PYBLOG_DEEPSEEK_API_KEY`,
`PYBLOG_DEEPL_API_KEY`, `PYBLOG_GOOGLE_API_KEY`):

```
PYBLOG_LLM_API_KEY=sk-ant-...
```

poi `sudo systemctl restart pyblog`. In **Impostazioni → Traduzione** scegli
il servizio e lascia vuoto il campo della chiave. Consiglio: una chiave
usata solo per il blog, con un tetto di spesa mensile impostato nella
console del servizio.

---

## Parte 7 — Tenerlo in salute

### 7.1 Il backup

Dal menu, **Scarica il backup** ti dà un file `.zip` con articoli, immagini
e impostazioni. Per un backup automatico ogni notte sul server:

```bash
$ sudo crontab -e
```

e aggiungi queste due righe:

```
0 3 * * * tar -czf /var/backups/pyblog-$(date +\%F).tar.gz -C /opt/pyblog posts config.json admin_password.txt output/media
30 3 * * * find /var/backups -name 'pyblog-*.tar.gz' -mtime +30 -delete
```

Ogni notte alle 3 un archivio datato; quelli più vecchi di 30 giorni se ne
vanno. Copia ogni tanto un archivio anche fuori dal server.

**Ripristinare** un archivio:

```bash
$ sudo systemctl stop pyblog
$ sudo tar -xzf /var/backups/pyblog-AAAA-MM-GG.tar.gz -C /opt/pyblog
$ sudo chown -R pyblog:pyblog /opt/pyblog
$ cd /opt/pyblog && sudo -u pyblog python3 pyblog.py build
$ sudo systemctl start pyblog
```

### 7.2 Aggiornare PyBlog

```bash
$ cd /opt/pyblog
$ sudo -u pyblog git pull
$ sudo systemctl restart pyblog
$ sudo -u pyblog python3 pyblog.py build
```

Articoli, impostazioni e password non vengono toccati. Se una nuova
versione cambia `nginx.conf.example`, confrontalo con il tuo file in
`/etc/nginx/sites-available/pyblog` (il CHANGELOG lo dice).

### 7.3 Se qualcosa non va

| Cosa vedi | Cosa vuol dire | Cosa fare |
|---|---|---|
| **502 Bad Gateway** su `/admin` | PyBlog è spento | `sudo systemctl restart pyblog`, poi `sudo journalctl -u pyblog -n 50 --no-pager` |
| **403 Forbidden** sul sito | nginx non può leggere `output/` | `sudo chmod 755 /opt/pyblog /opt/pyblog/output` |
| L'amministrazione senza colori né pulsanti | nginx non manda `/admin-static/` a PyBlog | rifai il passo 4.1 con la configurazione nuova |
| Una pagina dell'amministrazione dà 404 | una rotta nuova non è nella configurazione di nginx | confronta `/etc/nginx/sites-available/pyblog` con `nginx.conf.example` |
| Certbot fallisce | il dominio non punta ancora al server | rifai il controllo del passo 1.2 e riprova |
| "Troppi tentativi" al login | protezione contro chi indovina password | aspetta: il blocco riguarda solo il tuo indirizzo e si allunga a ogni errore |
| Password dimenticata | — | `cd /opt/pyblog && sudo -u pyblog python3 pyblog.py password` |
| Le modifiche non compaiono | il browser mostra la copia vecchia | ricarica forzata (Ctrl+F5); dal menu **Rigenera il sito** ricrea tutte le pagine |

---

## E adesso?

Nel **[MANUALE.md](MANUALE.md)** trovi tutto il resto: ogni sezione delle
Impostazioni, i codici esterni (Analytics, AdSense, widget) con il punto
scelto cliccando sulla pagina, il banner dei cookie, i commenti, le
statistiche con Umami, la traduzione, l'import da Word e da Markdown, le
altre installazioni (sul tuo computer, con Docker, senza Python sul server),
ogni chiave di `config.json` e la soluzione dei problemi.
