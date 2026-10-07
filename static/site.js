/* ---------------------------------------------------------------------------
   site.js - all the JavaScript of the public site.

   Independent pieces live here: the light/dark theme, applied immediately
   so the page never flashes; the client-side search on the homepage, which
   downloads the JSON index generated at build time and filters it locally;
   the folding menu of a phone; the table of contents that follows the
   reading; the copy button of the code blocks; the reading progress bar;
   the enlarged cover.

   The page-dependent values (language, link prefix, translated labels, the
   slice of articles shown by the pagination) are NOT written into this file:
   every page injects them as window.PB_SITE with json.dumps, so an Italian
   apostrophe can never break the syntax. The search settings are only there
   on the homepage; the rest is on every page.
   --------------------------------------------------------------------------- */

/* --- 1) Light/dark theme ------------------------------------------------- */

// We apply the saved theme right away, before the page is painted.
(function() {
  // The stylesheet folds the phone menu only when this class is there: a
  // browser without JavaScript keeps every link visible.
  document.documentElement.classList.add('js');
  try {
    var salvato = localStorage.getItem('pb-tema');
    if (salvato === 'dark') {
      document.documentElement.setAttribute('data-tema', 'dark');
    } else if (salvato === null && window.matchMedia
               && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      // No saved choice: we respect the system preference.
      document.documentElement.setAttribute('data-tema', 'dark');
    }
  } catch (e) { }
})();

// Aligns the code blocks theme (highlight.js) with the site theme.
// The link has id "hljs-tema" and only exists on the article pages.
function updateCodeTheme() {
  var link = document.getElementById('hljs-tema');
  if (!link) { return; }
  var scuro = document.documentElement.getAttribute('data-tema') === 'dark';
  if (scuro) {
    link.href = 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css';
  } else {
    link.href = 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css';
  }
}

// Switches between light and dark theme and saves the choice.
function toggleTheme() {
  var attuale = document.documentElement.getAttribute('data-tema');
  if (attuale === 'dark') {
    document.documentElement.removeAttribute('data-tema');
    try { localStorage.setItem('pb-tema', 'light'); } catch (e) { }
  } else {
    document.documentElement.setAttribute('data-tema', 'dark');
    try { localStorage.setItem('pb-tema', 'dark'); } catch (e) { }
  }
  updateCodeTheme();
}

// On load, we sync the code theme with the saved one.
document.addEventListener('DOMContentLoaded', updateCodeTheme);

/* --- 2) Syntax highlighting of the code blocks --------------------------- */

// The article pages load highlight.js from the CDN; the other pages do not.
// We only colour the blocks when the library is really there.
document.addEventListener('DOMContentLoaded', function() {
  if (!window.hljs) { return; }
  document.querySelectorAll('pre.ql-syntax').forEach(function(blocco) {
    hljs.highlightElement(blocco);
  });
});

/* --- 3) Client-side search ----------------------------------------------- */

// Browser-side search: it downloads the JSON index once and filters locally.
// It shows a snippet of the context around the searched word, with
// highlighting. It searches both languages. A 100% static site.
document.addEventListener('DOMContentLoaded', function() {
  var opzioni = window.PB_SITE;
  if (!opzioni) { return; }

  var input = document.getElementById('search-box-input');
  var info = document.getElementById('search-box-info');
  var lista = document.getElementById('lista-articoli');
  if (!input || !info || !lista) { return; }
  if (opzioni.post_prefix === undefined) { return; }

  // The list exactly as the generator wrote it. When the box is emptied it
  // goes back as it was, lead row and all: rebuilding it from the index used
  // to give back cards with a different excerpt, and on the translated
  // homepage with the excerpt of the other language.
  var listaOriginale = lista.innerHTML;
  var paginazione = document.querySelector('.paginazione');

  var indice = [];

  // Variables that depend on the page language (injected from Python).
  var LINGUA_PAGINA = opzioni.language;
  // True on the pages of the translation. The _en fields of the index hold
  // the translated version, whichever language that is: on a site written in
  // English they are the Italian one.
  var SECONDARIA = opzioni.secondary === true;
  var PREFISSO_POST = opzioni.post_prefix;
  var PREFISSO_TAG = opzioni.tag_prefix;
  var MSG_SEARCH_UNAVAILABLE = opzioni.msg_unavailable;
  var MSG_NO_RESULTS_FOR = opzioni.msg_no_results;
  var MSG_RESULTS_FOR = opzioni.msg_results_for;

  // Returns the date formatted in the page language.
  function articleDate(a) {
    if (LINGUA_PAGINA === 'en' && a.date_en) {
      return a.date_en;
    }
    return a.date_it;
  }

  // Returns the right title based on the page language.
  function articleTitle(a) {
    if (SECONDARIA && a.title_en) {
      return a.title_en;
    }
    return a.title;
  }

  // The reading time and the opening of the text, in the page language.
  function articleReading(a) {
    if (SECONDARIA && a.reading_en) { return a.reading_en; }
    return a.reading;
  }

  function articleExcerpt(a) {
    if (SECONDARIA && a.excerpt_en) { return a.excerpt_en; }
    return a.excerpt;
  }

  // Tells whether an article should be shown in this language.
  // On the translated home we only show articles with a confirmed translation.
  function articleIsVisible(a) {
    if (SECONDARIA) {
      return a.has_en === true;
    }
    return true;
  }

  // Loads the article index generated at build time. The 404 page sends
  // readers here with ?q=..., so once the index is in we run that query.
  fetch('/search-index.json')
    .then(function(r) { return r.json(); })
    .then(function(dati) {
      indice = dati;
      var iniziale = queryFromUrl();
      if (iniziale !== '') {
        input.value = iniziale;
        searchArticles(iniziale);
        input.focus();
      }
    })
    .catch(function() { info.textContent = MSG_SEARCH_UNAVAILABLE; });

  // Reads the q parameter of the address, if there is one.
  function queryFromUrl() {
    try {
      var parametri = new URLSearchParams(window.location.search);
      var valore = parametri.get('q');
      if (valore === null) { return ''; }
      return valore;
    } catch (e) {
      return '';
    }
  }

  // Strips accents and lowercases, for more forgiving comparisons.
  function normalizeText(s) {
    if (s === null || s === undefined) {
      return '';
    }
    return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  // Bolds the occurrences of the term in a text (already made safe).
  function highlight(testoSicuro, termine) {
    var testoNorm = normalizeText(testoSicuro);
    var termineNorm = normalizeText(termine);
    var risultato = '';
    var posizione = 0;
    var trovato = testoNorm.indexOf(termineNorm, posizione);
    while (trovato !== -1) {
      risultato = risultato + testoSicuro.substring(posizione, trovato);
      risultato = risultato + '<mark>' +
        testoSicuro.substring(trovato, trovato + termine.length) + '</mark>';
      posizione = trovato + termine.length;
      trovato = testoNorm.indexOf(termineNorm, posizione);
    }
    risultato = risultato + testoSicuro.substring(posizione);
    return risultato;
  }

  // Derives a text snippet around the first occurrence of the term.
  function extractSnippet(testo, termine) {
    var testoNorm = normalizeText(testo);
    var termineNorm = normalizeText(termine);
    var posizione = testoNorm.indexOf(termineNorm);
    if (posizione === -1) {
      return '';
    }
    // We take a bit of text before and after the word we found.
    var inizio = posizione - 60;
    if (inizio < 0) {
      inizio = 0;
    }
    var fine = posizione + termine.length + 60;
    if (fine > testo.length) {
      fine = testo.length;
    }
    var frammento = testo.substring(inizio, fine);
    if (inizio > 0) {
      frammento = '…' + frammento;
    }
    if (fine < testo.length) {
      frammento = frammento + '…';
    }
    // We make the text safe and then highlight the term.
    return highlight(escapeHtml(frammento), termine);
  }

  function searchArticles(q) {
    var termine = q.trim();
    var termineNorm = normalizeText(termine);
    if (termineNorm === '') {
      // Empty query: the list goes back exactly as the page had it.
      info.textContent = '';
      lista.innerHTML = listaOriginale;
      if (paginazione) { paginazione.hidden = false; }
      return;
    }
    // The pages of the pagination are pages of the full list; a list of
    // results has none.
    if (paginazione) { paginazione.hidden = true; }

    // For each article we check where the term appears.
    var risultati = [];
    for (var i = 0; i < indice.length; i++) {
      var a = indice[i];
      // On the translated home we skip the articles with no translation.
      if (articleIsVisible(a) === false) {
        continue;
      }
      var inTitolo = normalizeText(a.title).includes(termineNorm);
      var inDescr = normalizeText(a.description).includes(termineNorm);
      var inTags = normalizeText(a.tags).includes(termineNorm);
      var inTesto = normalizeText(a.text).includes(termineNorm);
      var inTestoEn = normalizeText(a.text_en).includes(termineNorm);
      var inTitoloEn = normalizeText(a.title_en).includes(termineNorm);

      if (inTitolo || inDescr || inTags || inTesto || inTestoEn || inTitoloEn) {
        // We build the snippet from the point where the word was found.
        var snippet = '';
        if (SECONDARIA && inTestoEn) {
          snippet = extractSnippet(a.text_en, termine);
        } else if (inTesto) {
          snippet = extractSnippet(a.text, termine);
        } else if (inTestoEn) {
          snippet = extractSnippet(a.text_en, termine);
        } else if (inDescr) {
          snippet = extractSnippet(a.description, termine);
        }
        risultati.push({ articolo: a, snippet: snippet });
      }
    }

    renderResults(risultati, termine);
    if (risultati.length === 0) {
      info.textContent = MSG_NO_RESULTS_FOR + ' "' + termine + '".';
    } else {
      info.textContent = risultati.length + ' ' + MSG_RESULTS_FOR + ' "' + termine + '".';
    }
  }

  // Builds one article row.
  //
  // The same markup the generator writes in templates/public/article_row.html,
  // because these rows REPLACE the generated ones the moment you type in the
  // search box: any difference here would show up as the page changing shape
  // mid-search.
  //
  // titoloHtml arrives ready: the results highlight the search term inside
  // it. testoSotto is the snippet around the term, or the opening of the
  // article when the term was only in the title.
  function rowHtml(a, titoloHtml, testoSotto) {
    var miniatura = '<span class="art-tile">' + escapeHtml(a.tile) + '</span>';
    if (a.image) {
      miniatura = '<img class="art-thumb-img" src="' + escapeHtml(a.image) +
                  '" alt="" loading="lazy">';
    }
    var indirizzo = PREFISSO_POST + a.slug + '.html';
    return '<article class="art-row">' +
      '<div class="art-thumb" aria-hidden="true">' + miniatura + '</div>' +
      '<div class="art-body">' +
      tagsHtml(a) +
      '<h3 class="art-title"><a href="' + indirizzo + '">' + titoloHtml + '</a></h3>' +
      '<p class="art-meta">' + articleDate(a) + ' &middot; ' + escapeHtml(articleReading(a)) + '</p>' +
      testoSotto +
      '</div></article>';
  }

  // The tags of a row, as links. The slugs come from the index rather than
  // being derived here: the generator folds accents when it makes them, and
  // a second version of that rule in JavaScript would drift.
  function tagsHtml(a) {
    if (!a.tag_links || a.tag_links.length === 0) { return ''; }
    var pezzi = '';
    for (var i = 0; i < a.tag_links.length; i++) {
      var tag = a.tag_links[i];
      pezzi = pezzi + '<a class="art-tag" href="' + PREFISSO_TAG +
              escapeHtml(tag.slug) + '.html">#' + escapeHtml(tag.name) + '</a>';
    }
    return '<p class="art-tags">' + pezzi + '</p>';
  }

  // Shows the search results, with highlighted title and snippet.
  function renderResults(risultati, termine) {
    var html = '';
    for (var i = 0; i < risultati.length; i++) {
      var a = risultati[i].articolo;
      var snippet = risultati[i].snippet;
      var testoSotto = '<p class="art-excerpt">' + escapeHtml(articleExcerpt(a)) + '</p>';
      if (snippet !== '') {
        testoSotto = '<p class="art-snippet">' + snippet + '</p>';
      }
      html = html + rowHtml(a, highlight(escapeHtml(articleTitle(a)), termine), testoSotto);
    }
    lista.innerHTML = html;
  }

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  var timer;
  input.addEventListener('input', function() {
    clearTimeout(timer);
    timer = setTimeout(function() { searchArticles(input.value); }, 120);
  });
});

/* --- 3b) The menu on a phone ---------------------------------------------- */

// On a narrow screen the links of the header fold behind a "Menu" button.
// Without JavaScript the button stays hidden and the links simply wrap: the
// stylesheet only folds the menu when the html element carries the "js"
// class, which the theme code above sets as soon as the script runs.
document.addEventListener('DOMContentLoaded', function() {
  var pulsante = document.querySelector('.menu-toggle');
  var menu = document.getElementById('site-nav');
  if (!pulsante || !menu) { return; }

  function chiudi() {
    menu.classList.remove('aperto');
    pulsante.setAttribute('aria-expanded', 'false');
  }

  pulsante.addEventListener('click', function() {
    var aperto = menu.classList.toggle('aperto');
    pulsante.setAttribute('aria-expanded', aperto ? 'true' : 'false');
  });
  // Esc closes it, and so does following one of its links (an anchor such
  // as #articles keeps the page, so the menu would stay open over it).
  document.addEventListener('keydown', function(evento) {
    if (evento.key === 'Escape' && menu.classList.contains('aperto')) {
      chiudi();
      pulsante.focus();
    }
  });
  menu.addEventListener('click', function(evento) {
    if (evento.target.closest('a')) { chiudi(); }
  });
});

/* --- 3c) The table of contents follows the reading ------------------------- */

// In the sidebar of an article, the entry of the section being read is
// marked, so the index doubles as a "you are here".
document.addEventListener('DOMContentLoaded', function() {
  var voci = document.querySelectorAll('.box-indice a[href^="#"]');
  if (voci.length === 0 || !('IntersectionObserver' in window)) { return; }

  var perId = {};
  var titoli = [];
  for (var i = 0; i < voci.length; i++) {
    var id = decodeURIComponent(voci[i].getAttribute('href').substring(1));
    var titolo = document.getElementById(id);
    if (titolo) {
      perId[id] = voci[i];
      titoli.push(titolo);
    }
  }
  if (titoli.length === 0) { return; }

  function segna(id) {
    for (var chiave in perId) {
      if (chiave === id) {
        perId[chiave].setAttribute('aria-current', 'location');
      } else {
        perId[chiave].removeAttribute('aria-current');
      }
    }
  }

  // A heading counts as "being read" once it has crossed the top third of
  // the window; the last one that did is the current section.
  var osservatore = new IntersectionObserver(function() {
    var attuale = titoli[0].id;
    for (var j = 0; j < titoli.length; j++) {
      if (titoli[j].getBoundingClientRect().top < window.innerHeight / 3) {
        attuale = titoli[j].id;
      }
    }
    segna(attuale);
  }, { rootMargin: '0px 0px -66% 0px' });
  for (var k = 0; k < titoli.length; k++) {
    osservatore.observe(titoli[k]);
  }
});

/* --- 4) Copy button on the code blocks ------------------------------------ */

// Adds a "copy" button to every code block of an article.
//
// A code block exists to be used, and selecting several screens of it with
// the mouse - on a phone especially - is miserable. The button is added by
// JavaScript rather than baked into the HTML so that articles written before
// this existed get it too, and so the generated pages stay clean.
document.addEventListener('DOMContentLoaded', function() {
  var opzioni = window.PB_SITE;
  if (!opzioni) { return; }

  var blocchi = document.querySelectorAll('article.post pre.ql-syntax, .card-page pre.ql-syntax');
  for (var i = 0; i < blocchi.length; i++) {
    aggiungiPulsanteCopia(blocchi[i], opzioni);
  }
});

function aggiungiPulsanteCopia(blocco, opzioni) {
  // The button is positioned against a wrapper, so the block itself keeps
  // its own scrolling and padding untouched.
  var contenitore = document.createElement('div');
  contenitore.className = 'blocco-codice';
  blocco.parentNode.insertBefore(contenitore, blocco);
  contenitore.appendChild(blocco);

  var pulsante = document.createElement('button');
  pulsante.type = 'button';
  pulsante.className = 'copia-codice';
  pulsante.textContent = opzioni.copy_label;
  pulsante.setAttribute('title', opzioni.copy_title);
  pulsante.setAttribute('aria-label', opzioni.copy_title);

  pulsante.addEventListener('click', function() {
    var testo = blocco.textContent;
    copiaTesto(testo, function(riuscito) {
      if (riuscito) {
        pulsante.textContent = opzioni.copied_label;
        pulsante.classList.add('copiato');
      }
      setTimeout(function() {
        pulsante.textContent = opzioni.copy_label;
        pulsante.classList.remove('copiato');
      }, 1500);
    });
  });

  contenitore.appendChild(pulsante);
}

// "Copy the link" at the end of an article: the address goes to the
// clipboard and the button says so for a moment.
document.addEventListener('DOMContentLoaded', function() {
  var pulsanti = document.querySelectorAll('.condividi-copia');
  for (var i = 0; i < pulsanti.length; i++) {
    pulsanti[i].addEventListener('click', function() {
      var pulsante = this;
      var scritta = pulsante.textContent;
      copiaTesto(pulsante.getAttribute('data-url'), function(riuscito) {
        if (!riuscito) { return; }
        pulsante.textContent = pulsante.getAttribute('data-fatto');
        setTimeout(function() { pulsante.textContent = scritta; }, 1500);
      });
    });
  }
});

// Copies text to the clipboard, with a fallback for browsers without the
// clipboard API and for pages served over plain HTTP, where it is disabled.
function copiaTesto(testo, quandoFatto) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(testo)
      .then(function() { quandoFatto(true); })
      .catch(function() { quandoFatto(false); });
    return;
  }
  var area = document.createElement('textarea');
  area.value = testo;
  area.setAttribute('readonly', 'readonly');
  area.style.position = 'absolute';
  area.style.left = '-9999px';
  document.body.appendChild(area);
  area.select();
  var riuscito = false;
  try {
    riuscito = document.execCommand('copy');
  } catch (e) {
    riuscito = false;
  }
  document.body.removeChild(area);
  quandoFatto(riuscito);
}

/* --- 5) Reading progress bar --------------------------------------------- */

// A thin bar at the top of an article showing how far down it you are.
//
// It measures the article itself, not the whole document: the header, the
// related articles and the footer are not part of the read, and counting
// them would show 60% when you have actually finished.
document.addEventListener('DOMContentLoaded', function() {
  var opzioni = window.PB_SITE;
  var articolo = document.querySelector('article.post');
  if (!opzioni || !articolo) { return; }

  var barra = document.createElement('div');
  barra.className = 'progresso-lettura';
  barra.setAttribute('role', 'progressbar');
  barra.setAttribute('aria-label', opzioni.progress_label);
  barra.setAttribute('aria-valuemin', '0');
  barra.setAttribute('aria-valuemax', '100');

  var riempimento = document.createElement('div');
  riempimento.className = 'progresso-lettura-barra';
  barra.appendChild(riempimento);
  document.body.appendChild(barra);

  var inAttesa = false;

  function aggiorna() {
    inAttesa = false;
    var inizio = articolo.offsetTop;
    var altezza = articolo.offsetHeight;
    var visibile = window.innerHeight;
    // How much of the article has scrolled past the bottom of the window.
    var percorso = altezza - visibile;
    if (percorso <= 0) {
      riempimento.style.width = '100%';
      barra.setAttribute('aria-valuenow', '100');
      return;
    }
    var avanzamento = (window.pageYOffset - inizio) / percorso;
    if (avanzamento < 0) { avanzamento = 0; }
    if (avanzamento > 1) { avanzamento = 1; }
    var percentuale = Math.round(avanzamento * 100);
    riempimento.style.width = percentuale + '%';
    barra.setAttribute('aria-valuenow', String(percentuale));
  }

  // requestAnimationFrame keeps the work to one update per painted frame,
  // instead of one per scroll event.
  function pianifica() {
    if (inAttesa) { return; }
    inAttesa = true;
    window.requestAnimationFrame(aggiorna);
  }

  window.addEventListener('scroll', pianifica, { passive: true });
  window.addEventListener('resize', pianifica);
  aggiorna();
});

/* --- 6) Enlarging the article cover --------------------------------------- */

// Opens the article cover at full size when it is clicked.
//
// Only the cover INSIDE an article gets this. On the homepage the same
// picture sits inside the link to the article, and a click there has to mean
// "open the article": giving one region of a card a different action is a
// trap, and on a touch screen there is no hover to hint at the difference.
// In the article the picture is not a link, and its height is capped - so
// part of it is cropped, and "let me see the whole thing" is a real need
// rather than an invented one.
document.addEventListener('DOMContentLoaded', function() {
  var opzioni = window.PB_SITE;
  if (!opzioni) { return; }

  var immagini = document.querySelectorAll('.articolo-copertina img[data-zoom]');
  if (immagini.length === 0) { return; }

  for (var i = 0; i < immagini.length; i++) {
    preparaZoom(immagini[i], opzioni);
  }
});

function preparaZoom(immagine, opzioni) {
  // The image becomes a real button: it can be reached with the keyboard and
  // a screen reader announces it as something you can activate.
  immagine.setAttribute('role', 'button');
  immagine.setAttribute('tabindex', '0');
  immagine.setAttribute('aria-label', opzioni.zoom_label);

  function apri() {
    apriZoom(immagine.getAttribute('data-zoom'), immagine.alt, opzioni);
  }

  immagine.addEventListener('click', apri);
  immagine.addEventListener('keydown', function(evento) {
    if (evento.key === 'Enter' || evento.key === ' ') {
      evento.preventDefault();
      apri();
    }
  });
}

// Shows the picture over the page. Built by hand rather than with a library:
// it is a div, an image and two ways to close it.
function apriZoom(indirizzo, testoAlternativo, opzioni) {
  if (document.querySelector('.zoom-immagine')) { return; }

  var sfondo = document.createElement('div');
  sfondo.className = 'zoom-immagine';
  sfondo.setAttribute('role', 'dialog');
  sfondo.setAttribute('aria-modal', 'true');
  sfondo.setAttribute('aria-label', testoAlternativo || opzioni.zoom_label);

  var grande = document.createElement('img');
  grande.src = indirizzo;
  grande.alt = testoAlternativo || '';
  sfondo.appendChild(grande);

  var chiudi = document.createElement('button');
  chiudi.type = 'button';
  chiudi.className = 'zoom-chiudi';
  chiudi.setAttribute('aria-label', opzioni.close_label);
  chiudi.textContent = '×';
  sfondo.appendChild(chiudi);

  // Where the focus was, so it can go back there when the picture closes.
  var elementoPrecedente = document.activeElement;

  function chiudiZoom() {
    document.removeEventListener('keydown', suTasto);
    if (sfondo.parentNode) { sfondo.parentNode.removeChild(sfondo); }
    document.body.classList.remove('zoom-aperto');
    if (elementoPrecedente && elementoPrecedente.focus) { elementoPrecedente.focus(); }
  }

  function suTasto(evento) {
    if (evento.key === 'Escape') { chiudiZoom(); }
  }

  chiudi.addEventListener('click', chiudiZoom);
  // A click ANYWHERE closes it, the picture included. Excluding the picture
  // meant that on a phone, where it fills nearly the whole screen, almost
  // every tap landed on it and did nothing: the only way out was a small
  // button in a corner. Tapping what you are looking at to dismiss it is
  // what people try first, and there is nothing else to do here.
  sfondo.addEventListener('click', chiudiZoom);
  document.addEventListener('keydown', suTasto);

  document.body.appendChild(sfondo);
  // Stops the page behind from scrolling while the picture is open.
  document.body.classList.add('zoom-aperto');
  chiudi.focus();
}

/* --- 6b) Code placed at a point chosen on the page -------------------------- */

// Turns an inert <template> into live code, in the very place it stands. A
// script cloned out of a template does not run: it has to be created anew.
// External scripts keep their own async; the others keep the order they were
// written in, which is what a loader followed by its set-up expects.
function attivaModello(modello) {
  var frammento = modello.content.cloneNode(true);
  var script = frammento.querySelectorAll('script');
  for (var j = 0; j < script.length; j++) {
    var vecchio = script[j];
    var nuovo = document.createElement('script');
    for (var k = 0; k < vecchio.attributes.length; k++) {
      nuovo.setAttribute(vecchio.attributes[k].name, vecchio.attributes[k].value);
    }
    if (vecchio.src) { nuovo.async = vecchio.hasAttribute('async'); }
    nuovo.text = vecchio.text;
    vecchio.parentNode.replaceChild(nuovo, vecchio);
  }
  modello.parentNode.replaceChild(frammento, modello);
}

// The author chose, by clicking on the page, the block a piece of code goes
// before or after. The code arrives inert at the end of the page, naming
// that block; here it moves next to it. If it waits for consent it stays
// inert in its new place, and the consent section below wakes it there; if
// not, it runs now. A page without that block simply does not show it.
// This listener is registered before the consent one, so it runs first.
document.addEventListener('DOMContentLoaded', function() {
  var modelli = document.querySelectorAll('template[data-pb-ancora]');
  for (var i = 0; i < modelli.length; i++) {
    var modello = modelli[i];
    var bersaglio = null;
    try {
      bersaglio = document.querySelector(modello.getAttribute('data-pb-ancora'));
    } catch (e) {
      bersaglio = null;
    }
    if (bersaglio === null) {
      modello.parentNode.removeChild(modello);
      continue;
    }
    var contenitore = document.createElement('div');
    contenitore.className = 'codice-posizionato';
    if (modello.getAttribute('data-pb-dove') === 'before') {
      bersaglio.parentNode.insertBefore(contenitore, bersaglio);
    } else {
      bersaglio.parentNode.insertBefore(contenitore, bersaglio.nextSibling);
    }
    contenitore.appendChild(modello);
    if (!modello.hasAttribute('data-pb-consenso')) {
      attivaModello(modello);
    }
  }
});

/* --- 7) Consent to statistics and advertising ------------------------------ */

// The code that needs the visitor's consent reaches the page inside inert
// <template data-pb-consenso="..."> elements: nothing in them runs or loads.
// Here, once the visitor has accepted a category, its templates become live
// code in the very place they stand, and Google's tags are told through
// Consent Mode. The choice is kept in this browser and asked again only when
// the site starts using a category the visitor never decided about, or when
// the author asks everybody again (the version number changes).
document.addEventListener('DOMContentLoaded', function() {
  var opzioni = window.PB_SITE;
  if (!opzioni || !opzioni.consent) { return; }
  var banner = document.getElementById('pb-consenso');
  if (!banner) { return; }

  var CHIAVE = 'pb-consenso';
  var versione = opzioni.consent.version;
  var categorie = opzioni.consent.categories || [];
  var scelte = document.getElementById('pb-consenso-scelte');
  var pulsanteSalva = banner.querySelector('[data-consenso="salva"]');
  var pulsantePersonalizza = banner.querySelector('[data-consenso="personalizza"]');

  function leggiScelta() {
    try {
      var valore = JSON.parse(localStorage.getItem(CHIAVE));
      if (valore && valore.v === versione) { return valore; }
    } catch (e) { }
    return null;
  }

  function salvaScelta(valore) {
    valore.v = versione;
    valore.data = new Date().toISOString();
    try { localStorage.setItem(CHIAVE, JSON.stringify(valore)); } catch (e) { }
  }

  function attivaCategoria(categoria) {
    var modelli = document.querySelectorAll('template[data-pb-consenso="' + categoria + '"]');
    for (var i = 0; i < modelli.length; i++) {
      attivaModello(modelli[i]);
    }
  }

  function aggiornaGoogle(valore) {
    if (typeof window.gtag !== 'function') { return; }
    var statistiche = valore.statistics === true ? 'granted' : 'denied';
    var pubblicita = valore.marketing === true ? 'granted' : 'denied';
    window.gtag('consent', 'update', {
      analytics_storage: statistiche,
      ad_storage: pubblicita,
      ad_user_data: pubblicita,
      ad_personalization: pubblicita
    });
  }

  function applica(valore) {
    aggiornaGoogle(valore);
    for (var i = 0; i < categorie.length; i++) {
      if (valore[categorie[i]] === true) { attivaCategoria(categorie[i]); }
    }
  }

  function mostraScelte(valore) {
    var caselle = scelte.querySelectorAll('input[data-categoria]');
    for (var i = 0; i < caselle.length; i++) {
      caselle[i].checked = !!(valore && valore[caselle[i].getAttribute('data-categoria')] === true);
    }
    scelte.hidden = false;
    pulsanteSalva.hidden = false;
    pulsantePersonalizza.hidden = true;
  }

  function apri(conScelte) {
    var attuale = leggiScelta();
    if (conScelte) {
      mostraScelte(attuale);
    } else {
      scelte.hidden = true;
      pulsanteSalva.hidden = true;
      pulsantePersonalizza.hidden = false;
    }
    banner.hidden = false;
  }

  // A category taken back cannot be switched off in a page where its code
  // already runs: the page is reloaded without it.
  function decidi(valore) {
    var prima = leggiScelta();
    salvaScelta(valore);
    banner.hidden = true;
    var ritirata = false;
    for (var i = 0; i < categorie.length; i++) {
      if (prima && prima[categorie[i]] === true && valore[categorie[i]] !== true) { ritirata = true; }
    }
    if (ritirata) {
      window.location.reload();
      return;
    }
    applica(valore);
  }

  function tutte(valoreDiOgni) {
    var valore = prendiPrecedenti();
    for (var i = 0; i < categorie.length; i++) { valore[categorie[i]] = valoreDiOgni; }
    return valore;
  }

  // Categories decided on another page, and not used on this one, keep the
  // answer the visitor gave there.
  function prendiPrecedenti() {
    var prima = leggiScelta();
    var valore = {};
    if (prima) {
      for (var chiave in prima) {
        if (chiave !== 'v' && chiave !== 'data') { valore[chiave] = prima[chiave]; }
      }
    }
    return valore;
  }

  banner.addEventListener('click', function(evento) {
    var pulsante = evento.target.closest('[data-consenso]');
    if (!pulsante) { return; }
    var azione = pulsante.getAttribute('data-consenso');
    if (azione === 'accetta') { decidi(tutte(true)); }
    if (azione === 'rifiuta') { decidi(tutte(false)); }
    if (azione === 'personalizza') { mostraScelte(leggiScelta()); }
    if (azione === 'salva') {
      var valore = prendiPrecedenti();
      var caselle = scelte.querySelectorAll('input[data-categoria]');
      for (var i = 0; i < caselle.length; i++) {
        valore[caselle[i].getAttribute('data-categoria')] = caselle[i].checked;
      }
      decidi(valore);
    }
  });

  // The "cookie preferences" link of the footer reopens the banner.
  document.addEventListener('click', function(evento) {
    if (evento.target.closest('.link-preferenze')) { apri(true); }
  });

  var salvata = leggiScelta();
  var daChiedere = salvata === null;
  if (salvata !== null) {
    for (var i = 0; i < categorie.length; i++) {
      if (salvata[categorie[i]] === undefined) { daChiedere = true; }
    }
  }
  if (salvata !== null) { applica(salvata); }
  if (daChiedere) { apri(false); }
});
