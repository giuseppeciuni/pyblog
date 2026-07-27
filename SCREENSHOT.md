# Screenshot e strategia di lancio

Questo file ti guida a preparare gli screenshot per il README e a lanciare
PyBlog su GitHub. Gli screenshot li devi generare tu, perche' servono catture
reali del blog in funzione sul tuo schermo.

## Screenshot da preparare

Crea una cartella `screenshots/` e metti dentro queste immagini. Poi togli i
commenti nel README (sezione "Screenshot") e inserisci i percorsi.

1. **homepage.png** — La homepage pubblica con la presentazione, le card e
   la griglia di articoli. E' la prima cosa che vede chi arriva: scegli un
   momento in cui il blog ha 3-4 articoli, cosi' sembra vivo.

2. **editor.png** — L'editor con la barra laterale: si vede il contenuto a
   sinistra e i metadati/azioni a destra. Mostra il punto di forza "scrivi
   come su Word ma generi HTML statico".

3. **articolo.png** — Un articolo pubblicato, con tempo di lettura, tag,
   magari un blocco di codice evidenziato. Dimostra la qualita' del risultato.

4. **dark-mode.png** (opzionale) — La stessa homepage in tema scuro, per
   mostrare il dark mode.

5. **mobile.png** (opzionale) — L'editor o la homepage su schermo stretto,
   per dimostrare che e' responsive.

### Consigli pratici

- Usa una finestra del browser pulita (niente decine di tab aperte).
- Risoluzione: cattura a larghezza ~1280px, cosi' le immagini non sono enormi.
- Per una GIF animata (molto efficace su GitHub): registra 5-10 secondi in cui
  scrivi un titolo, incolli testo e premi salva. Strumenti: LICEcap, Kap (macOS),
  Peek (Linux). Una GIF dell'editor in azione vale piu' di mille parole.

## Strategia di lancio

PyBlog ha un gancio forte e raro: **un motore di blog completo in un solo file
Python, zero dipendenze, con traduzione AI**. Questo e' il messaggio da
ripetere ovunque: e' cio' che lo rende condivisibile.

### Prima del lancio (checklist)

- [ ] Repository pubblico su GitHub con un nome chiaro (es. `pyblog`).
- [ ] README con almeno 1-2 screenshot (meglio se una GIF dell'editor).
- [ ] File LICENSE presente (MIT, gia' incluso).
- [ ] Una "description" del repo breve e d'effetto + qualche topic/tag GitHub
      (`python`, `static-site-generator`, `blog`, `self-hosted`, `wysiwyg`).
- [ ] Un sito demo dal vivo, se possibile (anche il tuo blog vero).

### Dove lanciarlo

In ordine di efficacia per un progetto come questo:

1. **Show HN (Hacker News)** — titolo: "Show HN: PyBlog – a complete blog engine
   in a single Python file, zero dependencies". Pubblica in mattinata (ora USA).
   Rispondi ai commenti con calma e senza difenderti troppo.

2. **r/selfhosted** e **r/Python** (Reddit) — il taglio "self-hosted, no database,
   own your data" funziona molto bene su r/selfhosted; su r/Python conta
   l'eleganza del "single file, stdlib only".

3. **Lobsters** (lobste.rs) — pubblico tecnico, apprezza la semplicita'.

4. **Dev.to / Hashnode** — scrivi un articolo "Ho costruito un blog engine in un
   solo file Python: ecco perche' e come". Il racconto del perche' attira piu'
   delle feature.

### Come scrivere il post di lancio

- Apri con il problema: "Volevo un blog mio, veloce, senza WordPress ne' database."
- Mostra la soluzione in una riga: un file, zero dipendenze, editor nel browser.
- Una GIF o uno screenshot subito.
- Link al repo e (se c'e') alla demo.
- Chiudi invitando al feedback, non vantandoti. La community premia l'umilta'.

### Dopo il lancio

- Rispondi a ogni issue e commento nelle prime 48 ore: la reattivita' iniziale
  decide se un progetto prende quota.
- Se ricevi richieste ricorrenti, aggiungile come "roadmap" nel README.
- Le star arrivano se il progetto risolve un problema reale in modo elegante:
  PyBlog lo fa. Non serve esagerare con la promozione.
