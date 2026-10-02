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

Questa e' la tua redazione. A sinistra c'e' il menu: "Articoli" (con
quanti ne hai), "Nuovo articolo" e "Impostazioni"; piu' in basso gli
strumenti ("Rigenera il sito", "Scarica il backup") e le voci del tuo
account ("Vedi il blog", "Cambia password", la lingua, "Esci"). Sul
telefono il menu diventa una barra in fondo allo schermo, e "Altro" apre
il resto.

La pagina "Articoli" elenca i tuoi articoli: in alto scegli se vederli
tutti, solo i pubblicati o solo le bozze, e puoi cercarli per titolo.
Ogni riga ha "Modifica"; il pulsante "⋯" accanto apre le azioni piu'
rare: anteprima, pubblica o ritira, elimina.

### Passo 2.3 — Configura prima la homepage e il sito

Clicca su "Impostazioni". Qui imposti tutto senza toccare codice.

Le impostazioni sono divise in sezioni, una per cosa da fare, e nel menu
a sinistra compaiono una sotto l'altra: "Sito e autore", "Home page",
"Pagine", "Commenti", "Traduzione", "Statistiche e annunci", "Cookie e
privacy", "Addestramento AI", "Avanzate". Sul telefono la pagina apre
l'elenco delle sezioni; dentro una sezione, la freccia in alto torna
all'elenco.

La barra in fondo dice se ci sono modifiche non salvate: "Salva e
rigenera sito" le salva tutte, di qualunque sezione, e "Annulla le
modifiche" riporta tutto all'ultimo salvataggio. Se lasci la pagina con
modifiche non salvate, il browser te lo chiede prima.

La homepage e' a due colonne: a sinistra gli articoli, ognuno con la sua
miniatura e qualche riga di anteprima; a destra una barra laterale con la tua
presentazione, la ricerca, il riquadro "Esplora" con le tue pagine, gli
argomenti e i tuoi profili. Sul telefono la barra scende sotto gli articoli e
il menu si apre da un pulsante.

1. In "Sito e autore" scrivi il titolo del sito, il sottotitolo, il dominio
   (es. https://miosito.it) e la lingua in cui scrivi. Sotto, in "Chi
   scrive", metti il tuo nome e, se vuoi, ruolo, una breve biografia, una
   foto, la tua pagina personale e soprattutto i tuoi profili pubblici
   (GitHub, LinkedIn...), uno per riga. Questi dati finiscono nei "dati
   strutturati" delle pagine e aiutano Google a riconoscerti come autore
   reale e a collegare tra loro i tuoi profili. Tutti i campi sono
   facoltativi. In "Logo e icona" puoi indicare un logo e una favicon
   personalizzata (se non ne metti una, PyBlog ne genera una in automatico
   con l'iniziale del titolo del sito).
2. In "Home page" c'e' un editor visuale per la presentazione: scrivi qui
   chi sei. Puoi mettere in grassetto, fare titoli, elenchi.
   Per aggiungere un'immagine clicca l'icona immagine nella barra
   dell'editor; per posizionarla a sinistra o a destra del testo, clicca
   sull'immagine e poi usa i pulsanti di allineamento: il testo le scorrera'
   intorno. Puoi anche inserire un video YouTube ("Inserisci video YouTube")
   o caricare un video dal computer ("Carica un video"), e con "Mostra/
   nascondi anteprima homepage" vedi subito come verra'.
3. Sempre in "Home page", in "Disposizione", scegli dove va la
   presentazione: nella barra laterale (cosi' gli articoli partono
   dall'alto) oppure sopra gli articoli. Qui imposti anche se mettere in
   evidenza l'ultimo articolo, quante parole mostrare per gli articoli
   senza anteprima e quanti articoli mostrare per pagina (vedi
   "Paginazione e archivio" piu' sotto).
4. In "Pagine" decidi quali pagine elencare nel riquadro "Esplora" della
   barra laterale. Ogni pagina (Biografia, Progetti, Informazioni in
   evidenza, Comunicazioni di servizio) ha la sua spunta "Mostra questa
   card": con la spunta compare in "Esplora" e ha una sua pagina, senza
   spunta sparisce. La spunta in cima, "Mostra la sezione delle card", vale
   per tutto il blocco: se la togli spariscono tutte insieme, e quando la
   rimetti ogni card torna come l'avevi lasciata.
5. In "Commenti" scegli se usare Giscus, Disqus o nessuno
   (vedi la PARTE 5 per come ottenere i dati).
6. Clicca "Salva e rigenera sito". Fatto: la configurazione e' salvata.

### Passo 2.4 — Scrivi il tuo primo articolo

Clicca "Nuovo articolo" nel menu a sinistra.

1. Scrivi il Titolo.
2. Lo Slug (la parte finale dell'indirizzo web) si genera da solo: lascialo vuoto.
   Se un altro articolo usa gia' quell'indirizzo, il nuovo ne prende uno
   libero (con "-2" in fondo, per esempio) e un messaggio te lo dice: un
   articolo non ne sovrascrive mai un altro.
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
8c. Se l'articolo esiste gia' come documento Word, il pulsante "Importa da
   Word (.docx)" sopra l'editor lo carica tutto: titoli, elenchi anche
   annidati, tabelle con le celle unite, immagini con il loro testo
   alternativo, note a pie' di pagina, link, apici e pedici, caselle di
   testo. Il titolo del documento (stile Titolo o Titolo 1 all'inizio)
   diventa il titolo dell'articolo, e il sottotitolo la descrizione se e'
   vuota. Il sommario di Word e il testo nascosto restano fuori, e un
   avviso ti dice cosa e' stato saltato (per esempio un'equazione, da
   riscrivere). L'articolo importato non e' ancora salvato: rivedilo, poi
   si modifica e si salva come tutti gli altri.
9. Puoi inserire video YouTube o caricare video dal computer con i pulsanti
   sotto l'editor.
10. Aggiungi i Tag separati da virgola (es. "Python, tutorial").
11. In cima alla colonna di destra vedi lo stato dell'articolo. Finche' e'
   una **bozza** ("i lettori non la vedono") hai tre pulsanti:
   - **Salva bozza** (o Ctrl+S): salva senza pubblicare. Le bozze si
     salvano anche da sole, ogni minuto;
   - **Anteprima**: apre in una nuova scheda la pagina com'e' adesso, con la
     grafica del sito vero, senza salvare niente;
   - **Pubblica**: dopo una conferma mette l'articolo sul sito, in homepage,
     nell'archivio e nel feed RSS.
12. Quando l'articolo e' **pubblicato**, in cima trovi "Vedi online" e i
   pulsanti cambiano: **Aggiorna l'articolo** (o Ctrl+S) salva e mette
   subito online le modifiche; **Anteprima** fa vedere le modifiche prima di
   farlo; **Ritira dalla pubblicazione** toglie la pagina dal sito e
   l'articolo torna bozza. Sotto i pulsanti una riga ti dice se ci sono
   "Modifiche non salvate". Per tornare all'elenco usa "Tutti gli articoli"
   in alto: se c'e' qualcosa da salvare, il browser te lo ricorda.

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
  "Aggiorna l'articolo" (o "Salva bozza", se non e' ancora pubblicato).
- "Pubblica" / "Ritira dalla pubblicazione": cambia lo stato dell'articolo
  senza aprirlo, con le stesse parole dei pulsanti dell'editor.
- "Anteprima": apre la pagina pubblicata in una nuova scheda.
- "Anteprima EN": compare solo se l'articolo ha del contenuto inglese, e apre
  la pagina inglese. Utile per controllare la traduzione prima di confermarla.
- "Elimina": rimuove l'articolo (chiede conferma prima).

### Passo 2.6 — Controlla il risultato

Dalla redazione clicca "Vedi il blog", oppure apri `http://localhost:8000/posts/`.
Vedrai la tua homepage con la presentazione in alto e gli articoli sotto.

### Passo 2.7 — La versione inglese di un articolo

Nell'editor, in fondo alla colonna laterale, c'e' la sezione "Versione inglese":

1. Spunta "Autorizza la creazione della versione inglese".
2. Clicca "Traduci automaticamente" (serve una chiave API nelle Impostazioni,
   sezione Traduzione) oppure scrivi la traduzione a mano nei campi EN.
3. Clicca "Anteprima della pagina in inglese": la pagina inglese si apre in
   una nuova scheda, esattamente come la vedranno i lettori, senza salvare
   niente.
4. Quando la traduzione ti convince, spunta "Conferma la traduzione e pubblica
   la pagina inglese" e salva. Da quel momento l'articolo compare anche nella
   home inglese (`/en/`), nell'archivio inglese e nella sitemap.

Le immagini, i video e i riquadri incorporati non vengono mandati al servizio
di traduzione: restano da parte e tornano al loro posto a traduzione finita.
Non c'e' niente da fare, e' automatico. Se il servizio perde per strada il
segnaposto di un'immagine, PyBlog la rimette comunque nell'articolo e te lo
dice ("controlla che siano al posto giusto"): in quel caso guarda dov'e'
finita prima di confermare. Il testo alternativo delle immagini resta in
italiano, perche' vive dentro il tag che non parte.

**Se il tuo sito e' in inglese** (Impostazioni, "Sito e autore", "Lingua principale
del sito": English) tutto si rovescia: scrivi gli articoli in inglese, la
sezione diventa "Versione in italiano", la traduzione va dall'inglese
all'italiano e le pagine tradotte stanno in `/it/`. Commenti, date, banner
dei cookie e anteprime seguono la lingua di ciascuna pagina.

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

### Passo 2.11 — Mettere il codice di un servizio esterno nelle pagine

Prima o poi un servizio ti dara' una riga da incollare nel sito: Google
Analytics, AdSense, un widget di assistenza, una chat, un pixel di
tracciamento. Qualcosa di questo genere:

```html
<script src="https://esempio.com/widget/loader.js" data-widget-id="a7ddc6ff" defer></script>
```

Non serve toccare i file del programma. Vai in **Impostazioni**, sezione
**Statistiche e annunci**, e in **Codici esterni e annunci** clicca
**Aggiungi codice**: ti viene
chiesto che cosa vuoi aggiungere.

**I servizi piu' comuni sono pronti.** Scegli dall'elenco Google Analytics 4,
Google Tag Manager, AdSense (annunci automatici oppure un'unita'
pubblicitaria), Google Ads, Meta Pixel o Microsoft Clarity, scrivi l'ID che
ti ha dato il servizio (per esempio `G-ABC123DEF4` per Analytics) e clicca
**Crea**. Il codice viene preparato con la posizione, le pagine e il
consenso adatti; se l'ID ha una forma sbagliata te lo dice prima. Con
AdSense viene aggiunta da sola anche la riga del file `ads.txt` (vedi
sotto). Puoi sempre cambiare tutto dopo.

**Per tutto il resto c'e' "Codice libero"**: una scheda vuota da compilare.

1. **Nome**: come lo chiami tu, per ritrovarlo. Es. "Widget assistenza".
2. **Dove va nella pagina**: le voci sono divise in due gruppi. Quelle
   *nel codice della pagina* (`head`, inizio, fondo) non si vedono e vanno
   bene per script e pixel: per l'esempio qui sopra scegli **il fondo della
   pagina**. Quelle *visibili* servono quando il codice deve comparire in un
   punto preciso: nel menu dell'intestazione, sotto l'intestazione, nella
   barra laterale (il posto di un annuncio 300x250), tra gli articoli della
   home, all'inizio, a meta' o in fondo al testo dell'articolo, prima del
   pie' di pagina. **Nel menu dell'intestazione** e' per una voce in piu'
   accanto a Home, Articoli e Archivio: per esempio un link "Chiedi
   all'assistente" che apre la chat di un widget.
3. **Su quali pagine**: tutto il sito, solo la homepage, solo gli articoli,
   homepage e articoli, oppure **solo gli articoli scelti**: con
   quest'ultima il codice resta spento finche' non lo accendi su un
   articolo, uno per uno.
4. **Consenso del visitatore**: "Necessario" se il codice non usa cookie
   (un widget, un embed), "Statistiche" per Analytics, Clarity e simili,
   "Pubblicita'" per AdSense, Google Ads e i pixel. Conta solo con il
   banner dei cookie acceso (passo 2.12).
5. **Codice**: incolli quello che ti ha dato il servizio, senza
   modificarlo. Il riquadro colora il codice e numera le righe, come un
   editor di programmazione.

Salvi, e il sito viene rigenerato. Quando riapri la pagina ogni codice e'
chiuso su una riga sola, che dice dove va, su quali pagine e con quale
consenso: clicca la riga per aprirlo.

**Il codice sul singolo articolo.** Apri l'articolo nell'editor: nella
colonna di destra, sotto **Codici esterni**, trovi i codici del sito che
possono uscire su quell'articolo, con una casella ciascuno. Quelli "da
spuntare" (ambito "articoli scelti") escono solo se li spunti; quelli "di
serie" escono su tutti gli articoli, e togliendo la spunta li spegni solo
su questo: utile, per esempio, per un articolo che non deve avere
pubblicita'. Sotto, **Solo per questo articolo** accoglie codice che esce
soltanto li': un annuncio dedicato, un embed, un widget. Salvi l'articolo
e basta.

**ads.txt.** E' un file che dice chi puo' vendere pubblicita' sul tuo
sito: AdSense lo cerca all'indirizzo `/ads.txt` e limita gli annunci
finche' non lo trova. Lo scrivi nel campo **ads.txt** sotto i codici (il
modello di AdSense ci mette gia' la sua riga); vuoto, il file non viene
pubblicato.

**Per provarlo davvero**, usa l'anteprima dell'articolo, non la pagina
delle Impostazioni: l'area di amministrazione blocca i domini esterni
per sicurezza, quindi li' il widget non partirebbe e sembrerebbe rotto.
Nell'anteprima, e nel sito pubblicato, funziona normalmente.

**Due avvertenze.** Il codice viene inserito nella pagina cosi' com'e',
senza controlli: incolla solo codice di cui ti fidi, perche' puo' fare
qualunque cosa sul tuo sito. E se cancelli un codice dalle Impostazioni,
gli articoli che lo avevano spuntato non si rompono: semplicemente non
lo ricevono piu'.

### Passo 2.12 — Il banner dei cookie

In Europa statistiche e pubblicita' che usano cookie possono partire solo
dopo il consenso del visitatore. PyBlog ha un banner suo: in
**Impostazioni**, sezione **Cookie e privacy**, spunta "Mostra il banner
del consenso ai visitatori", metti l'indirizzo della tua informativa
privacy e salva.

Da quel momento:

- i codici segnati "Statistiche" o "Pubblicita'", e Google Analytics,
  arrivano nella pagina fermi: non partono, non scrivono cookie e non
  chiamano nessuno finche' il visitatore non accetta;
- il visitatore puo' accettare tutto, rifiutare tutto o scegliere, e i due
  pulsanti hanno lo stesso peso; la scelta resta nel suo browser e non
  gli viene chiesta di nuovo a ogni pagina;
- i tag di Google ricevono la scelta tramite Consent Mode;
- in fondo a ogni pagina compare "Preferenze cookie", per cambiare idea.

Il banner compare solo se c'e' qualche codice che ne ha bisogno. Il testo
lo puoi cambiare (vuoto = quello predefinito), anche per la versione
nell'altra lingua. Quando aggiungi un servizio nuovo, clicca **Chiedi di
nuovo il consenso a tutti** e salva: ogni visitatore rivedra' il banner.

**AdSense in Europa** chiede anche un "CMP certificato". Hai due strade:
accendere il messaggio gratuito di Google dal pannello di AdSense ("Privacy
e messaggi") e lasciare il codice di AdSense su "Necessario"; oppure usare
questo banner con AdSense su "Pubblicita'": gli annunci partono dopo il
consenso.

Il banner e' uno strumento, non una consulenza legale: l'informativa
privacy e le scelte su quali servizi usare restano tue.

## PARTE 3 — Dove finiscono le cose (per capire, non e' obbligatorio)

- `posts/` : gli articoli che scrivi, salvati come file di testo (in formato JSON).
  Sono le tue "fonti". Conviene fare un backup di questa cartella ogni tanto.
- `config.json` : le impostazioni del sito e il contenuto della homepage.
  Contiene anche le chiavi dei servizi di traduzione, per questo non va su
  git. Se un giorno diventa illeggibile, PyBlog ne mette una copia in
  `config.broken.json` e riparte con i valori predefiniti.
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
5. Incollali in Impostazioni, sezione "Commenti", scegli "Giscus", salva.

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
  richiede il consenso ai cookie: accendi il banner di PyBlog (passo
  2.12) e GA parte solo dopo che il visitatore ha accettato.

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
