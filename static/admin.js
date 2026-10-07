/* ---------------------------------------------------------------------------
   admin.js - all the JavaScript of the administration area.

   Before this file the same functions (image overlay, paste from Word, image
   and video upload, YouTube embedding, toolbar tooltips) existed twice: once
   in the article editor and once in the settings page. They are unified here,
   so a fix lands in one place.

   Nothing in this file is translated at build time. Every visible string comes
   from window.PB_I18N, which the templates inject with json.dumps: an Italian
   apostrophe ("un'immagine") can therefore never break the JavaScript syntax.

   The page-specific values (article content, card contents, the CSRF token)
   arrive the same way, through window.PB_PAGE and window.PB_CSRF.
   --------------------------------------------------------------------------- */

/* --- Shared state and small helpers -------------------------------------- */

// The editor the media buttons act on. Each page sets it during its own init:
// the article editor sets its main Quill, the settings page sets the homepage
// introduction editor. This is what lets one set of upload functions serve
// both pages.
var PB_MAIN_QUILL = null;

// Returns a translated string, or the key itself if it is missing (so a
// forgotten key is visible during development instead of printing "undefined").
function t(chiave) {
  if (window.PB_I18N && window.PB_I18N[chiave] !== undefined) {
    return window.PB_I18N[chiave];
  }
  return chiave;
}

// Returns a page value injected by the template.
function pbPage(chiave, valorePredefinito) {
  if (window.PB_PAGE && window.PB_PAGE[chiave] !== undefined) {
    return window.PB_PAGE[chiave];
  }
  return valorePredefinito;
}

// Every state-changing request goes through here, so the CSRF token is never
// forgotten: the server rejects a POST that arrives without it.
function pbFetch(url, opzioni) {
  if (!opzioni) {
    opzioni = {};
  }
  if (!opzioni.headers) {
    opzioni.headers = {};
  }
  opzioni.headers['X-CSRF-Token'] = window.PB_CSRF || '';
  return fetch(url, opzioni);
}

// Shorthand for the common case: a POST with a JSON body.
function pbPostJson(url, dati) {
  return pbFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dati)
  }).then(function(r) { return r.json(); });
}

// Writes a message in a status element, if that element exists on the page.
function pbStatus(idElemento, testo) {
  var elemento = document.getElementById(idElemento);
  if (elemento) {
    elemento.textContent = testo;
  }
}

/* --- Feedback: toasts, confirmation modal, busy buttons ------------------- */

// Shows a Bootstrap toast. It replaces alert(), which blocks the page, steals
// the focus and cannot say whether something went well or badly.
// kind is a Bootstrap colour: success, danger, warning or info.
function pbToast(messaggio, kind) {
  var contenitore = document.getElementById('pb-toasts');
  if (!contenitore || !window.bootstrap) {
    // Without Bootstrap we still have to tell the author something.
    alert(messaggio);
    return;
  }
  if (!kind) { kind = 'success'; }

  var toast = document.createElement('div');
  toast.className = 'toast align-items-center text-bg-' + kind + ' border-0';
  toast.setAttribute('role', 'status');
  toast.setAttribute('aria-live', 'polite');
  toast.setAttribute('aria-atomic', 'true');

  var riga = document.createElement('div');
  riga.className = 'd-flex';
  var corpo = document.createElement('div');
  corpo.className = 'toast-body';
  // textContent, never innerHTML: a message can carry a server error, and an
  // error can carry anything.
  corpo.textContent = messaggio;
  var chiudi = document.createElement('button');
  chiudi.type = 'button';
  chiudi.className = 'btn-close btn-close-white me-2 m-auto';
  chiudi.setAttribute('data-bs-dismiss', 'toast');
  chiudi.setAttribute('aria-label', t('admin_chiudi'));
  riga.appendChild(corpo);
  riga.appendChild(chiudi);
  toast.appendChild(riga);
  contenitore.appendChild(toast);

  var delay = 4000;
  if (kind === 'danger' || kind === 'warning') { delay = 8000; }
  var istanza = new bootstrap.Toast(toast, { delay: delay });
  toast.addEventListener('hidden.bs.toast', function() { toast.remove(); });
  istanza.show();
}

// Asks the author to confirm a destructive or overwriting action, using the
// Bootstrap modal in the layout instead of the browser's confirm(), which
// cannot be styled and gives no room to explain the consequence.
function pbConfirm(titolo, corpo, etichettaConferma, kind, quandoConfermato) {
  var finestra = document.getElementById('pb-confirm');
  if (!finestra || !window.bootstrap) {
    if (confirm(titolo + '\n\n' + corpo)) { quandoConfermato(); }
    return;
  }
  document.getElementById('pb-confirm-title').textContent = titolo;
  document.getElementById('pb-confirm-body').textContent = corpo;

  var vecchio = document.getElementById('pb-confirm-ok');
  // Replacing the button drops every listener a previous call attached, so
  // confirming twice cannot fire the first action again.
  var conferma = vecchio.cloneNode(false);
  conferma.textContent = etichettaConferma;
  // The buttons of the shared family: a deleting action is red.
  conferma.className = 'pulsante pulsante-primario' + (kind === 'danger' ? ' pulsante-pericolo' : '');
  vecchio.parentNode.replaceChild(conferma, vecchio);

  var istanza = bootstrap.Modal.getOrCreateInstance(finestra);
  conferma.addEventListener('click', function() {
    istanza.hide();
    quandoConfermato();
  });
  istanza.show();
}

// Puts a button in its waiting state and back. The label is left alone: only
// a spinner appears in front of it, so the button keeps its width and the
// author is not shown a different word every time something is slow.
function pbBusy(pulsante, occupato) {
  if (!pulsante) { return; }
  if (occupato) {
    if (pulsante.querySelector('.pb-spinner')) { return; }
    var spinner = document.createElement('span');
    spinner.className = 'pb-spinner';
    spinner.setAttribute('aria-hidden', 'true');
    pulsante.insertBefore(spinner, pulsante.firstChild);
    pulsante.disabled = true;
    pulsante.setAttribute('aria-busy', 'true');
  } else {
    var esistente = pulsante.querySelector('.pb-spinner');
    if (esistente) { esistente.remove(); }
    pulsante.disabled = false;
    pulsante.removeAttribute('aria-busy');
  }
}

/* --- Quill: image overlay ------------------------------------------------ */

// Keeps the resize box glued to its image.
//
// BUG FIXED: blot-formatter computes the box position only once, at the
// moment you select the image. If you then change the alignment from the
// toolbar ("centre", for example), the image moves but the box stays where it
// was, on the left, with the old size: it looks "detached" from the image.
// Here we recompute it every time something in the editor moves.
function attachImageOverlay(istanzaQuill) {
  if (!istanzaQuill) { return; }
  var formattatore = istanzaQuill.getModule('blotFormatter');
  if (!formattatore) { return; }

  function reposition() {
    // No image selected: there is nothing to reposition.
    if (!formattatore.currentSpec) { return; }
    // When the paragraph formatting changes, Quill may recreate the
    // image from scratch: the box would point to an element that is no
    // longer in the page. In that case we hide it.
    if (typeof formattatore.currentSpec.getTargetElement === 'function') {
      var bersaglio = formattatore.currentSpec.getTargetElement();
      if (bersaglio && !document.contains(bersaglio)) {
        if (typeof formattatore.hide === 'function') { formattatore.hide(); }
        return;
      }
    }
    // update() recomputes both the box and the corner handles.
    // If the library version does not expose it, we fall back to
    // repositioning the box alone.
    if (typeof formattatore.update === 'function') {
      formattatore.update();
    } else if (typeof formattatore.repositionOverlay === 'function') {
      formattatore.repositionOverlay();
    }
  }

  // We wait for the browser to finish repainting: before the repaint
  // we would still read the old position of the image.
  function repositionAfterPaint() {
    window.requestAnimationFrame(reposition);
  }

  // 1) Any text or format change, including the "centre" button
  //    of the toolbar.
  istanzaQuill.on('editor-change', repositionAfterPaint);

  // 2) Style or class changes inside the editor: these are what really
  //    move the image (Quill puts the ql-align-center class on the
  //    paragraph, and resizing writes width/height on the image).
  //    The box lives outside .ql-editor, so it does not self-trigger.
  if (window.MutationObserver) {
    var osservatore = new MutationObserver(repositionAfterPaint);
    osservatore.observe(istanzaQuill.root, {
      attributes: true, childList: true, subtree: true,
      attributeFilter: ['style', 'class', 'width', 'height', 'align']
    });
  }

  // 3) A freshly inserted image changes size when it finishes
  //    loading, i.e. after the box has already been drawn.
  istanzaQuill.root.addEventListener('load', repositionAfterPaint, true);

  // 4) Window resizing and editor scrolling.
  window.addEventListener('resize', repositionAfterPaint);
  istanzaQuill.root.addEventListener('scroll', repositionAfterPaint);
}

/* --- Quill: recovering images pasted from Word ---------------------------- */

// Recovers images embedded in a pasted Word/Office document.
//
// THE PROBLEM: when you copy text and images from Word (or similar word
// processors) and paste them into the browser, the clipboard's HTML
// contains <img> tags whose "src" points to a local path on the sender's
// own computer (something like "file:///C:/Users/.../media/image1.png")
// or an internal reference the browser cannot resolve. The browser simply
// cannot load an image from another computer's disk, so the text pastes
// fine but every image silently fails and disappears. This is a limitation
// of the clipboard itself, not something specific to this editor: the same
// thing happens in most web-based rich text editors.
//
// THE FIX: alongside that broken HTML, the operating system also puts the
// actual image data in the clipboard as separate, real image items (this
// is how "paste image" works everywhere). We read those real images,
// upload each one to the server, and splice the resulting URLs into the
// pasted HTML in place of the broken ones.
//
// BUG FIXED: we used to pair the n-th clipboard image with the n-th <img>
// tag purely by position, in the order both lists happened to come in.
// That breaks when the source document mixes text and images: some
// applications place, as the clipboard's image item for that portion, a
// flattened screenshot of the text AND the image together, instead of the
// isolated picture the <img> tag actually points to. Paired by position,
// that screenshot landed inside the first <img> tag, so the text before
// the first picture visually turned into a single image, while the later
// pictures (each with a clean clipboard item of their own) still came out
// fine. The fix: whenever a pasted <img> tag declares its width/height
// (Word and Google Docs normally write them), we only pair it with a
// clipboard image whose real pixel size matches. Only tags with no
// declared size, and only when the remaining tags and remaining images
// are equal in number, fall back to the old position-based pairing.
function handlePastedImages(istanzaQuill, statusElementId) {
  istanzaQuill.root.addEventListener('paste', function(evento) {
    if (!evento.clipboardData) { return; }

    var elementiImmagine = [];
    for (var i = 0; i < evento.clipboardData.items.length; i++) {
      var voce = evento.clipboardData.items[i];
      if (voce.type && voce.type.indexOf('image/') === 0) {
        elementiImmagine.push(voce);
      }
    }
    // No embedded images in this paste: let Quill handle it as usual
    // (plain text, or a paste that already has no images at all).
    if (elementiImmagine.length === 0) {
      // Some sources (Word on Windows, when you copy text together with a
      // picture) put in the clipboard only a broken local reference
      // ("file:///C:/Users/.../image1.png") and no actual image data at
      // all: a web page has no way to read a local file path for security
      // reasons, so there is nothing here to recover. We at least warn the
      // author instead of letting the picture disappear with no
      // explanation (a plain web page copy does not have this problem:
      // browsers normally embed the picture itself in that HTML).
      var statoAvviso = statusElementId ? document.getElementById(statusElementId) : null;
      if (statoAvviso && contieneImmagineNonRecuperabile(evento.clipboardData.getData('text/html'))) {
        statoAvviso.textContent = t('js_pasted_word_image_unavailable');
      }
      return;
    }

    var htmlIncollato = evento.clipboardData.getData('text/html');
    // No HTML at all: a single image was copied on its own (e.g. from
    // an image viewer), not part of a larger document paste. Quill's own
    // built-in image paste handling already covers that case.
    if (!htmlIncollato) { return; }

    // From here on we take full control of this paste.
    evento.preventDefault();
    evento.stopPropagation();

    var stato = null;
    if (statusElementId) {
      stato = document.getElementById(statusElementId);
    }
    if (stato) { stato.textContent = t('js_recovering_pasted_images'); }

    // The <img> tags found in the pasted HTML, in the order they appear,
    // together with the width/height they declare (if any). This is what
    // lets us pair each tag with the right clipboard image further down,
    // instead of just trusting the order they came in.
    var tagImmagine = [];
    var regexTagImg = /<img\b[^>]*>/gi;
    var trovato = regexTagImg.exec(htmlIncollato);
    while (trovato !== null) {
      tagImmagine.push({
        larghezza: leggiLarghezzaDichiarata(trovato[0]),
        altezza: leggiAltezzaDichiarata(trovato[0])
      });
      trovato = regexTagImg.exec(htmlIncollato);
    }

    // We upload every clipboard image and, in parallel, decode it locally
    // to read its real pixel size: we need that size to pair it safely
    // with the right <img> tag.
    var operazioni = [];
    for (var j = 0; j < elementiImmagine.length; j++) {
      var blobCorrente = elementiImmagine[j].getAsFile();
      operazioni.push(Promise.all([uploadImageBlob(blobCorrente), leggiDimensioneBlob(blobCorrente)]));
    }

    Promise.all(operazioni).then(function(risultati) {
      var immaginiCaricate = [];
      for (var k = 0; k < risultati.length; k++) {
        var dimensioneReale = risultati[k][1];
        immaginiCaricate.push({
          url: risultati[k][0],
          larghezza: dimensioneReale ? dimensioneReale.larghezza : null,
          altezza: dimensioneReale ? dimensioneReale.altezza : null,
          usata: false
        });
      }

      // 1) Tags with a declared size are paired only with a clipboard
      //    image whose real size matches (within a small tolerance for
      //    Word/Google Docs rounding). This is what stops a flattened
      //    text+image screenshot from being mistaken for a real picture.
      var assegnazioni = [];
      for (var t1 = 0; t1 < tagImmagine.length; t1++) {
        assegnazioni.push(null);
      }
      for (var t2 = 0; t2 < tagImmagine.length; t2++) {
        var tagCorrente = tagImmagine[t2];
        if (tagCorrente.larghezza === null || tagCorrente.altezza === null) { continue; }
        var indiceTrovato = trovaImmagineDiTagliaCorrispondente(tagCorrente, immaginiCaricate);
        if (indiceTrovato !== null) {
          assegnazioni[t2] = immaginiCaricate[indiceTrovato].url;
          immaginiCaricate[indiceTrovato].usata = true;
        }
      }

      // 2) Tags with no declared size cannot be verified: we fall back to
      //    pairing them in order with whatever images are still unused,
      //    but only if their counts match exactly. This keeps the old,
      //    simple behaviour for the common case (a plain paste with no
      //    size hints at all, where there is no ambiguity to resolve).
      var tagScoperti = [];
      for (var t3 = 0; t3 < tagImmagine.length; t3++) {
        if (assegnazioni[t3] === null) { tagScoperti.push(t3); }
      }
      var immaginiLibere = immaginiCaricate.filter(function(im) { return !im.usata; });
      if (tagScoperti.length === immaginiLibere.length) {
        for (var m = 0; m < tagScoperti.length; m++) {
          assegnazioni[tagScoperti[m]] = immaginiLibere[m].url;
        }
      }

      // We rebuild the HTML: each <img> tag with a safe pairing is
      // replaced with its uploaded URL; the others are dropped rather
      // than risking a wrong image ending up in their place.
      var indiceTag = 0;
      var htmlFinale = htmlIncollato.replace(/<img\b[^>]*>/gi, function() {
        var urlAssegnato = assegnazioni[indiceTag];
        indiceTag = indiceTag + 1;
        if (urlAssegnato === null || urlAssegnato === undefined) { return ''; }
        return '<img src="' + urlAssegnato + '">';
      });
      var posizione = istanzaQuill.getSelection(true) || { index: istanzaQuill.getLength() };
      istanzaQuill.clipboard.dangerouslyPasteHTML(posizione.index, htmlFinale);
      if (stato) {
        var riuscite = 0;
        for (var n = 0; n < assegnazioni.length; n++) {
          if (assegnazioni[n] !== null && assegnazioni[n] !== undefined) { riuscite = riuscite + 1; }
        }
        if (riuscite === tagImmagine.length) {
          stato.textContent = t('js_pasted_all_recovered').replace('{n}', riuscite);
        } else {
          stato.textContent = t('js_pasted_partial_recovered')
            .replace('{ok}', riuscite).replace('{tot}', tagImmagine.length);
        }
      }
    });
  }, true);  // capture phase: we need to run before Quill's own paste handler.
}

// Detects a pasted <img> tag whose src is not a real, loadable address.
// Word (and similar word processors) leave all sorts of placeholders in
// the clipboard HTML instead of a usable picture: a local file path
// ("file:///C:/Users/...", unreadable by a web page for security reasons),
// or a bare "//:0" (the placeholder Word writes for some pictures and
// shapes when the clipboard does not carry a matching bitmap for them).
// Rather than list every placeholder we have seen, we accept only the
// addresses that are actually loadable in a browser (http/https/data, or
// a path relative to this site, like the "/media/..." PyBlog itself
// generates) and treat anything else as unrecoverable.
function contieneImmagineNonRecuperabile(html) {
  if (!html) { return false; }
  var regexTag = /<img\b[^>]*>/gi;
  var tag = regexTag.exec(html);
  while (tag !== null) {
    var corrispondenzaSrc = tag[0].match(/\bsrc\s*=\s*["']([^"']*)["']/i);
    var indirizzo = corrispondenzaSrc ? corrispondenzaSrc[1] : '';
    if (!/^(https?:|data:|\/)/i.test(indirizzo)) {
      return true;
    }
    tag = regexTag.exec(html);
  }
  return false;
}

// Reads the width a pasted <img> tag declares, either as a plain HTML
// attribute (width="200") or as an inline style (style="width:200px").
// Returns null when the tag declares no width at all.
function leggiLarghezzaDichiarata(tag) {
  var corrispondenzaAttributo = tag.match(/\bwidth\s*=\s*"(\d+)/i);
  if (corrispondenzaAttributo) { return parseInt(corrispondenzaAttributo[1], 10); }
  var corrispondenzaStile = tag.match(/width\s*:\s*(\d+)px/i);
  if (corrispondenzaStile) { return parseInt(corrispondenzaStile[1], 10); }
  return null;
}

// Same as leggiLarghezzaDichiarata, for the height.
function leggiAltezzaDichiarata(tag) {
  var corrispondenzaAttributo = tag.match(/\bheight\s*=\s*"(\d+)/i);
  if (corrispondenzaAttributo) { return parseInt(corrispondenzaAttributo[1], 10); }
  var corrispondenzaStile = tag.match(/height\s*:\s*(\d+)px/i);
  if (corrispondenzaStile) { return parseInt(corrispondenzaStile[1], 10); }
  return null;
}

// Decodes an image blob locally to read its real pixel size. Resolves to
// null if the blob turns out not to be a valid image.
function leggiDimensioneBlob(blob) {
  return new Promise(function(resolve) {
    var indirizzoTemporaneo = URL.createObjectURL(blob);
    var immagine = new Image();
    immagine.onload = function() {
      URL.revokeObjectURL(indirizzoTemporaneo);
      resolve({ larghezza: immagine.naturalWidth, altezza: immagine.naturalHeight });
    };
    immagine.onerror = function() {
      URL.revokeObjectURL(indirizzoTemporaneo);
      resolve(null);
    };
    immagine.src = indirizzoTemporaneo;
  });
}

// Looks, among the uploaded images not yet paired, for one whose real
// pixel size matches the size declared by the pasted tag (with a small
// tolerance for Word/Google Docs rounding). Returns its index in
// immaginiCaricate, or null when none matches closely enough.
function trovaImmagineDiTagliaCorrispondente(tagCorrente, immaginiCaricate) {
  var tolleranza = 3; // pixel di margine per arrotondamenti/DPI
  for (var i = 0; i < immaginiCaricate.length; i++) {
    var immagine = immaginiCaricate[i];
    if (immagine.usata) { continue; }
    if (immagine.larghezza === null) { continue; }
    var differenzaLarghezza = Math.abs(immagine.larghezza - tagCorrente.larghezza);
    var differenzaAltezza = Math.abs(immagine.altezza - tagCorrente.altezza);
    if (differenzaLarghezza <= tolleranza && differenzaAltezza <= tolleranza) {
      return i;
    }
  }
  return null;
}

// Uploads a single pasted image blob to the server, reusing the same
// /upload endpoint used by the "upload image" button. Returns a promise
// that resolves to the file URL, or null if the upload failed (so one
// broken image does not stop the others from being recovered).
function uploadImageBlob(blob) {
  var datiForm = new FormData();
  var estensione = 'png';
  if (blob.type && blob.type.split('/')[1]) {
    estensione = blob.type.split('/')[1];
  }
  datiForm.append('video', blob, 'pasted-image.' + estensione);
  return pbFetch('/upload', { method: 'POST', body: datiForm })
    .then(function(risposta) { return risposta.json(); })
    .then(function(risultato) {
      if (risultato.ok) {
        return risultato.url;
      }
      return null;
    })
    .catch(function() { return null; });
}

/* --- Quill: toolbar tooltips --------------------------------------------- */

// Adds an explanatory tooltip to every button of the Quill toolbar. Quill's
// own icons say nothing to a new author: hovering a button now shows a small
// bubble explaining what it does.
//
// The bubble is pure CSS (a data-tooltip attribute plus a ::after
// pseudo-element): no library, and it appears instantly, unlike the browser's
// native title, which waits about a second.
//
// The map of CSS selector -> translated label arrives in PB_I18N.tooltips.
function applyToolbarTooltips() {
  var mappa = {};
  if (window.PB_I18N && window.PB_I18N.tooltips) {
    mappa = window.PB_I18N.tooltips;
  }
  var barre = document.querySelectorAll('.ql-toolbar');
  for (var i = 0; i < barre.length; i++) {
    for (var selettore in mappa) {
      var elementi = barre[i].querySelectorAll(selettore);
      for (var j = 0; j < elementi.length; j++) {
        // The dropdowns (font, size, heading...) are wrapped in a
        // .ql-picker span: we put the tooltip on the wrapper, otherwise
        // it would follow the open list of options around.
        elementi[j].setAttribute('data-tooltip', mappa[selettore]);
      }
    }
  }
}

/* --- Media: YouTube, images, videos --------------------------------------- */

// A YouTube identifier is a short opaque string. Anything else is refused:
// the id goes straight into an iframe src, so a value carrying quotes or a
// path of its own must never reach the page.
var YOUTUBE_ID_PATTERN = /^[A-Za-z0-9_-]{6,20}$/;

// Extracts the video identifier from a YouTube link.
// It works with the youtube.com/watch?v=ID, youtu.be/ID and /embed/ID forms.
// Returns an empty string when the link is not recognised OR when what was
// extracted does not look like a real identifier.
function extractYoutubeId(url) {
  var idVideo = '';
  if (url.indexOf('youtu.be/') !== -1) {
    idVideo = url.split('youtu.be/')[1];
  } else if (url.indexOf('watch?v=') !== -1) {
    idVideo = url.split('watch?v=')[1];
  } else if (url.indexOf('/embed/') !== -1) {
    idVideo = url.split('/embed/')[1];
  }
  if (!idVideo) {
    return '';
  }
  // Removes any extra parameters after the ID (e.g. &t=10s).
  var posAmp = idVideo.indexOf('&');
  if (posAmp !== -1) {
    idVideo = idVideo.substring(0, posAmp);
  }
  var posQ = idVideo.indexOf('?');
  if (posQ !== -1) {
    idVideo = idVideo.substring(0, posQ);
  }
  var posSlash = idVideo.indexOf('/');
  if (posSlash !== -1) {
    idVideo = idVideo.substring(0, posSlash);
  }
  idVideo = idVideo.trim();
  if (YOUTUBE_ID_PATTERN.test(idVideo) === false) {
    return '';
  }
  return idVideo;
}

// Asks for the link and inserts the YouTube video into the main editor.
function insertYoutube() {
  if (!PB_MAIN_QUILL) { return; }
  var url = prompt(t('js_prompt_youtube_link'));
  if (url === null) { return; }
  if (url === '') { return; }
  var idVideo = extractYoutubeId(url);
  if (idVideo === '') {
    alert(t('js_youtube_not_recognized'));
    return;
  }
  var codice = '<div class="video-youtube">';
  codice = codice + '<iframe src="https://www.youtube.com/embed/' + idVideo + '"';
  codice = codice + ' allowfullscreen></iframe></div><p><br></p>';
  var posizione = PB_MAIN_QUILL.getSelection(true);
  PB_MAIN_QUILL.clipboard.dangerouslyPasteHTML(posizione.index, codice);
}

// Refuses a file that is over the limit before a single byte is uploaded.
//
// The server refuses it too, but it does so by answering and closing the
// connection while the browser is still sending: the author would see a
// network error rather than a reason. Checking here turns that into a
// sentence that says what the limit is.
function fileFitsLimit(file, limiteMb) {
  if (file.size <= limiteMb * 1024 * 1024) {
    return true;
  }
  pbToast(t('err_file_too_large').replace('{n}', String(limiteMb)), 'danger');
  return false;
}

// Uploads the file chosen in a file input and resolves to its URL, or to
// null when it was refused or the upload failed (the reason is shown to the
// author here, so the caller only has to check for null).
//
// This is the one place that talks to /upload: the buttons that put an image
// in the article, the one that puts a video in it and the one that sets the
// cover all go through it.
// Downscales an image in the browser before it is uploaded.
//
// This is where the JPEGs are dealt with. The server can read and write a
// PNG with the standard library alone, but not a JPEG: decoding one means an
// inverse DCT, which this project cannot carry. The browser already has a
// complete image pipeline, so it does the work here, at native speed and
// with proper smoothing, and what reaches the server is already the right
// size.
//
// Three formats are deliberately left alone. An SVG would be rasterised and
// stop being a drawing; an animated GIF would come back as one frame; a WebP
// may carry transparency that a re-encode would drop. None of those is a
// trade the author asked for.
function resizeImageBeforeUpload(file, latoMassimo) {
  var rimpicciolibili = ['image/png', 'image/jpeg'];
  if (!latoMassimo || rimpicciolibili.indexOf(file.type) === -1) {
    return Promise.resolve(file);
  }

  return new Promise(function(risolvi) {
    var indirizzo = URL.createObjectURL(file);
    var immagine = new Image();

    immagine.onload = function() {
      URL.revokeObjectURL(indirizzo);
      var larghezza = immagine.naturalWidth;
      var altezza = immagine.naturalHeight;
      var lato = Math.max(larghezza, altezza);
      // The same threshold the server uses: trimming an image by a little is
      // not worth re-encoding it.
      if (lato <= latoMassimo * 1.25) { risolvi(file); return; }

      var scala = latoMassimo / lato;
      var tela = document.createElement('canvas');
      tela.width = Math.round(larghezza * scala);
      tela.height = Math.round(altezza * scala);
      var contesto = tela.getContext('2d');
      contesto.imageSmoothingEnabled = true;
      contesto.imageSmoothingQuality = 'high';
      contesto.drawImage(immagine, 0, 0, tela.width, tela.height);

      tela.toBlob(function(blocco) {
        // A re-encode that came out bigger, or a browser that refused: keep
        // what the author chose. The file name is unchanged, so it still
        // matches the type the server checks it against.
        if (!blocco || blocco.size >= file.size) { risolvi(file); return; }
        var ridotto = new File([blocco], file.name, { type: file.type });
        pbToast(t('js_image_resized_local')
                  .replace('{w}', tela.width).replace('{h}', tela.height), 'info');
        risolvi(ridotto);
      }, file.type, 0.85);
    };

    immagine.onerror = function() {
      URL.revokeObjectURL(indirizzo);
      risolvi(file);
    };
    immagine.src = indirizzo;
  });
}

function uploadChosenFile(idCampoFile, limiteMb, idStato, messaggioInizio) {
  var campoFile = document.getElementById(idCampoFile);
  if (!campoFile || campoFile.files.length === 0) {
    return Promise.resolve(null);
  }
  var scelto = campoFile.files[0];
  // Clearing the input now lets the same file be chosen again later: without
  // this the change event would not fire a second time. FormData already
  // holds the file, so the upload is unaffected.
  campoFile.value = '';

  if (!fileFitsLimit(scelto, limiteMb)) {
    return Promise.resolve(null);
  }

  pbStatus(idStato, messaggioInizio);
  return resizeImageBeforeUpload(scelto, pbPage('max_image_width', 1600))
    .then(function(file) { return inviaFile(file, idStato); });
}

function inviaFile(file, idStato) {
  var datiForm = new FormData();
  datiForm.append('video', file);

  return pbFetch('/upload', { method: 'POST', body: datiForm })
    .then(function(risposta) { return risposta.json(); })
    .then(function(risultato) {
      if (risultato.ok === true) {
        // The server says what it did with the file: shrank it, dropped the
        // metadata, or left it alone because it could not.
        if (risultato.note) { pbToast(risultato.note, 'info'); }
        return risultato.url;
      }
      pbStatus(idStato, '');
      pbToast(t('js_error_prefix') + risultato.error, 'danger');
      return null;
    })
    .catch(function() {
      pbStatus(idStato, '');
      pbToast(t('js_upload_error'), 'danger');
      return null;
    });
}

// Uploads a file and inserts the snippet built by costruisciCodice() at the
// cursor. Used by the image and video buttons, on both admin pages.
function uploadMediaFile(idCampoFile, limiteMb, messaggioInizio, messaggioFine,
                         costruisciCodice) {
  if (!PB_MAIN_QUILL) { return; }
  uploadChosenFile(idCampoFile, limiteMb, 'upload-status', messaggioInizio)
    .then(function(url) {
      if (url === null) { return; }
      var posizione = PB_MAIN_QUILL.getSelection(true);
      PB_MAIN_QUILL.clipboard.dangerouslyPasteHTML(posizione.index, costruisciCodice(url));
      pbStatus('upload-status', messaggioFine);
    });
}

/* --- The cover image ------------------------------------------------------ */

// Uploads a file and puts its address in the cover field.
//
// The field used to be a bare text box: to give an article a cover you had to
// upload the image into the body, copy the address out of the HTML, paste it
// here and then delete the image from the body again. This does that in one
// click, through the same endpoint and the same checks.
function uploadCoverImage() {
  uploadChosenFile('file-cover', pbPage('max_image_mb', 10), 'cover-status',
                   t('js_uploading_image'))
    .then(function(url) {
      if (url === null) { return; }
      document.getElementById('image').value = url;
      updateCoverPreview();
      markEditorDirty();
      pbStatus('cover-status', t('js_image_uploaded'));
    });
}

// Shows the cover as a thumbnail, cropped the way the homepage crops it, so
// the framing is not a surprise once the article is published. Called when
// the field changes, however it changed.
function updateCoverPreview() {
  var campo = document.getElementById('image');
  var anteprima = document.getElementById('cover-preview');
  var rimuovi = document.getElementById('btn-rimuovi-cover');
  if (!campo || !anteprima) { return; }

  var indirizzo = campo.value.trim();
  if (indirizzo === '') {
    anteprima.removeAttribute('src');
    anteprima.hidden = true;
    if (rimuovi) { rimuovi.hidden = true; }
    return;
  }
  anteprima.src = indirizzo;
  anteprima.alt = document.getElementById('title').value;
  anteprima.hidden = false;
  if (rimuovi) { rimuovi.hidden = false; }
}

// Clears the cover. The file itself stays in the media folder: another
// article may be using it, and deleting an upload from here would be a
// surprise the author did not ask for.
function removeCoverImage() {
  document.getElementById('image').value = '';
  updateCoverPreview();
  markEditorDirty();
  pbStatus('cover-status', '');
}

// Uploads a video file to the server and inserts it into the editor.
function uploadVideo() {
  uploadMediaFile('file-video', pbPage('max_video_mb', 100),
    t('js_uploading'), t('js_video_uploaded'),
    function(url) {
      return '<video controls src="' + url + '"></video><p><br></p>';
    });
}

// Uploads an image (PNG, JPEG or SVG) to the server and inserts it.
function uploadImage() {
  uploadMediaFile('file-image', pbPage('max_image_mb', 10),
    t('js_uploading_image'), t('js_image_uploaded'),
    function(url) {
      return '<img src="' + url + '"><p><br></p>';
    });
}

/* --- Importing a Word document -------------------------------------------- */

// Sends the chosen .docx to the server, which converts it, and drops the
// result into the title field and the editor.
//
// Nothing is saved: the conversion is lossy by nature (Word has features a
// blog article does not), so the author has to look at the result before it
// becomes an article. If the editor already holds text, we ask first.
function importDocx() {
  var campoFile = document.getElementById('file-docx');
  if (!campoFile || campoFile.files.length === 0) { return; }
  var file = campoFile.files[0];
  // The same file can be chosen again after a cancelled confirmation.
  campoFile.value = '';

  if (file.name.toLowerCase().endsWith('.docx') === false) {
    pbToast(t('js_docx_wrong_extension'), 'danger');
    return;
  }
  if (!fileFitsLimit(file, pbPage('max_docx_mb', 30))) { return; }

  var vuoto = true;
  if (quill && quill.getText().trim() !== '') { vuoto = false; }

  if (vuoto) {
    sendDocx(file);
    return;
  }
  pbConfirm(t('js_docx_overwrite_title'), t('js_docx_overwrite_body'),
            t('js_docx_overwrite_confirm'), 'warning',
            function() { sendDocx(file); });
}

// Uploads the document and applies what comes back.
function sendDocx(file) {
  var pulsante = document.getElementById('btn-importa-docx');
  var datiForm = new FormData();
  datiForm.append('docx', file, file.name);

  pbBusy(pulsante, true);
  pbStatus('docx-status', t('js_docx_importing'));

  pbFetch('/import-docx', { method: 'POST', body: datiForm })
    .then(function(risposta) { return risposta.json(); })
    .then(function(risultato) {
      pbBusy(pulsante, false);
      if (risultato.ok !== true) {
        pbStatus('docx-status', '');
        pbToast(risultato.error, 'danger');
        return;
      }
      applyImportedDocx(risultato);
    })
    .catch(function() {
      pbBusy(pulsante, false);
      pbStatus('docx-status', '');
      pbToast(t('js_docx_net_error'), 'danger');
    });
}

// Fills the form with the converted document and reports what was dropped.
function applyImportedDocx(risultato) {
  var campoTitolo = document.getElementById('title');
  // An existing title is kept: the author may have chosen it deliberately,
  // and the one Word suggests is only the first heading of the file.
  if (campoTitolo.value.trim() === '') {
    campoTitolo.value = risultato.title;
  }
  quill.root.innerHTML = risultato.content;
  // Writing innerHTML puts the HTML in the page but leaves Quill's own
  // document model stale. update() makes it scan the new DOM now, so the
  // imported tables are recognised as rawHTML blots immediately instead of
  // at the next keystroke - and so an undo cannot rewind past the import.
  quill.update();
  markEditorDirty();
  updatePreview();
  refreshTableHints();

  // The subtitle of the document is a ready-made description. It only fills
  // an empty field: a description the author already wrote stays.
  var campoDescrizione = document.getElementById('description');
  if (risultato.subtitle && campoDescrizione && campoDescrizione.value.trim() === '') {
    campoDescrizione.value = risultato.subtitle;
    updateDescriptionCounter();
  }

  pbStatus('docx-status', '');
  pbToast(t('js_docx_imported'), 'success');

  // The warnings go in one message, one per line: each names a specific
  // image, link or table, and an author needs to know which - but a pile of
  // separate toasts covered the editor and disappeared one by one.
  if (risultato.warnings && risultato.warnings.length > 0) {
    pbToast(t('js_docx_warnings_title') + '\n\u2022 ' + risultato.warnings.join('\n\u2022 '),
            'warning');
  }
}

/* --- Tables: pasting from Word, and the small table editor ---------------- */

// The cell content is rebuilt as an HTML string, so text coming from the
// document must not be able to inject tags of its own.
function escapeCellText(testo) {
  return testo
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Finds the table a row or cell really belongs to. Word nests tables inside
// tables, and querySelectorAll reaches into the nested ones too: without this
// check a nested data table would be flattened into its wrapper.
function closestTable(nodo) {
  var corrente = nodo.parentNode;
  while (corrente) {
    if (corrente.tagName === 'TABLE') {
      return corrente;
    }
    corrente = corrente.parentNode;
  }
  return null;
}

// The <tr> elements belonging to this table only, skipping nested tables.
function ownRows(tabella) {
  var tutte = tabella.querySelectorAll('tr');
  var proprie = [];
  for (var i = 0; i < tutte.length; i++) {
    if (closestTable(tutte[i]) === tabella) {
      proprie.push(tutte[i]);
    }
  }
  return proprie;
}

// The cells belonging to this table only, skipping nested tables.
function ownCells(riga, tabella) {
  var tutte = riga.querySelectorAll('td, th');
  var proprie = [];
  for (var i = 0; i < tutte.length; i++) {
    if (closestTable(tutte[i]) === tabella) {
      proprie.push(tutte[i]);
    }
  }
  return proprie;
}

// Tells whether a pasted table is Word's page furniture rather than data.
// The rules are deliberately simple and conservative: when in doubt we treat
// it as a data table, because unwrapping a real grid loses more than keeping
// a layout wrapper would.
function isLayoutTable(tabella) {
  // A table wrapping another table is a layout wrapper: the inner one is
  // the real grid and will be matched on its own.
  if (tabella.querySelector('table')) {
    return true;
  }
  var righe = ownRows(tabella);
  // A single row is a strip of blocks placed side by side, not a grid:
  // this is the classic Word "text next to image" layout.
  if (righe.length <= 1) {
    return true;
  }
  // A single column is a stack of blocks, not a grid.
  var maxCelle = 0;
  for (var i = 0; i < righe.length; i++) {
    var quante = ownCells(righe[i], tabella).length;
    if (quante > maxCelle) {
      maxCelle = quante;
    }
  }
  if (maxCelle <= 1) {
    return true;
  }
  return false;
}

// Keeps the text AND the images of a cell, dropping Word's styling.
// The old version used innerText, which silently deleted every image
// inside a table cell.
function buildCleanCell(cella) {
  var pezzi = [];
  collectCellContent(cella, pezzi);
  return pezzi.join('').trim();
}

function collectCellContent(nodo, pezzi) {
  for (var i = 0; i < nodo.childNodes.length; i++) {
    var figlio = nodo.childNodes[i];
    if (figlio.nodeType === 3) {
      pezzi.push(escapeCellText(figlio.textContent.replace(/\s+/g, ' ')));
    } else if (figlio.nodeType === 1) {
      if (figlio.tagName === 'IMG') {
        // Only the src survives: Word's width/height/styles are dropped.
        var indirizzo = figlio.getAttribute('src');
        if (indirizzo) {
          pezzi.push('<img src="' + escapeCellText(indirizzo) + '">');
        }
      } else if (figlio.tagName === 'BR') {
        pezzi.push(' ');
      } else {
        collectCellContent(figlio, pezzi);
      }
    }
  }
}

// The merge of a cell, as attributes to write back: Word's merged cells
// arrive as colspan and rowspan, and dropping them shifts every cell after.
function mergeAttributes(cella) {
  var risultato = '';
  var colonne = parseInt(cella.getAttribute('colspan') || '1', 10);
  var righe = parseInt(cella.getAttribute('rowspan') || '1', 10);
  if (colonne > 1) { risultato = risultato + ' colspan="' + colonne + '"'; }
  if (righe > 1) { risultato = risultato + ' rowspan="' + righe + '"'; }
  return risultato;
}

// Turns a Word <table> node into simple, clean HTML, keeping the images.
function buildCleanTable(tabella) {
  var risultato = '<table class="article-table"><tbody>';
  var righe = ownRows(tabella);
  for (var i = 0; i < righe.length; i++) {
    risultato = risultato + '<tr>';
    var celle = ownCells(righe[i], tabella);
    for (var j = 0; j < celle.length; j++) {
      var contenuto = buildCleanCell(celle[j]);
      // We treat the first row as the header.
      if (i === 0) {
        risultato = risultato + '<th' + mergeAttributes(celle[j]) + '>' + contenuto + '</th>';
      } else {
        risultato = risultato + '<td' + mergeAttributes(celle[j]) + '>' + contenuto + '</td>';
      }
    }
    risultato = risultato + '</tr>';
  }
  risultato = risultato + '</tbody></table>';
  return risultato;
}

// Registers the "rawHTML" blot and the clipboard matcher on an editor.
//
// Lets Quill insert raw HTML (our table) into the content. It must be a
// BlockEmbed: Quill actively manages the children of ordinary blocks and,
// on the first edit, its normalisation would strip the <table> markup out
// (and the save would silently lose the table). An embed is opaque to that
// process, at the cost of not being editable cell by cell inside Quill.
// True in-editor table editing would require a dedicated table module.
function registerRawHtmlBlot() {
  var BlockEmbed = Quill.import('blots/block/embed');
  var RawHtmlBlot = class extends BlockEmbed {
    static create(valore) {
      var nodo = super.create();
      nodo.innerHTML = valore;
      // The browser must not let the user type inside the embed: Quill's
      // document model would not see those changes and could revert them.
      // Editing goes through the small table editor instead (click on it).
      nodo.setAttribute('contenteditable', 'false');
      return nodo;
    }
    static value(nodo) {
      return nodo.innerHTML;
    }
  };
  RawHtmlBlot.blotName = 'rawHTML';
  RawHtmlBlot.tagName = 'div';
  RawHtmlBlot.className = 'raw-html-block';
  Quill.register(RawHtmlBlot);
}

// When you paste from Word, the HTML contains <table> with many proprietary
// styles. Word also uses tables purely to lay out a page: a block of text and
// an image side by side is, on the clipboard, a <table>. So a pasted <table>
// means one of two very different things, and we must tell them apart:
//
//   - a LAYOUT table (Word's page furniture): we unwrap it and let its
//     contents through as ordinary text and images, so they stay editable;
//   - a DATA table (a real grid the author wants): we rebuild it clean,
//     discarding Word's messy styles but keeping rows, cells and images.
//
// Previously EVERY pasted table became a single atomic block: that is why a
// mixed text+image selection from Word arrived as one non-editable object.
// Now only real data tables become a block (a Quill limitation: editing
// table cells in place would need a dedicated table module); to change a
// data table, delete it and paste it again, or edit the source document.
function attachTableSupport(istanzaQuill) {
  istanzaQuill.clipboard.addMatcher('TABLE', function(nodo, delta) {
    // A layout table is not a table at all, semantically. We return the delta
    // Quill already built from its children: text stays text, images stay
    // images, and everything remains editable.
    if (isLayoutTable(nodo)) {
      return delta;
    }
    // A real data table: rebuild it clean and keep it as a single block.
    var Delta = Quill.import('delta');
    var htmlTabella = buildCleanTable(nodo);
    return new Delta().insert({ rawHTML: htmlTabella });
  });

  // A single click SELECTS the table, a double click opens the cell editor.
  //
  // It used to be one click to edit, which meant a table could never simply
  // be selected: the modal always got there first, and with no selection the
  // toolbar had nothing to act on. Selecting first is also what makes the
  // block buttons (alignment, indent) work, because Quill applies those to
  // whatever the selection covers.
  istanzaQuill.root.addEventListener('click', function(evento) {
    var blocco = evento.target.closest('.raw-html-block');
    if (!blocco) { return; }
    selectTableBlock(istanzaQuill, blocco);
  });

  istanzaQuill.root.addEventListener('dblclick', function(evento) {
    var blocco = evento.target.closest('.raw-html-block');
    if (!blocco) { return; }
    var tabella = blocco.querySelector('table');
    if (!tabella) { return; }
    openTableEditor(istanzaQuill, blocco, tabella);
  });

  // The selected table is outlined, so it is obvious what the toolbar will
  // act on. Quill draws no selection of its own around a block embed.
  istanzaQuill.on('selection-change', function(range) {
    highlightSelectedTable(istanzaQuill, range);
  });

  istanzaQuill.on('editor-change', refreshTableHints);
  refreshTableHints();
}

// The table the caret is currently on, or null. The toolbar handlers read it
// to decide whether a button should act on a table or on ordinary text.
var tabellaSelezionata = null;

// Puts Quill's own selection on a table block.
//
// A block embed occupies exactly one position in the document, so selecting
// it means a range of length 1 at its index. Once Quill knows that, the
// block-level buttons work through their normal path and the toolbar shows
// the right state.
function selectTableBlock(istanzaQuill, blocco) {
  var blot = Quill.find(blocco);
  if (!blot) { return; }
  var indice = istanzaQuill.getIndex(blot);
  istanzaQuill.setSelection(indice, 1, 'user');
}

// Outlines the selected table and remembers it.
function highlightSelectedTable(istanzaQuill, range) {
  var blocchi = istanzaQuill.root.querySelectorAll('.raw-html-block');
  for (var i = 0; i < blocchi.length; i++) {
    blocchi[i].classList.remove('pb-tabella-selezionata');
  }
  tabellaSelezionata = null;
  if (!range) { return; }

  var linea = istanzaQuill.getLine(range.index);
  if (!linea || !linea[0] || !linea[0].domNode) { return; }
  var nodo = linea[0].domNode;
  if (!nodo.classList || !nodo.classList.contains('raw-html-block')) { return; }

  nodo.classList.add('pb-tabella-selezionata');
  tabellaSelezionata = nodo;
}

// The "click to edit" hint over an embedded table is a translated string, so
// it cannot live in the stylesheet: the CSS reads it from this attribute
// instead. It is refreshed on every change, and again after a Word import
// replaces the whole document.
function refreshTableHints() {
  if (!quill) { return; }
  var blocchi = quill.root.querySelectorAll('.raw-html-block');
  for (var i = 0; i < blocchi.length; i++) {
    blocchi[i].setAttribute('data-hint', t('admin_table_hint'));
  }
}

/* --- Toolbar buttons applied to a selected table -------------------------- */

// Which toolbar formats become a class on the table, and which class.
//
// Alignment and indent are NOT here: Quill applies those itself, as block
// attributes on the embed, and they round-trip through its own model. These
// are the inline formats, which Quill can only attach to text; an embed has
// no text, so without this they would silently do nothing on a table.
var TABLE_FORMAT_CLASSES = {
  bold: 'pb-tbl-bold',
  italic: 'pb-tbl-italic',
  underline: 'pb-tbl-underline',
  strike: 'pb-tbl-strike'
};

// Every class this file can put on a table, used by "remove formatting".
var TABLE_ALL_CLASSES = ['pb-tbl-bold', 'pb-tbl-italic', 'pb-tbl-underline',
                         'pb-tbl-strike', 'pb-tbl-sfondo'];

// The <table> inside a selected block, or null.
function selectedTableElement() {
  if (!tabellaSelezionata) { return null; }
  return tabellaSelezionata.querySelector('table');
}

// Applies a change to the selected table and tells Quill about it.
//
// The change is made to the DOM inside the block, which is exactly what the
// blot stores and what the save reads (the article is saved from
// quill.root.innerHTML), so it survives a reload with no further work.
function changeSelectedTable(azione) {
  var tabella = selectedTableElement();
  if (!tabella) { return false; }
  azione(tabella);
  quill.update();
  markEditorDirty();
  updatePreview();
  return true;
}

// Turns an inline format on or off for the whole table.
function toggleTableClass(classe) {
  return changeSelectedTable(function(tabella) {
    tabella.classList.toggle(classe);
  });
}

// Builds the toolbar handler for one inline format: it acts on the table when
// one is selected, and otherwise does exactly what Quill would have done.
//
// The fallback is a plain quill.format(): Quill's toolbar has already worked
// out whether the click means on or off (it passes false when the button is
// active) and hands us the final value. Recomputing that here would be wrong
// for the buttons that carry a value of their own, such as the list ones.
//
// On a table we toggle instead, because the button's active state is derived
// from Quill's model and our table formatting lives in the DOM: the button
// never lights up, so the value we are handed is always "on".
function inlineFormatHandler(nome) {
  return function(valore) {
    if (tabellaSelezionata && TABLE_FORMAT_CLASSES[nome]) {
      toggleTableClass(TABLE_FORMAT_CLASSES[nome]);
      return;
    }
    quill.format(nome, valore, 'user');
  };
}

// Text colour: on a table it goes on the table element, and the cells
// inherit it.
function colorHandler(valore) {
  if (tabellaSelezionata) {
    changeSelectedTable(function(tabella) {
      if (valore) {
        tabella.style.color = valore;
      } else {
        tabella.style.color = '';
      }
    });
    return;
  }
  quill.format('color', valore, 'user');
}

// Background: a background is not inherited, and our own stylesheet paints
// the header row and the alternating rows. So the colour goes on the table
// and a class turns those cell backgrounds off, otherwise the new colour
// would be hidden behind them.
function backgroundHandler(valore) {
  if (tabellaSelezionata) {
    changeSelectedTable(function(tabella) {
      if (valore) {
        tabella.style.backgroundColor = valore;
        tabella.classList.add('pb-tbl-sfondo');
      } else {
        tabella.style.backgroundColor = '';
        tabella.classList.remove('pb-tbl-sfondo');
      }
    });
    return;
  }
  quill.format('background', valore, 'user');
}

// "Remove formatting" on a table strips what the buttons above added, and
// the alignment Quill added, without touching the table itself.
function cleanHandler() {
  if (tabellaSelezionata) {
    var blocco = tabellaSelezionata;
    changeSelectedTable(function(tabella) {
      for (var i = 0; i < TABLE_ALL_CLASSES.length; i++) {
        tabella.classList.remove(TABLE_ALL_CLASSES[i]);
      }
      tabella.style.color = '';
      tabella.style.backgroundColor = '';
    });
    var classi = blocco.className.split(/\s+/);
    for (var j = 0; j < classi.length; j++) {
      if (classi[j].indexOf('ql-align-') === 0 || classi[j].indexOf('ql-indent-') === 0) {
        blocco.classList.remove(classi[j]);
      }
    }
    quill.update();
    markEditorDirty();
    return;
  }
  // Away from a table this is Quill's own "remove formatting": with a
  // selection it strips the formats inside it, and with just a caret it
  // clears the inline formats that would apply to what you type next.
  var range = quill.getSelection();
  if (range === null) { return; }
  if (range.length === 0) {
    var formati = quill.getFormat();
    for (var nome in formati) {
      if (Quill.import('parchment').query(nome, Quill.import('parchment').Scope.INLINE) != null) {
        quill.format(nome, false, 'user');
      }
    }
    return;
  }
  quill.removeFormat(range.index, range.length, 'user');
}

// The formats that would replace the block with something else - a heading,
// a list, a quote, a code block - would destroy the table, so on a selected
// table they do nothing. Doing nothing is the point: before this they were
// one click away from silently swallowing the table.
function blockFormatHandler(nome) {
  return function(valore) {
    if (tabellaSelezionata) {
      pbToast(t('js_table_format_not_applicable'), 'info');
      return;
    }
    quill.format(nome, valore, 'user');
  };
}

// The handlers passed to the toolbar when the article editor is created.
function tableAwareToolbarHandlers() {
  return {
    bold: inlineFormatHandler('bold'),
    italic: inlineFormatHandler('italic'),
    underline: inlineFormatHandler('underline'),
    strike: inlineFormatHandler('strike'),
    color: colorHandler,
    background: backgroundHandler,
    clean: cleanHandler,
    header: blockFormatHandler('header'),
    blockquote: blockFormatHandler('blockquote'),
    'code-block': blockFormatHandler('code-block'),
    list: blockFormatHandler('list')
  };
}

// --- Small table editor ---------------------------------------------------
// Quill cannot edit the cells of an embedded table in place (its document
// model does not manage the embed's inner DOM). So we offer the next best
// thing: clicking a table opens a small editor where every cell can be
// changed and rows/columns added or removed. Saving rewrites the embed's
// HTML; the article save reads quill.root.innerHTML, so the change is
// picked up with no further work.

// Builds and shows the modal with an editable copy of the table.
function openTableEditor(istanzaQuill, blocco, tabellaOriginale) {
  // Only one editor at a time.
  var esistente = document.getElementById('table-editor-overlay');
  if (esistente) { return; }

  var sfondo = document.createElement('div');
  sfondo.id = 'table-editor-overlay';

  var finestra = document.createElement('div');
  finestra.className = 'table-editor-window';

  var titolo = document.createElement('h3');
  titolo.textContent = t('admin_table_editor_title');
  finestra.appendChild(titolo);

  // An editable copy: the original stays untouched until "save".
  var copia = tabellaOriginale.cloneNode(true);
  var celle = copia.querySelectorAll('td, th');
  for (var i = 0; i < celle.length; i++) {
    celle[i].setAttribute('contenteditable', 'true');
  }
  var areaTabella = document.createElement('div');
  areaTabella.className = 'table-editor-area';
  areaTabella.appendChild(copia);
  finestra.appendChild(areaTabella);

  // Row and column controls.
  var barra = document.createElement('div');
  barra.className = 'table-editor-bar';
  barra.appendChild(tableEditorButton(t('admin_table_add_row'), function() { tableAddRow(copia); }));
  barra.appendChild(tableEditorButton(t('admin_table_del_row'), function() { tableRemoveRow(copia); }));
  barra.appendChild(tableEditorButton(t('admin_table_add_col'), function() { tableAddColumn(copia); }));
  barra.appendChild(tableEditorButton(t('admin_table_del_col'), function() { tableRemoveColumn(copia); }));
  finestra.appendChild(barra);

  // Save and cancel.
  var azioni = document.createElement('div');
  azioni.className = 'table-editor-actions';
  var salva = tableEditorButton(t('admin_table_save'), function() {
    blocco.innerHTML = serializeEditedTable(copia);
    closeTableEditor();
    // Tells Quill the document changed, so autosave and counters react.
    istanzaQuill.update();
  });
  salva.className = 'table-editor-save';
  var annulla = tableEditorButton(t('admin_table_cancel'), function() {
    closeTableEditor();
  });
  azioni.appendChild(salva);
  azioni.appendChild(annulla);
  finestra.appendChild(azioni);

  sfondo.appendChild(finestra);
  // A click on the dark background closes without saving.
  sfondo.addEventListener('click', function(evento) {
    if (evento.target === sfondo) {
      closeTableEditor();
    }
  });
  document.body.appendChild(sfondo);
}

function closeTableEditor() {
  var sfondo = document.getElementById('table-editor-overlay');
  if (sfondo) {
    document.body.removeChild(sfondo);
  }
}

function tableEditorButton(etichetta, azione) {
  var btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = etichetta;
  btn.onclick = azione;
  return btn;
}

// The rows of the edited table (they all belong to it: no nesting here).
function editedTableRows(tabella) {
  return tabella.querySelectorAll('tr');
}

function tableAddRow(tabella) {
  var righe = editedTableRows(tabella);
  if (righe.length === 0) { return; }
  var ultima = righe[righe.length - 1];
  var colonne = ultima.querySelectorAll('td, th').length;
  var riga = document.createElement('tr');
  for (var i = 0; i < colonne; i++) {
    var cella = document.createElement('td');
    cella.setAttribute('contenteditable', 'true');
    riga.appendChild(cella);
  }
  ultima.parentNode.appendChild(riga);
}

function tableRemoveRow(tabella) {
  var righe = editedTableRows(tabella);
  // The header row always stays.
  if (righe.length <= 1) { return; }
  var ultima = righe[righe.length - 1];
  ultima.parentNode.removeChild(ultima);
}

function tableAddColumn(tabella) {
  var righe = editedTableRows(tabella);
  for (var i = 0; i < righe.length; i++) {
    var cella;
    if (i === 0) {
      cella = document.createElement('th');
    } else {
      cella = document.createElement('td');
    }
    cella.setAttribute('contenteditable', 'true');
    righe[i].appendChild(cella);
  }
}

function tableRemoveColumn(tabella) {
  var righe = editedTableRows(tabella);
  for (var i = 0; i < righe.length; i++) {
    var celle = righe[i].querySelectorAll('td, th');
    // At least one column always stays.
    if (celle.length <= 1) { return; }
  }
  for (var j = 0; j < righe.length; j++) {
    var proprie = righe[j].querySelectorAll('td, th');
    righe[j].removeChild(proprie[proprie.length - 1]);
  }
}

// Rebuilds clean table HTML from the edited copy, with the same rules
// used when pasting: text and images survive, styling does not.
function serializeEditedTable(tabella) {
  var risultato = '<table class="article-table"><tbody>';
  var righe = editedTableRows(tabella);
  for (var i = 0; i < righe.length; i++) {
    risultato = risultato + '<tr>';
    var celle = righe[i].querySelectorAll('td, th');
    for (var j = 0; j < celle.length; j++) {
      var contenuto = buildCleanCell(celle[j]);
      if (i === 0) {
        risultato = risultato + '<th' + mergeAttributes(celle[j]) + '>' + contenuto + '</th>';
      } else {
        risultato = risultato + '<td' + mergeAttributes(celle[j]) + '>' + contenuto + '</td>';
      }
    }
    risultato = risultato + '</tr>';
  }
  risultato = risultato + '</tbody></table>';
  return risultato;
}

// Inserts an empty table created by the user (rows x columns of their choice).
function insertTable() {
  if (!PB_MAIN_QUILL) { return; }
  var righe = prompt(t('js_table_how_many_rows'), '3');
  if (righe === null) { return; }
  var colonne = prompt(t('js_table_how_many_cols'), '3');
  if (colonne === null) { return; }
  var numRighe = parseInt(righe, 10);
  var numColonne = parseInt(colonne, 10);
  if (isNaN(numRighe) || isNaN(numColonne)) { return; }
  if (numRighe < 1 || numColonne < 1) { return; }

  var html = '<table class="article-table"><tbody>';
  for (var i = 0; i < numRighe; i++) {
    html = html + '<tr>';
    for (var j = 0; j < numColonne; j++) {
      if (i === 0) {
        html = html + '<th>' + escapeCellText(t('js_table_header_cell')) + '</th>';
      } else {
        html = html + '<td>' + escapeCellText(t('js_table_body_cell')) + '</td>';
      }
    }
    html = html + '</tr>';
  }
  html = html + '</tbody></table>';

  // We insert the table directly, without going through the clipboard
  // matcher: that matcher exists to interpret Word's HTML, where a table
  // may really be page layout. A table the author asked for is always a
  // real table, even with a single row.
  var posizione = PB_MAIN_QUILL.getSelection(true);
  PB_MAIN_QUILL.insertEmbed(posizione.index, 'rawHTML', html, Quill.sources.USER);
}

/* --- Admin interface language -------------------------------------------- */

// Changes the language of the administration interface and reloads.
function changeAdminLanguage(lingua) {
  pbPostJson('/admin-language', { language: lingua })
    .then(function() { window.location.reload(); });
}

/* --- Dashboard (the article list) ---------------------------------------- */

// Shows the rows that match both the typed text and the chosen status.
// Hidden rows get the hidden attribute, so sorting can keep moving them.
function filterArticles() {
  var termine = document.getElementById('search-box-admin').value.toLowerCase().trim();
  var scelto = document.querySelector('#filtro-stato [aria-pressed="true"]');
  var stato = scelto ? scelto.getAttribute('data-filtro') : 'tutti';
  var carte = document.querySelectorAll('.articolo-card');
  var visibili = 0;
  for (var i = 0; i < carte.length; i++) {
    var titolo = carte[i].getAttribute('data-titolo');
    var statoOk = stato === 'tutti' || carte[i].getAttribute('data-stato') === stato;
    if (statoOk && titolo.indexOf(termine) !== -1) {
      carte[i].hidden = false;
      visibili = visibili + 1;
    } else {
      carte[i].hidden = true;
    }
  }
  // With no article at all the list already says so: the message is for a
  // search or a filter that leaves nothing.
  document.getElementById('nessun-risultato').hidden = visibili > 0 || carte.length === 0;
}

// The All / Published / Drafts buttons: one pressed at a time.
function filterByStatus(pulsante) {
  var gruppo = pulsante.parentNode.querySelectorAll('.segmento');
  for (var i = 0; i < gruppo.length; i++) {
    gruppo[i].setAttribute('aria-pressed', gruppo[i] === pulsante ? 'true' : 'false');
  }
  filterArticles();
}

/* --- Menus: the "..." of each article and the phone's "More" ------------- */

// Opens or closes the small menu of an article row. Only one stays open.
function toggleRowMenu(pulsante) {
  var menu = document.getElementById(pulsante.getAttribute('aria-controls'));
  var apri = pulsante.getAttribute('aria-expanded') !== 'true';
  closeRowMenus();
  if (!apri) { return; }
  pulsante.setAttribute('aria-expanded', 'true');
  // The open menu has to cover the buttons of the rows below it.
  pulsante.parentNode.classList.add('aperto');
  menu.hidden = false;
  // Near the bottom of the window - or of the phone's bottom bar, which
  // would cover it - the menu opens upwards.
  var fondo = window.innerHeight;
  var barra = document.querySelector('.barra-basso');
  if (barra && barra.offsetHeight > 0) {
    fondo = barra.getBoundingClientRect().top;
  }
  var spazioSotto = fondo - pulsante.getBoundingClientRect().bottom;
  menu.classList.toggle('verso-alto', spazioSotto < menu.offsetHeight + 16);
  menu.querySelector('[role="menuitem"]').focus();
}

// Closes every open row menu; with ritornaFuoco, focus goes back to the
// button that opened it, as after Esc.
function closeRowMenus(ritornaFuoco) {
  var aperti = document.querySelectorAll('.riga-menu [aria-expanded="true"]');
  for (var i = 0; i < aperti.length; i++) {
    aperti[i].setAttribute('aria-expanded', 'false');
    aperti[i].parentNode.classList.remove('aperto');
    document.getElementById(aperti[i].getAttribute('aria-controls')).hidden = true;
    if (ritornaFuoco) { aperti[i].focus(); }
  }
}

// On a phone the side menu becomes a sheet that rises above the bottom bar.
// Called with no argument it switches; with true or false it opens or closes.
function toggleAdminMenu(apri) {
  var menu = document.getElementById('menu-admin');
  var pulsante = document.getElementById('barra-altro');
  if (!menu || !pulsante) { return; }
  if (apri === undefined) {
    apri = !menu.classList.contains('aperto');
  }
  menu.classList.toggle('aperto', apri);
  document.getElementById('menu-velo').hidden = !apri;
  pulsante.setAttribute('aria-expanded', apri ? 'true' : 'false');
  if (apri) {
    var prima = menu.querySelector('.menu-voci .voce');
    if (prima) { prima.focus(); }
  }
}

document.addEventListener('click', function(evento) {
  if (!evento.target.closest('.riga-menu')) { closeRowMenus(); }
});

document.addEventListener('keydown', function(evento) {
  var menu = evento.target.closest ? evento.target.closest('.menu-tendina') : null;
  if (evento.key === 'Escape') {
    if (document.querySelector('.riga-menu [aria-expanded="true"]')) {
      closeRowMenus(true);
    } else if (document.querySelector('.menu.aperto')) {
      toggleAdminMenu(false);
      document.getElementById('barra-altro').focus();
    }
    return;
  }
  if (!menu) { return; }
  // Arrows move between the items of a row menu; Tab leaves it closed.
  var voci = Array.prototype.slice.call(menu.querySelectorAll('[role="menuitem"]'));
  var posizione = voci.indexOf(evento.target);
  if (evento.key === 'ArrowDown' || evento.key === 'ArrowUp') {
    evento.preventDefault();
    var passo = evento.key === 'ArrowDown' ? 1 : -1;
    voci[(posizione + passo + voci.length) % voci.length].focus();
  } else if (evento.key === 'Home' || evento.key === 'End') {
    evento.preventDefault();
    voci[evento.key === 'Home' ? 0 : voci.length - 1].focus();
  } else if (evento.key === 'Tab') {
    closeRowMenus(true);
  }
});

// Rebuilds the static site.
function rebuildSite(pulsante) {
  pbBusy(pulsante, true);
  pbPostJson('/rebuild', {})
    .then(function(res) {
      pbBusy(pulsante, false);
      pbToast(t('js_site_rebuilt').replace('{n}', res.articles), 'success');
    })
    .catch(function() {
      pbBusy(pulsante, false);
      pbToast(t('js_site_rebuilt_error'), 'danger');
    });
}

// Changes an article's status (published/draft) and reloads the page.
function changeStatus(pulsante, slug, nuovoStato) {
  pbBusy(pulsante, true);
  pbPostJson('/toggle-status', { slug: slug, status: nuovoStato })
    .then(function(res) {
      if (res.ok === true) {
        window.location.reload();
      } else {
        pbBusy(pulsante, false);
        pbToast(t('js_status_change_error'), 'danger');
      }
    })
    .catch(function() {
      pbBusy(pulsante, false);
      pbToast(t('js_status_change_error'), 'danger');
    });
}

// Deletes an article after confirmation, then reloads the page.
function deleteArticle(slug, titolo) {
  pbConfirm(t('js_delete_title'),
            t('js_delete_body').replace('{title}', titolo),
            t('admin_elimina'), 'danger',
            function() {
    pbPostJson('/delete', { slug: slug })
      .then(function(res) {
        if (res.ok === true) {
          window.location.reload();
        } else {
          pbToast(t('js_delete_error'), 'danger');
        }
      })
      .catch(function() { pbToast(t('js_delete_error'), 'danger'); });
  });
}

/* --- Preview iframes ------------------------------------------------------ */

// Shows or hides a preview iframe. The content is rebuilt every time it is
// opened, and again on every keystroke while it stays open.
function togglePreview() {
  var frame = document.getElementById('preview-iframe');
  if (frame.style.display === 'none') {
    frame.style.display = 'block';
    updatePreview();
  } else {
    frame.style.display = 'none';
  }
}

// Writes the preview page into the iframe. Which page depends on where we
// are: the settings page previews the homepage introduction, the editor
// previews the article. Both use the public stylesheets, so what you see is
// what the reader will get.
function updatePreview() {
  var frame = document.getElementById('preview-iframe');
  if (!frame || frame.style.display === 'none') {
    return;
  }
  if (!PB_MAIN_QUILL) {
    return;
  }
  var contenuto = PB_MAIN_QUILL.root.innerHTML;
  var pagina = '<!DOCTYPE html><html><head>';
  pagina = pagina + '<meta charset="utf-8">';
  pagina = pagina + '<link rel="stylesheet" href="/common.css">';
  pagina = pagina + '<link rel="stylesheet" href="/style.css">';

  if (pbPage('preview_kind', '') === 'article') {
    var titolo = document.getElementById('title').value;
    pagina = pagina + '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css">';
    pagina = pagina + '</head><body>';
    pagina = pagina + '<article id="content" class="post">';
    pagina = pagina + '<h1></h1>';
    pagina = pagina + contenuto;
    pagina = pagina + '</article>';
    // We load highlight.js inside the preview to colour the code here too.
    pagina = pagina + '<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"><\/script>';
    pagina = pagina + '<script>document.querySelectorAll("pre.ql-syntax").forEach(function(b){hljs.highlightElement(b);});<\/script>';
    pagina = pagina + '</body></html>';
  } else {
    pagina = pagina + '</head><body>';
    pagina = pagina + '<section class="home-intro">';
    pagina = pagina + contenuto;
    pagina = pagina + '</section></body></html>';
  }

  var documento = frame.contentDocument;
  documento.open();
  documento.write(pagina);
  documento.close();
  // The article title is written as text, never as HTML: a title with a
  // "<" in it must not be able to inject markup into the preview.
  if (pbPage('preview_kind', '') === 'article') {
    var intestazione = documento.querySelector('article.post h1');
    if (intestazione) {
      intestazione.textContent = document.getElementById('title').value;
    }
  }
}

/* --- The article editor page --------------------------------------------- */

// The toolbar of the full article editor.
var TOOLBAR_ARTICOLO = [
  [{ font: [] }, { size: ['small', false, 'large', 'huge'] }],
  [{ header: [1, 2, 3, 4, false] }],
  ['bold', 'italic', 'underline', 'strike'],
  [{ color: [] }, { background: [] }],
  [{ script: 'sub' }, { script: 'super' }],
  [{ list: 'ordered' }, { list: 'bullet' }, { list: 'check' }],
  [{ indent: '-1' }, { indent: '+1' }],
  [{ align: '' }, { align: 'center' }, { align: 'right' }, { align: 'justify' }],
  ['blockquote', 'code-block'],
  ['link', 'image', 'video'],
  ['clean']
];

// The lighter toolbar of the homepage introduction.
var TOOLBAR_HOME = [
  [{ font: [] }, { size: ['small', false, 'large', 'huge'] }],
  [{ header: [1, 2, 3, false] }],
  ['bold', 'italic', 'underline'],
  [{ color: [] }, { background: [] }],
  [{ list: 'ordered' }, { list: 'bullet' }],
  [{ align: '' }, { align: 'center' }, { align: 'right' }, { align: 'justify' }],
  ['blockquote', 'link', 'image'],
  ['clean']
];

// The minimal toolbar of the homepage cards.
var TOOLBAR_CARD = [
  [{ header: [3, false] }],
  ['bold', 'italic', 'underline'],
  [{ color: [] }],
  [{ list: 'ordered' }, { list: 'bullet' }],
  ['link', 'image'],
  ['clean']
];

// Registers the image resize module, once per page.
function registerBlotFormatter() {
  if (window.QuillBlotFormatter) {
    Quill.register('modules/blotFormatter', window.QuillBlotFormatter.default);
  }
}

// The two Quill editors of the article page (Italian and English).
var quill = null;
var quillEn = null;
// The slug the article is currently saved with on disk. It is updated after
// every save (including the one from the EN preview), so that a later slug
// change does not leave orphan files.
var slugOriginale = '';

// Whether the editor holds changes that are not on disk yet. It drives three
// things: the warning when you leave the page, whether the autosave has any
// work to do, and the "Unsaved changes" line under the buttons.
var editorDirty = false;
// "draft" or "published", as saved. The buttons of the sidebar follow it.
var statoArticolo = 'draft';
// Set while a save is in flight, so the autosave and a manual save cannot
// overlap and race each other's writes.
var salvataggioInCorso = false;
var timerAutosalvataggio = null;

// How often the autosave runs, in milliseconds.
var AUTOSAVE_INTERVAL = 60000;

function initEditorPage() {
  registerBlotFormatter();
  registerRawHtmlBlot();

  quill = new Quill('#editor', {
    theme: 'snow',
    modules: {
      blotFormatter: {},
      syntax: true,
      // The toolbar needs handlers of our own so its buttons can act on a
      // selected table. Every handler falls back to Quill's own behaviour
      // when the selection is ordinary text.
      toolbar: {
        container: TOOLBAR_ARTICOLO,
        handlers: tableAwareToolbarHandlers()
      }
    }
  });
  quill.root.innerHTML = pbPage('content', '');
  // Quill notices the content just put in on its next update and reports it
  // as typed by the author, after the page has already declared itself
  // clean: an article opened and left untouched still asked to confirm
  // leaving, and a draft got a pointless autosave. Taking the content in
  // silently, here, makes loading the page what it is: no change at all.
  quill.update(Quill.sources.SILENT);
  PB_MAIN_QUILL = quill;
  attachImageOverlay(quill);
  handlePastedImages(quill, 'upload-status');
  attachTableSupport(quill);

  // We create a second Quill editor for the English translation, so the author
  // can review and correct it before confirming it.
  quillEn = new Quill('#editor-en', {
    theme: 'snow',
    modules: { blotFormatter: {}, syntax: true, toolbar: TOOLBAR_ARTICOLO }
  });
  attachImageOverlay(quillEn);
  handlePastedImages(quillEn, null);

  applyToolbarTooltips();

  // We load the saved English values (if any).
  document.getElementById('title_en').value = pbPage('title_en', '');
  document.getElementById('description_en').value = pbPage('description_en', '');
  document.getElementById('preview_en').value = pbPage('preview_en', '');
  quillEn.root.innerHTML = pbPage('content_en', '');
  quillEn.update(Quill.sources.SILENT);
  document.getElementById('translation_authorized').checked = pbPage('translation_authorized', false);
  document.getElementById('translation_confirmed').checked = pbPage('translation_confirmed', false);
  slugOriginale = pbPage('slug', '');
  statoArticolo = pbPage('status', 'draft');
  document.getElementById('publish_at').value = localInputValue(pbPage('publish_at', ''));

  updateTranslationSection();
  updateDescriptionCounter();
  updatePreviewCounter();
  updateCoverPreview();

  labelQuillEditors();
  quill.on('text-change', markEditorDirty);
  quillEn.on('text-change', markEditorDirty);
  watchEditorFields();
  // The code of the article: its checkboxes and its own cards.
  document.getElementById('lista-codice-articolo').addEventListener('change', markEditorDirty);
  watchCodeList(document.getElementById('lista-codice-proprio'), markEditorDirty);

  // The article as it is right now is what is on disk: loading the page is
  // not a change.
  markEditorClean();
  startAutosave();
  installUnsavedChangesGuard();
  installSaveShortcut();
}

// Every field of the form marks the article as changed when it is touched.
function watchEditorFields() {
  var campi = ['title', 'slug', 'tags', 'series', 'series_number', 'kind_lab', 'lab_of',
               'repo_url', 'stack', 'image', 'description',
               'reader_preview', 'title_en', 'description_en', 'preview_en',
               'translation_authorized', 'translation_confirmed'];
  for (var i = 0; i < campi.length; i++) {
    var elemento = document.getElementById(campi[i]);
    if (!elemento) { continue; }
    elemento.addEventListener('input', markEditorDirty);
    elemento.addEventListener('change', markEditorDirty);
  }
}

// A change not on disk yet is said under the buttons: on a published article
// nothing saves it on its own, and the author should not have to guess.
function markEditorDirty() {
  editorDirty = true;
  var riga = document.getElementById('autosave-status');
  if (riga && !riga.classList.contains('pb-autosave-error')) {
    riga.textContent = t('js_modifiche_da_salvare');
  }
}

function markEditorClean() {
  editorDirty = false;
}

// Warns before leaving the page with unsaved work. Browsers show their own
// wording and ignore ours, but the event still has to be cancelled for the
// dialog to appear at all.
function installUnsavedChangesGuard() {
  window.addEventListener('beforeunload', function(evento) {
    if (!editorDirty) { return undefined; }
    evento.preventDefault();
    evento.returnValue = t('js_unsaved_changes');
    return t('js_unsaved_changes');
  });
}

// Ctrl+S (Cmd+S on a Mac) saves without leaving the editor, which is what
// the muscle memory of anyone who has used a word processor expects: a
// draft stays a draft, a published article is updated. It never publishes.
function installSaveShortcut() {
  document.addEventListener('keydown', function(evento) {
    var modificatore = evento.ctrlKey || evento.metaKey;
    if (!modificatore || evento.key.toLowerCase() !== 's') { return; }
    evento.preventDefault();
    if (statoArticolo === 'published') {
      updateArticle(document.getElementById('btn-aggiorna'));
    } else if (statoArticolo === 'scheduled') {
      saveScheduled(document.getElementById('btn-salva-programmato'));
    } else {
      saveDraft(document.getElementById('btn-salva-bozza'));
    }
  });
}

// Saves the draft in the background every minute, but only when there is
// something to save.
//
// It deliberately runs on DRAFTS only. Saving also rebuilds the site, so
// autosaving a published article would push half-written edits live every
// minute; on a draft there is no public page to spoil.
function startAutosave() {
  if (timerAutosalvataggio !== null) {
    clearInterval(timerAutosalvataggio);
  }
  timerAutosalvataggio = setInterval(autosaveDraft, AUTOSAVE_INTERVAL);
}

function autosaveDraft() {
  if (!editorDirty || salvataggioInCorso) { return; }
  if (statoArticolo !== 'draft') { return; }
  if (document.getElementById('title').value.trim() === '') {
    pbStatus('autosave-status', t('js_autosave_needs_title'));
    return;
  }

  salvataggioInCorso = true;
  pbStatus('autosave-status', t('js_autosaving'));
  pbPostJson('/save', articleData('draft'))
    .then(function(res) {
      salvataggioInCorso = false;
      if (res.ok) {
        applySavedSlug(res);
        markEditorClean();
        setAutosaveIndicator(t('js_autosaved_at').replace('{time}', currentTime()), false);
      } else {
        setAutosaveIndicator(t('js_autosave_failed'), true);
      }
    })
    .catch(function() {
      salvataggioInCorso = false;
      setAutosaveIndicator(t('js_autosave_failed'), true);
    });
}

function setAutosaveIndicator(testo, errore) {
  var elemento = document.getElementById('autosave-status');
  if (!elemento) { return; }
  elemento.textContent = testo;
  if (errore) {
    elemento.classList.add('pb-autosave-error');
  } else {
    elemento.classList.remove('pb-autosave-error');
  }
}

// The current time as HH:MM, for the "saved at" indicator.
function currentTime() {
  var adesso = new Date();
  var ore = String(adesso.getHours());
  var minuti = String(adesso.getMinutes());
  if (ore.length < 2) { ore = '0' + ore; }
  if (minuti.length < 2) { minuti = '0' + minuti; }
  return ore + ':' + minuti;
}

// Character counter for the SEO description, warning about Google's limit.
function updateDescriptionCounter() {
  var campo = document.getElementById('description');
  var contatore = document.getElementById('description-counter');
  if (!campo || !contatore) { return; }
  var lunghezza = campo.value.length;
  var messaggio = '';
  // Google shows about 120-160 characters: we flag when you leave the ideal range.
  if (lunghezza === 0) {
    messaggio = t('js_desc_counter_empty');
  } else if (lunghezza > 160) {
    messaggio = lunghezza + ' ' + t('js_chars_unit') + ' - ' + t('js_chars_too_long_google');
  } else if (lunghezza < 50) {
    messaggio = lunghezza + ' ' + t('js_chars_unit') + ' - ' + t('js_chars_too_short_seo');
  } else {
    messaggio = lunghezza + ' ' + t('js_chars_unit') + ' - ' + t('js_chars_ideal_length');
  }
  contatore.textContent = messaggio;
}

// Character counter for the preview meant for readers.
function updatePreviewCounter() {
  var campo = document.getElementById('reader_preview');
  var contatore = document.getElementById('preview-counter');
  if (!campo || !contatore) { return; }
  var lunghezza = campo.value.length;
  if (lunghezza === 0) {
    contatore.textContent = t('js_preview_counter_empty');
  } else {
    contatore.textContent = lunghezza + ' ' + t('js_chars_unit');
  }
}

// Asks the AI to propose an SEO description from the article content.
// The author sees the proposal in the textarea and can edit or rewrite it.
function suggestDescription(pulsante) {
  if (quill.getText().trim() === '') {
    pbStatus('description-status', t('js_write_article_content_first'));
    return;
  }
  pbBusy(pulsante, true);
  pbStatus('description-status', t('js_generating'));

  pbPostJson('/generate-description', {
    content: quill.root.innerHTML,
    title: document.getElementById('title').value
  })
  .then(function(res) {
    pbBusy(pulsante, false);
    if (res.ok === true) {
      document.getElementById('description').value = res.description;
      updateDescriptionCounter();
      markEditorDirty();
      pbStatus('description-status', t('js_suggestion_inserted'));
    } else {
      pbStatus('description-status', '');
      pbToast(t('js_error_prefix') + res.error, 'danger');
    }
  })
  .catch(function() {
    pbBusy(pulsante, false);
    pbStatus('description-status', '');
    pbToast(t('js_net_error_generation'), 'danger');
  });
}

// Asks the AI to write a narrative preview for readers (longer and more
// descriptive than the SEO meta description). The author can then edit it.
function generatePreview(pulsante) {
  if (quill.getText().trim() === '') {
    pbStatus('preview-status', t('js_write_article_content_first'));
    return;
  }
  pbBusy(pulsante, true);
  pbStatus('preview-status', t('js_generating'));

  pbPostJson('/generate-preview', {
    content: quill.root.innerHTML,
    title: document.getElementById('title').value
  })
  .then(function(res) {
    pbBusy(pulsante, false);
    if (res.ok === true) {
      document.getElementById('reader_preview').value = res.preview;
      updatePreviewCounter();
      markEditorDirty();
      pbStatus('preview-status', t('js_suggestion_inserted'));
    } else {
      pbStatus('preview-status', '');
      pbToast(t('js_error_prefix') + res.error, 'danger');
    }
  })
  .catch(function() {
    pbBusy(pulsante, false);
    pbStatus('preview-status', '');
    pbToast(t('js_net_error_generation'), 'danger');
  });
}

// Full SEO / AI-SEO analysis: asks the server (which asks the LLM) for
// keywords, backlink anchor texts, internal link suggestions, FAQ and
// advice, then renders everything in the sidebar panel.
// The results are rendered with textContent only: nothing coming from the
// model is ever inserted as HTML.
function analyzeSeo() {
  var pannello = document.getElementById('seo-results');

  if (quill.getText().trim() === '') {
    pbStatus('seo-status', t('js_write_article_content_first'));
    return;
  }

  // The analysis needs the slug to build the article URL for the backlink.
  var slugCorrente = document.getElementById('slug').value.trim();
  if (slugCorrente === '') {
    slugCorrente = slugOriginale;
  }
  if (slugCorrente === '') {
    pbStatus('seo-status', t('js_seo_save_first'));
    return;
  }

  var pulsante = document.getElementById('seo-analyze-btn');
  pbBusy(pulsante, true);
  pbStatus('seo-status', t('js_seo_analyzing'));
  pannello.style.display = 'none';
  pannello.textContent = '';

  pbPostJson('/analyze-seo', {
    content: quill.root.innerHTML,
    title: document.getElementById('title').value,
    slug: slugCorrente,
    tags: document.getElementById('tags').value,
    description: document.getElementById('description').value
  })
  .then(function(res) {
    pbBusy(pulsante, false);
    if (res.ok === true) {
      pbStatus('seo-status', t('js_seo_done'));
      renderSeoResults(pannello, res.analysis, res.article_url);
      pannello.style.display = 'block';
    } else {
      pbStatus('seo-status', '');
      pbToast(t('js_error_prefix') + res.error, 'danger');
    }
  })
  .catch(function() {
    pbBusy(pulsante, false);
    pbStatus('seo-status', '');
    pbToast(t('js_net_error_generation'), 'danger');
  });
}

// A section title inside the results panel.
function seoHeading(testo) {
  var h = document.createElement('div');
  h.className = 'seo-heading';
  h.textContent = testo;
  return h;
}

// A row of text with a small "copy" button next to it.
function seoCopyRow(testo) {
  var riga = document.createElement('div');
  riga.className = 'seo-row';
  var span = document.createElement('span');
  span.textContent = testo;
  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'seo-copy';
  btn.textContent = t('seo_copy');
  btn.onclick = function() { copyToClipboard(testo, btn); };
  riga.appendChild(span);
  riga.appendChild(btn);
  return riga;
}

// Copies a text to the clipboard and gives feedback on the button.
function copyToClipboard(testo, bottone) {
  var conferma = function() {
    var originale = bottone.textContent;
    bottone.textContent = t('seo_copied');
    setTimeout(function() { bottone.textContent = originale; }, 1200);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(testo).then(conferma);
  } else {
    // Fallback for older browsers or non-HTTPS contexts.
    var area = document.createElement('textarea');
    area.value = testo;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    document.body.removeChild(area);
    conferma();
  }
}

// Renders the analysis into the panel. Every field is optional: the model
// may omit some keys, and the panel simply skips the missing sections.
function renderSeoResults(pannello, analisi, urlArticolo) {
  if (!analisi) { return; }

  // The exact URL to use as the backlink target on the external site.
  pannello.appendChild(seoHeading(t('seo_backlink_target')));
  pannello.appendChild(seoCopyRow(urlArticolo));

  var liste = [
    ['primary_keywords', t('seo_primary_keywords')],
    ['secondary_keywords', t('seo_secondary_keywords')],
    ['title_variants', t('seo_title_variants')],
    ['anchor_texts', t('seo_anchor_texts')]
  ];
  for (var i = 0; i < liste.length; i++) {
    var chiave = liste[i][0];
    var titolo = liste[i][1];
    var valori = analisi[chiave];
    if (valori && valori.length > 0) {
      pannello.appendChild(seoHeading(titolo));
      for (var j = 0; j < valori.length; j++) {
        pannello.appendChild(seoCopyRow(String(valori[j])));
      }
    }
  }

  // Suggested tags: shown as text, with a button applying them to the field.
  var tagValori = analisi['suggested_tags'];
  if (tagValori && tagValori.length > 0) {
    pannello.appendChild(seoHeading(t('seo_suggested_tags')));
    var tagTesto = tagValori.join(', ');
    var rigaTag = seoCopyRow(tagTesto);
    var btnTag = document.createElement('button');
    btnTag.type = 'button';
    btnTag.className = 'seo-copy';
    btnTag.textContent = t('seo_apply_tags');
    btnTag.onclick = function() {
      document.getElementById('tags').value = tagTesto;
    };
    rigaTag.appendChild(btnTag);
    pannello.appendChild(rigaTag);
  }

  // The model's opinion on the current meta description.
  if (analisi['meta_description_review']) {
    pannello.appendChild(seoHeading(t('seo_meta_review')));
    var giudizio = document.createElement('div');
    giudizio.className = 'seo-text';
    giudizio.textContent = String(analisi['meta_description_review']);
    pannello.appendChild(giudizio);
  }

  // Internal links: slug plus the suggested anchor text.
  var interni = analisi['internal_links'];
  if (interni && interni.length > 0) {
    pannello.appendChild(seoHeading(t('seo_internal_links')));
    for (var k = 0; k < interni.length; k++) {
      var voce = interni[k];
      if (voce && voce.slug) {
        var anchor = '';
        if (voce.anchor) { anchor = String(voce.anchor); }
        pannello.appendChild(seoCopyRow(anchor + '  ->  /posts/' + String(voce.slug) + '.html'));
      }
    }
  }

  // FAQ suggested for AI answer engines: ready to paste at the end of
  // the article (AI crawlers favour explicit question/answer blocks).
  var faq = analisi['faq'];
  if (faq && faq.length > 0) {
    pannello.appendChild(seoHeading(t('seo_faq')));
    for (var f = 0; f < faq.length; f++) {
      if (faq[f] && faq[f].question) {
        var blocco = document.createElement('div');
        blocco.className = 'seo-text';
        var domanda = document.createElement('strong');
        domanda.textContent = String(faq[f].question);
        blocco.appendChild(domanda);
        blocco.appendChild(document.createElement('br'));
        blocco.appendChild(document.createTextNode(String(faq[f].answer || '')));
        pannello.appendChild(blocco);
      }
    }
  }

  // Concrete AI-SEO advice for this specific article.
  var consigli = analisi['ai_seo_tips'];
  if (consigli && consigli.length > 0) {
    pannello.appendChild(seoHeading(t('seo_ai_tips')));
    for (var c = 0; c < consigli.length; c++) {
      var tip = document.createElement('div');
      tip.className = 'seo-text';
      tip.textContent = '\u2022 ' + String(consigli[c]);
      pannello.appendChild(tip);
    }
  }
}

// Shows or hides the translation block based on the authorisation flag.
function updateTranslationSection() {
  var autorizzata = document.getElementById('translation_authorized').checked;
  var blocco = document.getElementById('translation-block');
  if (autorizzata) {
    blocco.style.display = 'block';
  } else {
    blocco.style.display = 'none';
  }
}

// Asks the server to translate title, description and content into English.
// The calls happen in the backend, where the API keys are safe.
function translateArticle(pulsante) {
  pbBusy(pulsante, true);
  pbStatus('translation-status', t('js_translating'));
  // The three pieces are translated one after the other; the button comes
  // back to life when the last one lands.
  var quandoFinito = function() { pbBusy(pulsante, false); };

  // We take the Italian texts to translate.
  var titoloIt = document.getElementById('title').value;
  var descrizioneIt = document.getElementById('description').value;
  var contenutoIt = quill.root.innerHTML;

  // We translate the three pieces one after the other.
  translatePiece(titoloIt, function(titoloTradotto) {
    document.getElementById('title_en').value = titoloTradotto;
    translatePiece(descrizioneIt, function(descrizioneTradotta) {
      document.getElementById('description_en').value = descrizioneTradotta;
      translatePiece(contenutoIt, function(contenutoTradotto, mediaRimesse) {
        quillEn.root.innerHTML = contenutoTradotto;
        markEditorDirty();
        pbStatus('translation-status', avvisoMedia(t('js_translated_review'), mediaRimesse));
        quandoFinito();
      });
    });
  });
}

// The images never travel to the translation service: the server swaps them
// for a marker and puts them back afterwards. When a service loses a marker
// too, the server still puts the image back, but no longer where it was - so
// the editor says how many need a second look instead of letting the author
// find out from a reader.
function avvisoMedia(messaggio, quante) {
  if (!quante || quante < 1) { return messaggio; }
  return messaggio + t('js_media_recovered').replace('{n}', String(quante));
}

// Translates a single piece of text by calling the backend.
function translatePiece(testo, quandoFinito) {
  if (testo === null || testo.trim() === '') {
    quandoFinito('');
    return;
  }
  pbPostJson('/translate', { text: testo })
    .then(function(res) {
      if (res.ok === true) {
        quandoFinito(res.text, res.media_recovered || 0);
      } else {
        pbStatus('translation-status',
          t('js_error_prefix') + res.error + t('js_check_api_key'));
        quandoFinito('');
      }
    })
    .catch(function() {
      pbStatus('translation-status', t('js_net_error_translation'));
      quandoFinito('');
    });
}

// The site's snippets on this article, read from the checkboxes: a
// "selected articles" one counts when ticked (tipo "optin"), one that goes on
// every article counts when unticked (tipo "sempre"), as switched off here.
// The editor only lists the snippets that are active in the Settings, so the
// ids the article already had for the others are kept as they were: the day
// one of them is switched back on, the article's choice is still there.
function articleCodeIds(tipo, spuntate, salvati) {
  var caselle = document.querySelectorAll('.codice-articolo');
  var mostrati = {};
  var ids = [];
  for (var i = 0; i < caselle.length; i++) {
    mostrati[caselle[i].value] = true;
    if (caselle[i].getAttribute('data-tipo') === tipo && caselle[i].checked === spuntate) {
      ids.push(caselle[i].value);
    }
  }
  for (var j = 0; j < salvati.length; j++) {
    if (!mostrati[salvati[j]] && ids.indexOf(salvati[j]) === -1) {
      ids.push(salvati[j]);
    }
  }
  return ids;
}

// A new piece of code for this article only.
function addOwnCode() {
  var card = cloneBlankCard('codice-proprio-modello', 'art');
  document.getElementById('lista-codice-proprio').appendChild(card);
  updateCardSummary(card);
  startCodeEditor(card);
  markEditorDirty();
  card.querySelector('.codice-nome').focus();
}

// Collects every form field into a single article object, for a save or a
// preview. stato is the status to save with; without it, the current one.
function articleData(stato) {
  return {
    title: document.getElementById('title').value,
    slug: document.getElementById('slug').value,
    description: document.getElementById('description').value,
    preview: document.getElementById('reader_preview').value,
    content: quill.root.innerHTML,
    tags: document.getElementById('tags').value,
    series: document.getElementById('series').value,
    series_number: document.getElementById('series_number').value,
    kind: document.getElementById('kind_lab').checked ? 'lab' : '',
    lab_of: document.getElementById('lab_of').value,
    repo_url: document.getElementById('repo_url').value,
    stack: document.getElementById('stack').value,
    image: document.getElementById('image').value,
    status: stato || statoArticolo,
    // The moment a scheduled article goes out, in UTC; ignored otherwise.
    publish_at: (stato || statoArticolo) === 'scheduled' ? scheduledMoment() : '',
    notify_subscribers: notifySubscribers(),
    original_slug: slugOriginale,
    custom_code_ids: articleCodeIds('optin', true, pbPage('custom_code_ids', [])),
    custom_code_off_ids: articleCodeIds('sempre', false, pbPage('custom_code_off_ids', [])),
    custom_code: customCodeData(document.getElementById('lista-codice-proprio'), 'art'),
    // Fields of the English version.
    title_en: document.getElementById('title_en').value,
    description_en: document.getElementById('description_en').value,
    preview_en: document.getElementById('preview_en').value,
    content_en: quillEn.root.innerHTML,
    translation_authorized: document.getElementById('translation_authorized').checked,
    translation_confirmed: document.getElementById('translation_confirmed').checked
  };
}

// After a save the server says which slug the article really has. It goes
// back into the Slug field, so the next save asks for that same address
// instead of deriving a new one from the title. When the address the article
// wanted already belonged to another article, the server picked a free one
// and says so: the author has to know the page is not where they expected.
function applySavedSlug(res) {
  slugOriginale = res.slug;
  var campo = document.getElementById('slug');
  if (campo) { campo.value = res.slug; }
  if (res.notice) { pbToast(res.notice, 'warning'); }
}

// The panel at the top of the sidebar shows the buttons of the state the
// article is in, and where the published page lives.
function updateStatePanel(indirizzo) {
  // A saved article has versions to look at.
  if (slugOriginale !== '') {
    var versioni = document.querySelectorAll('#btn-versioni, #versioni-aiuto');
    for (var v = 0; v < versioni.length; v++) { versioni[v].hidden = false; }
  }
  var pannello = document.getElementById('pannello-pubblica');
  if (pannello) { pannello.setAttribute('data-stato', statoArticolo); }
  var quando = document.getElementById('programmato-quando');
  if (quando && statoArticolo === 'scheduled') {
    quando.textContent = t('admin_esce_il').replace('{date}', formatMoment(scheduledMoment()));
  }
  toggleScheduleForm(null, false);
  var link = document.getElementById('link-online');
  if (link && indirizzo) { link.setAttribute('href', indirizzo); }
}

// --- The four things the sidebar can do with an article ---------------------
// A draft is saved or published; a published article is updated (its
// changes go online) or taken back to the drafts. Every one of them is a
// save with a status: what changes is the status and what the author is told.

function saveDraft(pulsante) {
  saveWithStatus('draft', pulsante, t('js_bozza_salvata'));
}

/* --- Scheduled publishing -------------------------------------------------- */

// The field holds the author's local time ("2026-10-04T09:00"); the server
// keeps the moment in UTC. These two convert between them.
function scheduledMoment() {
  var valore = document.getElementById('publish_at').value;
  if (!valore) { return ''; }
  var momento = new Date(valore);
  return isNaN(momento.getTime()) ? '' : momento.toISOString();
}

function localInputValue(iso) {
  if (!iso) { return ''; }
  var momento = new Date(iso);
  if (isNaN(momento.getTime())) { return ''; }
  var due = function(n) { return (n < 10 ? '0' : '') + n; };
  return momento.getFullYear() + '-' + due(momento.getMonth() + 1) + '-' + due(momento.getDate()) +
    'T' + due(momento.getHours()) + ':' + due(momento.getMinutes());
}

// "saturday 4 october, 09:00", in the language of the administration.
function formatMoment(iso) {
  var momento = new Date(iso);
  if (isNaN(momento.getTime())) { return iso; }
  return momento.toLocaleString(document.documentElement.lang || undefined, {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

// Every <time class="ora-locale"> written by the server shows UTC; here it
// becomes the reader's own time.
function localizeMoments(radice) {
  var tempi = (radice || document).querySelectorAll('time.ora-locale');
  for (var i = 0; i < tempi.length; i++) {
    tempi[i].textContent = formatMoment(tempi[i].getAttribute('datetime'));
  }
}
document.addEventListener('DOMContentLoaded', function() { localizeMoments(); });

// Opens or closes the little form with the date and time. With no button
// (null) it is closed, as after a save.
function toggleScheduleForm(pulsante, apri) {
  var modulo = document.getElementById('programma-modulo');
  if (!modulo) { return; }
  if (apri === undefined) { apri = modulo.hidden; }
  modulo.hidden = !apri;
  var pulsanti = document.querySelectorAll('[aria-controls="programma-modulo"]');
  for (var i = 0; i < pulsanti.length; i++) {
    pulsanti[i].setAttribute('aria-expanded', apri ? 'true' : 'false');
  }
  var campo = document.getElementById('publish_at');
  if (apri) {
    if (!campo.value) {
      // Tomorrow at nine is a sensible first proposal.
      var domani = new Date();
      domani.setDate(domani.getDate() + 1);
      domani.setHours(9, 0, 0, 0);
      campo.value = localInputValue(domani.toISOString());
    }
    campo.focus();
  }
}

function scheduleArticle(pulsante) {
  var titolo = document.getElementById('title').value.trim();
  if (titolo === '') {
    pbToast(t('js_titolo_per_pubblicare'), 'warning');
    document.getElementById('title').focus();
    return;
  }
  var momento = scheduledMoment();
  if (momento === '' || new Date(momento).getTime() <= Date.now()) {
    pbToast(t('js_programma_data'), 'warning');
    document.getElementById('publish_at').focus();
    return;
  }
  var quando = formatMoment(momento);
  pbConfirm(t('js_programma_titolo'),
            t('js_programma_corpo').replace('{title}', titolo).replace('{date}', quando),
            t('admin_programma_conferma'), 'primary', function() {
    saveWithStatus('scheduled', pulsante, t('js_programmato').replace('{date}', quando));
  });
}

function saveScheduled(pulsante) {
  saveWithStatus('scheduled', pulsante, t('js_modifiche_salvate'));
}

function publishNow(pulsante) {
  publishArticle(pulsante);
}

function cancelSchedule(pulsante) {
  saveWithStatus('draft', pulsante, t('js_programmazione_annullata'));
}

function updateArticle(pulsante) {
  saveWithStatus('published', pulsante, t('js_aggiornato'));
}

// Publishing puts the article on the homepage and in the RSS feed, where a
// feed reader may pick it up within minutes: it asks first.
function publishArticle(pulsante) {
  var titolo = document.getElementById('title').value.trim();
  if (titolo === '') {
    pbToast(t('js_titolo_per_pubblicare'), 'warning');
    document.getElementById('title').focus();
    return;
  }
  pbConfirm(t('js_pubblica_titolo'), t('js_pubblica_corpo').replace('{title}', titolo),
            t('admin_pubblica'), 'primary', function() {
    saveWithStatus('published', pulsante, t('js_pubblicato'));
  });
}

function unpublishArticle(pulsante) {
  var titolo = document.getElementById('title').value.trim();
  pbConfirm(t('js_ritira_titolo'), t('js_ritira_corpo').replace('{title}', titolo),
            t('admin_ritira'), 'danger', function() {
    saveWithStatus('draft', pulsante, t('js_ritirato'));
  });
}

function saveWithStatus(stato, pulsante, messaggio) {
  if (salvataggioInCorso) { return; }
  salvataggioInCorso = true;
  pbBusy(pulsante, true);

  pbPostJson('/save', articleData(stato))
    .then(function(res) {
      salvataggioInCorso = false;
      pbBusy(pulsante, false);
      if (!res.ok) {
        pbToast(t('js_save_error') + ' ' + res.error, 'danger');
        return;
      }
      applySavedSlug(res);
      statoArticolo = stato;
      updateStatePanel(res.url);
      markEditorClean();
      var ora = t('js_autosaved_at');
      if (stato === 'published') { ora = t('js_aggiornato_alle'); }
      if (stato === 'scheduled') { ora = t('js_salvato_alle'); }
      setAutosaveIndicator(ora.replace('{time}', currentTime()), false);
      // The address bar still says "new article" after the first save of a
      // new one; correcting it means a reload would reopen the right article.
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, '',
          '/edit?slug=' + encodeURIComponent(res.slug));
      }
      pbToast(messaggio, 'success');
    })
    .catch(function() {
      salvataggioInCorso = false;
      pbBusy(pulsante, false);
      pbToast(t('js_save_error'), 'danger');
    });
}

// --- Preview -------------------------------------------------------------------

// Opens the page as it is in the editor right now, in a new tab, and saves
// nothing: the fields travel in a form posted to /preview, which answers
// with the public page. Saving first, as the preview of the translation used
// to, would put the half-done changes of a published article online.
function previewArticle(lingua) {
  var modulo = document.createElement('form');
  modulo.method = 'post';
  modulo.action = '/preview';
  modulo.target = '_blank';
  var campi = {
    csrf_token: window.PB_CSRF,
    language: lingua || pbPage('main_language', 'it'),
    data: JSON.stringify(articleData())
  };
  for (var nome in campi) {
    var campo = document.createElement('input');
    campo.type = 'hidden';
    campo.name = nome;
    campo.value = campi[nome];
    modulo.appendChild(campo);
  }
  document.body.appendChild(modulo);
  modulo.submit();
  modulo.remove();
}

function previewTranslation() {
  previewArticle(pbPage('secondary_language', 'en'));
}

function deleteItem() {
  var titolo = document.getElementById('title').value;
  pbConfirm(t('js_delete_title'),
            t('js_delete_body').replace('{title}', titolo),
            t('admin_elimina'), 'danger',
            function() {
    // slugOriginale, not the slug the page was opened with: after a rename
    // the old address no longer exists, and deleting it would delete nothing.
    pbPostJson('/delete', { slug: slugOriginale })
      .then(function(res) {
        if (res.ok) {
          // The article is gone, so there is nothing left to warn about.
          markEditorClean();
          window.location.href = '/admin';
        } else {
          pbToast(t('js_delete_error'), 'danger');
        }
      })
      .catch(function() { pbToast(t('js_delete_error'), 'danger'); });
  });
}

/* --- The settings page ---------------------------------------------------- */

var quillHome = null;
var quillHomeEn = null;
var quillBio = null;
var quillBioEn = null;
var editorCard = [];
var configRawIniziale = '';

function initConfigPage() {
  registerBlotFormatter();

  quillHome = new Quill('#editor-home', {
    theme: 'snow',
    placeholder: t('js_home_intro_placeholder_it'),
    modules: { blotFormatter: {}, toolbar: TOOLBAR_HOME }
  });
  quillHome.root.innerHTML = pbPage('home_content', '');
  quillHome.update(Quill.sources.SILENT);
  PB_MAIN_QUILL = quillHome;
  attachImageOverlay(quillHome);
  handlePastedImages(quillHome, 'upload-status');

  // Quill editor for the English introduction of the homepage.
  quillHomeEn = new Quill('#editor-home-en', {
    theme: 'snow',
    placeholder: t('js_home_intro_placeholder_en'),
    modules: { blotFormatter: {}, toolbar: TOOLBAR_HOME }
  });
  quillHomeEn.root.innerHTML = pbPage('home_content_en', '');
  quillHomeEn.update(Quill.sources.SILENT);
  attachImageOverlay(quillHomeEn);
  handlePastedImages(quillHomeEn, null);

  // We create a WYSIWYG editor (Quill) for each homepage card.
  var contenutiCard = pbPage('card_contents', []);
  editorCard = [];
  for (var c = 0; c < contenutiCard.length; c++) {
    var editorCardSingolo = new Quill('#card-editor-' + c, {
      theme: 'snow',
      modules: { blotFormatter: {}, toolbar: TOOLBAR_CARD }
    });
    editorCardSingolo.root.innerHTML = contenutiCard[c];
    editorCardSingolo.update(Quill.sources.SILENT);
    attachImageOverlay(editorCardSingolo);
    handlePastedImages(editorCardSingolo, null);
    editorCard.push(editorCardSingolo);
  }

  // The biography: the whole text, and its translation.
  quillBio = new Quill('#editor-bio', {
    theme: 'snow',
    modules: { blotFormatter: {}, toolbar: TOOLBAR_HOME }
  });
  quillBio.root.innerHTML = pbPage('bio_content', '');
  quillBio.update(Quill.sources.SILENT);
  attachImageOverlay(quillBio);
  handlePastedImages(quillBio, null);
  quillBioEn = new Quill('#editor-bio-en', {
    theme: 'snow',
    modules: { blotFormatter: {}, toolbar: TOOLBAR_HOME }
  });
  quillBioEn.root.innerHTML = pbPage('bio_content_en', '');
  quillBioEn.update(Quill.sources.SILENT);
  attachImageOverlay(quillBioEn);
  handlePastedImages(quillBioEn, null);
  updateBioPhotoPreview();
  var progetti = document.querySelectorAll('#lista-progetti .progetto-config');
  for (var pr = 0; pr < progetti.length; pr++) { updateProjectPreview(progetti[pr]); }

  applyToolbarTooltips();

  quillHome.on('text-change', function() { updatePreview(); });

  updateCommentGroups();
  updateAiTrainingGroup();
  updateTranslationGroups();

  updateCustomCodeNote();
  watchCodeList(document.getElementById('lista-codice'), null);
  // Enter in a field of the templates creates the code, as a form would.
  document.getElementById('modello-campi').addEventListener('keydown', function(evento) {
    if (evento.key === 'Enter') {
      evento.preventDefault();
      createCodeFromTemplate();
    }
  });
  versioneConsensoSalvata = pbPage('consent_version', 1);
  versioneConsenso = versioneConsensoSalvata;

  // --- Advanced config.json editor ---
  configRawIniziale = pbPage('config_raw', '');
  document.getElementById('config-raw').value = configRawIniziale;

  labelQuillEditors();
  watchConfigChanges();
  showConfigSection(false);
  window.addEventListener('hashchange', function() { showConfigSection(true); });
  // Turning a tablet round can cross the phone width: the page without a
  // section shows the list on a phone and the first section on a computer.
  PB_TELEFONO.addEventListener('change', function() { showConfigSection(false); });
}

// Quill writes into a div of its own: the name and the help the template
// gave the editor's box go onto that div, where screen readers look.
function labelQuillEditors() {
  var scatole = document.querySelectorAll('.ql-container');
  for (var i = 0; i < scatole.length; i++) {
    var area = scatole[i].querySelector('.ql-editor');
    var attributi = ['aria-labelledby', 'aria-describedby'];
    for (var j = 0; j < attributi.length; j++) {
      var valore = scatole[i].getAttribute(attributi[j]);
      if (valore) { area.setAttribute(attributi[j], valore); }
    }
    area.setAttribute('role', 'textbox');
    area.setAttribute('aria-multiline', 'true');
  }
}

/* --- Settings: one section at a time ------------------------------------- */

var PB_TELEFONO = window.matchMedia('(max-width: 860px)');

// Shows the section named in the address (#sito, #home...). With none, a
// phone shows the list of sections and a computer the first one, since its
// side menu already lists them. After a click in the menu (spostaFuoco) the
// focus moves to the section's title, so a screen reader starts from there.
function showConfigSection(spostaFuoco) {
  var richiesta = window.location.hash.replace('#', '');
  var sezioni = document.querySelectorAll('.impostazioni .sezione');
  var trovata = null;
  for (var i = 0; i < sezioni.length; i++) {
    if (sezioni[i].getAttribute('data-sezione') === richiesta) { trovata = sezioni[i]; }
  }
  if (trovata === null && richiesta !== 'elenco' && !PB_TELEFONO.matches) {
    trovata = sezioni[0];
  }
  for (var j = 0; j < sezioni.length; j++) {
    sezioni[j].hidden = sezioni[j] !== trovata;
  }
  document.getElementById('sezione-elenco').hidden = trovata !== null;

  var chiave = trovata ? trovata.getAttribute('data-sezione') : 'elenco';
  document.getElementById('impostazioni').setAttribute('data-sezione', chiave);
  var voci = document.querySelectorAll('.voce-sotto[data-sezione]');
  for (var k = 0; k < voci.length; k++) {
    if (voci[k].getAttribute('data-sezione') === chiave) {
      voci[k].setAttribute('aria-current', 'page');
    } else {
      voci[k].removeAttribute('aria-current');
    }
  }
  updateSaveBar();

  if (trovata !== null) {
    // CodeMirror measures itself when created: inside a hidden section it
    // measured nothing, so it has to look again now that it can be seen.
    var codici = trovata.querySelectorAll('.CodeMirror');
    for (var c = 0; c < codici.length; c++) { codici[c].CodeMirror.refresh(); }
  }
  if (spostaFuoco) {
    window.scrollTo(0, 0);
    var titolo = trovata ? trovata.querySelector('h1') : document.getElementById('sezioni-elenco-titolo');
    titolo.setAttribute('tabindex', '-1');
    titolo.focus({ preventScroll: true });
  }
}

/* --- Settings: unsaved changes ------------------------------------------- */

var configModificata = false;

// Every field of the sections counts, except the hand-edited config.json,
// which has its own button, and the template chooser, which only prepares
// a card. Adding or removing a card of code counts too.
function watchConfigChanges() {
  var pagina = document.getElementById('impostazioni');
  var segna = function(evento) {
    if (evento.target.closest('#sezione-avanzate, #codice-modelli')) { return; }
    markConfigDirty();
  };
  pagina.addEventListener('input', segna);
  pagina.addEventListener('change', segna);
  var editors = [quillHome, quillHomeEn, quillBio, quillBioEn].concat(editorCard);
  for (var i = 0; i < editors.length; i++) {
    editors[i].on('text-change', markConfigDirty);
  }
  new MutationObserver(markConfigDirty)
    .observe(document.getElementById('lista-codice'), { childList: true });
  // Adding, removing and moving a project changes the list itself.
  new MutationObserver(markConfigDirty)
    .observe(document.getElementById('lista-progetti'), { childList: true });

  window.addEventListener('beforeunload', function(evento) {
    if (!configModificata) { return undefined; }
    evento.preventDefault();
    evento.returnValue = t('js_impostazioni_non_salvate');
    return t('js_impostazioni_non_salvate');
  });
}

function markConfigDirty() {
  if (configModificata) { return; }
  configModificata = true;
  updateSaveBar();
}

// The save bar says whether something is waiting to be saved. Where there
// is nothing to save - the list of sections, the raw config.json with its
// own button - it only shows up once something has changed.
function updateSaveBar() {
  var barra = document.getElementById('barra-salva');
  var sezione = document.getElementById('impostazioni').getAttribute('data-sezione');
  barra.hidden = !configModificata && (sezione === 'avanzate' || sezione === 'elenco');
  barra.classList.toggle('modificata', configModificata);
  document.getElementById('annulla-modifiche').hidden = !configModificata;
  document.getElementById('salva-nota').hidden = configModificata;
  document.getElementById('save-status').textContent =
    configModificata ? t('js_modifiche_da_salvare') : '';
}

// Throws the changes away by loading the page again, as it was saved.
function discardConfigChanges() {
  pbConfirm(t('js_annulla_modifiche_titolo'), t('js_annulla_modifiche_corpo'),
            t('admin_annulla_modifiche'), 'danger', function() {
    configModificata = false;
    window.location.reload();
  });
}

// Translates the home introduction from Italian to English with AI.
function translateHome(pulsante) {
  translateEditorInto(pulsante, quillHome, quillHomeEn, 'home-en-status');
}

// Translates the biography the same way.
function translateBiography(pulsante) {
  translateEditorInto(pulsante, quillBio, quillBioEn, 'bio-en-status');
}

// Sends the text of one editor to the translation service and puts the
// result into the other one.
function translateEditorInto(pulsante, origine, destinazione, idStato) {
  if (origine.getText().trim() === '') {
    pbStatus(idStato, t('js_write_intro_first'));
    return;
  }
  pbBusy(pulsante, true);
  pbStatus(idStato, t('js_translating'));

  pbPostJson('/translate', { text: origine.root.innerHTML })
    .then(function(res) {
      pbBusy(pulsante, false);
      if (res.ok === true) {
        destinazione.root.innerHTML = res.text;
        pbStatus(idStato,
          avvisoMedia(t('js_translated_home'), res.media_recovered || 0));
      } else {
        pbStatus(idStato, t('js_error_prefix') + res.error);
      }
    })
    .catch(function() {
      pbBusy(pulsante, false);
      pbStatus(idStato, '');
      pbToast(t('js_net_error_translation'), 'danger');
    });
}

/* --- Settings: the biography's photo ------------------------------------- */

function updateBioPhotoPreview() {
  var indirizzo = document.getElementById('bio_photo').value.trim();
  var anteprima = document.getElementById('bio-photo-preview');
  document.getElementById('bio-photo-remove').hidden = indirizzo === '';
  if (indirizzo === '') {
    anteprima.removeAttribute('src');
    anteprima.hidden = true;
    return;
  }
  anteprima.src = indirizzo;
  anteprima.hidden = false;
}

function uploadBioPhoto() {
  uploadChosenFile('file-bio-photo', pbPage('max_image_mb', 10), 'bio-photo-status',
                   t('js_uploading_image'))
    .then(function(url) {
      if (url === null) { return; }
      document.getElementById('bio_photo').value = url;
      updateBioPhotoPreview();
      markConfigDirty();
      pbStatus('bio-photo-status', t('js_image_uploaded'));
    });
}

// Clears the photo; the file stays in the media folder, as for the covers.
function removeBioPhoto() {
  document.getElementById('bio_photo').value = '';
  updateBioPhotoPreview();
  markConfigDirty();
  pbStatus('bio-photo-status', '');
}

/* --- Settings: the projects ---------------------------------------------- */

// A new project starts as the blank card of the template, at the end of the
// list, with the cursor on its name.
function addProject() {
  var modello = document.getElementById('progetto-modello');
  var card = modello.content.firstElementChild.cloneNode(true);
  document.getElementById('lista-progetti').appendChild(card);
  updateProjectsNote();
  card.querySelector('.progetto-nome').focus();
}

// Moves a project one place up or down: the order of the list is the order
// on the homepage. The focus stays on the button that was pressed.
function moveProject(pulsante, passo) {
  var card = pulsante.closest('.progetto-config');
  var lista = card.parentNode;
  if (passo < 0 && card.previousElementSibling) {
    lista.insertBefore(card, card.previousElementSibling);
  } else if (passo > 0 && card.nextElementSibling) {
    lista.insertBefore(card.nextElementSibling, card);
  }
  pulsante.focus();
}

function removeProject(pulsante) {
  var card = pulsante.closest('.progetto-config');
  var nome = card.querySelector('.progetto-nome').value.trim() || t('admin_progetto_senza_nome');
  pbConfirm(t('admin_progetto_elimina'), nome, t('admin_progetto_elimina'), 'danger',
    function() {
      card.remove();
      updateProjectsNote();
    });
}

function updateProjectsNote() {
  document.getElementById('progetti-vuoto-nota').hidden =
    document.querySelectorAll('#lista-progetti .progetto-config').length > 0;
}

// One file field serves every card: it remembers which card asked.
var progettoInCaricamento = null;

function chooseProjectImage(pulsante) {
  progettoInCaricamento = pulsante.closest('.progetto-config');
  document.getElementById('file-progetto').click();
}

function uploadProjectImage() {
  var card = progettoInCaricamento;
  if (card === null) { return; }
  var stato = card.querySelector('.progetto-stato');
  stato.id = 'progetto-stato-attivo';
  uploadChosenFile('file-progetto', pbPage('max_image_mb', 10), 'progetto-stato-attivo',
                   t('js_uploading_image'))
    .then(function(url) {
      stato.removeAttribute('id');
      if (url === null) { return; }
      card.querySelector('.progetto-immagine').value = url;
      updateProjectPreview(card);
      markConfigDirty();
      stato.textContent = t('js_image_uploaded');
    });
}

function updateProjectPreview(card) {
  var indirizzo = card.querySelector('.progetto-immagine').value.trim();
  var anteprima = card.querySelector('.progetto-anteprima');
  if (indirizzo === '') {
    anteprima.removeAttribute('src');
    anteprima.hidden = true;
    return;
  }
  anteprima.src = indirizzo;
  anteprima.hidden = false;
}

// The projects as they are saved, in the order of the list.
function projectsData() {
  var carte = document.querySelectorAll('#lista-progetti .progetto-config');
  var elenco = [];
  for (var i = 0; i < carte.length; i++) {
    var c = carte[i];
    elenco.push({
      name: c.querySelector('.progetto-nome').value.trim(),
      description: c.querySelector('.progetto-descrizione').value.trim(),
      description_en: c.querySelector('.progetto-descrizione-en').value.trim(),
      url: c.querySelector('.progetto-link').value.trim(),
      image: c.querySelector('.progetto-immagine').value.trim(),
      visible: c.querySelector('.progetto-visibile').checked
    });
  }
  return elenco;
}

// Shows only the field group of the chosen comment system.
function updateCommentGroups() {
  var scelta = document.getElementById('commenti').value;
  var gruppoGiscus = document.getElementById('gruppo-giscus');
  var gruppoDisqus = document.getElementById('gruppo-disqus');
  gruppoGiscus.classList.remove('attivo');
  gruppoDisqus.classList.remove('attivo');
  if (scelta === 'giscus') {
    gruppoGiscus.classList.add('attivo');
  }
  if (scelta === 'disqus') {
    gruppoDisqus.classList.add('attivo');
  }
}

// Shows the licensing contact field only when the policy requires one.
function updateAiTrainingGroup() {
  var scelta = document.getElementById('ai_training_policy').value;
  var gruppo = document.getElementById('gruppo-ai-licenza');
  if (scelta === 'licensed') {
    gruppo.style.display = 'block';
  } else {
    gruppo.style.display = 'none';
  }
}

// Shows only the fields of the chosen translation service.
function updateTranslationGroups() {
  var scelta = document.getElementById('translation_service').value;
  var gruppi = ['deepl', 'google', 'llm', 'openai', 'deepseek'];
  for (var i = 0; i < gruppi.length; i++) {
    var elemento = document.getElementById('gruppo-' + gruppi[i]);
    if (gruppi[i] === scelta) {
      elemento.classList.add('attivo');
    } else {
      elemento.classList.remove('attivo');
    }
  }
}

// --- Custom code -----------------------------------------------------------
// The same cards serve two lists: the site's code in the Settings and the
// code written inside one article in the editor. The article's cards have
// no "on which pages" dropdown, because their only page is the article.

// A new snippet gets its id here, in the browser, so that the checkboxes in
// the article editor have something stable to point at from the very first
// save. The timestamp keeps them ordered and the random tail keeps two cards
// added in the same millisecond apart. The code of an article has ids of
// its own kind ("art-"), never mistaken for the site's.
function newSnippetId(prefisso) {
  var casuale = Math.floor(Math.random() * 1679616).toString(36);
  return (prefisso || 'snip') + '-' + Date.now().toString(36) + '-' + casuale;
}

function customCodeCards(lista) {
  if (lista === null) { return []; }
  return lista.querySelectorAll('.codice-config');
}

// The empty-list note shows only while there are no cards at all.
function updateCustomCodeNote() {
  var nota = document.getElementById('codice-vuoto-nota');
  if (nota === null) { return; }
  nota.hidden = customCodeCards(document.getElementById('lista-codice')).length > 0;
}

// A new card, cloned from the blank one the server rendered into a
// <template>: the markup and its translated labels live in the template file
// and nowhere else.
function cloneBlankCard(idModello, prefisso) {
  var modello = document.getElementById(idModello);
  var card = modello.content.firstElementChild.cloneNode(true);
  card.setAttribute('data-id', newSnippetId(prefisso));
  return card;
}

// The code box of a card: CodeMirror when the CDN delivered it, the plain
// textarea when it did not. CodeMirror cannot measure itself inside a closed
// <details>, so it starts the first time its card is opened.
function startCodeEditor(card) {
  var area = card.querySelector('.codice-testo');
  if (area === null || area.pbEditor || typeof window.CodeMirror !== 'function') { return; }
  var editor = window.CodeMirror.fromTextArea(area, {
    mode: 'htmlmixed',
    lineNumbers: true,
    indentUnit: 2,
    tabSize: 2,
    viewportMargin: Infinity
  });
  area.pbEditor = editor;
  // The field CodeMirror types into takes the textarea's name.
  editor.getInputField().setAttribute('aria-label', area.getAttribute('aria-label') || '');
  // Every change goes back into the textarea and is announced the way
  // typing would be, so the summary and the unsaved-changes guard hear
  // about it like they hear about any other field.
  editor.on('change', function() {
    editor.save();
    area.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

function cardCode(card) {
  var area = card.querySelector('.codice-testo');
  if (area.pbEditor) { return area.pbEditor.getValue(); }
  return area.value;
}

function selectedLabel(tendina) {
  var scelta = tendina.options[tendina.selectedIndex];
  if (!scelta) { return ''; }
  return scelta.textContent;
}

function consentLabel(valore) {
  if (valore === 'statistics') { return t('consenso_statistics'); }
  if (valore === 'marketing') { return t('consenso_marketing'); }
  return t('consenso_necessary');
}

// The line under the name of a folded card, rewritten while the fields
// change, in the words the server used to draw it: where the code goes, on
// which pages, which consent it waits for.
function updateCardSummary(card) {
  var nome = card.querySelector('.codice-nome').value.trim();
  if (nome === '') { nome = t('admin_codice_senza_nome'); }
  card.querySelector('.codice-sommario-nome').textContent = nome;

  var posizione = card.querySelector('.codice-posizione');
  var pezzi = [selectedLabel(posizione)];
  var etichettaPunto = card.querySelector('.codice-ancora-etichetta');
  if (posizione.value === 'anchor' && etichettaPunto && etichettaPunto.value !== '') {
    pezzi = [etichettaPunto.value];
  }
  var riquadroPunto = card.querySelector('.codice-punto');
  if (riquadroPunto) { riquadroPunto.hidden = posizione.value !== 'anchor'; }
  var ambito = card.querySelector('.codice-ambito');
  if (ambito !== null) { pezzi.push(selectedLabel(ambito)); }
  pezzi.push(consentLabel(card.querySelector('.codice-consenso').value));
  card.querySelector('.codice-sommario-dove').textContent = pezzi.join(' · ');

  var attivo = card.querySelector('.codice-attivo').checked;
  var stato = card.querySelector('.codice-sommario-stato');
  stato.textContent = attivo ? t('admin_codice_attivo') : t('admin_codice_spento');
  stato.classList.toggle('spento', !attivo);
}

// Wires a list of cards: the summary follows the fields and the code editor
// starts when a card opens. Listening on the list covers the cards added
// later as well. "toggle" does not bubble, hence the capture phase.
function watchCodeList(lista, quandoCambia) {
  if (lista === null) { return; }
  var aggiorna = function(evento) {
    var card = evento.target.closest('.codice-config');
    if (card === null) { return; }
    updateCardSummary(card);
    if (quandoCambia) { quandoCambia(); }
    // Choosing "a point on the page" with no point yet opens the page.
    if (evento.type === 'change' && evento.target.classList.contains('codice-posizione')
        && evento.target.value === 'anchor' && card.querySelector('.codice-ancora').value === '') {
      openPointPicker(evento.target);
    }
  };
  lista.addEventListener('input', aggiorna);
  lista.addEventListener('change', aggiorna);
  lista.addEventListener('toggle', function(evento) {
    var card = evento.target;
    if (card.classList && card.classList.contains('codice-config') && card.open) {
      startCodeEditor(card);
    }
  }, true);
  var aperte = lista.querySelectorAll('.codice-config[open]');
  for (var i = 0; i < aperte.length; i++) {
    startCodeEditor(aperte[i]);
  }
}

function removeCustomCode(pulsante) {
  var card = pulsante.closest('.codice-config');
  if (card === null) { return; }
  var nome = card.querySelector('.codice-nome').value.trim();
  if (nome === '') { nome = t('admin_codice_titolo'); }
  pbConfirm(t('admin_codice_elimina'), nome, t('admin_codice_elimina'), 'danger',
    function() {
      card.remove();
      updateCustomCodeNote();
      if (pbPage('page', '') === 'editor') { markEditorDirty(); }
    });
}

// Reads a list of cards back into the snippets that are saved: the site's
// into config.json, an article's into the article.
function customCodeData(lista, prefisso) {
  var cards = customCodeCards(lista);
  var dati = [];
  for (var i = 0; i < cards.length; i++) {
    var card = cards[i];
    var id = card.getAttribute('data-id');
    if (id === null || id === '') {
      // Written back on the card, so the next save sends the same id.
      id = newSnippetId(prefisso);
      card.setAttribute('data-id', id);
    }
    var snippet = {
      id: id,
      name: card.querySelector('.codice-nome').value.trim(),
      enabled: card.querySelector('.codice-attivo').checked,
      position: card.querySelector('.codice-posizione').value,
      consent: card.querySelector('.codice-consenso').value,
      code: cardCode(card)
    };
    var ambito = card.querySelector('.codice-ambito');
    if (ambito !== null) { snippet.scope = ambito.value; }
    // The point chosen on the page travels with the snippet even when another
    // position is picked for now: going back to it finds it again.
    var ancora = card.querySelector('.codice-ancora');
    if (ancora !== null && ancora.value !== '') {
      snippet.anchor_selector = ancora.value;
      snippet.anchor_where = card.querySelector('.codice-ancora-dove').value || 'after';
      snippet.anchor_label = card.querySelector('.codice-ancora-etichetta').value;
      snippet.anchor_page = card.querySelector('.codice-ancora-pagina').value;
    }
    dati.push(snippet);
  }
  return dati;
}

// --- Ready-made code for the common services ---------------------------------

// The fields of a template accept the id the way people copy it: with
// spaces around, in lower case, with or without its prefix. normalizza puts
// it in the one shape forma checks.
function adsensePublisherField() {
  return {
    etichetta: t('js_modello_campo_pub'),
    esempio: 'pub-1234567890123456',
    forma: /^pub-\d{10,20}$/,
    normalizza: function(valore) {
      valore = valore.toLowerCase().replace(/^ca-/, '');
      if (/^\d+$/.test(valore)) { valore = 'pub-' + valore; }
      return valore;
    }
  };
}

function upperCaseId(valore) {
  return valore.toUpperCase();
}

// Each service: the fields it needs and the cards it writes from them, with
// the position, the pages and the consent that suit it. The code is the one
// the service itself publishes, with the id put in. A template is a starting
// point: everything stays editable in the card.
function codeTemplates() {
  return {
    ga4: {
      campi: [{ etichetta: t('js_modello_campo_ga4'), esempio: 'G-ABC123DEF4',
                forma: /^G-[A-Z0-9]{4,15}$/, normalizza: upperCaseId }],
      schede: function(valori, nome) {
        return [{ nome: nome, posizione: 'head', ambito: 'all', consenso: 'statistics', codice:
          '<!-- Google tag (gtag.js) -->\n' +
          '<script async src="https://www.googletagmanager.com/gtag/js?id=' + valori[0] + '"></script>\n' +
          '<script>\n' +
          '  window.dataLayer = window.dataLayer || [];\n' +
          '  function gtag(){dataLayer.push(arguments);}\n' +
          "  gtag('js', new Date());\n" +
          '\n' +
          "  gtag('config', '" + valori[0] + "');\n" +
          '</script>' }];
      }
    },
    // Tag Manager comes in two pieces, one for the head and one right after
    // <body>. It waits for the statistics consent: the tags it loads are
    // not known here, and the safe side is not to load them uninvited.
    gtm: {
      campi: [{ etichetta: t('js_modello_campo_gtm'), esempio: 'GTM-ABC1234',
                forma: /^GTM-[A-Z0-9]{4,12}$/, normalizza: upperCaseId }],
      schede: function(valori, nome) {
        return [
          { nome: nome, posizione: 'head', ambito: 'all', consenso: 'statistics', codice:
            '<!-- Google Tag Manager -->\n' +
            "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':\n" +
            "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],\n" +
            "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=\n" +
            "'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);\n" +
            "})(window,document,'script','dataLayer','" + valori[0] + "');</script>\n" +
            '<!-- End Google Tag Manager -->' },
          { nome: nome + ' (noscript)', posizione: 'body_start', ambito: 'all', consenso: 'statistics', codice:
            '<!-- Google Tag Manager (noscript) -->\n' +
            '<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=' + valori[0] + '"\n' +
            'height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>\n' +
            '<!-- End Google Tag Manager (noscript) -->' }
        ];
      }
    },
    adsense_auto: {
      campi: [adsensePublisherField()],
      adsTxt: true,
      schede: function(valori, nome) {
        return [{ nome: nome, posizione: 'head', ambito: 'all', consenso: 'marketing', codice:
          '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-' + valori[0] + '"\n' +
          '     crossorigin="anonymous"></script>' }];
      }
    },
    // One ad unit, in the sidebar to begin with: the place the layout keeps
    // for it. AdSense ignores its loader when the page already has one.
    adsense_unita: {
      campi: [adsensePublisherField(),
              { etichetta: t('js_modello_campo_slot'), esempio: '1234567890', forma: /^\d{6,12}$/ }],
      adsTxt: true,
      schede: function(valori, nome) {
        return [{ nome: nome, posizione: 'sidebar', ambito: 'all', consenso: 'marketing', codice:
          '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-' + valori[0] + '"\n' +
          '     crossorigin="anonymous"></script>\n' +
          '<ins class="adsbygoogle"\n' +
          '     style="display:block"\n' +
          '     data-ad-client="ca-' + valori[0] + '"\n' +
          '     data-ad-slot="' + valori[1] + '"\n' +
          '     data-ad-format="auto"\n' +
          '     data-full-width-responsive="true"></ins>\n' +
          '<script>\n' +
          '     (adsbygoogle = window.adsbygoogle || []).push({});\n' +
          '</script>' }];
      }
    },
    google_ads: {
      campi: [{ etichetta: t('js_modello_campo_aw'), esempio: 'AW-123456789',
                forma: /^AW-\d{6,12}$/,
                normalizza: function(valore) {
                  valore = valore.toUpperCase();
                  if (/^\d+$/.test(valore)) { valore = 'AW-' + valore; }
                  return valore;
                } }],
      schede: function(valori, nome) {
        return [{ nome: nome, posizione: 'head', ambito: 'all', consenso: 'marketing', codice:
          '<!-- Google tag (gtag.js) -->\n' +
          '<script async src="https://www.googletagmanager.com/gtag/js?id=' + valori[0] + '"></script>\n' +
          '<script>\n' +
          '  window.dataLayer = window.dataLayer || [];\n' +
          '  function gtag(){dataLayer.push(arguments);}\n' +
          "  gtag('js', new Date());\n" +
          '\n' +
          "  gtag('config', '" + valori[0] + "');\n" +
          '</script>' }];
      }
    },
    meta_pixel: {
      campi: [{ etichetta: t('js_modello_campo_pixel'), esempio: '1234567890123456',
                forma: /^\d{10,20}$/ }],
      schede: function(valori, nome) {
        return [{ nome: nome, posizione: 'head', ambito: 'all', consenso: 'marketing', codice:
          '<!-- Meta Pixel Code -->\n' +
          '<script>\n' +
          '!function(f,b,e,v,n,t,s)\n' +
          '{if(f.fbq)return;n=f.fbq=function(){n.callMethod?\n' +
          'n.callMethod.apply(n,arguments):n.queue.push(arguments)};\n' +
          "if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';\n" +
          'n.queue=[];t=b.createElement(e);t.async=!0;\n' +
          't.src=v;s=b.getElementsByTagName(e)[0];\n' +
          "s.parentNode.insertBefore(t,s)}(window, document,'script',\n" +
          "'https://connect.facebook.net/en_US/fbevents.js');\n" +
          "fbq('init', '" + valori[0] + "');\n" +
          "fbq('track', 'PageView');\n" +
          '</script>\n' +
          '<noscript><img height="1" width="1" style="display:none"\n' +
          'src="https://www.facebook.com/tr?id=' + valori[0] + '&ev=PageView&noscript=1"\n' +
          '/></noscript>\n' +
          '<!-- End Meta Pixel Code -->' }];
      }
    },
    clarity: {
      campi: [{ etichetta: t('js_modello_campo_clarity'), esempio: 'abcd1234ef',
                forma: /^[a-z0-9]{6,14}$/,
                normalizza: function(valore) { return valore.toLowerCase(); } }],
      schede: function(valori, nome) {
        return [{ nome: nome, posizione: 'head', ambito: 'all', consenso: 'statistics', codice:
          '<script type="text/javascript">\n' +
          '    (function(c,l,a,r,i,t,y){\n' +
          '        c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};\n' +
          '        t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;\n' +
          '        y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);\n' +
          '    })(window, document, "clarity", "script", "' + valori[0] + '");\n' +
          '</script>' }];
      }
    }
  };
}

// "Add code" opens the choice of templates in its place.
function openCodeTemplates() {
  var pannello = document.getElementById('codice-modelli');
  if (pannello === null) { return; }
  pannello.hidden = false;
  document.getElementById('btn-aggiungi-codice').hidden = true;
  updateCodeTemplateFields();
  document.getElementById('modello-codice').focus();
}

function closeCodeTemplates() {
  document.getElementById('codice-modelli').hidden = true;
  document.getElementById('btn-aggiungi-codice').hidden = false;
}

// The fields of the chosen template, built with textContent: a label is a
// translated string, never markup.
function updateCodeTemplateFields() {
  var contenitore = document.getElementById('modello-campi');
  contenitore.textContent = '';
  var modello = codeTemplates()[document.getElementById('modello-codice').value];
  if (!modello) { return; }
  for (var i = 0; i < modello.campi.length; i++) {
    var etichetta = document.createElement('label');
    etichetta.setAttribute('for', 'modello-campo-' + i);
    etichetta.textContent = modello.campi[i].etichetta;
    var campo = document.createElement('input');
    campo.type = 'text';
    campo.id = 'modello-campo-' + i;
    campo.placeholder = modello.campi[i].esempio;
    campo.spellcheck = false;
    campo.autocomplete = 'off';
    contenitore.appendChild(etichetta);
    contenitore.appendChild(campo);
  }
}

// A card at the bottom of the Settings list, empty or filled from a template.
function addCustomCodeCard(scheda) {
  var lista = document.getElementById('lista-codice');
  var card = cloneBlankCard('codice-modello', 'snip');
  if (scheda) {
    card.querySelector('.codice-nome').value = scheda.nome;
    card.querySelector('.codice-posizione').value = scheda.posizione;
    card.querySelector('.codice-ambito').value = scheda.ambito;
    card.querySelector('.codice-consenso').value = scheda.consenso;
    card.querySelector('.codice-testo').value = scheda.codice;
  }
  lista.appendChild(card);
  updateCardSummary(card);
  updateCustomCodeNote();
  startCodeEditor(card);
  return card;
}

// Adds a line to ads.txt unless it is there already. Says whether it did.
function addAdsTxtLine(riga) {
  var campo = document.getElementById('ads_txt');
  if (campo === null) { return false; }
  var righe = campo.value.split('\n');
  for (var i = 0; i < righe.length; i++) {
    if (righe[i].replace(/\s+/g, '').toLowerCase() === riga.replace(/\s+/g, '').toLowerCase()) {
      return false;
    }
  }
  var testo = campo.value.replace(/\s+$/, '');
  campo.value = (testo === '' ? '' : testo + '\n') + riga;
  return true;
}

function createCodeFromTemplate() {
  var tendina = document.getElementById('modello-codice');
  var scelta = tendina.value;
  if (scelta === 'libero') {
    var vuota = addCustomCodeCard(null);
    closeCodeTemplates();
    vuota.querySelector('.codice-nome').focus();
    return;
  }

  // Two Google Analytics on the same page count every visit twice.
  if (scelta === 'ga4' && document.getElementById('analytics_id').value.trim() !== '') {
    pbToast(t('js_modello_ga4_doppio'), 'warning');
    return;
  }

  var modello = codeTemplates()[scelta];
  var valori = [];
  for (var i = 0; i < modello.campi.length; i++) {
    var definizione = modello.campi[i];
    var campo = document.getElementById('modello-campo-' + i);
    var valore = campo.value.replace(/\s+/g, '');
    if (definizione.normalizza) { valore = definizione.normalizza(valore); }
    if (!definizione.forma.test(valore)) {
      pbToast(t('js_modello_non_valido').replace('{campo}', definizione.etichetta)
                                        .replace('{esempio}', definizione.esempio), 'warning');
      campo.focus();
      return;
    }
    valori.push(valore);
  }

  var schede = modello.schede(valori, selectedLabel(tendina));
  var prima = null;
  for (var s = 0; s < schede.length; s++) {
    var card = addCustomCodeCard(schede[s]);
    if (prima === null) { prima = card; }
  }
  var messaggio = t('js_modello_creato');
  if (modello.adsTxt && addAdsTxtLine('google.com, ' + valori[0] + ', DIRECT, f08c47fec0942fa0')) {
    messaggio = messaggio + '\n' + t('js_modello_ads_txt');
  }
  closeCodeTemplates();
  prima.scrollIntoView({ block: 'center' });
  pbToast(messaggio, 'success');
}

// --- Consent banner -------------------------------------------------------------

// The consent version as saved, and the one the next save will send. "Ask
// everyone again" raises it by one; a visitor whose choice was made under an
// older number sees the banner again.
var versioneConsensoSalvata = 1;
var versioneConsenso = 1;

function renewConsent() {
  versioneConsenso = versioneConsensoSalvata + 1;
  markConfigDirty();
  pbToast(t('js_consenso_rinnovato'), 'success');
}

function saveConfig(pulsante) {
  // We collect the data of the homepage cards.
  var cardElementi = document.querySelectorAll('.card-config');
  var cardDati = [];
  for (var i = 0; i < cardElementi.length; i++) {
    var elemento = cardElementi[i];
    var attiva = elemento.querySelector('.card-attiva').checked;
    var titolo = elemento.querySelector('.card-title').value;
    // The content comes from the Quill editor matching this card.
    var contenuto = editorCard[i].root.innerHTML;
    cardDati.push({ active: attiva, title: titolo, content: contenuto });
  }

  // Social profiles: from the textarea, one line per profile (blank lines excluded).
  var righeProfili = document.getElementById('seo_profili').value.split('\n');
  var profiliSocial = [];
  for (var p = 0; p < righeProfili.length; p++) {
    var rigaProfilo = righeProfili[p].trim();
    if (rigaProfilo !== '') {
      profiliSocial.push(rigaProfilo);
    }
  }

  // How many words of each article the lists show when it has no preview.
  var paroleAnteprima = parseInt(document.getElementById('home_excerpt_words').value, 10);
  if (isNaN(paroleAnteprima) || paroleAnteprima < 10) {
    paroleAnteprima = 40;
  }

  var articoliPerPagina = parseInt(document.getElementById('articoli_per_pagina').value, 10);
  if (isNaN(articoliPerPagina) || articoliPerPagina < 0) {
    articoliPerPagina = 10;
  }

  var config = {
    site_title: document.getElementById('site_title').value,
    subtitle: document.getElementById('subtitle').value,
    author: document.getElementById('author').value,
    base_url: document.getElementById('base_url').value,
    analytics_id: document.getElementById('analytics_id').value.trim(),
    umami_url: document.getElementById('umami_url').value.trim(),
    umami_website_id: document.getElementById('umami_website_id').value.trim(),
    language: document.getElementById('language').value,
    home_intro_position: document.getElementById('home_intro_position').value,
    home_excerpt_words: paroleAnteprima,
    articles_per_page: articoliPerPagina,
    home_featured: document.getElementById('home_featured').checked,
    article_cover: document.getElementById('article_cover').checked,
    seo: {
      author_url: document.getElementById('seo_author_url').value.trim(),
      author_image: document.getElementById('seo_author_image').value.trim(),
      author_role: document.getElementById('seo_author_role').value.trim(),
      author_bio: document.getElementById('seo_author_bio').value.trim(),
      social_profiles: profiliSocial,
      logo: document.getElementById('seo_logo').value.trim(),
      twitter_site: document.getElementById('seo_twitter').value.trim(),
      favicon: document.getElementById('seo_favicon').value.trim()
    },
    home_content: quillHome.root.innerHTML,
    home_content_en: quillHomeEn.root.innerHTML,
    home_cards_enabled: document.getElementById('home_cards_enabled').checked,
    biography: {
      enabled: document.getElementById('bio_enabled').checked,
      position: document.getElementById('bio_position').value,
      photo: document.getElementById('bio_photo').value.trim(),
      content: quillBio.root.innerHTML,
      content_en: quillBioEn.root.innerHTML
    },
    newsletter: newsletterData(),
    projects: {
      enabled: document.getElementById('projects_enabled').checked,
      position: document.getElementById('projects_position').value,
      items: projectsData()
    },
    home_cards: cardDati,
    custom_code: customCodeData(document.getElementById('lista-codice'), 'snip'),
    ads_txt: document.getElementById('ads_txt').value.trim(),
    consent: {
      enabled: document.getElementById('consent_enabled').checked,
      text: document.getElementById('consent_text').value.trim(),
      text_en: document.getElementById('consent_text_en').value.trim(),
      privacy_url: document.getElementById('consent_privacy_url').value.trim(),
      version: versioneConsenso
    },
    comments: document.getElementById('commenti').value,
    giscus: {
      repo: document.getElementById('giscus_repo').value,
      repo_id: document.getElementById('giscus_repo_id').value,
      category: document.getElementById('giscus_category').value,
      category_id: document.getElementById('giscus_category_id').value,
      theme: document.getElementById('giscus_theme').value
    },
    disqus: {
      shortname: document.getElementById('disqus_shortname').value
    },
    ai_training: {
      policy: document.getElementById('ai_training_policy').value,
      contact_email: document.getElementById('ai_training_contact_email').value.trim(),
      license_url: document.getElementById('ai_training_license_url').value.trim(),
      statement: document.getElementById('ai_training_statement').value.trim()
    },
    translation: {
      service: document.getElementById('translation_service').value,
      deepl_api_key: document.getElementById('deepl_api_key').value,
      google_api_key: document.getElementById('google_api_key').value,
      llm_api_key: document.getElementById('llm_api_key').value,
      llm_endpoint: document.getElementById('llm_endpoint').value,
      llm_model: document.getElementById('llm_modello').value,
      openai_api_key: document.getElementById('openai_api_key').value,
      openai_model: document.getElementById('openai_modello').value,
      deepseek_api_key: document.getElementById('deepseek_api_key').value,
      deepseek_model: document.getElementById('deepseek_modello').value
    }
  };

  pbBusy(pulsante, true);
  pbStatus('save-status', t('admin_salvataggio'));
  pbPostJson('/save-config', config)
    .then(function(res) {
      pbBusy(pulsante, false);
      if (res.ok === true) {
        versioneConsensoSalvata = config.consent.version;
        configModificata = false;
        pbToast(t('admin_config_salvata'), 'success');
      } else {
        pbToast(t('js_error_prefix') + res.error, 'danger');
      }
      updateSaveBar();
    })
    .catch(function() {
      pbBusy(pulsante, false);
      updateSaveBar();
      pbToast(t('admin_errore_salvataggio'), 'danger');
    });
}

// Puts the original config back into the textarea (discards unsaved changes).
function restoreRawConfig() {
  document.getElementById('config-raw').value = configRawIniziale;
  pbStatus('config-raw-status', '');
}

// Saves the hand-edited config.json, after server-side validation.
function saveRawConfig(pulsante) {
  var contenuto = document.getElementById('config-raw').value;

  // Preliminary browser-side check: warns immediately if the JSON is broken.
  try {
    JSON.parse(contenuto);
  } catch (e) {
    pbToast(t('err_invalid_json_prefix') + e.message, 'danger');
    return;
  }

  pbBusy(pulsante, true);
  pbStatus('config-raw-status', t('admin_salvataggio'));
  pbPostJson('/save-config-raw', { content: contenuto })
    .then(function(res) {
      pbBusy(pulsante, false);
      pbStatus('config-raw-status', '');
      if (res.ok === true) {
        pbToast(t('admin_config_raw_salvata'), 'success');
        // We update the "original" reference to the newly saved content.
        configRawIniziale = contenuto;
      } else {
        pbToast(t('js_error_prefix') + res.error, 'danger');
      }
    })
    .catch(function() {
      pbBusy(pulsante, false);
      pbStatus('config-raw-status', '');
      pbToast(t('admin_errore_salvataggio'), 'danger');
    });
}

/* --- Page dispatch -------------------------------------------------------- */

// Each admin template declares which page it is; we run only its init.
document.addEventListener('DOMContentLoaded', function() {
  var pagina = pbPage('page', '');
  if (pagina === 'editor') {
    initEditorPage();
  } else if (pagina === 'config') {
    initConfigPage();
  }
});

/* --- Dashboard: sorting --------------------------------------------------- */

// Reorders the article cards in place. Sorting in the browser keeps the page
// static: no reload, no round trip, and the search filter stays applied.
function sortArticles() {
  var scelta = document.getElementById('ordina-articoli').value;
  var contenitore = document.getElementById('elenco-articoli');
  if (!contenitore) { return; }

  var carte = [];
  var elementi = contenitore.querySelectorAll('.articolo-card');
  for (var i = 0; i < elementi.length; i++) {
    carte.push(elementi[i]);
  }

  carte.sort(function(a, b) {
    if (scelta === 'titolo') {
      return a.getAttribute('data-titolo').localeCompare(b.getAttribute('data-titolo'));
    }
    if (scelta === 'stato') {
      // Drafts first, then the scheduled ones, then the published ones.
      var ordine = { '0': 0, 's': 1, '1': 2 };
      var statoA = ordine[a.getAttribute('data-stato')];
      var statoB = ordine[b.getAttribute('data-stato')];
      if (statoA !== statoB) {
        return statoA - statoB;
      }
      // Within one status, the newest first: the same order as the default.
      return b.getAttribute('data-data').localeCompare(a.getAttribute('data-data'));
    }
    var dataA = a.getAttribute('data-data');
    var dataB = b.getAttribute('data-data');
    if (scelta === 'vecchi') {
      return dataA.localeCompare(dataB);
    }
    return dataB.localeCompare(dataA);
  });

  for (var j = 0; j < carte.length; j++) {
    contenitore.appendChild(carte[j]);
  }
}


/* --- Choosing on the page where a piece of code goes ---------------------- */

// The window shows the real page (the homepage or an article, generated
// without any code) in a frame of the same site. Moving over it lights up
// the blocks; a click chooses one, and "before" or "after" says on which
// side the code goes. The same blocks are listed in a dropdown, for the
// keyboard and for screen readers. What is saved is a CSS selector that
// names the block in a way every page of that kind shares: "the third
// paragraph of the text", not "this paragraph of this article".

var puntoScheda = null;      // the card the window is choosing for
var puntoBlocchi = [];       // the blocks of the page on show
var puntoScelto = null;      // the block chosen, or null

// The containers whose children can be chosen, from the outside in.
var PUNTO_CONTENITORI = ['body', '.layout-colonne', 'main', '.colonna-principale',
  'article.post', '.post-content', '.articles-section', '.articles-list',
  '.barra-laterale'];

function puntoT(chiave, valori) {
  var testo = t(chiave);
  for (var nome in (valori || {})) { testo = testo.replace('{' + nome + '}', valori[nome]); }
  return testo;
}

function openPointPicker(origine) {
  puntoScheda = origine.closest('.codice-config');
  var finestra = pointPickerWindow();
  var scelta = document.getElementById('sp-pagina');
  scelta.innerHTML = '';
  var avviso = document.getElementById('sp-avviso');
  avviso.textContent = '';
  var nellEditor = pbPage('page', '') === 'editor';
  var opzioni = [];
  if (nellEditor) {
    var slug = pbPage('slug', '');
    if (slug === '') {
      avviso.textContent = t('js_sp_salva_prima');
    } else {
      opzioni.push({ valore: slug, testo: puntoT('js_sp_articolo', { title: document.getElementById('title').value }) });
    }
  } else {
    opzioni.push({ valore: '', testo: t('js_sp_home') });
    var articoli = pbPage('articoli_punto', []);
    for (var i = 0; i < articoli.length; i++) {
      opzioni.push({ valore: articoli[i].slug, testo: puntoT('js_sp_articolo', { title: articoli[i].title }) });
    }
    if (articoli.length === 0) { avviso.textContent = t('js_sp_nessun_articolo'); }
  }
  for (var j = 0; j < opzioni.length; j++) {
    var o = document.createElement('option');
    o.value = opzioni[j].valore;
    o.textContent = opzioni[j].testo;
    scelta.appendChild(o);
  }
  // Start from the page the point was chosen on, or the one the scope suggests.
  var paginaSalvata = puntoScheda.querySelector('.codice-ancora-pagina').value;
  var ambito = puntoScheda.querySelector('.codice-ambito');
  var preferisciArticolo = paginaSalvata === 'article' ||
    (paginaSalvata === '' && ambito !== null && ['articles', 'optin'].indexOf(ambito.value) !== -1);
  if (!nellEditor && preferisciArticolo && scelta.options.length > 1) { scelta.selectedIndex = 1; }
  var dove = puntoScheda.querySelector('.codice-ancora-dove').value || 'after';
  document.querySelector('input[name="sp-dove"][value="' + dove + '"]').checked = true;
  document.getElementById('sp-conferma').disabled = true;
  if (!finestra.open) { finestra.showModal(); }
  if (scelta.options.length > 0) {
    loadPointPage();
  } else {
    document.getElementById('sp-iframe').removeAttribute('src');
  }
}

// The window is built once, the first time it is needed.
function pointPickerWindow() {
  var finestra = document.getElementById('scelta-punto');
  if (finestra) { return finestra; }
  finestra = document.createElement('dialog');
  finestra.id = 'scelta-punto';
  finestra.className = 'scelta-punto';
  finestra.setAttribute('aria-labelledby', 'sp-titolo');
  finestra.innerHTML =
    '<div class="sp-testata">' +
      '<div class="sp-testata-testo"><h2 id="sp-titolo"></h2><p class="aiuto" id="sp-istruzioni"></p></div>' +
      '<div class="campo sp-campo-pagina"><label for="sp-pagina"></label><select class="campo-input" id="sp-pagina"></select></div>' +
    '</div>' +
    '<p class="avviso avviso-danger" id="sp-avviso" role="status"></p>' +
    '<div class="sp-corpo"><iframe id="sp-iframe"></iframe></div>' +
    '<div class="sp-piede">' +
      '<div class="campo sp-campo-blocco"><label for="sp-elenco"></label><select class="campo-input" id="sp-elenco"></select></div>' +
      '<fieldset class="sp-dove"><legend></legend>' +
        '<label class="campo-spunta"><input type="radio" name="sp-dove" value="before"> <span></span></label>' +
        '<label class="campo-spunta"><input type="radio" name="sp-dove" value="after" checked> <span></span></label>' +
      '</fieldset>' +
      '<div class="azioni sp-azioni">' +
        '<button type="button" class="pulsante" id="sp-annulla"></button>' +
        '<button type="button" class="pulsante pulsante-primario" id="sp-conferma" disabled></button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(finestra);
  document.getElementById('sp-titolo').textContent = t('js_sp_titolo');
  document.getElementById('sp-istruzioni').textContent = t('js_sp_istruzioni');
  finestra.querySelector('label[for="sp-pagina"]').textContent = t('js_sp_pagina');
  finestra.querySelector('label[for="sp-elenco"]').textContent = t('js_sp_punto');
  finestra.querySelector('.sp-dove legend').textContent = t('js_sp_dove');
  var etichette = finestra.querySelectorAll('.sp-dove span');
  etichette[0].textContent = t('js_pd_prima');
  etichette[1].textContent = t('js_pd_dopo');
  document.getElementById('sp-annulla').textContent = t('admin_annulla');
  document.getElementById('sp-conferma').textContent = t('js_sp_metti');
  document.getElementById('sp-iframe').title = t('js_sp_titolo');

  document.getElementById('sp-pagina').addEventListener('change', loadPointPage);
  document.getElementById('sp-elenco').addEventListener('change', function() {
    var indice = parseInt(this.value, 10);
    choosePointBlock(isNaN(indice) ? null : puntoBlocchi[indice], true);
  });
  var radio = finestra.querySelectorAll('input[name="sp-dove"]');
  for (var i = 0; i < radio.length; i++) {
    radio[i].addEventListener('change', drawPointMark);
  }
  document.getElementById('sp-annulla').addEventListener('click', function() { finestra.close(); });
  document.getElementById('sp-conferma').addEventListener('click', confirmPoint);
  document.getElementById('sp-iframe').addEventListener('load', preparePointPage);
  return finestra;
}

function loadPointPage() {
  puntoBlocchi = [];
  puntoScelto = null;
  document.getElementById('sp-elenco').innerHTML = '';
  document.getElementById('sp-conferma').disabled = true;
  var slug = document.getElementById('sp-pagina').value;
  document.getElementById('sp-iframe').src = '/scegli-punto' + (slug ? '?slug=' + encodeURIComponent(slug) : '');
}

// The page has loaded in the frame: list its blocks, light them up on hover,
// and stop its links and forms - here a click chooses, it does not go.
function preparePointPage() {
  var cornice = document.getElementById('sp-iframe');
  var doc = cornice.contentDocument;
  if (!doc || !doc.body) { return; }
  var stile = doc.createElement('style');
  stile.textContent =
    '.pb-sp-sopra { outline:2px dashed #0066cc !important; outline-offset:3px; cursor:pointer !important; }' +
    '.pb-sp-scelto { outline:3px solid #0066cc !important; outline-offset:3px; }' +
    '.pb-sp-segno { margin:8px 0; padding:10px 14px; border:2px dashed #0066cc; border-radius:8px;' +
    ' background:#e8f1fb; color:#0057ad; font:600 14px/1.4 system-ui, sans-serif; text-align:center; }';
  doc.head.appendChild(stile);

  puntoBlocchi = pointBlocksOf(doc);
  var elenco = document.getElementById('sp-elenco');
  elenco.innerHTML = '';
  var vuota = document.createElement('option');
  vuota.value = '';
  vuota.textContent = t('js_sp_scegli');
  elenco.appendChild(vuota);
  for (var i = 0; i < puntoBlocchi.length; i++) {
    var o = document.createElement('option');
    o.value = String(i);
    o.textContent = describeBlock(puntoBlocchi[i]);
    elenco.appendChild(o);
  }

  var sopra = null;
  doc.addEventListener('mouseover', function(evento) {
    var blocco = pointBlockFrom(evento.target);
    if (sopra && sopra !== blocco) { sopra.classList.remove('pb-sp-sopra'); }
    sopra = blocco;
    if (blocco) { blocco.classList.add('pb-sp-sopra'); }
  });
  doc.addEventListener('click', function(evento) {
    evento.preventDefault();
    evento.stopPropagation();
    var blocco = pointBlockFrom(evento.target);
    if (blocco) { choosePointBlock(blocco, false); }
  }, true);
  doc.addEventListener('submit', function(evento) { evento.preventDefault(); }, true);

  // A point already saved is found again, when this page has it.
  var salvato = puntoScheda ? puntoScheda.querySelector('.codice-ancora').value : '';
  if (salvato !== '') {
    var trovato = null;
    try { trovato = doc.querySelector(salvato); } catch (e) { trovato = null; }
    if (trovato && puntoBlocchi.indexOf(trovato) !== -1) { choosePointBlock(trovato, true); }
  }
}

// The blocks that can be chosen: the children of the main containers that
// have a size, in the order of the page.
function pointBlocksOf(doc) {
  var blocchi = [];
  for (var i = 0; i < PUNTO_CONTENITORI.length; i++) {
    var contenitori = doc.querySelectorAll(PUNTO_CONTENITORI[i]);
    for (var c = 0; c < contenitori.length; c++) {
      var figli = contenitori[c].children;
      for (var f = 0; f < figli.length; f++) {
        var el = figli[f];
        var nome = el.tagName.toLowerCase();
        if (['script', 'style', 'template', 'link', 'meta', 'dialog'].indexOf(nome) !== -1) { continue; }
        if (el.classList.contains('skip-to-content') || el.classList.contains('pb-sp-segno')) { continue; }
        if (el.id === 'pb-consenso') { continue; }
        // The containers themselves are not chosen: their children are.
        var eContenitore = false;
        for (var k = 0; k < PUNTO_CONTENITORI.length; k++) {
          if (el.matches(PUNTO_CONTENITORI[k])) { eContenitore = true; }
        }
        if (eContenitore) { continue; }
        var r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) { continue; }
        if (blocchi.indexOf(el) === -1) { blocchi.push(el); }
      }
    }
  }
  blocchi.sort(function(a, b) {
    return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
  });
  return blocchi;
}

function pointBlockFrom(nodo) {
  while (nodo && nodo.nodeType === 1) {
    if (puntoBlocchi.indexOf(nodo) !== -1) { return nodo; }
    nodo = nodo.parentElement;
  }
  return null;
}

function choosePointBlock(blocco, scorri) {
  var precedente = puntoScelto;
  if (precedente) { precedente.classList.remove('pb-sp-scelto'); }
  puntoScelto = blocco;
  document.getElementById('sp-conferma').disabled = blocco === null;
  document.getElementById('sp-elenco').value = blocco ? String(puntoBlocchi.indexOf(blocco)) : '';
  if (blocco) {
    blocco.classList.add('pb-sp-scelto');
    if (scorri) { blocco.scrollIntoView({ block: 'center' }); }
  }
  drawPointMark();
}

// The dashed box that shows where the code will go.
function drawPointMark() {
  var doc = document.getElementById('sp-iframe').contentDocument;
  if (!doc) { return; }
  var vecchio = doc.querySelector('.pb-sp-segno');
  if (vecchio) { vecchio.parentNode.removeChild(vecchio); }
  if (!puntoScelto) { return; }
  var segno = doc.createElement('div');
  segno.className = 'pb-sp-segno';
  var nome = puntoScheda ? puntoScheda.querySelector('.codice-nome').value.trim() : '';
  segno.textContent = puntoT('js_sp_qui', { name: nome || t('admin_codice_senza_nome') });
  if (pointSide() === 'before') {
    puntoScelto.parentNode.insertBefore(segno, puntoScelto);
  } else {
    puntoScelto.parentNode.insertBefore(segno, puntoScelto.nextSibling);
  }
}

function pointSide() {
  var scelto = document.querySelector('input[name="sp-dove"]:checked');
  return scelto ? scelto.value : 'after';
}

// A selector that names the block the same way on every page of its kind:
// an id or a class found once on the page, otherwise its place among the
// elements of the same tag inside such a parent.
function pointSelector(el) {
  var doc = el.ownerDocument;
  var nome = el.tagName.toLowerCase();
  if (nome === 'body') { return 'body'; }
  if (el.id && el.id !== 'content' && doc.querySelectorAll('#' + CSS.escape(el.id)).length === 1) {
    return '#' + CSS.escape(el.id);
  }
  for (var i = 0; i < el.classList.length; i++) {
    var classe = el.classList[i];
    if (classe.indexOf('pb-sp-') === 0) { continue; }
    var candidato = nome + '.' + CSS.escape(classe);
    if (doc.querySelectorAll(candidato).length === 1) { return candidato; }
  }
  var posto = 1;
  for (var fratello = el.previousElementSibling; fratello; fratello = fratello.previousElementSibling) {
    if (fratello.tagName === el.tagName && !fratello.classList.contains('pb-sp-segno')) { posto++; }
  }
  return pointSelector(el.parentElement) + ' > ' + nome + ':nth-of-type(' + posto + ')';
}

// The place of an element among the ones of its tag in its parent.
function pointOrdinal(el) {
  var posto = 1;
  for (var f = el.previousElementSibling; f; f = f.previousElementSibling) {
    if (f.tagName === el.tagName && !f.classList.contains('pb-sp-segno')) { posto++; }
  }
  return posto;
}

// A name for a block that the author recognises on any page of its kind.
function describeBlock(el) {
  var c = el.classList;
  var nome = el.tagName.toLowerCase();
  var genitore = el.parentElement;
  if (nome === 'header') { return t('js_pd_intestazione'); }
  if (nome === 'footer') { return t('js_pd_piede'); }
  if (c.contains('barra-argomenti')) { return t('js_pd_argomenti'); }
  if (c.contains('home-intro')) { return t('js_pd_presentazione'); }
  if (c.contains('home-biografia')) { return t('js_pd_biografia'); }
  if (c.contains('home-progetti')) { return t('js_pd_progetti'); }
  if (c.contains('articles-section')) { return t('js_pd_elenco'); }
  if (c.contains('articles-head')) { return t('js_pd_testata_elenco'); }
  if (c.contains('art-row')) { return puntoT('js_pd_articolo_n', { n: pointOrdinal(el) }); }
  if (c.contains('paginazione')) { return t('js_pd_paginazione'); }
  if (c.contains('box')) {
    var titolo = el.querySelector('.box-titolo');
    if (titolo && titolo.textContent.trim() !== '') {
      return puntoT('js_pd_riquadro', { title: titolo.textContent.trim() });
    }
    return puntoT('js_pd_riquadro_n', { n: pointOrdinal(el) });
  }
  if (c.contains('language-switcher')) { return t('js_pd_lingue'); }
  if (c.contains('breadcrumbs')) { return t('js_pd_percorso'); }
  if (nome === 'h1') { return t('js_pd_titolo'); }
  if (c.contains('meta')) { return t('js_pd_meta'); }
  if (c.contains('articolo-copertina')) { return t('js_pd_copertina'); }
  if (c.contains('toc-telefono')) { return t('js_pd_indice'); }
  if (c.contains('post-content')) { return t('js_pd_testo'); }
  if (c.contains('author-box')) { return t('js_pd_autore'); }
  if (c.contains('article-nav')) { return t('js_pd_navigazione'); }
  if (c.contains('post-ritorno')) { return t('js_pd_ritorno'); }
  if (c.contains('related-articles')) { return t('js_pd_correlati'); }
  if (c.contains('commenti')) { return t('js_pd_commenti'); }
  if (genitore && genitore.classList.contains('post-content')) {
    var n = pointOrdinal(el);
    if (nome === 'p') {
      if (el.querySelector('img') && el.textContent.trim() === '') { return puntoT('js_pd_immagine', { n: n }); }
      return puntoT('js_pd_paragrafo', { n: n });
    }
    if (/^h[2-6]$/.test(nome)) {
      var testo = el.textContent.trim();
      if (testo.length > 40) { testo = testo.slice(0, 40) + '…'; }
      return puntoT('js_pd_titoletto', { n: n, text: testo });
    }
    if (nome === 'ul' || nome === 'ol') { return puntoT('js_pd_elenco_testo', { n: n }); }
    if (nome === 'figure' || nome === 'img') { return puntoT('js_pd_immagine', { n: n }); }
    if (nome === 'pre') { return puntoT('js_pd_codice', { n: n }); }
    if (nome === 'blockquote') { return puntoT('js_pd_citazione', { n: n }); }
    if (nome === 'table') { return puntoT('js_pd_tabella', { n: n }); }
  }
  return puntoT('js_pd_blocco', { n: pointOrdinal(el), tag: nome });
}

// "Put it here": the card gets the point, its summary says where, and the
// form knows something changed.
function confirmPoint() {
  if (!puntoScelto || !puntoScheda) { return; }
  var lato = pointSide();
  var etichetta = t(lato === 'before' ? 'js_pd_prima' : 'js_pd_dopo') + ' · ' + describeBlock(puntoScelto);
  puntoScheda.querySelector('.codice-ancora').value = pointSelector(puntoScelto);
  puntoScheda.querySelector('.codice-ancora-dove').value = lato;
  puntoScheda.querySelector('.codice-ancora-etichetta').value = etichetta;
  puntoScheda.querySelector('.codice-ancora-pagina').value =
    document.getElementById('sp-pagina').value === '' ? 'home' : 'article';
  puntoScheda.querySelector('.codice-punto-testo').textContent = etichetta;
  var posizione = puntoScheda.querySelector('.codice-posizione');
  posizione.value = 'anchor';
  posizione.dispatchEvent(new Event('change', { bubbles: true }));
  document.getElementById('scelta-punto').close();
  puntoScheda.querySelector('.codice-punto .pulsante').focus();
}


/* --- Earlier versions of an article --------------------------------------- */

// The window lists the versions kept by the saves, newest first; choosing
// one shows it, and "Bring back into the editor" puts its texts in the
// fields. Nothing is saved: the author saves to keep it, as with any edit.
// The address, the status and the article's own code stay as they are.

var versioneMostrata = null;

function versionsWindow() {
  var finestra = document.getElementById('finestra-versioni');
  if (finestra) { return finestra; }
  finestra = document.createElement('dialog');
  finestra.id = 'finestra-versioni';
  finestra.className = 'finestra-versioni';
  finestra.setAttribute('aria-labelledby', 'versioni-titolo');
  finestra.innerHTML =
    '<div class="fv-testata"><h2 id="versioni-titolo"></h2>' +
      '<button type="button" class="pulsante pulsante-testo" id="fv-chiudi"></button></div>' +
    '<div class="fv-corpo">' +
      '<ul class="fv-elenco" id="fv-elenco"></ul>' +
      '<div class="fv-vista" id="fv-vista" tabindex="-1">' +
        '<p class="aiuto" id="fv-vuota"></p>' +
        '<div id="fv-contenuto" hidden>' +
          '<p class="fv-quando" id="fv-quando"></p><h3 id="fv-titolo-articolo"></h3>' +
          '<div class="ql-snow"><div class="ql-editor fv-testo" id="fv-testo"></div></div>' +
        '</div>' +
      '</div>' +
    '</div>' +
    '<div class="fv-piede"><button type="button" class="pulsante pulsante-primario" id="fv-ripristina" disabled></button></div>';
  document.body.appendChild(finestra);
  document.getElementById('versioni-titolo').textContent = t('admin_versioni');
  document.getElementById('fv-chiudi').textContent = t('admin_chiudi');
  document.getElementById('fv-ripristina').textContent = t('js_versione_ripristina');
  document.getElementById('fv-chiudi').addEventListener('click', function() { finestra.close(); });
  document.getElementById('fv-ripristina').addEventListener('click', restoreVersion);
  return finestra;
}

function versionStatusLabel(stato) {
  if (stato === 'published') { return t('admin_stato_pubblicato'); }
  if (stato === 'scheduled') { return t('admin_stato_programmato'); }
  return t('admin_stato_bozza');
}

function openVersions() {
  var finestra = versionsWindow();
  versioneMostrata = null;
  document.getElementById('fv-ripristina').disabled = true;
  document.getElementById('fv-contenuto').hidden = true;
  document.getElementById('fv-vuota').textContent = '';
  var elenco = document.getElementById('fv-elenco');
  elenco.innerHTML = '';
  finestra.showModal();
  fetch('/versioni?slug=' + encodeURIComponent(slugOriginale), { credentials: 'same-origin' })
    .then(function(r) { return r.json(); })
    .then(function(res) {
      var versioni = res.versions || [];
      if (versioni.length === 0) {
        document.getElementById('fv-vuota').textContent = t('js_versioni_vuoto');
        return;
      }
      document.getElementById('fv-vuota').textContent = t('js_versione_scegli');
      for (var i = 0; i < versioni.length; i++) {
        var v = versioni[i];
        var voce = document.createElement('li');
        var pulsante = document.createElement('button');
        pulsante.type = 'button';
        pulsante.className = 'fv-voce';
        pulsante.setAttribute('aria-pressed', 'false');
        pulsante.dataset.id = v.id;
        var quando = document.createElement('span');
        quando.className = 'fv-voce-quando';
        quando.textContent = formatMoment(v.saved_at);
        var dettagli = document.createElement('span');
        dettagli.className = 'fv-voce-dettagli';
        dettagli.textContent = versionStatusLabel(v.status) + ' · ' +
          t('js_versione_parole').replace('{n}', v.words) + ' · ' + v.title;
        pulsante.appendChild(quando);
        pulsante.appendChild(dettagli);
        pulsante.addEventListener('click', showVersion);
        voce.appendChild(pulsante);
        elenco.appendChild(voce);
      }
      elenco.querySelector('.fv-voce').focus();
    })
    .catch(function() { document.getElementById('fv-vuota').textContent = t('js_versione_errore'); });
}

function showVersion(evento) {
  var pulsante = evento.currentTarget;
  var voci = document.querySelectorAll('#fv-elenco .fv-voce');
  for (var i = 0; i < voci.length; i++) { voci[i].setAttribute('aria-pressed', voci[i] === pulsante ? 'true' : 'false'); }
  fetch('/versione?slug=' + encodeURIComponent(slugOriginale) + '&id=' + encodeURIComponent(pulsante.dataset.id),
        { credentials: 'same-origin' })
    .then(function(r) { return r.json(); })
    .then(function(res) {
      if (!res.ok) { pbToast(t('js_versione_errore'), 'danger'); return; }
      versioneMostrata = res.version;
      versioneMostrata._quando = pulsante.querySelector('.fv-voce-quando').textContent;
      document.getElementById('fv-vuota').textContent = '';
      document.getElementById('fv-contenuto').hidden = false;
      document.getElementById('fv-quando').textContent = versioneMostrata._quando + ' · ' + versionStatusLabel(versioneMostrata.status);
      document.getElementById('fv-titolo-articolo').textContent = versioneMostrata.title || '';
      // The article's own HTML, written by the author: the same trust as
      // the editor, and the admin CSP stops any script in it.
      document.getElementById('fv-testo').innerHTML = versioneMostrata.content || '';
      document.getElementById('fv-ripristina').disabled = false;
    })
    .catch(function() { pbToast(t('js_versione_errore'), 'danger'); });
}

function restoreVersion() {
  if (!versioneMostrata) { return; }
  var applica = function() {
    var v = versioneMostrata;
    var campi = { title: 'title', description: 'description', preview: 'reader_preview', tags: 'tags',
                  series: 'series', series_number: 'series_number', lab_of: 'lab_of',
                  repo_url: 'repo_url', stack: 'stack',
                  image: 'image', title_en: 'title_en', description_en: 'description_en', preview_en: 'preview_en' };
    for (var chiave in campi) {
      var campo = document.getElementById(campi[chiave]);
      if (campo) { campo.value = v[chiave] || ''; }
    }
    quill.root.innerHTML = v.content || '';
    quillEn.root.innerHTML = v.content_en || '';
    document.getElementById('translation_authorized').checked = v.translation_authorized === true;
    document.getElementById('translation_confirmed').checked = v.translation_confirmed === true;
    document.getElementById('kind_lab').checked = v.kind === 'lab';
    toggleLabFields();
    updateTranslationSection();
    updateCoverPreview();
    updateDescriptionCounter();
    updatePreviewCounter();
    markEditorDirty();
    var finestra = document.getElementById('finestra-versioni');
    if (finestra.open) { finestra.close(); }
    pbToast(t('js_versione_ripristinata').replace('{date}', v._quando), 'success');
    document.getElementById('title').focus();
  };
  if (editorDirty) {
    // A <dialog> sits above everything, the confirmation window included:
    // it closes first, so the question can be seen and answered.
    document.getElementById('finestra-versioni').close();
    pbConfirm(t('js_versione_ripristina'), t('js_versione_perdi'), t('js_versione_ripristina'), 'primary', applica);
  } else {
    applica();
  }
}


/* --- Newsletter ------------------------------------------------------------ */

// The newsletter fields of the Settings, as saved. An empty password keeps
// the one already saved (the server sees to that).
function newsletterData() {
  var valore = function(id) { return document.getElementById(id).value.trim(); };
  return {
    enabled: document.getElementById('nl_enabled').checked,
    in_sidebar: document.getElementById('nl_in_sidebar').checked,
    after_article: document.getElementById('nl_after_article').checked,
    send_on_publish: document.getElementById('nl_send_on_publish').checked,
    title: valore('nl_title'),
    text: valore('nl_text'),
    sender_name: valore('nl_sender_name'),
    sender_email: valore('nl_sender_email'),
    smtp_host: valore('nl_smtp_host'),
    smtp_port: parseInt(valore('nl_smtp_port'), 10) || 587,
    smtp_security: document.getElementById('nl_smtp_security').value,
    smtp_user: valore('nl_smtp_user'),
    smtp_password: document.getElementById('nl_smtp_password').value
  };
}

// A test email with what is written in the form, saved or not.
function sendNewsletterTest(pulsante) {
  pbBusy(pulsante, true);
  pbStatus('nl-prova-stato', '');
  pbPostJson('/newsletter-prova', newsletterData())
    .then(function(res) {
      pbBusy(pulsante, false);
      if (res.ok) {
        pbToast(t('js_nl_prova_ok').replace('{to}', res.to), 'success');
      } else {
        pbToast(t('js_nl_prova_errore').replace('{error}', res.error), 'danger');
      }
    })
    .catch(function() {
      pbBusy(pulsante, false);
      pbToast(t('js_nl_prova_errore').replace('{error}', ''), 'danger');
    });
}

function removeSubscriber(pulsante) {
  var email = pulsante.getAttribute('data-email');
  pbConfirm(t('js_nl_rimuovi_titolo'), email, t('admin_nl_rimuovi'), 'danger', function() {
    pbPostJson('/newsletter-rimuovi', { email: email })
      .then(function(res) {
        if (res.ok) {
          pulsante.closest('li').remove();
          pbToast(t('js_nl_rimosso').replace('{email}', email), 'success');
        }
      });
  });
}

// In the editor: whether the subscribers hear about this article.
// The fields of a lab show only on an article ticked as one.
function toggleLabFields() {
  document.getElementById('campi-lab').hidden = !document.getElementById('kind_lab').checked;
}

function notifySubscribers() {
  var spunta = document.getElementById('notify_subscribers');
  return spunta ? spunta.checked : true;
}
