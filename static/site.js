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
    // The theme was saved as pb-tema before the names went English.
    var savedValue = localStorage.getItem('pb-theme') || localStorage.getItem('pb-tema');
    if (savedValue === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else if (savedValue === null && window.matchMedia
               && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      // No saved choice: we respect the system preference.
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  } catch (e) { }
})();

// Aligns the code blocks theme (highlight.js) with the site theme.
// The link has id "hljs-theme" and only exists on the article pages.
function updateCodeTheme() {
  var link = document.getElementById('hljs-theme');
  if (!link) { return; }
  var dark = document.documentElement.getAttribute('data-theme') === 'dark';
  if (dark) {
    link.href = 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css';
  } else {
    link.href = 'https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css';
  }
}

// Switches between light and dark theme and saves the choice.
function toggleTheme() {
  var current = document.documentElement.getAttribute('data-theme');
  if (current === 'dark') {
    document.documentElement.removeAttribute('data-theme');
    try { localStorage.setItem('pb-theme', 'light'); } catch (e) { }
  } else {
    document.documentElement.setAttribute('data-theme', 'dark');
    try { localStorage.setItem('pb-theme', 'dark'); } catch (e) { }
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
  document.querySelectorAll('pre.ql-syntax').forEach(function(blockEl) {
    hljs.highlightElement(blockEl);
  });
});

/* --- 3) Client-side search ----------------------------------------------- */

// Browser-side search: it downloads the JSON index once and filters locally.
// It shows a snippet of the context around the searched word, with
// highlighting. It searches both languages. A 100% static site.
document.addEventListener('DOMContentLoaded', function() {
  var options = window.PB_SITE;
  if (!options) { return; }

  var input = document.getElementById('search-box-input');
  var info = document.getElementById('search-box-info');
  var itemList = document.getElementById('list-box-articles');
  if (!input || !info || !itemList) { return; }
  if (options.post_prefix === undefined) { return; }

  // The list exactly as the generator wrote it. When the box is emptied it
  // goes back as it was, lead row and all: rebuilding it from the index used
  // to give back cards with a different excerpt, and on the translated
  // homepage with the excerpt of the other language.
  var originalList = itemList.innerHTML;
  var pagination = document.querySelector('.pagination');

  var idx = [];

  // Variables that depend on the page language (injected from Python).
  var PAGE_LANGUAGE = options.language;
  // True on the pages of the translation. The _en fields of the index hold
  // the translated version, whichever language that is: on a site written in
  // English they are the Italian one.
  var SECONDARY = options.secondary === true;
  var POST_PREFIX = options.post_prefix;
  var TAG_PREFIX = options.tag_prefix;
  var MSG_SEARCH_UNAVAILABLE = options.msg_unavailable;
  var MSG_NO_RESULTS_FOR = options.msg_no_results;
  var MSG_RESULTS_FOR = options.msg_results_for;

  // Returns the date formatted in the page language.
  function articleDate(a) {
    if (PAGE_LANGUAGE === 'en' && a.date_en) {
      return a.date_en;
    }
    return a.date_it;
  }

  // Returns the right title based on the page language.
  function articleTitle(a) {
    if (SECONDARY && a.title_en) {
      return a.title_en;
    }
    return a.title;
  }

  // The reading time and the opening of the text, in the page language.
  function articleReading(a) {
    if (SECONDARY && a.reading_en) { return a.reading_en; }
    return a.reading;
  }

  function articleExcerpt(a) {
    if (SECONDARY && a.excerpt_en) { return a.excerpt_en; }
    return a.excerpt;
  }

  // Tells whether an article should be shown in this language.
  // On the translated home we only show articles with a confirmed translation.
  function articleIsVisible(a) {
    if (SECONDARY) {
      return a.has_en === true;
    }
    return true;
  }

  // Loads the article index generated at build time. The 404 page sends
  // readers here with ?q=..., so once the index is in we run that query.
  fetch('/search-index.json')
    .then(function(r) { return r.json(); })
    .then(function(payload) {
      idx = payload;
      var initial = queryFromUrl();
      if (initial !== '') {
        input.value = initial;
        searchArticles(initial);
        input.focus();
      }
    })
    .catch(function() { info.textContent = MSG_SEARCH_UNAVAILABLE; });

  // Reads the q parameter of the address, if there is one.
  function queryFromUrl() {
    try {
      var params = new URLSearchParams(window.location.search);
      var val = params.get('q');
      if (val === null) { return ''; }
      return val;
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
  function highlight(safeText, term) {
    var textNorm = normalizeText(safeText);
    var termNorm = normalizeText(term);
    var resultValue = '';
    var placement = 0;
    var found = textNorm.indexOf(termNorm, placement);
    while (found !== -1) {
      resultValue = resultValue + safeText.substring(placement, found);
      resultValue = resultValue + '<mark>' +
        safeText.substring(found, found + term.length) + '</mark>';
      placement = found + term.length;
      found = textNorm.indexOf(termNorm, placement);
    }
    resultValue = resultValue + safeText.substring(placement);
    return resultValue;
  }

  // Derives a text snippet around the first occurrence of the term.
  function extractSnippet(textValue, term) {
    var textNorm = normalizeText(textValue);
    var termNorm = normalizeText(term);
    var placement = textNorm.indexOf(termNorm);
    if (placement === -1) {
      return '';
    }
    // We take a bit of text before and after the word we found.
    var startAt = placement - 60;
    if (startAt < 0) {
      startAt = 0;
    }
    var endAt = placement + term.length + 60;
    if (endAt > textValue.length) {
      endAt = textValue.length;
    }
    var fragment = textValue.substring(startAt, endAt);
    if (startAt > 0) {
      fragment = '…' + fragment;
    }
    if (endAt < textValue.length) {
      fragment = fragment + '…';
    }
    // We make the text safe and then highlight the term.
    return highlight(escapeHtml(fragment), term);
  }

  function searchArticles(q) {
    var term = q.trim();
    var termNorm = normalizeText(term);
    if (termNorm === '') {
      // Empty query: the list goes back exactly as the page had it.
      info.textContent = '';
      itemList.innerHTML = originalList;
      if (pagination) { pagination.hidden = false; }
      return;
    }
    // The pages of the pagination are pages of the full list; a list of
    // results has none.
    if (pagination) { pagination.hidden = true; }

    // For each article we check where the term appears.
    var results = [];
    for (var i = 0; i < idx.length; i++) {
      var a = idx[i];
      // On the translated home we skip the articles with no translation.
      if (articleIsVisible(a) === false) {
        continue;
      }
      var inTitle = normalizeText(a.title).includes(termNorm);
      var inDescription = normalizeText(a.description).includes(termNorm);
      var inTags = normalizeText(a.tags).includes(termNorm);
      var inText = normalizeText(a.text).includes(termNorm);
      var inTextEn = normalizeText(a.text_en).includes(termNorm);
      var inTitleEn = normalizeText(a.title_en).includes(termNorm);

      if (inTitle || inDescription || inTags || inText || inTextEn || inTitleEn) {
        // We build the snippet from the point where the word was found.
        var snippet = '';
        if (SECONDARY && inTextEn) {
          snippet = extractSnippet(a.text_en, term);
        } else if (inText) {
          snippet = extractSnippet(a.text, term);
        } else if (inTextEn) {
          snippet = extractSnippet(a.text_en, term);
        } else if (inDescription) {
          snippet = extractSnippet(a.description, term);
        }
        results.push({ article: a, snippet: snippet });
      }
    }

    renderResults(results, term);
    if (results.length === 0) {
      info.textContent = MSG_NO_RESULTS_FOR + ' "' + term + '".';
    } else {
      info.textContent = results.length + ' ' + MSG_RESULTS_FOR + ' "' + term + '".';
    }
  }

  // Builds one article row.
  //
  // The same markup the generator writes in templates/public/article_row.html,
  // because these rows REPLACE the generated ones the moment you type in the
  // search box: any difference here would show up as the page changing shape
  // mid-search.
  //
  // titleHtml arrives ready: the results highlight the search term inside
  // it. textBelow is the snippet around the term, or the opening of the
  // article when the term was only in the title.
  function rowHtml(a, titleHtml, textBelow) {
    var thumbnail = '<span class="art-tile">' + escapeHtml(a.tile) + '</span>';
    if (a.image) {
      thumbnail = '<img class="art-thumb-img" src="' + escapeHtml(a.image) +
                  '" alt="" loading="lazy">';
    }
    var address = POST_PREFIX + a.slug + '.html';
    return '<article class="art-row">' +
      '<div class="art-thumb" aria-hidden="true">' + thumbnail + '</div>' +
      '<div class="art-body">' +
      tagsHtml(a) +
      '<h3 class="art-title"><a href="' + address + '">' + titleHtml + '</a></h3>' +
      '<p class="art-meta">' + articleDate(a) + ' &middot; ' + escapeHtml(articleReading(a)) + '</p>' +
      textBelow +
      '</div></article>';
  }

  // The tags of a row, as links. The slugs come from the index rather than
  // being derived here: the generator folds accents when it makes them, and
  // a second version of that rule in JavaScript would drift.
  function tagsHtml(a) {
    if (!a.tag_links || a.tag_links.length === 0) { return ''; }
    var pieces = '';
    for (var i = 0; i < a.tag_links.length; i++) {
      var tag = a.tag_links[i];
      pieces = pieces + '<a class="art-tag" href="' + TAG_PREFIX +
              escapeHtml(tag.slug) + '.html">#' + escapeHtml(tag.name) + '</a>';
    }
    return '<p class="art-tags">' + pieces + '</p>';
  }

  // Shows the search results, with highlighted title and snippet.
  function renderResults(results, term) {
    var html = '';
    for (var i = 0; i < results.length; i++) {
      var a = results[i].article;
      var snippet = results[i].snippet;
      var textBelow = '<p class="art-excerpt">' + escapeHtml(articleExcerpt(a)) + '</p>';
      if (snippet !== '') {
        textBelow = '<p class="art-snippet">' + snippet + '</p>';
      }
      html = html + rowHtml(a, highlight(escapeHtml(articleTitle(a)), term), textBelow);
    }
    itemList.innerHTML = html;
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
  var buttonEl = document.querySelector('.menu-toggle');
  var menu = document.getElementById('site-nav');
  if (!buttonEl || !menu) { return; }

  function closeIt() {
    menu.classList.remove('open');
    buttonEl.setAttribute('aria-expanded', 'false');
  }

  buttonEl.addEventListener('click', function() {
    var isOpen = menu.classList.toggle('open');
    buttonEl.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  });
  // Esc closes it, and so does following one of its links (an anchor such
  // as #articles keeps the page, so the menu would stay open over it).
  document.addEventListener('keydown', function(evt) {
    if (evt.key === 'Escape' && menu.classList.contains('open')) {
      closeIt();
      buttonEl.focus();
    }
  });
  menu.addEventListener('click', function(evt) {
    if (evt.target.closest('a')) { closeIt(); }
  });
});

/* --- 3c) The table of contents follows the reading ------------------------- */

// In the sidebar of an article, the entry of the section being read is
// marked, so the index doubles as a "you are here".
document.addEventListener('DOMContentLoaded', function() {
  var entries = document.querySelectorAll('.box-toc-index a[href^="#"]');
  if (entries.length === 0 || !('IntersectionObserver' in window)) { return; }

  var byId = {};
  var titles = [];
  for (var i = 0; i < entries.length; i++) {
    var id = decodeURIComponent(entries[i].getAttribute('href').substring(1));
    var titleText = document.getElementById(id);
    if (titleText) {
      byId[id] = entries[i];
      titles.push(titleText);
    }
  }
  if (titles.length === 0) { return; }

  function mark(id) {
    for (var key in byId) {
      if (key === id) {
        byId[key].setAttribute('aria-current', 'location');
      } else {
        byId[key].removeAttribute('aria-current');
      }
    }
  }

  // A heading counts as "being read" once it has crossed the top third of
  // the window; the last one that did is the current section.
  var observer = new IntersectionObserver(function() {
    var current = titles[0].id;
    for (var j = 0; j < titles.length; j++) {
      if (titles[j].getBoundingClientRect().top < window.innerHeight / 3) {
        current = titles[j].id;
      }
    }
    mark(current);
  }, { rootMargin: '0px 0px -66% 0px' });
  for (var k = 0; k < titles.length; k++) {
    observer.observe(titles[k]);
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
  var options = window.PB_SITE;
  if (!options) { return; }

  var blocks = document.querySelectorAll('article.post pre.ql-syntax, .card-page pre.ql-syntax');
  for (var i = 0; i < blocks.length; i++) {
    addCopyButton(blocks[i], options);
  }
});

function addCopyButton(blockEl, options) {
  // The button is positioned against a wrapper, so the block itself keeps
  // its own scrolling and padding untouched.
  var containerEl = document.createElement('div');
  containerEl.className = 'code-block';
  blockEl.parentNode.insertBefore(containerEl, blockEl);
  containerEl.appendChild(blockEl);

  var buttonEl = document.createElement('button');
  buttonEl.type = 'button';
  buttonEl.className = 'copy-code';
  buttonEl.textContent = options.copy_label;
  buttonEl.setAttribute('title', options.copy_title);
  buttonEl.setAttribute('aria-label', options.copy_title);

  buttonEl.addEventListener('click', function() {
    var textValue = blockEl.textContent;
    copyText(textValue, function(success) {
      if (success) {
        buttonEl.textContent = options.copied_label;
        buttonEl.classList.add('copied');
      }
      setTimeout(function() {
        buttonEl.textContent = options.copy_label;
        buttonEl.classList.remove('copied');
      }, 1500);
    });
  });

  containerEl.appendChild(buttonEl);
}

// "Copy the link" at the end of an article: the address goes to the
// clipboard and the button says so for a moment.
document.addEventListener('DOMContentLoaded', function() {
  var buttons = document.querySelectorAll('.share-copy');
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].addEventListener('click', function() {
      var buttonEl = this;
      var caption = buttonEl.textContent;
      copyText(buttonEl.getAttribute('data-url'), function(success) {
        if (!success) { return; }
        buttonEl.textContent = buttonEl.getAttribute('data-done');
        setTimeout(function() { buttonEl.textContent = caption; }, 1500);
      });
    });
  }
});

// Copies text to the clipboard, with a fallback for browsers without the
// clipboard API and for pages served over plain HTTP, where it is disabled.
function copyText(textValue, onDone) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(textValue)
      .then(function() { onDone(true); })
      .catch(function() { onDone(false); });
    return;
  }
  var area = document.createElement('textarea');
  area.value = textValue;
  area.setAttribute('readonly', 'readonly');
  area.style.position = 'absolute';
  area.style.left = '-9999px';
  document.body.appendChild(area);
  area.select();
  var success = false;
  try {
    success = document.execCommand('copy');
  } catch (e) {
    success = false;
  }
  document.body.removeChild(area);
  onDone(success);
}

/* --- 5) Reading progress bar --------------------------------------------- */

// A thin bar at the top of an article showing how far down it you are.
//
// It measures the article itself, not the whole document: the header, the
// related articles and the footer are not part of the read, and counting
// them would show 60% when you have actually finished.
document.addEventListener('DOMContentLoaded', function() {
  var options = window.PB_SITE;
  var article = document.querySelector('article.post');
  if (!options || !article) { return; }

  var bar = document.createElement('div');
  bar.className = 'progress-reading';
  bar.setAttribute('role', 'progressbar');
  bar.setAttribute('aria-label', options.progress_label);
  bar.setAttribute('aria-valuemin', '0');
  bar.setAttribute('aria-valuemax', '100');

  var fill = document.createElement('div');
  fill.className = 'progress-reading-bar';
  bar.appendChild(fill);
  document.body.appendChild(bar);

  var pending = false;

  function refresh() {
    pending = false;
    var startAt = article.offsetTop;
    var height = article.offsetHeight;
    var visible = window.innerHeight;
    // How much of the article has scrolled past the bottom of the window.
    var path = height - visible;
    if (path <= 0) {
      fill.style.width = '100%';
      bar.setAttribute('aria-valuenow', '100');
      return;
    }
    var progress = (window.pageYOffset - startAt) / path;
    if (progress < 0) { progress = 0; }
    if (progress > 1) { progress = 1; }
    var percent = Math.round(progress * 100);
    fill.style.width = percent + '%';
    bar.setAttribute('aria-valuenow', String(percent));
  }

  // requestAnimationFrame keeps the work to one update per painted frame,
  // instead of one per scroll event.
  function schedule() {
    if (pending) { return; }
    pending = true;
    window.requestAnimationFrame(refresh);
  }

  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule);
  refresh();
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
  var options = window.PB_SITE;
  if (!options) { return; }

  var images = document.querySelectorAll('.article-cover img[data-zoom]');
  if (images.length === 0) { return; }

  for (var i = 0; i < images.length; i++) {
    prepareZoom(images[i], options);
  }
});

function prepareZoom(img, options) {
  // The image becomes a real button: it can be reached with the keyboard and
  // a screen reader announces it as something you can activate.
  img.setAttribute('role', 'button');
  img.setAttribute('tabindex', '0');
  img.setAttribute('aria-label', options.zoom_label);

  function openIt() {
    openZoom(img.getAttribute('data-zoom'), img.alt, options);
  }

  img.addEventListener('click', openIt);
  img.addEventListener('keydown', function(evt) {
    if (evt.key === 'Enter' || evt.key === ' ') {
      evt.preventDefault();
      openIt();
    }
  });
}

// Shows the picture over the page. Built by hand rather than with a library:
// it is a div, an image and two ways to close it.
function openZoom(address, altText, options) {
  if (document.querySelector('.zoom-picture')) { return; }

  var backdrop = document.createElement('div');
  backdrop.className = 'zoom-picture';
  backdrop.setAttribute('role', 'dialog');
  backdrop.setAttribute('aria-modal', 'true');
  backdrop.setAttribute('aria-label', altText || options.zoom_label);

  var bigImage = document.createElement('img');
  bigImage.src = address;
  bigImage.alt = altText || '';
  backdrop.appendChild(bigImage);

  var closeIt = document.createElement('button');
  closeIt.type = 'button';
  closeIt.className = 'zoom-close';
  closeIt.setAttribute('aria-label', options.close_label);
  closeIt.textContent = '×';
  backdrop.appendChild(closeIt);

  // Where the focus was, so it can go back there when the picture closes.
  var previousElement = document.activeElement;

  function closeZoom() {
    document.removeEventListener('keydown', onKey);
    if (backdrop.parentNode) { backdrop.parentNode.removeChild(backdrop); }
    document.body.classList.remove('zoom-open');
    if (previousElement && previousElement.focus) { previousElement.focus(); }
  }

  function onKey(evt) {
    if (evt.key === 'Escape') { closeZoom(); }
  }

  closeIt.addEventListener('click', closeZoom);
  // A click ANYWHERE closes it, the picture included. Excluding the picture
  // meant that on a phone, where it fills nearly the whole screen, almost
  // every tap landed on it and did nothing: the only way out was a small
  // button in a corner. Tapping what you are looking at to dismiss it is
  // what people try first, and there is nothing else to do here.
  backdrop.addEventListener('click', closeZoom);
  document.addEventListener('keydown', onKey);

  document.body.appendChild(backdrop);
  // Stops the page behind from scrolling while the picture is open.
  document.body.classList.add('zoom-open');
  closeIt.focus();
}

/* --- 6b) Code placed at a point chosen on the page -------------------------- */

// Turns an inert <template> into live code, in the very place it stands. A
// script cloned out of a template does not run: it has to be created anew.
// External scripts keep their own async; the others keep the order they were
// written in, which is what a loader followed by its set-up expects.
function activateTemplate(template) {
  var fragment = template.content.cloneNode(true);
  var script = fragment.querySelectorAll('script');
  for (var j = 0; j < script.length; j++) {
    var oldValue = script[j];
    var newValue = document.createElement('script');
    for (var k = 0; k < oldValue.attributes.length; k++) {
      newValue.setAttribute(oldValue.attributes[k].name, oldValue.attributes[k].value);
    }
    if (oldValue.src) { newValue.async = oldValue.hasAttribute('async'); }
    newValue.text = oldValue.text;
    oldValue.parentNode.replaceChild(newValue, oldValue);
  }
  template.parentNode.replaceChild(fragment, template);
}

// The author chose, by clicking on the page, the block a piece of code goes
// before or after. The code arrives inert at the end of the page, naming
// that block; here it moves next to it. If it waits for consent it stays
// inert in its new place, and the consent section below wakes it there; if
// not, it runs now. A page without that block simply does not show it.
// This listener is registered before the consent one, so it runs first.
document.addEventListener('DOMContentLoaded', function() {
  var templates = document.querySelectorAll('template[data-pb-anchor]');
  for (var i = 0; i < templates.length; i++) {
    var template = templates[i];
    var targetEl = null;
    try {
      targetEl = document.querySelector(template.getAttribute('data-pb-anchor'));
    } catch (e) {
      targetEl = null;
    }
    if (targetEl === null) {
      template.parentNode.removeChild(template);
      continue;
    }
    var containerEl = document.createElement('div');
    containerEl.className = 'code-positioned';
    if (template.getAttribute('data-pb-where') === 'before') {
      targetEl.parentNode.insertBefore(containerEl, targetEl);
    } else {
      targetEl.parentNode.insertBefore(containerEl, targetEl.nextSibling);
    }
    containerEl.appendChild(template);
    if (!template.hasAttribute('data-pb-consent')) {
      activateTemplate(template);
    }
  }
});

/* --- 7) Consent to statistics and advertising ------------------------------ */

// The code that needs the visitor's consent reaches the page inside inert
// <template data-pb-consent="..."> elements: nothing in them runs or loads.
// Here, once the visitor has accepted a category, its templates become live
// code in the very place they stand, and Google's tags are told through
// Consent Mode. The choice is kept in this browser and asked again only when
// the site starts using a category the visitor never decided about, or when
// the author asks everybody again (the version number changes).
document.addEventListener('DOMContentLoaded', function() {
  var options = window.PB_SITE;
  if (!options || !options.consent) { return; }
  var banner = document.getElementById('pb-consent');
  if (!banner) { return; }

  var STORAGE_KEY = 'pb-consent';
  var version = options.consent.version;
  var categories = options.consent.categories || [];
  var choices = document.getElementById('pb-consent-choices');
  var saveButton = banner.querySelector('[data-consent="save"]');
  var customizeButton = banner.querySelector('[data-consent="customize"]');

  function readChoice() {
    try {
      // A choice made before the names went English was saved as pb-consenso:
      // it still counts, so a visitor is not asked again.
      var val = JSON.parse(localStorage.getItem(STORAGE_KEY) || localStorage.getItem('pb-consenso'));
      if (val && val.v === version) { return val; }
    } catch (e) { }
    return null;
  }

  function saveChoice(val) {
    val.v = version;
    val.data = new Date().toISOString();
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(val)); } catch (e) { }
  }

  function activateCategory(category) {
    var templates = document.querySelectorAll('template[data-pb-consent="' + category + '"]');
    for (var i = 0; i < templates.length; i++) {
      activateTemplate(templates[i]);
    }
  }

  function updateGoogle(val) {
    if (typeof window.gtag !== 'function') { return; }
    var analytics = val.statistics === true ? 'granted' : 'denied';
    var advertising = val.marketing === true ? 'granted' : 'denied';
    window.gtag('consent', 'update', {
      analytics_storage: analytics,
      ad_storage: advertising,
      ad_user_data: advertising,
      ad_personalization: advertising
    });
  }

  function applyIt(val) {
    updateGoogle(val);
    for (var i = 0; i < categories.length; i++) {
      if (val[categories[i]] === true) { activateCategory(categories[i]); }
    }
  }

  function showChoices(val) {
    var checkboxes = choices.querySelectorAll('input[data-category]');
    for (var i = 0; i < checkboxes.length; i++) {
      checkboxes[i].checked = !!(val && val[checkboxes[i].getAttribute('data-category')] === true);
    }
    choices.hidden = false;
    saveButton.hidden = false;
    customizeButton.hidden = true;
  }

  function openIt(withChoices) {
    var current = readChoice();
    if (withChoices) {
      showChoices(current);
    } else {
      choices.hidden = true;
      saveButton.hidden = true;
      customizeButton.hidden = false;
    }
    banner.hidden = false;
  }

  // A category taken back cannot be switched off in a page where its code
  // already runs: the page is reloaded without it.
  function decide(val) {
    var before = readChoice();
    saveChoice(val);
    banner.hidden = true;
    var withdrawn = false;
    for (var i = 0; i < categories.length; i++) {
      if (before && before[categories[i]] === true && val[categories[i]] !== true) { withdrawn = true; }
    }
    if (withdrawn) {
      window.location.reload();
      return;
    }
    applyIt(val);
  }

  function all(valueOfEach) {
    var val = takePrevious();
    for (var i = 0; i < categories.length; i++) { val[categories[i]] = valueOfEach; }
    return val;
  }

  // Categories decided on another page, and not used on this one, keep the
  // answer the visitor gave there.
  function takePrevious() {
    var before = readChoice();
    var val = {};
    if (before) {
      for (var key in before) {
        if (key !== 'v' && key !== 'data') { val[key] = before[key]; }
      }
    }
    return val;
  }

  banner.addEventListener('click', function(evt) {
    var buttonEl = evt.target.closest('[data-consent]');
    if (!buttonEl) { return; }
    var action = buttonEl.getAttribute('data-consent');
    if (action === 'accept') { decide(all(true)); }
    if (action === 'refuse') { decide(all(false)); }
    if (action === 'customize') { showChoices(readChoice()); }
    if (action === 'save') {
      var val = takePrevious();
      var checkboxes = choices.querySelectorAll('input[data-category]');
      for (var i = 0; i < checkboxes.length; i++) {
        val[checkboxes[i].getAttribute('data-category')] = checkboxes[i].checked;
      }
      decide(val);
    }
  });

  // The "cookie preferences" link of the footer reopens the banner.
  document.addEventListener('click', function(evt) {
    if (evt.target.closest('.link-preferences')) { openIt(true); }
  });

  var saved = readChoice();
  var toAsk = saved === null;
  if (saved !== null) {
    for (var i = 0; i < categories.length; i++) {
      if (saved[categories[i]] === undefined) { toAsk = true; }
    }
  }
  if (saved !== null) { applyIt(saved); }
  if (toAsk) { openIt(false); }
});
