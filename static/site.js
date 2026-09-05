/* ---------------------------------------------------------------------------
   site.js - all the JavaScript of the public site.

   Two independent pieces live here:
     1) the light/dark theme, applied immediately so the page never flashes;
     2) the client-side search on the homepage, which downloads the JSON index
        generated at build time and filters it locally.

   The page-dependent values (language, link prefix, translated labels, the
   slice of articles shown by the pagination) are NOT written into this file:
   the homepage template injects them as window.PB_SITE with json.dumps, so an
   Italian apostrophe can never break the syntax.
   --------------------------------------------------------------------------- */

/* --- 1) Light/dark theme ------------------------------------------------- */

// We apply the saved theme right away, before the page is painted.
(function() {
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
// highlighting. It searches both Italian and English. A 100% static site.
document.addEventListener('DOMContentLoaded', function() {
  var opzioni = window.PB_SITE;
  if (!opzioni) { return; }

  var input = document.getElementById('search-box-input');
  var info = document.getElementById('search-box-info');
  var lista = document.getElementById('lista-articoli');
  if (!input || !info || !lista) { return; }

  var indice = [];

  // Variables that depend on the page language (injected from Python).
  var LINGUA_PAGINA = opzioni.language;
  var PREFISSO_POST = opzioni.post_prefix;
  var ETICHETTA_LEGGI = opzioni.read_label;
  var MSG_SEARCH_UNAVAILABLE = opzioni.msg_unavailable;
  var MSG_NO_RESULTS_FOR = opzioni.msg_no_results;
  var MSG_RESULTS_FOR = opzioni.msg_results_for;
  // Slice of articles shown on this page (for the pagination).
  // When the search is cleared, we restore ONLY this slice,
  // not the whole index. The search itself always searches everything.
  var PAGINA_INIZIO = opzioni.page_start;
  var PAGINA_FINE = opzioni.page_end;

  // Returns the date formatted in the page language.
  function articleDate(a) {
    if (LINGUA_PAGINA === 'en' && a.date_en) {
      return a.date_en;
    }
    return a.date_it;
  }

  // Returns the right title based on the page language.
  function articleTitle(a) {
    if (LINGUA_PAGINA === 'en') {
      if (a.title_en) {
        return a.title_en;
      }
      return a.title;
    }
    return a.title;
  }

  // Tells whether an article should be shown in this language.
  // On the English home we only show articles with a confirmed translation.
  function articleIsVisible(a) {
    if (LINGUA_PAGINA === 'en') {
      return a.has_en === true;
    }
    return true;
  }

  // Loads the article index generated at build time.
  fetch('/search-index.json')
    .then(function(r) { return r.json(); })
    .then(function(dati) { indice = dati; })
    .catch(function() { info.textContent = MSG_SEARCH_UNAVAILABLE; });

  // Strips accents and lowercases, for more forgiving comparisons.
  function normalizeText(s) {
    if (s === null || s === undefined) {
      return '';
    }
    return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
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
      frammento = '...' + frammento;
    }
    if (fine < testo.length) {
      frammento = frammento + '...';
    }
    // We make the text safe and then highlight the term.
    return highlight(escapeHtml(frammento), termine);
  }

  function searchArticles(q) {
    var termine = q.trim();
    var termineNorm = normalizeText(termine);
    if (termineNorm === '') {
      // Empty query: restore the original full list.
      info.textContent = '';
      renderAll();
      return;
    }

    // For each article we check where the term appears.
    var risultati = [];
    for (var i = 0; i < indice.length; i++) {
      var a = indice[i];
      // On the English home we skip the articles with no translation.
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
        if (LINGUA_PAGINA === 'en' && inTestoEn) {
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

  // Shows the search results, with highlighted title and snippet.
  function renderResults(risultati, termine) {
    if (risultati.length === 0) {
      lista.innerHTML = '';
      return;
    }
    var html = '';
    for (var i = 0; i < risultati.length; i++) {
      var a = risultati[i].articolo;
      var snippet = risultati[i].snippet;
      var bloccoSnippet = '';
      if (snippet !== '') {
        bloccoSnippet = '<p class="card-snippet">' + snippet + '</p>';
      }
      html = html +
        '<a class="article-card" href="' + PREFISSO_POST + a.slug + '.html">' +
        '<div class="card-date">' + articleDate(a) + '</div>' +
        '<h3 class="card-title">' + highlight(escapeHtml(articleTitle(a)), termine) + '</h3>' +
        bloccoSnippet +
        '<span class="card-read-more">' + ETICHETTA_LEGGI + ' &rarr;</span>' +
        '</a>';
    }
    lista.innerHTML = html;
  }

  // Shows every article (the initial state, with no search).
  function render(elenco) {
    if (elenco.length === 0) {
      lista.innerHTML = '';
      return;
    }
    var html = '';
    for (var i = 0; i < elenco.length; i++) {
      var a = elenco[i];
      if (articleIsVisible(a) === false) {
        continue;
      }
      // Card preview. Priority: preview written by the author,
      // then automatic excerpt (about 9 lines), then SEO description.
      var testoAnteprima = '';
      if (LINGUA_PAGINA === 'en' && a.preview_en) {
        testoAnteprima = a.preview_en;
      } else if (a.preview) {
        testoAnteprima = a.preview;
      }
      if (!testoAnteprima) {
        var fonte = a.text;
        if (LINGUA_PAGINA === 'en' && a.text_en) {
          fonte = a.text_en;
        }
        if (fonte) {
          testoAnteprima = fonte.substring(0, 640);
          if (fonte.length > 640) {
            testoAnteprima = testoAnteprima + '...';
          }
        }
      }
      if (!testoAnteprima) {
        testoAnteprima = a.description;
      }
      var estratto = '';
      if (testoAnteprima) {
        estratto = '<p class="card-excerpt">' + escapeHtml(testoAnteprima) + '</p>';
      }
      html = html +
        '<a class="article-card" href="' + PREFISSO_POST + a.slug + '.html">' +
        '<div class="card-date">' + articleDate(a) + '</div>' +
        '<h3 class="card-title">' + escapeHtml(articleTitle(a)) + '</h3>' +
        estratto +
        '<span class="card-read-more">' + ETICHETTA_LEGGI + ' &rarr;</span>' +
        '</a>';
    }
    lista.innerHTML = html;
  }

  function renderAll() {
    // First we filter by language, then we take the page slice.
    var visibili = [];
    for (var i = 0; i < indice.length; i++) {
      if (articleIsVisible(indice[i])) {
        visibili.push(indice[i]);
      }
    }
    render(visibili.slice(PAGINA_INIZIO, PAGINA_FINE));
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
