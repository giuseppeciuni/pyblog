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
function t(key) {
  if (window.PB_I18N && window.PB_I18N[key] !== undefined) {
    return window.PB_I18N[key];
  }
  return key;
}

// Returns a page value injected by the template.
function pbPage(key, defaultValue) {
  if (window.PB_PAGE && window.PB_PAGE[key] !== undefined) {
    return window.PB_PAGE[key];
  }
  return defaultValue;
}

// Every state-changing request goes through here, so the CSRF token is never
// forgotten: the server rejects a POST that arrives without it.
function pbFetch(url, options) {
  if (!options) {
    options = {};
  }
  if (!options.headers) {
    options.headers = {};
  }
  options.headers['X-CSRF-Token'] = window.PB_CSRF || '';
  return fetch(url, options);
}

// Shorthand for the common case: a POST with a JSON body.
function pbPostJson(url, payload) {
  return pbFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).then(function(r) { return r.json(); });
}

// Writes a message in a status element, if that element exists on the page.
function pbStatus(elementId, textValue) {
  var element = document.getElementById(elementId);
  if (element) {
    element.textContent = textValue;
  }
}

/* --- Feedback: toasts, confirmation modal, busy buttons ------------------- */

// Shows a Bootstrap toast. It replaces alert(), which blocks the page, steals
// the focus and cannot say whether something went well or badly.
// kind is a Bootstrap colour: success, danger, warning or info.
function pbToast(message, kind) {
  var containerEl = document.getElementById('pb-toasts');
  if (!containerEl || !window.bootstrap) {
    // Without Bootstrap we still have to tell the author something.
    alert(message);
    return;
  }
  if (!kind) { kind = 'success'; }

  var toast = document.createElement('div');
  toast.className = 'toast align-items-center text-bg-' + kind + ' border-0';
  toast.setAttribute('role', 'status');
  toast.setAttribute('aria-live', 'polite');
  toast.setAttribute('aria-atomic', 'true');

  var row = document.createElement('div');
  row.className = 'd-flex';
  var bodyEl = document.createElement('div');
  bodyEl.className = 'toast-body';
  // textContent, never innerHTML: a message can carry a server error, and an
  // error can carry anything.
  bodyEl.textContent = message;
  var closeIt = document.createElement('button');
  closeIt.type = 'button';
  closeIt.className = 'btn-close btn-close-white me-2 m-auto';
  closeIt.setAttribute('data-bs-dismiss', 'toast');
  closeIt.setAttribute('aria-label', t('admin_close'));
  row.appendChild(bodyEl);
  row.appendChild(closeIt);
  toast.appendChild(row);
  containerEl.appendChild(toast);

  var delay = 4000;
  if (kind === 'danger' || kind === 'warning') { delay = 8000; }
  var instance = new bootstrap.Toast(toast, { delay: delay });
  toast.addEventListener('hidden.bs.toast', function() { toast.remove(); });
  instance.show();
}

// Asks the author to confirm a destructive or overwriting action, using the
// Bootstrap modal in the layout instead of the browser's confirm(), which
// cannot be styled and gives no room to explain the consequence.
function pbConfirm(titleText, bodyEl, confirmLabel, kind, onConfirmed) {
  var popup = document.getElementById('pb-confirm');
  if (!popup || !window.bootstrap) {
    if (confirm(titleText + '\n\n' + bodyEl)) { onConfirmed(); }
    return;
  }
  document.getElementById('pb-confirm-title').textContent = titleText;
  document.getElementById('pb-confirm-body').textContent = bodyEl;

  var oldValue = document.getElementById('pb-confirm-ok');
  // Replacing the button drops every listener a previous call attached, so
  // confirming twice cannot fire the first action again.
  var confirmButton = oldValue.cloneNode(false);
  confirmButton.textContent = confirmLabel;
  // The buttons of the shared family: a deleting action is red.
  confirmButton.className = 'button button-primary' + (kind === 'danger' ? ' button-danger' : '');
  oldValue.parentNode.replaceChild(confirmButton, oldValue);

  var instance = bootstrap.Modal.getOrCreateInstance(popup);
  confirmButton.addEventListener('click', function() {
    instance.hide();
    onConfirmed();
  });
  instance.show();
}

// Puts a button in its waiting state and back. The label is left alone: only
// a spinner appears in front of it, so the button keeps its width and the
// author is not shown a different word every time something is slow.
function pbBusy(buttonEl, busy) {
  if (!buttonEl) { return; }
  if (busy) {
    if (buttonEl.querySelector('.pb-spinner')) { return; }
    var spinner = document.createElement('span');
    spinner.className = 'pb-spinner';
    spinner.setAttribute('aria-hidden', 'true');
    buttonEl.insertBefore(spinner, buttonEl.firstChild);
    buttonEl.disabled = true;
    buttonEl.setAttribute('aria-busy', 'true');
  } else {
    var existing = buttonEl.querySelector('.pb-spinner');
    if (existing) { existing.remove(); }
    buttonEl.disabled = false;
    buttonEl.removeAttribute('aria-busy');
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
function attachImageOverlay(quillInstance) {
  if (!quillInstance) { return; }
  var formatter = quillInstance.getModule('blotFormatter');
  if (!formatter) { return; }

  function reposition() {
    // No image selected: there is nothing to reposition.
    if (!formatter.currentSpec) { return; }
    // When the paragraph formatting changes, Quill may recreate the
    // image from scratch: the box would point to an element that is no
    // longer in the page. In that case we hide it.
    if (typeof formatter.currentSpec.getTargetElement === 'function') {
      var targetEl = formatter.currentSpec.getTargetElement();
      if (targetEl && !document.contains(targetEl)) {
        if (typeof formatter.hide === 'function') { formatter.hide(); }
        return;
      }
    }
    // update() recomputes both the box and the corner handles.
    // If the library version does not expose it, we fall back to
    // repositioning the box alone.
    if (typeof formatter.update === 'function') {
      formatter.update();
    } else if (typeof formatter.repositionOverlay === 'function') {
      formatter.repositionOverlay();
    }
  }

  // We wait for the browser to finish repainting: before the repaint
  // we would still read the old position of the image.
  function repositionAfterPaint() {
    window.requestAnimationFrame(reposition);
  }

  // 1) Any text or format change, including the "centre" button
  //    of the toolbar.
  quillInstance.on('editor-change', repositionAfterPaint);

  // 2) Style or class changes inside the editor: these are what really
  //    move the image (Quill puts the ql-align-center class on the
  //    paragraph, and resizing writes width/height on the image).
  //    The box lives outside .ql-editor, so it does not self-trigger.
  if (window.MutationObserver) {
    var observer = new MutationObserver(repositionAfterPaint);
    observer.observe(quillInstance.root, {
      attributes: true, childList: true, subtree: true,
      attributeFilter: ['style', 'class', 'width', 'height', 'align']
    });
  }

  // 3) A freshly inserted image changes size when it finishes
  //    loading, i.e. after the box has already been drawn.
  quillInstance.root.addEventListener('load', repositionAfterPaint, true);

  // 4) Window resizing and editor scrolling.
  window.addEventListener('resize', repositionAfterPaint);
  quillInstance.root.addEventListener('scroll', repositionAfterPaint);
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
function handlePastedImages(quillInstance, statusElementId) {
  quillInstance.root.addEventListener('paste', function(evt) {
    if (!evt.clipboardData) { return; }

    var imageElements = [];
    for (var i = 0; i < evt.clipboardData.items.length; i++) {
      var entryEl = evt.clipboardData.items[i];
      if (entryEl.type && entryEl.type.indexOf('image/') === 0) {
        imageElements.push(entryEl);
      }
    }
    // No embedded images in this paste: let Quill handle it as usual
    // (plain text, or a paste that already has no images at all).
    if (imageElements.length === 0) {
      // Some sources (Word on Windows, when you copy text together with a
      // picture) put in the clipboard only a broken local reference
      // ("file:///C:/Users/.../image1.png") and no actual image data at
      // all: a web page has no way to read a local file path for security
      // reasons, so there is nothing here to recover. We at least warn the
      // author instead of letting the picture disappear with no
      // explanation (a plain web page copy does not have this problem:
      // browsers normally embed the picture itself in that HTML).
      var noticeState = statusElementId ? document.getElementById(statusElementId) : null;
      if (noticeState && hasUnrecoverableImage(evt.clipboardData.getData('text/html'))) {
        noticeState.textContent = t('js_pasted_word_image_unavailable');
      }
      return;
    }

    var pastedHtml = evt.clipboardData.getData('text/html');
    // No HTML at all: a single image was copied on its own (e.g. from
    // an image viewer), not part of a larger document paste. Quill's own
    // built-in image paste handling already covers that case.
    if (!pastedHtml) { return; }

    // From here on we take full control of this paste.
    evt.preventDefault();
    evt.stopPropagation();

    var state = null;
    if (statusElementId) {
      state = document.getElementById(statusElementId);
    }
    if (state) { state.textContent = t('js_recovering_pasted_images'); }

    // The <img> tags found in the pasted HTML, in the order they appear,
    // together with the width/height they declare (if any). This is what
    // lets us pair each tag with the right clipboard image further down,
    // instead of just trusting the order they came in.
    var imageTag = [];
    var regexTagImg = /<img\b[^>]*>/gi;
    var found = regexTagImg.exec(pastedHtml);
    while (found !== null) {
      imageTag.push({
        width: readDeclaredWidth(found[0]),
        height: readDeclaredHeight(found[0])
      });
      found = regexTagImg.exec(pastedHtml);
    }

    // We upload every clipboard image and, in parallel, decode it locally
    // to read its real pixel size: we need that size to pair it safely
    // with the right <img> tag.
    var operations = [];
    for (var j = 0; j < imageElements.length; j++) {
      var currentBlob = imageElements[j].getAsFile();
      operations.push(Promise.all([uploadImageBlob(currentBlob), readBlobSize(currentBlob)]));
    }

    Promise.all(operations).then(function(results) {
      var uploadedImages = [];
      for (var k = 0; k < results.length; k++) {
        var realSize = results[k][1];
        uploadedImages.push({
          url: results[k][0],
          width: realSize ? realSize.width : null,
          height: realSize ? realSize.height : null,
          used: false
        });
      }

      // 1) Tags with a declared size are paired only with a clipboard
      //    image whose real size matches (within a small tolerance for
      //    Word/Google Docs rounding). This is what stops a flattened
      //    text+image screenshot from being mistaken for a real picture.
      var assignments = [];
      for (var t1 = 0; t1 < imageTag.length; t1++) {
        assignments.push(null);
      }
      for (var t2 = 0; t2 < imageTag.length; t2++) {
        var currentTag = imageTag[t2];
        if (currentTag.width === null || currentTag.height === null) { continue; }
        var foundIndex = findImageOfMatchingSize(currentTag, uploadedImages);
        if (foundIndex !== null) {
          assignments[t2] = uploadedImages[foundIndex].url;
          uploadedImages[foundIndex].used = true;
        }
      }

      // 2) Tags with no declared size cannot be verified: we fall back to
      //    pairing them in order with whatever images are still unused,
      //    but only if their counts match exactly. This keeps the old,
      //    simple behaviour for the common case (a plain paste with no
      //    size hints at all, where there is no ambiguity to resolve).
      var uncoveredTags = [];
      for (var t3 = 0; t3 < imageTag.length; t3++) {
        if (assignments[t3] === null) { uncoveredTags.push(t3); }
      }
      var freeImages = uploadedImages.filter(function(im) { return !im.used; });
      if (uncoveredTags.length === freeImages.length) {
        for (var m = 0; m < uncoveredTags.length; m++) {
          assignments[uncoveredTags[m]] = freeImages[m].url;
        }
      }

      // We rebuild the HTML: each <img> tag with a safe pairing is
      // replaced with its uploaded URL; the others are dropped rather
      // than risking a wrong image ending up in their place.
      var tagIndex = 0;
      var htmlFinale = pastedHtml.replace(/<img\b[^>]*>/gi, function() {
        var assignedUrl = assignments[tagIndex];
        tagIndex = tagIndex + 1;
        if (assignedUrl === null || assignedUrl === undefined) { return ''; }
        return '<img src="' + assignedUrl + '">';
      });
      var placement = quillInstance.getSelection(true) || { index: quillInstance.getLength() };
      quillInstance.clipboard.dangerouslyPasteHTML(placement.index, htmlFinale);
      if (state) {
        var succeeded = 0;
        for (var n = 0; n < assignments.length; n++) {
          if (assignments[n] !== null && assignments[n] !== undefined) { succeeded = succeeded + 1; }
        }
        if (succeeded === imageTag.length) {
          state.textContent = t('js_pasted_all_recovered').replace('{n}', succeeded);
        } else {
          state.textContent = t('js_pasted_partial_recovered')
            .replace('{ok}', succeeded).replace('{tot}', imageTag.length);
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
function hasUnrecoverableImage(html) {
  if (!html) { return false; }
  var regexTag = /<img\b[^>]*>/gi;
  var tag = regexTag.exec(html);
  while (tag !== null) {
    var srcMatch = tag[0].match(/\bsrc\s*=\s*["']([^"']*)["']/i);
    var address = srcMatch ? srcMatch[1] : '';
    if (!/^(https?:|data:|\/)/i.test(address)) {
      return true;
    }
    tag = regexTag.exec(html);
  }
  return false;
}

// Reads the width a pasted <img> tag declares, either as a plain HTML
// attribute (width="200") or as an inline style (style="width:200px").
// Returns null when the tag declares no width at all.
function readDeclaredWidth(tag) {
  var attributeMatch = tag.match(/\bwidth\s*=\s*"(\d+)/i);
  if (attributeMatch) { return parseInt(attributeMatch[1], 10); }
  var styleMatch = tag.match(/width\s*:\s*(\d+)px/i);
  if (styleMatch) { return parseInt(styleMatch[1], 10); }
  return null;
}

// Same as readDeclaredWidth, for the height.
function readDeclaredHeight(tag) {
  var attributeMatch = tag.match(/\bheight\s*=\s*"(\d+)/i);
  if (attributeMatch) { return parseInt(attributeMatch[1], 10); }
  var styleMatch = tag.match(/height\s*:\s*(\d+)px/i);
  if (styleMatch) { return parseInt(styleMatch[1], 10); }
  return null;
}

// Decodes an image blob locally to read its real pixel size. Resolves to
// null if the blob turns out not to be a valid image.
function readBlobSize(blob) {
  return new Promise(function(resolve) {
    var temporaryAddress = URL.createObjectURL(blob);
    var img = new Image();
    img.onload = function() {
      URL.revokeObjectURL(temporaryAddress);
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.onerror = function() {
      URL.revokeObjectURL(temporaryAddress);
      resolve(null);
    };
    img.src = temporaryAddress;
  });
}

// Looks, among the uploaded images not yet paired, for one whose real
// pixel size matches the size declared by the pasted tag (with a small
// tolerance for Word/Google Docs rounding). Returns its index in
// uploadedImages, or null when none matches closely enough.
function findImageOfMatchingSize(currentTag, uploadedImages) {
  var tolerance = 3; // pixel di margine per arrotondamenti/DPI
  for (var i = 0; i < uploadedImages.length; i++) {
    var img = uploadedImages[i];
    if (img.used) { continue; }
    if (img.width === null) { continue; }
    var widthDiff = Math.abs(img.width - currentTag.width);
    var heightDiff = Math.abs(img.height - currentTag.height);
    if (widthDiff <= tolerance && heightDiff <= tolerance) {
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
  var formValues = new FormData();
  var extension = 'png';
  if (blob.type && blob.type.split('/')[1]) {
    extension = blob.type.split('/')[1];
  }
  formValues.append('video', blob, 'pasted-image.' + extension);
  return pbFetch('/upload', { method: 'POST', body: formValues })
    .then(function(reply) { return reply.json(); })
    .then(function(resultValue) {
      if (resultValue.ok) {
        return resultValue.url;
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
  var mapping = {};
  if (window.PB_I18N && window.PB_I18N.tooltips) {
    mapping = window.PB_I18N.tooltips;
  }
  var bars = document.querySelectorAll('.ql-toolbar');
  for (var i = 0; i < bars.length; i++) {
    for (var selector in mapping) {
      var elements = bars[i].querySelectorAll(selector);
      for (var j = 0; j < elements.length; j++) {
        // The dropdowns (font, size, heading...) are wrapped in a
        // .ql-picker span: we put the tooltip on the wrapper, otherwise
        // it would follow the open list of options around.
        elements[j].setAttribute('data-tooltip', mapping[selector]);
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
  var snippetCode = '<div class="video-youtube">';
  snippetCode = snippetCode + '<iframe src="https://www.youtube.com/embed/' + idVideo + '"';
  snippetCode = snippetCode + ' allowfullscreen></iframe></div><p><br></p>';
  var placement = PB_MAIN_QUILL.getSelection(true);
  PB_MAIN_QUILL.clipboard.dangerouslyPasteHTML(placement.index, snippetCode);
}

// Refuses a file that is over the limit before a single byte is uploaded.
//
// The server refuses it too, but it does so by answering and closing the
// connection while the browser is still sending: the author would see a
// network error rather than a reason. Checking here turns that into a
// sentence that says what the limit is.
function fileFitsLimit(file, limitMb) {
  if (file.size <= limitMb * 1024 * 1024) {
    return true;
  }
  pbToast(t('err_file_too_large').replace('{n}', String(limitMb)), 'danger');
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
function resizeImageBeforeUpload(file, maxSide) {
  var shrinkable = ['image/png', 'image/jpeg'];
  if (!maxSide || shrinkable.indexOf(file.type) === -1) {
    return Promise.resolve(file);
  }

  return new Promise(function(resolveIt) {
    var address = URL.createObjectURL(file);
    var img = new Image();

    img.onload = function() {
      URL.revokeObjectURL(address);
      var width = img.naturalWidth;
      var height = img.naturalHeight;
      var side = Math.max(width, height);
      // The same threshold the server uses: trimming an image by a little is
      // not worth re-encoding it.
      if (side <= maxSide * 1.25) { resolveIt(file); return; }

      var scala = maxSide / side;
      var canvas = document.createElement('canvas');
      canvas.width = Math.round(width * scala);
      canvas.height = Math.round(height * scala);
      var context = canvas.getContext('2d');
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = 'high';
      context.drawImage(img, 0, 0, canvas.width, canvas.height);

      canvas.toBlob(function(blockEl) {
        // A re-encode that came out bigger, or a browser that refused: keep
        // what the author chose. The file name is unchanged, so it still
        // matches the type the server checks it against.
        if (!blockEl || blockEl.size >= file.size) { resolveIt(file); return; }
        var reduced = new File([blockEl], file.name, { type: file.type });
        pbToast(t('js_image_resized_local')
                  .replace('{w}', canvas.width).replace('{h}', canvas.height), 'info');
        resolveIt(reduced);
      }, file.type, 0.85);
    };

    img.onerror = function() {
      URL.revokeObjectURL(address);
      resolveIt(file);
    };
    img.src = address;
  });
}

function uploadChosenFile(fileFieldId, limitMb, stateId, startMessage) {
  var fileField = document.getElementById(fileFieldId);
  if (!fileField || fileField.files.length === 0) {
    return Promise.resolve(null);
  }
  var chosen = fileField.files[0];
  // Clearing the input now lets the same file be chosen again later: without
  // this the change event would not fire a second time. FormData already
  // holds the file, so the upload is unaffected.
  fileField.value = '';

  if (!fileFitsLimit(chosen, limitMb)) {
    return Promise.resolve(null);
  }

  pbStatus(stateId, startMessage);
  return resizeImageBeforeUpload(chosen, pbPage('max_image_width', 1600))
    .then(function(file) { return sendFile(file, stateId); });
}

function sendFile(file, stateId) {
  var formValues = new FormData();
  formValues.append('video', file);

  return pbFetch('/upload', { method: 'POST', body: formValues })
    .then(function(reply) { return reply.json(); })
    .then(function(resultValue) {
      if (resultValue.ok === true) {
        // The server says what it did with the file: shrank it, dropped the
        // metadata, or left it alone because it could not.
        if (resultValue.note) { pbToast(resultValue.note, 'info'); }
        return resultValue.url;
      }
      pbStatus(stateId, '');
      pbToast(t('js_error_prefix') + resultValue.error, 'danger');
      return null;
    })
    .catch(function() {
      pbStatus(stateId, '');
      pbToast(t('js_upload_error'), 'danger');
      return null;
    });
}

// Uploads a file and inserts the snippet built by buildCode() at the
// cursor. Used by the image and video buttons, on both admin pages.
function uploadMediaFile(fileFieldId, limitMb, startMessage, endMessage,
                         buildCode) {
  if (!PB_MAIN_QUILL) { return; }
  uploadChosenFile(fileFieldId, limitMb, 'upload-status', startMessage)
    .then(function(url) {
      if (url === null) { return; }
      var placement = PB_MAIN_QUILL.getSelection(true);
      PB_MAIN_QUILL.clipboard.dangerouslyPasteHTML(placement.index, buildCode(url));
      pbStatus('upload-status', endMessage);
    });
}

/* --- Alternative text and caption of a picture ------------------------------- */

// The alternative text describes a picture to Google Images and to whoever
// cannot see it; the caption is the line under it. Clicking a picture shows
// the button that edits both (a double click opens the window at once), and
// a line under the editor counts the pictures that still have no
// description. Everything goes through Quill, so the change is part of the
// text, saved with it and undone with Ctrl+Z.

var imageDetailsTarget = null;

function watchImageDescriptions(editor) {
  editor.root.addEventListener('click', function(event) {
    var button = document.getElementById('image-details-button');
    if (event.target.tagName === 'IMG') {
      imageDetailsTarget = { editor: editor, image: event.target };
      if (button) { button.hidden = false; }
    } else if (button) {
      button.hidden = true;
    }
  });
  editor.root.addEventListener('dblclick', function(event) {
    if (event.target.tagName === 'IMG') {
      imageDetailsTarget = { editor: editor, image: event.target };
      openImageDetails();
    }
  });
  var pending = null;
  editor.on('text-change', function() {
    clearTimeout(pending);
    pending = setTimeout(function() { countUndescribedImages(editor); }, 400);
  });
  countUndescribedImages(editor);
}

function undescribedImages(editor) {
  return Array.prototype.filter.call(editor.root.querySelectorAll('img'), function(image) {
    return (image.getAttribute('alt') || '').trim() === '';
  });
}

function countUndescribedImages(editor) {
  var line = document.getElementById('image-alt-status');
  if (!line) { return; }
  var missing = undescribedImages(editor).length;
  line.hidden = missing === 0;
  document.getElementById('image-alt-status-text').textContent = missing === 1
    ? t('js_image_alt_missing_one') : t('js_image_alt_missing').replace('{n}', missing);
}

// "Fix": the first picture without a description, selected and opened.
function describeNextImage() {
  var missing = undescribedImages(PB_MAIN_QUILL);
  if (missing.length === 0) { return; }
  missing[0].scrollIntoView({ block: 'center' });
  imageDetailsTarget = { editor: PB_MAIN_QUILL, image: missing[0] };
  openImageDetails();
}

// The block that holds the picture, and the caption under it if there is one.
function imageLines(editor, image) {
  var blot = Quill.find(image);
  var index = editor.getIndex(blot);
  var line = editor.getLine(index)[0];
  var next = line ? line.next : null;
  var caption = next && next.domNode.classList && next.domNode.classList.contains('image-caption') ? next : null;
  return { index: index, line: line, caption: caption };
}

function imageDetailsDialog() {
  var dialog = document.getElementById('image-details');
  if (dialog) { return dialog; }
  dialog = document.createElement('dialog');
  dialog.id = 'image-details';
  dialog.className = 'image-details';
  dialog.setAttribute('aria-labelledby', 'image-details-title');
  var title = document.createElement('h2');
  title.id = 'image-details-title';
  title.textContent = t('js_image_details_title');
  var preview = document.createElement('img');
  preview.id = 'image-details-preview';
  preview.alt = '';
  dialog.appendChild(title);
  dialog.appendChild(preview);
  [['image-details-alt', 'js_image_alt_label', 'js_image_alt_hint', 'textarea'],
   ['image-details-caption', 'js_image_caption_label', 'js_image_caption_hint', 'input']].forEach(function(field) {
    var wrapper = document.createElement('div');
    wrapper.className = 'field';
    var label = document.createElement('label');
    label.htmlFor = field[0];
    label.textContent = t(field[1]);
    var control = document.createElement(field[3]);
    control.id = field[0];
    control.className = 'field-input';
    if (field[3] === 'textarea') { control.rows = 2; } else { control.type = 'text'; }
    control.setAttribute('aria-describedby', field[0] + '-hint');
    var hint = document.createElement('p');
    hint.className = 'help';
    hint.id = field[0] + '-hint';
    hint.textContent = t(field[2]);
    wrapper.appendChild(label);
    wrapper.appendChild(control);
    wrapper.appendChild(hint);
    dialog.appendChild(wrapper);
  });
  var actions = document.createElement('div');
  actions.className = 'actions';
  var save = document.createElement('button');
  save.type = 'button';
  save.className = 'button button-primary';
  save.textContent = t('js_image_details_apply');
  save.addEventListener('click', applyImageDetails);
  var cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.className = 'button';
  cancel.textContent = t('admin_cancel');
  cancel.addEventListener('click', function() { dialog.close(); });
  actions.appendChild(save);
  actions.appendChild(cancel);
  dialog.appendChild(actions);
  document.body.appendChild(dialog);
  return dialog;
}

function openImageDetails() {
  if (!imageDetailsTarget || !document.contains(imageDetailsTarget.image)) { return; }
  var dialog = imageDetailsDialog();
  var image = imageDetailsTarget.image;
  var lines = imageLines(imageDetailsTarget.editor, image);
  document.getElementById('image-details-preview').src = image.getAttribute('src');
  document.getElementById('image-details-alt').value = image.getAttribute('alt') || '';
  document.getElementById('image-details-caption').value = lines.caption ? lines.caption.domNode.textContent : '';
  dialog.showModal();
  document.getElementById('image-details-alt').focus();
}

function applyImageDetails() {
  var editor = imageDetailsTarget.editor;
  var image = imageDetailsTarget.image;
  var alt = document.getElementById('image-details-alt').value.replace(/\s+/g, ' ').trim();
  var caption = document.getElementById('image-details-caption').value.replace(/\s+/g, ' ').trim();
  document.getElementById('image-details').close();
  if (!document.contains(image)) { return; }

  var lines = imageLines(editor, image);
  editor.formatText(lines.index, 1, 'alt', alt === '' ? false : alt, 'user');

  lines = imageLines(editor, image);
  if (caption !== '' && !lines.caption) {
    // A caption belongs to a picture that stands on its own line: one put
    // in the middle of a sentence is moved to a paragraph of its own first,
    // or the page could not show it as a picture with its caption.
    var start0 = editor.getIndex(lines.line);
    var end0 = start0 + lines.line.length() - 1;
    if (lines.index + 1 < end0) { editor.insertText(lines.index + 1, '\n', 'user'); }
    if (lines.index > start0) { editor.insertText(lines.index, '\n', 'user'); }
    lines = imageLines(editor, image);
  }
  if (lines.caption) {
    var start = editor.getIndex(lines.caption);
    if (caption === '') {
      editor.deleteText(start, lines.caption.length(), 'user');
    } else {
      editor.deleteText(start, lines.caption.length() - 1, 'user');
      editor.insertText(start, caption, 'user');
    }
  } else if (caption !== '') {
    // A new line right after the picture's, with the picture's alignment.
    // Quill gives an inserted line break no block format, so the picture's
    // line gets its alignment back, and the caption gets it and its class.
    var lineStart = editor.getIndex(lines.line);
    var align = editor.getFormat(lineStart).align || false;
    var end = lineStart + lines.line.length() - 1;
    editor.insertText(end, '\n' + caption, 'user');
    editor.formatLine(lineStart, 1, { align: align }, 'user');
    editor.formatLine(end + 1, 1, { align: align, imagecaption: 'caption' }, 'user');
  }
  countUndescribedImages(editor);
}

/* --- Choosing from the media library ---------------------------------------- */

// A file already uploaded goes into the text, or becomes the cover, without
// being uploaded again. The window is built the first time it is needed,
// so it works on every page with an editor; it is a <dialog>, which keeps
// the focus inside and closes with Esc.

var mediaPickerTarget = 'editor';
var mediaPickerRange = null;
var mediaPickerItems = [];

function mediaPickerDialog() {
  var dialog = document.getElementById('media-picker');
  if (dialog) { return dialog; }
  dialog = document.createElement('dialog');
  dialog.id = 'media-picker';
  dialog.className = 'media-picker';
  dialog.setAttribute('aria-labelledby', 'media-picker-title');

  var header = document.createElement('div');
  header.className = 'media-picker-header';
  var title = document.createElement('h2');
  title.id = 'media-picker-title';
  title.textContent = t('js_media_picker_title');
  var close = document.createElement('button');
  close.type = 'button';
  close.className = 'button button-small';
  close.textContent = t('admin_close');
  close.addEventListener('click', function() { dialog.close(); });
  header.appendChild(title);
  header.appendChild(close);

  var label = document.createElement('label');
  label.className = 'vh';
  label.htmlFor = 'media-picker-search';
  label.textContent = t('js_media_picker_search');
  var search = document.createElement('input');
  search.type = 'search';
  search.id = 'media-picker-search';
  search.className = 'field-input';
  search.placeholder = t('js_media_picker_search');
  search.addEventListener('input', renderMediaPicker);

  var status = document.createElement('p');
  status.id = 'media-picker-status';
  status.className = 'list-empty';
  status.setAttribute('role', 'status');

  var grid = document.createElement('ul');
  grid.id = 'media-picker-grid';
  grid.className = 'media-picker-grid';

  dialog.appendChild(header);
  dialog.appendChild(label);
  dialog.appendChild(search);
  dialog.appendChild(status);
  dialog.appendChild(grid);
  document.body.appendChild(dialog);
  return dialog;
}

// target is 'editor' (the text, at the cursor) or 'cover' (the cover field).
function openMediaPicker(target) {
  mediaPickerTarget = target;
  mediaPickerRange = null;
  if (target === 'editor' && PB_MAIN_QUILL) {
    // The window takes the focus: remember where the cursor was.
    mediaPickerRange = PB_MAIN_QUILL.getSelection() || { index: Math.max(0, PB_MAIN_QUILL.getLength() - 1) };
  }
  var dialog = mediaPickerDialog();
  document.getElementById('media-picker-search').value = '';
  document.getElementById('media-picker-grid').innerHTML = '';
  document.getElementById('media-picker-status').textContent = t('js_media_picker_loading');
  document.getElementById('media-picker-status').hidden = false;
  dialog.showModal();
  fetch('/media-library-items', { credentials: 'same-origin', cache: 'no-store' })
    .then(function(response) { return response.json(); })
    .then(function(result) {
      mediaPickerItems = result.items || [];
      renderMediaPicker();
    })
    .catch(function() {
      document.getElementById('media-picker-status').textContent = t('js_media_picker_error');
    });
}

function renderMediaPicker() {
  var grid = document.getElementById('media-picker-grid');
  var status = document.getElementById('media-picker-status');
  var query = document.getElementById('media-picker-search').value.trim().toLowerCase();
  grid.innerHTML = '';
  var shown = 0;
  mediaPickerItems.forEach(function(item) {
    // A cover is a picture: videos are not offered for it.
    if (mediaPickerTarget === 'cover' && item.kind !== 'image') { return; }
    if (query !== '' && item.name.toLowerCase().indexOf(query) === -1) { return; }
    var entry = document.createElement('li');
    var choice = document.createElement('button');
    choice.type = 'button';
    choice.className = 'media-picker-item';
    var preview;
    if (item.kind === 'video') {
      preview = document.createElement('video');
      preview.preload = 'metadata';
      preview.muted = true;
    } else {
      preview = document.createElement('img');
      preview.alt = '';
      preview.loading = 'lazy';
    }
    preview.src = item.url;
    var name = document.createElement('span');
    name.className = 'media-picker-name';
    name.textContent = item.name;
    var details = document.createElement('span');
    details.className = 'media-picker-size';
    details.textContent = item.size;
    choice.appendChild(preview);
    choice.appendChild(name);
    choice.appendChild(details);
    choice.addEventListener('click', function() { chooseMedia(item); });
    entry.appendChild(choice);
    grid.appendChild(entry);
    shown++;
  });
  status.hidden = shown > 0;
  status.textContent = t('js_media_picker_empty');
}

function chooseMedia(item) {
  document.getElementById('media-picker').close();
  if (mediaPickerTarget === 'cover') {
    document.getElementById('image').value = item.url;
    updateCoverPreview();
    if (typeof markEditorDirty === 'function') { markEditorDirty(); }
    return;
  }
  if (!PB_MAIN_QUILL) { return; }
  // The addresses come from names the server checked: safe in the markup.
  var html = item.kind === 'video'
    ? '<video controls src="' + item.url + '"></video><p><br></p>'
    : '<img src="' + item.url + '"><p><br></p>';
  var index = mediaPickerRange ? mediaPickerRange.index : 0;
  PB_MAIN_QUILL.focus();
  PB_MAIN_QUILL.clipboard.dangerouslyPasteHTML(index, html, 'user');
  PB_MAIN_QUILL.setSelection(index + 1, 0);
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
  var fieldEl = document.getElementById('image');
  var previewEl = document.getElementById('cover-preview');
  var removeButton = document.getElementById('btn-remove-cover');
  if (!fieldEl || !previewEl) { return; }

  var address = fieldEl.value.trim();
  if (address === '') {
    previewEl.removeAttribute('src');
    previewEl.hidden = true;
    if (removeButton) { removeButton.hidden = true; }
    return;
  }
  previewEl.src = address;
  previewEl.alt = document.getElementById('title').value;
  previewEl.hidden = false;
  if (removeButton) { removeButton.hidden = false; }
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
  var fileField = document.getElementById('file-docx');
  if (!fileField || fileField.files.length === 0) { return; }
  var file = fileField.files[0];
  // The same file can be chosen again after a cancelled confirmation.
  fileField.value = '';

  if (file.name.toLowerCase().endsWith('.docx') === false) {
    pbToast(t('js_docx_wrong_extension'), 'danger');
    return;
  }
  if (!fileFitsLimit(file, pbPage('max_docx_mb', 30))) { return; }

  var isEmpty = true;
  if (quill && quill.getText().trim() !== '') { isEmpty = false; }

  if (isEmpty) {
    sendDocx(file);
    return;
  }
  pbConfirm(t('js_docx_overwrite_title'), t('js_docx_overwrite_body'),
            t('js_docx_overwrite_confirm'), 'warning',
            function() { sendDocx(file); });
}

// Uploads the document and applies what comes back.
function sendDocx(file) {
  var buttonEl = document.getElementById('btn-import-docx');
  var formValues = new FormData();
  formValues.append('docx', file, file.name);

  pbBusy(buttonEl, true);
  pbStatus('docx-status', t('js_docx_importing'));

  pbFetch('/import-docx', { method: 'POST', body: formValues })
    .then(function(reply) { return reply.json(); })
    .then(function(resultValue) {
      pbBusy(buttonEl, false);
      if (resultValue.ok !== true) {
        pbStatus('docx-status', '');
        pbToast(resultValue.error, 'danger');
        return;
      }
      applyImportedDocx(resultValue);
    })
    .catch(function() {
      pbBusy(buttonEl, false);
      pbStatus('docx-status', '');
      pbToast(t('js_docx_net_error'), 'danger');
    });
}

// Fills the form with the converted document and reports what was dropped.
function applyImportedDocx(resultValue) {
  var titleField = document.getElementById('title');
  // An existing title is kept: the author may have chosen it deliberately,
  // and the one Word suggests is only the first heading of the file.
  if (titleField.value.trim() === '') {
    titleField.value = resultValue.title;
  }
  quill.root.innerHTML = resultValue.content;
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
  var descriptionField = document.getElementById('description');
  if (resultValue.subtitle && descriptionField && descriptionField.value.trim() === '') {
    descriptionField.value = resultValue.subtitle;
    updateDescriptionCounter();
  }

  pbStatus('docx-status', '');
  pbToast(t('js_docx_imported'), 'success');

  // The warnings go in one message, one per line: each names a specific
  // image, link or table, and an author needs to know which - but a pile of
  // separate toasts covered the editor and disappeared one by one.
  if (resultValue.warnings && resultValue.warnings.length > 0) {
    pbToast(t('js_docx_warnings_title') + '\n\u2022 ' + resultValue.warnings.join('\n\u2022 '),
            'warning');
  }
}

/* --- Tables: pasting from Word, and the small table editor ---------------- */

// The cell content is rebuilt as an HTML string, so text coming from the
// document must not be able to inject tags of its own.
function escapeCellText(textValue) {
  return textValue
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Finds the table a row or cell really belongs to. Word nests tables inside
// tables, and querySelectorAll reaches into the nested ones too: without this
// check a nested data table would be flattened into its wrapper.
function closestTable(node) {
  var currentItem = node.parentNode;
  while (currentItem) {
    if (currentItem.tagName === 'TABLE') {
      return currentItem;
    }
    currentItem = currentItem.parentNode;
  }
  return null;
}

// The <tr> elements belonging to this table only, skipping nested tables.
function ownRows(table) {
  var all = table.querySelectorAll('tr');
  var own = [];
  for (var i = 0; i < all.length; i++) {
    if (closestTable(all[i]) === table) {
      own.push(all[i]);
    }
  }
  return own;
}

// The cells belonging to this table only, skipping nested tables.
function ownCells(row, table) {
  var all = row.querySelectorAll('td, th');
  var own = [];
  for (var i = 0; i < all.length; i++) {
    if (closestTable(all[i]) === table) {
      own.push(all[i]);
    }
  }
  return own;
}

// Tells whether a pasted table is Word's page furniture rather than data.
// The rules are deliberately simple and conservative: when in doubt we treat
// it as a data table, because unwrapping a real grid loses more than keeping
// a layout wrapper would.
function isLayoutTable(table) {
  // A table wrapping another table is a layout wrapper: the inner one is
  // the real grid and will be matched on its own.
  if (table.querySelector('table')) {
    return true;
  }
  var rows = ownRows(table);
  // A single row is a strip of blocks placed side by side, not a grid:
  // this is the classic Word "text next to image" layout.
  if (rows.length <= 1) {
    return true;
  }
  // A single column is a stack of blocks, not a grid.
  var maxCells = 0;
  for (var i = 0; i < rows.length; i++) {
    var howMany = ownCells(rows[i], table).length;
    if (howMany > maxCells) {
      maxCells = howMany;
    }
  }
  if (maxCells <= 1) {
    return true;
  }
  return false;
}

// Keeps the text AND the images of a cell, dropping Word's styling.
// The old version used innerText, which silently deleted every image
// inside a table cell.
function buildCleanCell(cell) {
  var pieces = [];
  collectCellContent(cell, pieces);
  return pieces.join('').trim();
}

function collectCellContent(node, pieces) {
  for (var i = 0; i < node.childNodes.length; i++) {
    var child = node.childNodes[i];
    if (child.nodeType === 3) {
      pieces.push(escapeCellText(child.textContent.replace(/\s+/g, ' ')));
    } else if (child.nodeType === 1) {
      if (child.tagName === 'IMG') {
        // Only the src survives: Word's width/height/styles are dropped.
        var address = child.getAttribute('src');
        if (address) {
          pieces.push('<img src="' + escapeCellText(address) + '">');
        }
      } else if (child.tagName === 'BR') {
        pieces.push(' ');
      } else {
        collectCellContent(child, pieces);
      }
    }
  }
}

// The merge of a cell, as attributes to write back: Word's merged cells
// arrive as colspan and rowspan, and dropping them shifts every cell after.
function mergeAttributes(cell) {
  var resultValue = '';
  var columns = parseInt(cell.getAttribute('colspan') || '1', 10);
  var rows = parseInt(cell.getAttribute('rowspan') || '1', 10);
  if (columns > 1) { resultValue = resultValue + ' colspan="' + columns + '"'; }
  if (rows > 1) { resultValue = resultValue + ' rowspan="' + rows + '"'; }
  return resultValue;
}

// Turns a Word <table> node into simple, clean HTML, keeping the images.
function buildCleanTable(table) {
  var resultValue = '<table class="article-table"><tbody>';
  var rows = ownRows(table);
  for (var i = 0; i < rows.length; i++) {
    resultValue = resultValue + '<tr>';
    var cells = ownCells(rows[i], table);
    for (var j = 0; j < cells.length; j++) {
      var contentValue = buildCleanCell(cells[j]);
      // We treat the first row as the header.
      if (i === 0) {
        resultValue = resultValue + '<th' + mergeAttributes(cells[j]) + '>' + contentValue + '</th>';
      } else {
        resultValue = resultValue + '<td' + mergeAttributes(cells[j]) + '>' + contentValue + '</td>';
      }
    }
    resultValue = resultValue + '</tr>';
  }
  resultValue = resultValue + '</tbody></table>';
  return resultValue;
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
    static create(val) {
      var node = super.create();
      node.innerHTML = val;
      // The browser must not let the user type inside the embed: Quill's
      // document model would not see those changes and could revert them.
      // Editing goes through the small table editor instead (click on it).
      node.setAttribute('contenteditable', 'false');
      return node;
    }
    static value(node) {
      return node.innerHTML;
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
function attachTableSupport(quillInstance) {
  quillInstance.clipboard.addMatcher('TABLE', function(node, delta) {
    // A layout table is not a table at all, semantically. We return the delta
    // Quill already built from its children: text stays text, images stay
    // images, and everything remains editable.
    if (isLayoutTable(node)) {
      return delta;
    }
    // A real data table: rebuild it clean and keep it as a single block.
    var Delta = Quill.import('delta');
    var tableHtml = buildCleanTable(node);
    return new Delta().insert({ rawHTML: tableHtml });
  });

  // A single click SELECTS the table, a double click opens the cell editor.
  //
  // It used to be one click to edit, which meant a table could never simply
  // be selected: the modal always got there first, and with no selection the
  // toolbar had nothing to act on. Selecting first is also what makes the
  // block buttons (alignment, indent) work, because Quill applies those to
  // whatever the selection covers.
  quillInstance.root.addEventListener('click', function(evt) {
    var blockEl = evt.target.closest('.raw-html-block');
    if (!blockEl) { return; }
    selectTableBlock(quillInstance, blockEl);
  });

  quillInstance.root.addEventListener('dblclick', function(evt) {
    var blockEl = evt.target.closest('.raw-html-block');
    if (!blockEl) { return; }
    var table = blockEl.querySelector('table');
    if (!table) { return; }
    openTableEditor(quillInstance, blockEl, table);
  });

  // The selected table is outlined, so it is obvious what the toolbar will
  // act on. Quill draws no selection of its own around a block embed.
  quillInstance.on('selection-change', function(range) {
    highlightSelectedTable(quillInstance, range);
  });

  quillInstance.on('editor-change', refreshTableHints);
  refreshTableHints();
}

// The table the caret is currently on, or null. The toolbar handlers read it
// to decide whether a button should act on a table or on ordinary text.
var selectedTable = null;

// Puts Quill's own selection on a table block.
//
// A block embed occupies exactly one position in the document, so selecting
// it means a range of length 1 at its index. Once Quill knows that, the
// block-level buttons work through their normal path and the toolbar shows
// the right state.
function selectTableBlock(quillInstance, blockEl) {
  var blot = Quill.find(blockEl);
  if (!blot) { return; }
  var idx = quillInstance.getIndex(blot);
  quillInstance.setSelection(idx, 1, 'user');
}

// Outlines the selected table and remembers it.
function highlightSelectedTable(quillInstance, range) {
  var blocks = quillInstance.root.querySelectorAll('.raw-html-block');
  for (var i = 0; i < blocks.length; i++) {
    blocks[i].classList.remove('pb-table-selected');
  }
  selectedTable = null;
  if (!range) { return; }

  var lineText = quillInstance.getLine(range.index);
  if (!lineText || !lineText[0] || !lineText[0].domNode) { return; }
  var node = lineText[0].domNode;
  if (!node.classList || !node.classList.contains('raw-html-block')) { return; }

  node.classList.add('pb-table-selected');
  selectedTable = node;
}

// The "click to edit" hint over an embedded table is a translated string, so
// it cannot live in the stylesheet: the CSS reads it from this attribute
// instead. It is refreshed on every change, and again after a Word import
// replaces the whole document.
function refreshTableHints() {
  if (!quill) { return; }
  var blocks = quill.root.querySelectorAll('.raw-html-block');
  for (var i = 0; i < blocks.length; i++) {
    blocks[i].setAttribute('data-hint', t('admin_table_hint'));
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
                         'pb-tbl-strike', 'pb-tbl-background'];

// The <table> inside a selected block, or null.
function selectedTableElement() {
  if (!selectedTable) { return null; }
  return selectedTable.querySelector('table');
}

// Applies a change to the selected table and tells Quill about it.
//
// The change is made to the DOM inside the block, which is exactly what the
// blot stores and what the save reads (the article is saved from
// quill.root.innerHTML), so it survives a reload with no further work.
function changeSelectedTable(action) {
  var table = selectedTableElement();
  if (!table) { return false; }
  action(table);
  quill.update();
  markEditorDirty();
  updatePreview();
  return true;
}

// Turns an inline format on or off for the whole table.
function toggleTableClass(cls) {
  return changeSelectedTable(function(table) {
    table.classList.toggle(cls);
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
function inlineFormatHandler(itemName) {
  return function(val) {
    if (selectedTable && TABLE_FORMAT_CLASSES[itemName]) {
      toggleTableClass(TABLE_FORMAT_CLASSES[itemName]);
      return;
    }
    quill.format(itemName, val, 'user');
  };
}

// Text colour: on a table it goes on the table element, and the cells
// inherit it.
function colorHandler(val) {
  if (selectedTable) {
    changeSelectedTable(function(table) {
      if (val) {
        table.style.color = val;
      } else {
        table.style.color = '';
      }
    });
    return;
  }
  quill.format('color', val, 'user');
}

// Background: a background is not inherited, and our own stylesheet paints
// the header row and the alternating rows. So the colour goes on the table
// and a class turns those cell backgrounds off, otherwise the new colour
// would be hidden behind them.
function backgroundHandler(val) {
  if (selectedTable) {
    changeSelectedTable(function(table) {
      if (val) {
        table.style.backgroundColor = val;
        table.classList.add('pb-tbl-background');
      } else {
        table.style.backgroundColor = '';
        table.classList.remove('pb-tbl-background');
      }
    });
    return;
  }
  quill.format('background', val, 'user');
}

// "Remove formatting" on a table strips what the buttons above added, and
// the alignment Quill added, without touching the table itself.
function cleanHandler() {
  if (selectedTable) {
    var blockEl = selectedTable;
    changeSelectedTable(function(table) {
      for (var i = 0; i < TABLE_ALL_CLASSES.length; i++) {
        table.classList.remove(TABLE_ALL_CLASSES[i]);
      }
      table.style.color = '';
      table.style.backgroundColor = '';
    });
    var classes = blockEl.className.split(/\s+/);
    for (var j = 0; j < classes.length; j++) {
      if (classes[j].indexOf('ql-align-') === 0 || classes[j].indexOf('ql-indent-') === 0) {
        blockEl.classList.remove(classes[j]);
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
    var formats = quill.getFormat();
    for (var itemName in formats) {
      if (Quill.import('parchment').query(itemName, Quill.import('parchment').Scope.INLINE) != null) {
        quill.format(itemName, false, 'user');
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
function blockFormatHandler(itemName) {
  return function(val) {
    if (selectedTable) {
      pbToast(t('js_table_format_not_applicable'), 'info');
      return;
    }
    quill.format(itemName, val, 'user');
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
function openTableEditor(quillInstance, blockEl, originalTable) {
  // Only one editor at a time.
  var existing = document.getElementById('table-editor-overlay');
  if (existing) { return; }

  var backdrop = document.createElement('div');
  backdrop.id = 'table-editor-overlay';

  var popup = document.createElement('div');
  popup.className = 'table-editor-window';

  var titleText = document.createElement('h3');
  titleText.textContent = t('admin_table_editor_title');
  popup.appendChild(titleText);

  // An editable copy: the original stays untouched until "save".
  var copyItem = originalTable.cloneNode(true);
  var cells = copyItem.querySelectorAll('td, th');
  for (var i = 0; i < cells.length; i++) {
    cells[i].setAttribute('contenteditable', 'true');
  }
  var tableArea = document.createElement('div');
  tableArea.className = 'table-editor-area';
  tableArea.appendChild(copyItem);
  popup.appendChild(tableArea);

  // Row and column controls.
  var bar = document.createElement('div');
  bar.className = 'table-editor-bar';
  bar.appendChild(tableEditorButton(t('admin_table_add_row'), function() { tableAddRow(copyItem); }));
  bar.appendChild(tableEditorButton(t('admin_table_of_the_row'), function() { tableRemoveRow(copyItem); }));
  bar.appendChild(tableEditorButton(t('admin_table_add_col'), function() { tableAddColumn(copyItem); }));
  bar.appendChild(tableEditorButton(t('admin_table_of_the_col'), function() { tableRemoveColumn(copyItem); }));
  popup.appendChild(bar);

  // Save and cancel.
  var actionsEl = document.createElement('div');
  actionsEl.className = 'table-editor-actions';
  var saveBtn = tableEditorButton(t('admin_table_save'), function() {
    blockEl.innerHTML = serializeEditedTable(copyItem);
    closeTableEditor();
    // Tells Quill the document changed, so autosave and counters react.
    quillInstance.update();
  });
  saveBtn.className = 'table-editor-save';
  var cancelButton = tableEditorButton(t('admin_table_cancel'), function() {
    closeTableEditor();
  });
  actionsEl.appendChild(saveBtn);
  actionsEl.appendChild(cancelButton);
  popup.appendChild(actionsEl);

  backdrop.appendChild(popup);
  // A click on the dark background closes without saving.
  backdrop.addEventListener('click', function(evt) {
    if (evt.target === backdrop) {
      closeTableEditor();
    }
  });
  document.body.appendChild(backdrop);
}

function closeTableEditor() {
  var backdrop = document.getElementById('table-editor-overlay');
  if (backdrop) {
    document.body.removeChild(backdrop);
  }
}

function tableEditorButton(labelText, action) {
  var btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = labelText;
  btn.onclick = action;
  return btn;
}

// The rows of the edited table (they all belong to it: no nesting here).
function editedTableRows(table) {
  return table.querySelectorAll('tr');
}

function tableAddRow(table) {
  var rows = editedTableRows(table);
  if (rows.length === 0) { return; }
  var last = rows[rows.length - 1];
  var columns = last.querySelectorAll('td, th').length;
  var row = document.createElement('tr');
  for (var i = 0; i < columns; i++) {
    var cell = document.createElement('td');
    cell.setAttribute('contenteditable', 'true');
    row.appendChild(cell);
  }
  last.parentNode.appendChild(row);
}

function tableRemoveRow(table) {
  var rows = editedTableRows(table);
  // The header row always stays.
  if (rows.length <= 1) { return; }
  var last = rows[rows.length - 1];
  last.parentNode.removeChild(last);
}

function tableAddColumn(table) {
  var rows = editedTableRows(table);
  for (var i = 0; i < rows.length; i++) {
    var cell;
    if (i === 0) {
      cell = document.createElement('th');
    } else {
      cell = document.createElement('td');
    }
    cell.setAttribute('contenteditable', 'true');
    rows[i].appendChild(cell);
  }
}

function tableRemoveColumn(table) {
  var rows = editedTableRows(table);
  for (var i = 0; i < rows.length; i++) {
    var cells = rows[i].querySelectorAll('td, th');
    // At least one column always stays.
    if (cells.length <= 1) { return; }
  }
  for (var j = 0; j < rows.length; j++) {
    var own = rows[j].querySelectorAll('td, th');
    rows[j].removeChild(own[own.length - 1]);
  }
}

// Rebuilds clean table HTML from the edited copy, with the same rules
// used when pasting: text and images survive, styling does not.
function serializeEditedTable(table) {
  var resultValue = '<table class="article-table"><tbody>';
  var rows = editedTableRows(table);
  for (var i = 0; i < rows.length; i++) {
    resultValue = resultValue + '<tr>';
    var cells = rows[i].querySelectorAll('td, th');
    for (var j = 0; j < cells.length; j++) {
      var contentValue = buildCleanCell(cells[j]);
      if (i === 0) {
        resultValue = resultValue + '<th' + mergeAttributes(cells[j]) + '>' + contentValue + '</th>';
      } else {
        resultValue = resultValue + '<td' + mergeAttributes(cells[j]) + '>' + contentValue + '</td>';
      }
    }
    resultValue = resultValue + '</tr>';
  }
  resultValue = resultValue + '</tbody></table>';
  return resultValue;
}

// Inserts an empty table created by the user (rows x columns of their choice).
function insertTable() {
  if (!PB_MAIN_QUILL) { return; }
  var rows = prompt(t('js_table_how_many_rows'), '3');
  if (rows === null) { return; }
  var columns = prompt(t('js_table_how_many_cols'), '3');
  if (columns === null) { return; }
  var numRows = parseInt(rows, 10);
  var numColumns = parseInt(columns, 10);
  if (isNaN(numRows) || isNaN(numColumns)) { return; }
  if (numRows < 1 || numColumns < 1) { return; }

  var html = '<table class="article-table"><tbody>';
  for (var i = 0; i < numRows; i++) {
    html = html + '<tr>';
    for (var j = 0; j < numColumns; j++) {
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
  var placement = PB_MAIN_QUILL.getSelection(true);
  PB_MAIN_QUILL.insertEmbed(placement.index, 'rawHTML', html, Quill.sources.USER);
}

/* --- Admin interface language -------------------------------------------- */

// Changes the language of the administration interface and reloads.
function changeAdminLanguage(lang) {
  pbPostJson('/admin-language', { language: lang })
    .then(function() { window.location.reload(); });
}

/* --- Dashboard (the article list) ---------------------------------------- */

// Shows the rows that match both the typed text and the chosen status.
// Hidden rows get the hidden attribute, so sorting can keep moving them.
function filterArticles() {
  var term = document.getElementById('search-box-admin').value.toLowerCase().trim();
  var chosen = document.querySelector('#filter-state [aria-pressed="true"]');
  var state = chosen ? chosen.getAttribute('data-filter') : 'all';
  var cardList = document.querySelectorAll('.article-card');
  var visibleOnes = 0;
  for (var i = 0; i < cardList.length; i++) {
    var titleText = cardList[i].getAttribute('data-title');
    var stateOk = state === 'all' || cardList[i].getAttribute('data-state') === state;
    if (stateOk && titleText.indexOf(term) !== -1) {
      cardList[i].hidden = false;
      visibleOnes = visibleOnes + 1;
    } else {
      cardList[i].hidden = true;
    }
  }
  // With no article at all the list already says so: the message is for a
  // search or a filter that leaves nothing.
  document.getElementById('no-result').hidden = visibleOnes > 0 || cardList.length === 0;
}

// The All / Published / Drafts buttons: one pressed at a time.
function filterByStatus(buttonEl) {
  var group = buttonEl.parentNode.querySelectorAll('.segment');
  for (var i = 0; i < group.length; i++) {
    group[i].setAttribute('aria-pressed', group[i] === buttonEl ? 'true' : 'false');
  }
  filterArticles();
}

/* --- Menus: the "..." of each article and the phone's "More" ------------- */

// Opens or closes the small menu of an article row. Only one stays open.
function toggleRowMenu(buttonEl) {
  var menu = document.getElementById(buttonEl.getAttribute('aria-controls'));
  var openIt = buttonEl.getAttribute('aria-expanded') !== 'true';
  closeRowMenus();
  if (!openIt) { return; }
  buttonEl.setAttribute('aria-expanded', 'true');
  // The open menu has to cover the buttons of the rows below it.
  buttonEl.parentNode.classList.add('open');
  menu.hidden = false;
  // Near the bottom of the window - or of the phone's bottom bar, which
  // would cover it - the menu opens upwards.
  var bottomEdge = window.innerHeight;
  var bar = document.querySelector('.bar-bottom');
  if (bar && bar.offsetHeight > 0) {
    bottomEdge = bar.getBoundingClientRect().top;
  }
  var spaceBelow = bottomEdge - buttonEl.getBoundingClientRect().bottom;
  menu.classList.toggle('toward-top', spaceBelow < menu.offsetHeight + 16);
  menu.querySelector('[role="menuitem"]').focus();
}

// Closes every open row menu; with returnFocus, focus goes back to the
// button that opened it, as after Esc.
function closeRowMenus(returnFocus) {
  var openedOnes = document.querySelectorAll('.row-menu [aria-expanded="true"]');
  for (var i = 0; i < openedOnes.length; i++) {
    openedOnes[i].setAttribute('aria-expanded', 'false');
    openedOnes[i].parentNode.classList.remove('open');
    document.getElementById(openedOnes[i].getAttribute('aria-controls')).hidden = true;
    if (returnFocus) { openedOnes[i].focus(); }
  }
}

// On a phone the side menu becomes a sheet that rises above the bottom bar.
// Called with no argument it switches; with true or false it opens or closes.
function toggleAdminMenu(openIt) {
  var menu = document.getElementById('menu-admin');
  var buttonEl = document.getElementById('bar-other');
  if (!menu || !buttonEl) { return; }
  if (openIt === undefined) {
    openIt = !menu.classList.contains('open');
  }
  menu.classList.toggle('open', openIt);
  document.getElementById('menu-veil').hidden = !openIt;
  buttonEl.setAttribute('aria-expanded', openIt ? 'true' : 'false');
  if (openIt) {
    var before = menu.querySelector('.menu-items .item');
    if (before) { before.focus(); }
  }
}

document.addEventListener('click', function(evt) {
  if (!evt.target.closest('.row-menu')) { closeRowMenus(); }
});

document.addEventListener('keydown', function(evt) {
  var menu = evt.target.closest ? evt.target.closest('.menu-dropdown') : null;
  if (evt.key === 'Escape') {
    if (document.querySelector('.row-menu [aria-expanded="true"]')) {
      closeRowMenus(true);
    } else if (document.querySelector('.menu.open')) {
      toggleAdminMenu(false);
      document.getElementById('bar-other').focus();
    }
    return;
  }
  if (!menu) { return; }
  // Arrows move between the items of a row menu; Tab leaves it closed.
  var entries = Array.prototype.slice.call(menu.querySelectorAll('[role="menuitem"]'));
  var placement = entries.indexOf(evt.target);
  if (evt.key === 'ArrowDown' || evt.key === 'ArrowUp') {
    evt.preventDefault();
    var step = evt.key === 'ArrowDown' ? 1 : -1;
    entries[(placement + step + entries.length) % entries.length].focus();
  } else if (evt.key === 'Home' || evt.key === 'End') {
    evt.preventDefault();
    entries[evt.key === 'Home' ? 0 : entries.length - 1].focus();
  } else if (evt.key === 'Tab') {
    closeRowMenus(true);
  }
});

// Rebuilds the static site.
function rebuildSite(buttonEl) {
  pbBusy(buttonEl, true);
  pbPostJson('/rebuild', {})
    .then(function(res) {
      pbBusy(buttonEl, false);
      pbToast(t('js_site_rebuilt').replace('{n}', res.articles), 'success');
    })
    .catch(function() {
      pbBusy(buttonEl, false);
      pbToast(t('js_site_rebuilt_error'), 'danger');
    });
}

// Changes an article's status (published/draft) and reloads the page.
function changeStatus(buttonEl, slug, newState) {
  pbBusy(buttonEl, true);
  pbPostJson('/toggle-status', { slug: slug, status: newState })
    .then(function(res) {
      if (res.ok === true) {
        window.location.reload();
      } else {
        pbBusy(buttonEl, false);
        pbToast(t('js_status_change_error'), 'danger');
      }
    })
    .catch(function() {
      pbBusy(buttonEl, false);
      pbToast(t('js_status_change_error'), 'danger');
    });
}

// Deletes an article after confirmation, then reloads the page.
function deleteArticle(slug, titleText) {
  pbConfirm(t('js_delete_title'),
            t('js_delete_body').replace('{title}', titleText),
            t('admin_delete'), 'danger',
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
  var contentValue = PB_MAIN_QUILL.root.innerHTML;
  var page = '<!DOCTYPE html><html><head>';
  page = page + '<meta charset="utf-8">';
  page = page + '<link rel="stylesheet" href="/common.css">';
  page = page + '<link rel="stylesheet" href="/style.css">';

  if (pbPage('preview_kind', '') === 'article') {
    var titleText = document.getElementById('title').value;
    page = page + '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css">';
    page = page + '</head><body>';
    page = page + '<article id="content" class="post">';
    page = page + '<h1></h1>';
    page = page + contentValue;
    page = page + '</article>';
    // We load highlight.js inside the preview to colour the code here too.
    page = page + '<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"><\/script>';
    page = page + '<script>document.querySelectorAll("pre.ql-syntax").forEach(function(b){hljs.highlightElement(b);});<\/script>';
    page = page + '</body></html>';
  } else {
    page = page + '</head><body>';
    page = page + '<section class="home-intro">';
    page = page + contentValue;
    page = page + '</section></body></html>';
  }

  var docFile = frame.contentDocument;
  docFile.open();
  docFile.write(page);
  docFile.close();
  // The article title is written as text, never as HTML: a title with a
  // "<" in it must not be able to inject markup into the preview.
  if (pbPage('preview_kind', '') === 'article') {
    var heading = docFile.querySelector('article.post h1');
    if (heading) {
      heading.textContent = document.getElementById('title').value;
    }
  }
}

/* --- The article editor page --------------------------------------------- */

// The toolbar of the full article editor.
var ARTICLE_TOOLBAR = [
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
  registerImageCaption();
}

// A caption is a paragraph with the class image-caption: the author sees it
// and types into it like any text, and the build turns it and the picture
// above it into <figure> and <figcaption>. Quill only keeps the classes it
// knows, so the class is registered as a block format of its own.
function registerImageCaption() {
  var Parchment = Quill.import('parchment');
  Quill.register(new Parchment.Attributor.Class('imagecaption', 'image', {
    scope: Parchment.Scope.BLOCK, whitelist: ['caption']
  }), true);
}

// The two Quill editors of the article page (Italian and English).
var quill = null;
var quillEn = null;
// The slug the article is currently saved with on disk. It is updated after
// every save (including the one from the EN preview), so that a later slug
// change does not leave orphan files.
var originalSlug = '';

// Whether the editor holds changes that are not on disk yet. It drives three
// things: the warning when you leave the page, whether the autosave has any
// work to do, and the "Unsaved changes" line under the buttons.
var editorDirty = false;
// "draft" or "published", as saved. The buttons of the sidebar follow it.
var articleState = 'draft';
// Set while a save is in flight, so the autosave and a manual save cannot
// overlap and race each other's writes.
var savingNow = false;
var autosaveTimer = null;

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
        container: ARTICLE_TOOLBAR,
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
  watchImageDescriptions(quill);
  handlePastedImages(quill, 'upload-status');
  attachTableSupport(quill);

  // We create a second Quill editor for the English translation, so the author
  // can review and correct it before confirming it.
  quillEn = new Quill('#editor-en', {
    theme: 'snow',
    modules: { blotFormatter: {}, syntax: true, toolbar: ARTICLE_TOOLBAR }
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
  originalSlug = pbPage('slug', '');
  articleState = pbPage('status', 'draft');
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
  document.getElementById('list-box-code-article').addEventListener('change', markEditorDirty);
  watchCodeList(document.getElementById('list-box-code-own'), markEditorDirty);

  // The article as it is right now is what is on disk: loading the page is
  // not a change.
  markEditorClean();
  startAutosave();
  installUnsavedChangesGuard();
  installSaveShortcut();
  rememberOpenGroups();
  updateShareLinks();
  document.getElementById('title').addEventListener('input', updateShareLinks);
}

// Every field of the form marks the article as changed when it is touched.
function watchEditorFields() {
  var fields = ['title', 'slug', 'tags', 'series', 'series_number', 'kind', 'lab_of',
               'repo_url', 'stack', 'run_steps', 'original_url', 'original_canonical', 'image', 'description',
               'reader_preview', 'title_en', 'description_en', 'preview_en',
               'translation_authorized', 'translation_confirmed'];
  for (var i = 0; i < fields.length; i++) {
    var element = document.getElementById(fields[i]);
    if (!element) { continue; }
    element.addEventListener('input', markEditorDirty);
    element.addEventListener('change', markEditorDirty);
  }
}

// A change not on disk yet is said under the buttons: on a published article
// nothing saves it on its own, and the author should not have to guess.
function markEditorDirty() {
  editorDirty = true;
  updateGroupSummaries();
  var row = document.getElementById('autosave-status');
  if (row && !row.classList.contains('pb-autosave-error')) {
    row.textContent = t('js_changes_made_from_to_save');
  }
}

function markEditorClean() {
  editorDirty = false;
}

// Warns before leaving the page with unsaved work. Browsers show their own
// wording and ignore ours, but the event still has to be cancelled for the
// dialog to appear at all.
function installUnsavedChangesGuard() {
  window.addEventListener('beforeunload', function(evt) {
    if (!editorDirty) { return undefined; }
    evt.preventDefault();
    evt.returnValue = t('js_unsaved_changes');
    return t('js_unsaved_changes');
  });
}

// Ctrl+S (Cmd+S on a Mac) saves without leaving the editor, which is what
// the muscle memory of anyone who has used a word processor expects: a
// draft stays a draft, a published article is updated. It never publishes.
function installSaveShortcut() {
  document.addEventListener('keydown', function(evt) {
    var modifier = evt.ctrlKey || evt.metaKey;
    if (!modifier || evt.key.toLowerCase() !== 's') { return; }
    evt.preventDefault();
    if (articleState === 'published') {
      updateArticle(document.getElementById('btn-update'));
    } else if (articleState === 'scheduled') {
      saveScheduled(document.getElementById('btn-save-scheduled'));
    } else {
      saveDraft(document.getElementById('btn-save-draft'));
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
  if (autosaveTimer !== null) {
    clearInterval(autosaveTimer);
  }
  autosaveTimer = setInterval(autosaveDraft, AUTOSAVE_INTERVAL);
}

function autosaveDraft() {
  if (!editorDirty || savingNow) { return; }
  if (articleState !== 'draft') { return; }
  if (document.getElementById('title').value.trim() === '') {
    pbStatus('autosave-status', t('js_autosave_needs_title'));
    return;
  }

  savingNow = true;
  pbStatus('autosave-status', t('js_autosaving'));
  pbPostJson('/save', articleData('draft'))
    .then(function(res) {
      savingNow = false;
      if (res.ok) {
        applySavedSlug(res);
        markEditorClean();
        setAutosaveIndicator(t('js_autosaved_at').replace('{time}', currentTime()), false);
      } else {
        setAutosaveIndicator(t('js_autosave_failed'), true);
      }
    })
    .catch(function() {
      savingNow = false;
      setAutosaveIndicator(t('js_autosave_failed'), true);
    });
}

function setAutosaveIndicator(textValue, err) {
  var element = document.getElementById('autosave-status');
  if (!element) { return; }
  element.textContent = textValue;
  if (err) {
    element.classList.add('pb-autosave-error');
  } else {
    element.classList.remove('pb-autosave-error');
  }
}

// The current time as HH:MM, for the "saved at" indicator.
function currentTime() {
  var nowDate = new Date();
  var ore = String(nowDate.getHours());
  var minutes = String(nowDate.getMinutes());
  if (ore.length < 2) { ore = '0' + ore; }
  if (minutes.length < 2) { minutes = '0' + minutes; }
  return ore + ':' + minutes;
}

// Character counter for the SEO description, warning about Google's limit.
function updateDescriptionCounter() {
  var fieldEl = document.getElementById('description');
  var counter = document.getElementById('description-counter');
  if (!fieldEl || !counter) { return; }
  var len = fieldEl.value.length;
  var message = '';
  // Google shows about 120-160 characters: we flag when you leave the ideal range.
  if (len === 0) {
    message = t('js_desc_counter_empty');
  } else if (len > 160) {
    message = len + ' ' + t('js_chars_unit') + ' - ' + t('js_chars_too_long_google');
  } else if (len < 50) {
    message = len + ' ' + t('js_chars_unit') + ' - ' + t('js_chars_too_short_seo');
  } else {
    message = len + ' ' + t('js_chars_unit') + ' - ' + t('js_chars_ideal_length');
  }
  counter.textContent = message;
}

// Character counter for the preview meant for readers.
function updatePreviewCounter() {
  var fieldEl = document.getElementById('reader_preview');
  var counter = document.getElementById('preview-counter');
  if (!fieldEl || !counter) { return; }
  var len = fieldEl.value.length;
  if (len === 0) {
    counter.textContent = t('js_preview_counter_empty');
  } else {
    counter.textContent = len + ' ' + t('js_chars_unit');
  }
}

// Asks the AI to propose an SEO description from the article content.
// The author sees the proposal in the textarea and can edit or rewrite it.
function suggestDescription(buttonEl) {
  if (quill.getText().trim() === '') {
    pbStatus('description-status', t('js_write_article_content_first'));
    return;
  }
  pbBusy(buttonEl, true);
  pbStatus('description-status', t('js_generating'));

  pbPostJson('/generate-description', {
    content: quill.root.innerHTML,
    title: document.getElementById('title').value
  })
  .then(function(res) {
    pbBusy(buttonEl, false);
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
    pbBusy(buttonEl, false);
    pbStatus('description-status', '');
    pbToast(t('js_net_error_generation'), 'danger');
  });
}

// Asks the AI to write a narrative preview for readers (longer and more
// descriptive than the SEO meta description). The author can then edit it.
function generatePreview(buttonEl) {
  if (quill.getText().trim() === '') {
    pbStatus('preview-status', t('js_write_article_content_first'));
    return;
  }
  pbBusy(buttonEl, true);
  pbStatus('preview-status', t('js_generating'));

  pbPostJson('/generate-preview', {
    content: quill.root.innerHTML,
    title: document.getElementById('title').value
  })
  .then(function(res) {
    pbBusy(buttonEl, false);
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
    pbBusy(buttonEl, false);
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
  var panel = document.getElementById('seo-results');

  if (quill.getText().trim() === '') {
    pbStatus('seo-status', t('js_write_article_content_first'));
    return;
  }

  // The analysis needs the slug to build the article URL for the backlink.
  var currentSlug = document.getElementById('slug').value.trim();
  if (currentSlug === '') {
    currentSlug = originalSlug;
  }
  if (currentSlug === '') {
    pbStatus('seo-status', t('js_seo_save_first'));
    return;
  }

  var buttonEl = document.getElementById('seo-analyze-btn');
  pbBusy(buttonEl, true);
  pbStatus('seo-status', t('js_seo_analyzing'));
  panel.style.display = 'none';
  panel.textContent = '';

  pbPostJson('/analyze-seo', {
    content: quill.root.innerHTML,
    title: document.getElementById('title').value,
    slug: currentSlug,
    tags: document.getElementById('tags').value,
    description: document.getElementById('description').value
  })
  .then(function(res) {
    pbBusy(buttonEl, false);
    if (res.ok === true) {
      pbStatus('seo-status', t('js_seo_done'));
      renderSeoResults(panel, res.analysis, res.article_url);
      panel.style.display = 'block';
    } else {
      pbStatus('seo-status', '');
      pbToast(t('js_error_prefix') + res.error, 'danger');
    }
  })
  .catch(function() {
    pbBusy(buttonEl, false);
    pbStatus('seo-status', '');
    pbToast(t('js_net_error_generation'), 'danger');
  });
}

// A section title inside the results panel.
function seoHeading(textValue) {
  var h = document.createElement('div');
  h.className = 'seo-heading';
  h.textContent = textValue;
  return h;
}

// A row of text with a small "copy" button next to it.
function seoCopyRow(textValue) {
  var row = document.createElement('div');
  row.className = 'seo-row';
  var span = document.createElement('span');
  span.textContent = textValue;
  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'seo-copy';
  btn.textContent = t('seo_copy');
  btn.onclick = function() { copyToClipboard(textValue, btn); };
  row.appendChild(span);
  row.appendChild(btn);
  return row;
}

// Copies a text to the clipboard and gives feedback on the button.
function copyToClipboard(textValue, btnEl) {
  var confirmButton = function() {
    var original = btnEl.textContent;
    btnEl.textContent = t('seo_copied');
    setTimeout(function() { btnEl.textContent = original; }, 1200);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(textValue).then(confirmButton);
  } else {
    // Fallback for older browsers or non-HTTPS contexts.
    var area = document.createElement('textarea');
    area.value = textValue;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    document.body.removeChild(area);
    confirmButton();
  }
}

// Renders the analysis into the panel. Every field is optional: the model
// may omit some keys, and the panel simply skips the missing sections.
function renderSeoResults(panel, analysis, articleUrl) {
  if (!analysis) { return; }

  // The exact URL to use as the backlink target on the external site.
  panel.appendChild(seoHeading(t('seo_backlink_target')));
  panel.appendChild(seoCopyRow(articleUrl));

  var lists = [
    ['primary_keywords', t('seo_primary_keywords')],
    ['secondary_keywords', t('seo_secondary_keywords')],
    ['title_variants', t('seo_title_variants')],
    ['anchor_texts', t('seo_anchor_texts')]
  ];
  for (var i = 0; i < lists.length; i++) {
    var key = lists[i][0];
    var titleText = lists[i][1];
    var values = analysis[key];
    if (values && values.length > 0) {
      panel.appendChild(seoHeading(titleText));
      for (var j = 0; j < values.length; j++) {
        panel.appendChild(seoCopyRow(String(values[j])));
      }
    }
  }

  // Suggested tags: shown as text, with a button applying them to the field.
  var tagValues = analysis['suggested_tags'];
  if (tagValues && tagValues.length > 0) {
    panel.appendChild(seoHeading(t('seo_suggested_tags')));
    var textTag = tagValues.join(', ');
    var tagRow = seoCopyRow(textTag);
    var btnTag = document.createElement('button');
    btnTag.type = 'button';
    btnTag.className = 'seo-copy';
    btnTag.textContent = t('seo_apply_tags');
    btnTag.onclick = function() {
      document.getElementById('tags').value = textTag;
    };
    tagRow.appendChild(btnTag);
    panel.appendChild(tagRow);
  }

  // The model's opinion on the current meta description.
  if (analysis['meta_description_review']) {
    panel.appendChild(seoHeading(t('seo_meta_review')));
    var verdict = document.createElement('div');
    verdict.className = 'seo-text';
    verdict.textContent = String(analysis['meta_description_review']);
    panel.appendChild(verdict);
  }

  // Internal links: slug plus the suggested anchor text.
  var internal = analysis['internal_links'];
  if (internal && internal.length > 0) {
    panel.appendChild(seoHeading(t('seo_internal_links')));
    for (var k = 0; k < internal.length; k++) {
      var entryEl = internal[k];
      if (entryEl && entryEl.slug) {
        var anchor = '';
        if (entryEl.anchor) { anchor = String(entryEl.anchor); }
        panel.appendChild(seoCopyRow(anchor + '  ->  /posts/' + String(entryEl.slug) + '.html'));
      }
    }
  }

  // FAQ suggested for AI answer engines: ready to paste at the end of
  // the article (AI crawlers favour explicit question/answer blocks).
  var faq = analysis['faq'];
  if (faq && faq.length > 0) {
    panel.appendChild(seoHeading(t('seo_faq')));
    for (var f = 0; f < faq.length; f++) {
      if (faq[f] && faq[f].question) {
        var blockEl = document.createElement('div');
        blockEl.className = 'seo-text';
        var question = document.createElement('strong');
        question.textContent = String(faq[f].question);
        blockEl.appendChild(question);
        blockEl.appendChild(document.createElement('br'));
        blockEl.appendChild(document.createTextNode(String(faq[f].answer || '')));
        panel.appendChild(blockEl);
      }
    }
  }

  // Concrete AI-SEO advice for this specific article.
  var tips = analysis['ai_seo_tips'];
  if (tips && tips.length > 0) {
    panel.appendChild(seoHeading(t('seo_ai_tips')));
    for (var c = 0; c < tips.length; c++) {
      var tip = document.createElement('div');
      tip.className = 'seo-text';
      tip.textContent = '\u2022 ' + String(tips[c]);
      panel.appendChild(tip);
    }
  }
}

// Shows or hides the translation block based on the authorisation flag.
function updateTranslationSection() {
  var authorized = document.getElementById('translation_authorized').checked;
  var blockEl = document.getElementById('translation-block');
  if (authorized) {
    blockEl.style.display = 'block';
  } else {
    blockEl.style.display = 'none';
  }
}

// Asks the server to translate title, description and content into English.
// The calls happen in the backend, where the API keys are safe.
function translateArticle(buttonEl) {
  pbBusy(buttonEl, true);
  pbStatus('translation-status', t('js_translating'));
  // The three pieces are translated one after the other; the button comes
  // back to life when the last one lands.
  var onFinished = function() { pbBusy(buttonEl, false); };

  // We take the Italian texts to translate.
  var titleIt = document.getElementById('title').value;
  var descriptionIt = document.getElementById('description').value;
  var contentIt = quill.root.innerHTML;

  // We translate the three pieces one after the other.
  translatePiece(titleIt, function(translatedTitle) {
    document.getElementById('title_en').value = translatedTitle;
    translatePiece(descriptionIt, function(translatedDescription) {
      document.getElementById('description_en').value = translatedDescription;
      translatePiece(contentIt, function(translatedContent, restoredMedia) {
        quillEn.root.innerHTML = translatedContent;
        markEditorDirty();
        pbStatus('translation-status', mediaNotice(t('js_translated_review'), restoredMedia));
        onFinished();
      });
    });
  });
}

// The images never travel to the translation service: the server swaps them
// for a marker and puts them back afterwards. When a service loses a marker
// too, the server still puts the image back, but no longer where it was - so
// the editor says how many need a second look instead of letting the author
// find out from a reader.
function mediaNotice(message, howMany) {
  if (!howMany || howMany < 1) { return message; }
  return message + t('js_media_recovered').replace('{n}', String(howMany));
}

// Translates a single piece of text by calling the backend.
function translatePiece(textValue, onFinished) {
  if (textValue === null || textValue.trim() === '') {
    onFinished('');
    return;
  }
  pbPostJson('/translate', { text: textValue })
    .then(function(res) {
      if (res.ok === true) {
        onFinished(res.text, res.media_recovered || 0);
      } else {
        pbStatus('translation-status',
          t('js_error_prefix') + res.error + t('js_check_api_key'));
        onFinished('');
      }
    })
    .catch(function() {
      pbStatus('translation-status', t('js_net_error_translation'));
      onFinished('');
    });
}

// The site's snippets on this article, read from the checkboxes: a
// "selected articles" one counts when ticked (kind "optin"), one that goes on
// every article counts when unticked (kind "always"), as switched off here.
// The editor only lists the snippets that are active in the Settings, so the
// ids the article already had for the others are kept as they were: the day
// one of them is switched back on, the article's choice is still there.
function articleCodeIds(kindValue, ticked, savedOnes) {
  var checkboxes = document.querySelectorAll('.code-article');
  var shownItems = {};
  var ids = [];
  for (var i = 0; i < checkboxes.length; i++) {
    shownItems[checkboxes[i].value] = true;
    if (checkboxes[i].getAttribute('data-kind') === kindValue && checkboxes[i].checked === ticked) {
      ids.push(checkboxes[i].value);
    }
  }
  for (var j = 0; j < savedOnes.length; j++) {
    if (!shownItems[savedOnes[j]] && ids.indexOf(savedOnes[j]) === -1) {
      ids.push(savedOnes[j]);
    }
  }
  return ids;
}

// A new piece of code for this article only.
function addOwnCode() {
  var card = cloneBlankCard('code-own-template', 'art');
  document.getElementById('list-box-code-own').appendChild(card);
  updateCardSummary(card);
  startCodeEditor(card);
  markEditorDirty();
  card.querySelector('.code-name').focus();
}

// Collects every form field into a single article object, for a save or a
// preview. state is the status to save with; without it, the current one.
function articleData(state) {
  return {
    title: document.getElementById('title').value,
    slug: document.getElementById('slug').value,
    description: document.getElementById('description').value,
    preview: document.getElementById('reader_preview').value,
    content: quill.root.innerHTML,
    tags: document.getElementById('tags').value,
    series: document.getElementById('series').value,
    series_number: document.getElementById('series_number').value,
    kind: document.getElementById('kind').value,
    lab_of: document.getElementById('lab_of').value,
    repo_url: document.getElementById('repo_url').value,
    stack: document.getElementById('stack').value,
    run_steps: document.getElementById('run_steps').value,
    original_url: document.getElementById('original_url').value,
    original_canonical: document.getElementById('original_canonical').checked,
    image: document.getElementById('image').value,
    status: state || articleState,
    // The moment a scheduled article goes out, in UTC; ignored otherwise.
    publish_at: (state || articleState) === 'scheduled' ? scheduledMoment() : '',
    notify_subscribers: notifySubscribers(),
    original_slug: originalSlug,
    custom_code_ids: articleCodeIds('optin', true, pbPage('custom_code_ids', [])),
    custom_code_off_ids: articleCodeIds('always', false, pbPage('custom_code_off_ids', [])),
    custom_code: customCodeData(document.getElementById('list-box-code-own'), 'art'),
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
  originalSlug = res.slug;
  var fieldEl = document.getElementById('slug');
  if (fieldEl) { fieldEl.value = res.slug; }
  if (res.notice) { pbToast(res.notice, 'warning'); }
}

// The panel at the top of the sidebar shows the buttons of the state the
// article is in, and where the published page lives.
function updateStatePanel(address) {
  // A saved article has versions to look at.
  if (originalSlug !== '') {
    var versions = document.querySelectorAll('#btn-versions, #versions-help');
    for (var v = 0; v < versions.length; v++) { versions[v].hidden = false; }
  }
  var panel = document.getElementById('panel-publish');
  if (panel) { panel.setAttribute('data-state', articleState); }
  var when = document.getElementById('scheduled-when');
  if (when && articleState === 'scheduled') {
    when.textContent = t('admin_goes_out_the').replace('{date}', formatMoment(scheduledMoment()));
  }
  toggleScheduleForm(null, false);
  var link = document.getElementById('link-online');
  if (link && address) { link.setAttribute('href', address); }
  updateShareLinks();
}

// The links that post a published article elsewhere: each opens the
// posting page of that site with the public address and the title filled in.
function updateShareLinks() {
  var online = document.getElementById('link-online');
  if (!online) { return; }
  var path = online.getAttribute('href') || '';
  if (path.indexOf('http') !== 0) { path = pbPage('public_base', '') + path; }
  var address = encodeURIComponent(path);
  var titleText = encodeURIComponent(document.getElementById('title').value.trim());
  var destinations = {
    'share-linkedin': 'https://www.linkedin.com/sharing/share-offsite/?url=' + address,
    'share-hn': 'https://news.ycombinator.com/submitlink?u=' + address + '&t=' + titleText,
    'share-reddit': 'https://www.reddit.com/submit?url=' + address + '&title=' + titleText,
    'share-x': 'https://twitter.com/intent/tweet?url=' + address + '&text=' + titleText
  };
  for (var id in destinations) {
    var entryEl = document.getElementById(id);
    if (entryEl) { entryEl.setAttribute('href', destinations[id]); }
  }
}

// --- The four things the sidebar can do with an article ---------------------
// A draft is saved or published; a published article is updated (its
// changes go online) or taken back to the drafts. Every one of them is a
// save with a status: what changes is the status and what the author is told.

function saveDraft(buttonEl) {
  saveWithStatus('draft', buttonEl, t('js_draft_saved_f'));
}

/* --- Scheduled publishing -------------------------------------------------- */

// The field holds the author's local time ("2026-10-04T09:00"); the server
// keeps the moment in UTC. These two convert between them.
function scheduledMoment() {
  var val = document.getElementById('publish_at').value;
  if (!val) { return ''; }
  var moment = new Date(val);
  return isNaN(moment.getTime()) ? '' : moment.toISOString();
}

function localInputValue(iso) {
  if (!iso) { return ''; }
  var moment = new Date(iso);
  if (isNaN(moment.getTime())) { return ''; }
  var due = function(n) { return (n < 10 ? '0' : '') + n; };
  return moment.getFullYear() + '-' + due(moment.getMonth() + 1) + '-' + due(moment.getDate()) +
    'T' + due(moment.getHours()) + ':' + due(moment.getMinutes());
}

// "saturday 4 october, 09:00", in the language of the administration.
function formatMoment(iso) {
  var moment = new Date(iso);
  if (isNaN(moment.getTime())) { return iso; }
  return moment.toLocaleString(document.documentElement.lang || undefined, {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

// Every <time class="now-local"> written by the server shows UTC; here it
// becomes the reader's own time.
function localizeMoments(root) {
  var tempi = (root || document).querySelectorAll('time.now-local');
  for (var i = 0; i < tempi.length; i++) {
    tempi[i].textContent = formatMoment(tempi[i].getAttribute('datetime'));
  }
}
document.addEventListener('DOMContentLoaded', function() { localizeMoments(); });

// Opens or closes the little form with the date and time. With no button
// (null) it is closed, as after a save.
function toggleScheduleForm(buttonEl, openIt) {
  var modulo = document.getElementById('schedule-form');
  if (!modulo) { return; }
  if (openIt === undefined) { openIt = modulo.hidden; }
  modulo.hidden = !openIt;
  var buttons = document.querySelectorAll('[aria-controls="schedule-form"]');
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].setAttribute('aria-expanded', openIt ? 'true' : 'false');
  }
  var fieldEl = document.getElementById('publish_at');
  if (openIt) {
    if (!fieldEl.value) {
      // Tomorrow at nine is a sensible first proposal.
      var tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      tomorrow.setHours(9, 0, 0, 0);
      fieldEl.value = localInputValue(tomorrow.toISOString());
    }
    fieldEl.focus();
  }
}

function scheduleArticle(buttonEl) {
  var titleText = document.getElementById('title').value.trim();
  if (titleText === '') {
    pbToast(t('js_title_for_to_publish'), 'warning');
    document.getElementById('title').focus();
    return;
  }
  var moment = scheduledMoment();
  if (moment === '' || new Date(moment).getTime() <= Date.now()) {
    pbToast(t('js_schedule_data'), 'warning');
    document.getElementById('publish_at').focus();
    return;
  }
  var when = formatMoment(moment);
  pbConfirm(t('js_schedule_title'),
            t('js_schedule_body').replace('{title}', titleText).replace('{date}', when),
            t('admin_schedule_confirm'), 'primary', function() {
    saveWithStatus('scheduled', buttonEl, t('js_scheduled').replace('{date}', when));
  });
}

function saveScheduled(buttonEl) {
  saveWithStatus('scheduled', buttonEl, t('js_changes_made_saved_pl'));
}

function publishNow(buttonEl) {
  publishArticle(buttonEl);
}

function cancelSchedule(buttonEl) {
  saveWithStatus('draft', buttonEl, t('js_scheduling_cancelled'));
}

function updateArticle(buttonEl) {
  saveWithStatus('published', buttonEl, t('js_updated'));
}

// Publishing puts the article on the homepage and in the RSS feed, where a
// feed reader may pick it up within minutes: it asks first.
function publishArticle(buttonEl) {
  var titleText = document.getElementById('title').value.trim();
  if (titleText === '') {
    pbToast(t('js_title_for_to_publish'), 'warning');
    document.getElementById('title').focus();
    return;
  }
  pbConfirm(t('js_publish_title'), t('js_publish_body').replace('{title}', titleText),
            t('admin_publish'), 'primary', function() {
    saveWithStatus('published', buttonEl, t('js_published'));
  });
}

function unpublishArticle(buttonEl) {
  var titleText = document.getElementById('title').value.trim();
  pbConfirm(t('js_withdraw_title'), t('js_withdraw_body').replace('{title}', titleText),
            t('admin_withdraw'), 'danger', function() {
    saveWithStatus('draft', buttonEl, t('js_withdrawn'));
  });
}

function saveWithStatus(state, buttonEl, message) {
  if (savingNow) { return; }
  savingNow = true;
  pbBusy(buttonEl, true);

  pbPostJson('/save', articleData(state))
    .then(function(res) {
      savingNow = false;
      pbBusy(buttonEl, false);
      if (!res.ok) {
        pbToast(t('js_save_error') + ' ' + res.error, 'danger');
        return;
      }
      applySavedSlug(res);
      articleState = state;
      updateStatePanel(res.url);
      markEditorClean();
      var nowTime = t('js_autosaved_at');
      if (state === 'published') { nowTime = t('js_updated_at'); }
      if (state === 'scheduled') { nowTime = t('js_saved_at'); }
      setAutosaveIndicator(nowTime.replace('{time}', currentTime()), false);
      // The address bar still says "new article" after the first save of a
      // new one; correcting it means a reload would reopen the right article.
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, '',
          '/edit?slug=' + encodeURIComponent(res.slug));
      }
      pbToast(message, 'success');
    })
    .catch(function() {
      savingNow = false;
      pbBusy(buttonEl, false);
      pbToast(t('js_save_error'), 'danger');
    });
}

// --- Preview -------------------------------------------------------------------

// Opens the page as it is in the editor right now, in a new tab, and saves
// nothing: the fields travel in a form posted to /preview, which answers
// with the public page. Saving first, as the preview of the translation used
// to, would put the half-done changes of a published article online.
function previewArticle(lang) {
  var modulo = document.createElement('form');
  modulo.method = 'post';
  modulo.action = '/preview';
  modulo.target = '_blank';
  var fields = {
    csrf_token: window.PB_CSRF,
    language: lang || pbPage('main_language', 'it'),
    data: JSON.stringify(articleData())
  };
  for (var itemName in fields) {
    var fieldEl = document.createElement('input');
    fieldEl.type = 'hidden';
    fieldEl.name = itemName;
    fieldEl.value = fields[itemName];
    modulo.appendChild(fieldEl);
  }
  document.body.appendChild(modulo);
  modulo.submit();
  modulo.remove();
}

function previewTranslation() {
  previewArticle(pbPage('secondary_language', 'en'));
}

function deleteItem() {
  var titleText = document.getElementById('title').value;
  pbConfirm(t('js_delete_title'),
            t('js_delete_body').replace('{title}', titleText),
            t('admin_delete'), 'danger',
            function() {
    // originalSlug, not the slug the page was opened with: after a rename
    // the old address no longer exists, and deleting it would delete nothing.
    pbPostJson('/delete', { slug: originalSlug })
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
var initialRawConfig = '';

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
  watchImageDescriptions(quillHome);
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
  var cardContents = pbPage('card_contents', []);
  editorCard = [];
  for (var c = 0; c < cardContents.length; c++) {
    var singleCardEditor = new Quill('#card-editor-' + c, {
      theme: 'snow',
      modules: { blotFormatter: {}, toolbar: TOOLBAR_CARD }
    });
    singleCardEditor.root.innerHTML = cardContents[c];
    singleCardEditor.update(Quill.sources.SILENT);
    attachImageOverlay(singleCardEditor);
    handlePastedImages(singleCardEditor, null);
    editorCard.push(singleCardEditor);
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
  var projectList = document.querySelectorAll('#list-box-projects .project-config');
  for (var pr = 0; pr < projectList.length; pr++) { updateProjectPreview(projectList[pr]); }

  applyToolbarTooltips();

  quillHome.on('text-change', function() { updatePreview(); });

  updateCommentGroups();
  updateAiTrainingGroup();
  updateTranslationGroups();

  updateCustomCodeNote();
  watchCodeList(document.getElementById('list-box-code'), null);
  // Enter in a field of the templates creates the code, as a form would.
  document.getElementById('template-fields').addEventListener('keydown', function(evt) {
    if (evt.key === 'Enter') {
      evt.preventDefault();
      createCodeFromTemplate();
    }
  });
  savedConsentVersion = pbPage('consent_version', 1);
  consentVersion = savedConsentVersion;

  // --- Advanced config.json editor ---
  initialRawConfig = pbPage('config_raw', '');
  document.getElementById('config-raw').value = initialRawConfig;

  labelQuillEditors();
  watchConfigChanges();
  indexSettingsSearch();
  watchFilledFields();
  showConfigSection(false);
  window.addEventListener('hashchange', function() { showConfigSection(true); });
}

// Quill writes into a div of its own: the name and the help the template
// gave the editor's box go onto that div, where screen readers look.
function labelQuillEditors() {
  var boxes = document.querySelectorAll('.ql-container');
  for (var i = 0; i < boxes.length; i++) {
    var area = boxes[i].querySelector('.ql-editor');
    var attrs = ['aria-labelledby', 'aria-describedby'];
    for (var j = 0; j < attrs.length; j++) {
      var val = boxes[i].getAttribute(attrs[j]);
      if (val) { area.setAttribute(attrs[j], val); }
    }
    area.setAttribute('role', 'textbox');
    area.setAttribute('aria-multiline', 'true');
  }
}

/* --- Settings: one section at a time ------------------------------------- */

// The Italian names the sections had in the address before they went
// English: a bookmark or a link in an old email still lands on the section.
var LEGACY_SECTION_HASHES = {
  sito: 'site', biografia: 'biography', progetti: 'projects', pagine: 'boxes', commenti: 'comments',
  traduzione: 'translation', statistiche: 'analytics', codici: 'code', avanzate: 'advanced', elenco: 'list'
};

// Shows the section named in the address (#site, #home...). With none, or
// with #list, the panel of all the sections shows, on a computer as on a
// phone. After a click (moveFocus) the focus moves to the title of what
// is now on screen, so a screen reader starts from there.
function showConfigSection(moveFocus) {
  var request = window.location.hash.replace('#', '');
  if (LEGACY_SECTION_HASHES[request]) {
    request = LEGACY_SECTION_HASHES[request];
    history.replaceState(null, '', '#' + request);
  }
  var sections = document.querySelectorAll('.settings .section');
  var foundOne = null;
  for (var i = 0; i < sections.length; i++) {
    if (sections[i].getAttribute('data-section') === request) { foundOne = sections[i]; }
  }
  for (var j = 0; j < sections.length; j++) {
    sections[j].hidden = sections[j] !== foundOne;
  }
  document.getElementById('section-list').hidden = foundOne !== null;

  var key = foundOne ? foundOne.getAttribute('data-section') : 'list';
  document.getElementById('settings').setAttribute('data-section', key);
  // A photo uploaded or a translation filled in writes into a field without
  // the input event: looking again on every visit keeps the colours right.
  markFilledFields();
  updateSaveBar();

  if (foundOne !== null) {
    // CodeMirror measures itself when created: inside a hidden section it
    // measured nothing, so it has to look again now that it can be seen.
    var codes = foundOne.querySelectorAll('.CodeMirror');
    for (var c = 0; c < codes.length; c++) { codes[c].CodeMirror.refresh(); }
  }
  if (moveFocus) {
    window.scrollTo(0, 0);
    var titleText = foundOne ? foundOne.querySelector('h1') : document.getElementById('sections-list-title');
    titleText.setAttribute('tabindex', '-1');
    titleText.focus({ preventScroll: true });
  }
}

/* --- Settings: the fields already filled in --------------------------------- */

// The fields that hold something take a green tint, so a long section
// shows at a glance what is done and what is still empty. Choices
// (select) always hold a value and are left alone; ticked boxes are
// coloured by the CSS on their own. The search box and the raw
// config.json are tools, not settings.
var FIELDS_TO_MARK = 'input[type="text"], input[type="url"], input[type="email"], ' +
                       'input[type="number"], input[type="password"], input:not([type]), textarea';

function markFilled(fieldEl) {
  if (!fieldEl.matches || !fieldEl.matches(FIELDS_TO_MARK)) { return; }
  if (fieldEl.closest('#code-templates') || fieldEl.id === 'search-settings' || fieldEl.id === 'config-raw') {
    return;
  }
  fieldEl.classList.toggle('filled', fieldEl.value.trim() !== '');
}

function markFilledFields() {
  var fields = document.querySelectorAll('#settings .section :is(' + FIELDS_TO_MARK + ')');
  for (var i = 0; i < fields.length; i++) { markFilled(fields[i]); }
}

function watchFilledFields() {
  var page = document.getElementById('settings');
  page.addEventListener('input', function(evt) { markFilled(evt.target); });
  page.addEventListener('change', function(evt) { markFilled(evt.target); });
  // Cards of code and projects added on the page bring fields of their own.
  var lists = ['list-box-code', 'list-box-projects'];
  for (var i = 0; i < lists.length; i++) {
    new MutationObserver(markFilledFields)
      .observe(document.getElementById(lists[i]), { childList: true });
  }
  markFilledFields();
}

/* --- Settings: searching the panel ------------------------------------------ */

// Lower case and without accents, so "pubblicità" is found by "pubblicita".
function normalizeSearch(textValue) {
  return textValue.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

// Each card is found by its name, its description and its keywords, and
// also by the words of its section: the titles and the labels of the
// fields. Someone who types "smtp" or "giscus" finds the right card even
// though neither word is on it.
function indexSettingsSearch() {
  var cardSet = document.querySelectorAll('.card-setting');
  for (var i = 0; i < cardSet.length; i++) {
    var section = document.getElementById('section-' + cardSet[i].getAttribute('data-section'));
    var words = [cardSet[i].textContent, cardSet[i].getAttribute('data-search') || ''];
    if (section) {
      var nameList = section.querySelectorAll('h1, h2, label, .field-title');
      for (var j = 0; j < nameList.length; j++) { words.push(nameList[j].textContent); }
    }
    cardSet[i].setAttribute('data-index', normalizeSearch(words.join(' ')));
  }
}

// Every word typed has to be somewhere in a card's index for it to stay.
function filterSettings() {
  var words = normalizeSearch(document.getElementById('search-settings').value)
    .split(/\s+/).filter(function(p) { return p !== ''; });
  var visibleOnes = 0;
  var groups = document.querySelectorAll('.panel-group');
  for (var g = 0; g < groups.length; g++) {
    var inGroup = 0;
    var cardSet = groups[g].querySelectorAll('.card-setting');
    for (var i = 0; i < cardSet.length; i++) {
      var idx = cardSet[i].getAttribute('data-index') || '';
      var keeps = words.every(function(p) { return idx.indexOf(p) !== -1; });
      cardSet[i].parentNode.hidden = !keeps;
      if (keeps) { inGroup++; }
    }
    groups[g].hidden = inGroup === 0;
    visibleOnes += inGroup;
  }
  document.getElementById('panel-none').hidden = visibleOnes > 0;
}

// After a save the states on the cards are old: the page asks the server
// for the panel again and swaps the cards in, keeping what was typed in
// the search. A failure leaves the old cards; the next visit is right.
function refreshSettingsPanel() {
  fetch('/config', { credentials: 'same-origin' })
    .then(function(reply) { return reply.ok ? reply.text() : Promise.reject(); })
    .then(function(textValue) {
      var newValue = new DOMParser().parseFromString(textValue, 'text/html').getElementById('panel-groups');
      if (!newValue) { return; }
      document.getElementById('panel-groups').innerHTML = newValue.innerHTML;
      // The warnings at the top of each section are old too.
      var notices = document.querySelectorAll('.section-notices');
      for (var i = 0; i < notices.length; i++) {
        var fresco = newValue.ownerDocument.getElementById(notices[i].id);
        if (fresco) {
          notices[i].innerHTML = fresco.innerHTML;
          notices[i].hidden = fresco.hidden;
        }
      }
      indexSettingsSearch();
      filterSettings();
    })
    .catch(function() { });
}

/* --- Settings: unsaved changes ------------------------------------------- */

var configChanged = false;

// Every field of the sections counts, except the hand-edited config.json,
// which has its own button, and the template chooser, which only prepares
// a card. Adding or removing a card of code counts too.
function watchConfigChanges() {
  var page = document.getElementById('settings');
  var mark = function(evt) {
    if (evt.target.closest('#section-advanced, #code-templates')) { return; }
    markConfigDirty();
  };
  page.addEventListener('input', mark);
  page.addEventListener('change', mark);
  var editors = [quillHome, quillHomeEn, quillBio, quillBioEn].concat(editorCard);
  for (var i = 0; i < editors.length; i++) {
    editors[i].on('text-change', markConfigDirty);
  }
  new MutationObserver(markConfigDirty)
    .observe(document.getElementById('list-box-code'), { childList: true });
  // Adding, removing and moving a project changes the list itself.
  new MutationObserver(markConfigDirty)
    .observe(document.getElementById('list-box-projects'), { childList: true });

  window.addEventListener('beforeunload', function(evt) {
    if (!configChanged) { return undefined; }
    evt.preventDefault();
    evt.returnValue = t('js_settings_page_not_saved_pl');
    return t('js_settings_page_not_saved_pl');
  });
}

function markConfigDirty() {
  if (configChanged) { return; }
  configChanged = true;
  updateSaveBar();
}

// The save bar says whether something is waiting to be saved. Where there
// is nothing to save - the list of sections, the raw config.json with its
// own button - it only shows up once something has changed.
function updateSaveBar() {
  var bar = document.getElementById('bar-save');
  var section = document.getElementById('settings').getAttribute('data-section');
  bar.hidden = !configChanged && (section === 'advanced' || section === 'list');
  bar.classList.toggle('modified', configChanged);
  document.getElementById('cancel-changes-made').hidden = !configChanged;
  document.getElementById('save-note').hidden = configChanged;
  document.getElementById('save-status').textContent =
    configChanged ? t('js_changes_made_from_to_save') : '';
}

// Throws the changes away by loading the page again, as it was saved.
function discardConfigChanges() {
  pbConfirm(t('js_cancel_changes_made_title'), t('js_cancel_changes_made_body'),
            t('admin_cancel_changes_made'), 'danger', function() {
    configChanged = false;
    window.location.reload();
  });
}

// Translates the home introduction from Italian to English with AI.
function translateHome(buttonEl) {
  translateEditorInto(buttonEl, quillHome, quillHomeEn, 'home-en-status');
}

// Translates the biography the same way.
function translateBiography(buttonEl) {
  translateEditorInto(buttonEl, quillBio, quillBioEn, 'bio-en-status');
}

// Sends the text of one editor to the translation service and puts the
// result into the other one.
function translateEditorInto(buttonEl, sourceValue, destination, stateId) {
  if (sourceValue.getText().trim() === '') {
    pbStatus(stateId, t('js_write_intro_first'));
    return;
  }
  pbBusy(buttonEl, true);
  pbStatus(stateId, t('js_translating'));

  pbPostJson('/translate', { text: sourceValue.root.innerHTML })
    .then(function(res) {
      pbBusy(buttonEl, false);
      if (res.ok === true) {
        destination.root.innerHTML = res.text;
        pbStatus(stateId,
          mediaNotice(t('js_translated_home'), res.media_recovered || 0));
      } else {
        pbStatus(stateId, t('js_error_prefix') + res.error);
      }
    })
    .catch(function() {
      pbBusy(buttonEl, false);
      pbStatus(stateId, '');
      pbToast(t('js_net_error_translation'), 'danger');
    });
}

// The subtitle, the role and the bio, translated in one go into the fields
// of the other language. Each is a request of its own, one after the
// other, so a failure leaves the others as they were.
function translateSiteTexts(buttonEl) {
  var pairs = [['subtitle', 'subtitle_en'], ['seo_author_role', 'seo_author_role_en'],
                ['seo_author_bio', 'seo_author_bio_en']];
  var toDo = pairs.filter(function(c) { return document.getElementById(c[0]).value.trim() !== ''; });
  if (toDo.length === 0) {
    pbStatus('site-en-status', t('js_write_site_texts_first'));
    return;
  }
  pbBusy(buttonEl, true);
  pbStatus('site-en-status', t('js_translating'));
  var nextOne = function(idx) {
    if (idx >= toDo.length) {
      pbBusy(buttonEl, false);
      pbStatus('site-en-status', t('js_translated_site_texts'));
      markFilledFields();
      markConfigDirty();
      return;
    }
    pbPostJson('/translate', { text: document.getElementById(toDo[idx][0]).value.trim() })
      .then(function(res) {
        if (res.ok !== true) {
          pbBusy(buttonEl, false);
          pbStatus('site-en-status', t('js_error_prefix') + res.error);
          return;
        }
        document.getElementById(toDo[idx][1]).value = res.text.trim();
        nextOne(idx + 1);
      })
      .catch(function() {
        pbBusy(buttonEl, false);
        pbStatus('site-en-status', '');
        pbToast(t('js_net_error_translation'), 'danger');
      });
  };
  nextOne(0);
}

/* --- Updates ------------------------------------------------------------- */

// The dashboard says so when an update is waiting. The server asks GitHub
// at most twice a day, so opening the dashboard costs nothing most times.
function showUpdateNotice() {
  var notice = document.getElementById('notice-update-notice');
  if (!notice) { return; }
  fetch('/updates-status', { credentials: 'same-origin', cache: 'no-store' })
    .then(function(reply) { return reply.json(); })
    .then(function(state) {
      if (state.available === true) {
        document.getElementById('notice-update-notice-text').textContent = state.message;
        notice.hidden = false;
      }
    })
    .catch(function() { });
}

function checkUpdates(force) {
  var row = document.getElementById('updates-state');
  row.textContent = t('upd_checking');
  fetch('/updates-status' + (force ? '?force=1' : ''), { credentials: 'same-origin', cache: 'no-store' })
    .then(function(reply) { return reply.json(); })
    .then(function(state) {
      row.textContent = state.message;
      var listEl = document.getElementById('updates-news');
      listEl.innerHTML = '';
      (state.news || []).forEach(function(row) {
        var entryEl = document.createElement('li');
        entryEl.textContent = row;
        listEl.appendChild(entryEl);
      });
      listEl.hidden = !state.news || state.news.length === 0;
      document.getElementById('update-now').hidden = state.can_update !== true;
      document.getElementById('update-help').hidden = state.can_update !== true;
      document.getElementById('updates-instructions').hidden = state.instructions !== true;
    })
    .catch(function() { row.textContent = ''; });
}

function installUpdate(buttonEl) {
  pbConfirm(t('upd_confirm_title'), t('upd_confirm_body'), t('admin_update_now'), 'primary', function() {
    var row = document.getElementById('updates-state');
    pbBusy(buttonEl, true);
    row.textContent = t('upd_installation');
    pbPostJson('/update', {})
      .then(function(outcome) {
        if (outcome.ok !== true) {
          pbBusy(buttonEl, false);
          row.textContent = outcome.error;
          return;
        }
        row.textContent = t('upd_restarting');
        waitForRestart();
      })
      .catch(function() {
        pbBusy(buttonEl, false);
        row.textContent = t('upd_offline');
      });
  });
}

// The old process answers for another moment, then the new one starts:
// wait a little, then knock until it opens. Sessions live in memory, so
// the new process asks for the password again.
function waitForRestart() {
  var attempts = 0;
  var knock = function() {
    attempts++;
    fetch('/pyblog-ping', { cache: 'no-store' })
      .then(function(reply) {
        if (!reply.ok) { return Promise.reject(); }
        document.getElementById('updates-state').textContent = t('upd_restarted');
        setTimeout(function() { window.location.href = '/login'; }, 1500);
      })
      .catch(function() {
        if (attempts < 60) { setTimeout(knock, 1500); }
      });
  };
  setTimeout(knock, 4000);
}

function setAutomaticCheck(checkbox) {
  pbPostJson('/updates-auto', { on: checkbox.checked })
    .then(function(outcome) { checkbox.checked = outcome.auto === true; })
    .catch(function() { checkbox.checked = !checkbox.checked; });
}

/* --- The media library ---------------------------------------------------- */

// The filter buttons and the search work together: a card stays when it
// matches both.
function filterMedia(buttonEl) {
  if (buttonEl) {
    var btns = document.querySelectorAll('#filter-media .segment');
    for (var i = 0; i < btns.length; i++) {
      btns[i].setAttribute('aria-pressed', btns[i] === buttonEl ? 'true' : 'false');
    }
  }
  var chosen = document.querySelector('#filter-media .segment[aria-pressed="true"]');
  var filterValue = chosen ? chosen.getAttribute('data-filter') : 'all';
  var textValue = document.getElementById('search-media').value.trim().toLowerCase();
  var cardSet = document.querySelectorAll('.media-card');
  var visibleOnes = 0;
  for (var j = 0; j < cardSet.length; j++) {
    var keeps = (filterValue === 'all' || cardSet[j].getAttribute('data-used') === filterValue)
      && cardSet[j].getAttribute('data-name').indexOf(textValue) !== -1;
    cardSet[j].hidden = !keeps;
    if (keeps) { visibleOnes++; }
  }
  document.getElementById('media-library-no-result').hidden = visibleOnes > 0 || cardSet.length === 0;
}

function copyMediaAddress(address) {
  var done = function() { pbToast(t('js_media_copied'), 'success'); };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(address).then(done, function() { window.prompt('', address); });
  } else {
    window.prompt('', address);
  }
}

function sendMediaDeletion(buttonEl, nameList) {
  pbBusy(buttonEl, true);
  pbPostJson('/media-library-delete', { names: nameList })
    .then(function(outcome) {
      if (outcome.ok !== true) {
        pbBusy(buttonEl, false);
        pbToast(t('js_error_prefix') + outcome.error, 'danger');
        return;
      }
      window.location.reload();
    })
    .catch(function() {
      pbBusy(buttonEl, false);
      pbToast(t('admin_failure_saving'), 'danger');
    });
}

function deleteMedia(buttonEl, itemName, uses) {
  var bodyEl = uses > 0 ? t('js_media_delete_used').replace('{n}', uses) : t('js_media_delete_body');
  pbConfirm(t('js_media_delete_title'), itemName + '\n\n' + bodyEl, t('admin_delete'), 'danger',
            function() { sendMediaDeletion(buttonEl, [itemName]); });
}

function deleteUnusedMedia(buttonEl) {
  var cardSet = document.querySelectorAll('.media-card[data-used="0"]');
  var nameList = [];
  for (var i = 0; i < cardSet.length; i++) {
    nameList.push(cardSet[i].querySelector('.media-name').textContent);
  }
  if (nameList.length === 0) { return; }
  pbConfirm(t('js_media_delete_title'), t('js_media_cleanup_body').replace('{n}', nameList.length),
            t('admin_delete'), 'danger', function() { sendMediaDeletion(buttonEl, nameList); });
}

// The files go one after the other, through the same door as the editor:
// the same checks, and pictures shrunk in the browser first.
function uploadToLibrary(fieldEl) {
  var file = Array.prototype.slice.call(fieldEl.files);
  fieldEl.value = '';
  var buttonEl = document.getElementById('media-library-upload');
  var loaded = 0;
  var nextItem = function(idx) {
    if (idx >= file.length) {
      pbBusy(buttonEl, false);
      if (loaded > 0) { window.location.reload(); }
      return;
    }
    var chosen = file[idx];
    var video = chosen.type.indexOf('video/') === 0;
    if (!fileFitsLimit(chosen, video ? pbPage('max_video_mb', 100) : pbPage('max_image_mb', 10))) {
      nextItem(idx + 1);
      return;
    }
    pbStatus('media-library-state', t('js_media_uploading').replace('{i}', idx + 1).replace('{n}', file.length));
    var pronto = video ? Promise.resolve(chosen) : resizeImageBeforeUpload(chosen, pbPage('max_image_width', 1600));
    pronto
      .then(function(toSend) { return sendFile(toSend, 'media-library-state'); })
      .then(function(address) {
        if (address) { loaded++; }
        nextItem(idx + 1);
      });
  };
  if (file.length > 0) {
    pbBusy(buttonEl, true);
    nextItem(0);
  }
}

/* --- Restoring a backup -------------------------------------------------- */

// The archive goes as it is, not inside a form: with videos it can weigh
// hundreds of megabytes, and the server writes it straight to a file.
function restoreBackup(buttonEl) {
  var fieldEl = document.getElementById('file-restoring');
  if (!fieldEl.files || fieldEl.files.length === 0) {
    pbStatus('restoring-state', t('js_choose_backup'));
    return;
  }
  var file = fieldEl.files[0];
  pbConfirm(t('js_restoring_title'), t('js_restoring_body'), t('js_restoring_confirm'),
            'danger', function() {
    pbBusy(buttonEl, true);
    pbStatus('restoring-state', t('js_restoring_in_progress'));
    pbFetch('/restore', { method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file })
      .then(function(reply) { return reply.json(); })
      .then(function(outcome) { showRestoreResult(buttonEl, outcome); })
      .catch(function() {
        pbBusy(buttonEl, false);
        pbStatus('restoring-state', '');
        pbToast(t('js_restoring_failure_network'), 'danger');
      });
  });
}

// One of the automatic backups, to undo a restore.
function restoreAutomatic(buttonEl, itemName) {
  pbConfirm(t('js_restoring_title'), t('js_restoring_automatic_body'), t('js_restoring_confirm'),
            'danger', function() {
    pbBusy(buttonEl, true);
    pbStatus('restoring-state', t('js_restoring_in_progress'));
    pbPostJson('/restore-automatic', { file: itemName })
      .then(function(outcome) { showRestoreResult(buttonEl, outcome); })
      .catch(function() {
        pbBusy(buttonEl, false);
        pbStatus('restoring-state', '');
        pbToast(t('js_restoring_failure_network'), 'danger');
      });
  });
}

function showRestoreResult(buttonEl, outcome) {
  pbBusy(buttonEl, false);
  pbStatus('restoring-state', '');
  if (!outcome || outcome.ok !== true) {
    pbToast(t('js_error_prefix') + (outcome && outcome.error ? outcome.error : ''), 'danger');
    return;
  }
  var textValue = t('js_restoring_made').replace('{a}', outcome.articles).replace('{m}', outcome.media);
  if (outcome.ignored && outcome.ignored.length > 0) {
    textValue = textValue + ' ' + t('js_restoring_ignored').replace('{n}', outcome.ignored.length);
  }
  pbStatus('restoring-state', textValue);
  pbToast(textValue, 'success');
  // The list of automatic backups has one more: the page shows it.
  setTimeout(function() { window.location.reload(); }, 2500);
}

/* --- Settings: the biography's photo ------------------------------------- */

function updateBioPhotoPreview() {
  var address = document.getElementById('bio_photo').value.trim();
  var previewEl = document.getElementById('bio-photo-preview');
  document.getElementById('bio-photo-remove').hidden = address === '';
  if (address === '') {
    previewEl.removeAttribute('src');
    previewEl.hidden = true;
    return;
  }
  previewEl.src = address;
  previewEl.hidden = false;
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
  var template = document.getElementById('project-template');
  var card = template.content.firstElementChild.cloneNode(true);
  document.getElementById('list-box-projects').appendChild(card);
  updateProjectsNote();
  card.querySelector('.project-name').focus();
}

// Moves a project one place up or down: the order of the list is the order
// on the homepage. The focus stays on the button that was pressed.
function moveProject(buttonEl, step) {
  var card = buttonEl.closest('.project-config');
  var itemList = card.parentNode;
  if (step < 0 && card.previousElementSibling) {
    itemList.insertBefore(card, card.previousElementSibling);
  } else if (step > 0 && card.nextElementSibling) {
    itemList.insertBefore(card.nextElementSibling, card);
  }
  buttonEl.focus();
}

function removeProject(buttonEl) {
  var card = buttonEl.closest('.project-config');
  var itemName = card.querySelector('.project-name').value.trim() || t('admin_project_without_name');
  pbConfirm(t('admin_project_delete'), itemName, t('admin_project_delete'), 'danger',
    function() {
      card.remove();
      updateProjectsNote();
    });
}

function updateProjectsNote() {
  document.getElementById('projects-empty-note').hidden =
    document.querySelectorAll('#list-box-projects .project-config').length > 0;
}

// One file field serves every card: it remembers which card asked.
var projectLoading = null;

function chooseProjectImage(buttonEl) {
  projectLoading = buttonEl.closest('.project-config');
  document.getElementById('file-project').click();
}

function uploadProjectImage() {
  var card = projectLoading;
  if (card === null) { return; }
  var state = card.querySelector('.project-state');
  state.id = 'project-upload-state';
  uploadChosenFile('file-project', pbPage('max_image_mb', 10), 'project-upload-state',
                   t('js_uploading_image'))
    .then(function(url) {
      state.removeAttribute('id');
      if (url === null) { return; }
      card.querySelector('.project-picture').value = url;
      updateProjectPreview(card);
      markConfigDirty();
      state.textContent = t('js_image_uploaded');
    });
}

function updateProjectPreview(card) {
  var address = card.querySelector('.project-picture').value.trim();
  var previewEl = card.querySelector('.project-preview');
  if (address === '') {
    previewEl.removeAttribute('src');
    previewEl.hidden = true;
    return;
  }
  previewEl.src = address;
  previewEl.hidden = false;
}

// The projects as they are saved, in the order of the list.
function projectsData() {
  var cardList = document.querySelectorAll('#list-box-projects .project-config');
  var listEl = [];
  for (var i = 0; i < cardList.length; i++) {
    var c = cardList[i];
    listEl.push({
      name: c.querySelector('.project-name').value.trim(),
      description: c.querySelector('.project-description').value.trim(),
      description_en: c.querySelector('.project-description-en').value.trim(),
      url: c.querySelector('.project-link').value.trim(),
      image: c.querySelector('.project-picture').value.trim(),
      visible: c.querySelector('.project-visible').checked
    });
  }
  return listEl;
}

// Shows only the field group of the chosen comment system.
function updateCommentGroups() {
  var choiceValue = document.getElementById('comments').value;
  var giscusGroup = document.getElementById('group-giscus');
  var disqusGroup = document.getElementById('group-disqus');
  giscusGroup.classList.remove('active');
  disqusGroup.classList.remove('active');
  if (choiceValue === 'giscus') {
    giscusGroup.classList.add('active');
  }
  if (choiceValue === 'disqus') {
    disqusGroup.classList.add('active');
  }
}

// Shows the licensing contact field only when the policy requires one.
function updateAiTrainingGroup() {
  var choiceValue = document.getElementById('ai_training_policy').value;
  var group = document.getElementById('group-ai-licence');
  if (choiceValue === 'licensed') {
    group.style.display = 'block';
  } else {
    group.style.display = 'none';
  }
}

// Shows only the fields of the chosen translation service.
function updateTranslationGroups() {
  var choiceValue = document.getElementById('translation_service').value;
  var groups = ['deepl', 'google', 'llm', 'openai', 'deepseek'];
  for (var i = 0; i < groups.length; i++) {
    var element = document.getElementById('group-' + groups[i]);
    if (groups[i] === choiceValue) {
      element.classList.add('active');
    } else {
      element.classList.remove('active');
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
function newSnippetId(prefix) {
  var randomPart = Math.floor(Math.random() * 1679616).toString(36);
  return (prefix || 'snip') + '-' + Date.now().toString(36) + '-' + randomPart;
}

function customCodeCards(itemList) {
  if (itemList === null) { return []; }
  return itemList.querySelectorAll('.code-config');
}

// The empty-list note shows only while there are no cards at all.
function updateCustomCodeNote() {
  var note = document.getElementById('code-empty-note');
  if (note === null) { return; }
  note.hidden = customCodeCards(document.getElementById('list-box-code')).length > 0;
}

// A new card, cloned from the blank one the server rendered into a
// <template>: the markup and its translated labels live in the template file
// and nowhere else.
function cloneBlankCard(templateId, prefix) {
  var template = document.getElementById(templateId);
  var card = template.content.firstElementChild.cloneNode(true);
  card.setAttribute('data-id', newSnippetId(prefix));
  return card;
}

// The code box of a card: CodeMirror when the CDN delivered it, the plain
// textarea when it did not. CodeMirror cannot measure itself inside a closed
// <details>, so it starts the first time its card is opened.
function startCodeEditor(card) {
  var area = card.querySelector('.code-text');
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
  var area = card.querySelector('.code-text');
  if (area.pbEditor) { return area.pbEditor.getValue(); }
  return area.value;
}

function selectedLabel(dropdown) {
  var choiceValue = dropdown.options[dropdown.selectedIndex];
  if (!choiceValue) { return ''; }
  return choiceValue.textContent;
}

function consentLabel(val) {
  if (val === 'statistics') { return t('consent_statistics'); }
  if (val === 'marketing') { return t('consent_marketing'); }
  return t('consent_necessary');
}

// The line under the name of a folded card, rewritten while the fields
// change, in the words the server used to draw it: where the code goes, on
// which pages, which consent it waits for.
function updateCardSummary(card) {
  var itemName = card.querySelector('.code-name').value.trim();
  if (itemName === '') { itemName = t('admin_code_without_name'); }
  card.querySelector('.code-summary-name').textContent = itemName;

  var placement = card.querySelector('.code-position');
  var pieces = [selectedLabel(placement)];
  var pointLabel = card.querySelector('.code-anchor-point-label-text');
  if (placement.value === 'anchor' && pointLabel && pointLabel.value !== '') {
    pieces = [pointLabel.value];
  }
  var pointBox = card.querySelector('.code-point');
  if (pointBox) { pointBox.hidden = placement.value !== 'anchor'; }
  var pageScope = card.querySelector('.code-scope');
  if (pageScope !== null) { pieces.push(selectedLabel(pageScope)); }
  pieces.push(consentLabel(card.querySelector('.code-consent').value));
  card.querySelector('.code-summary-where').textContent = pieces.join(' · ');

  var isActive = card.querySelector('.code-active').checked;
  var state = card.querySelector('.code-summary-state');
  state.textContent = isActive ? t('admin_code_active') : t('admin_code_off_m');
  state.classList.toggle('off', !isActive);
}

// Wires a list of cards: the summary follows the fields and the code editor
// starts when a card opens. Listening on the list covers the cards added
// later as well. "toggle" does not bubble, hence the capture phase.
function watchCodeList(itemList, onChange) {
  if (itemList === null) { return; }
  var refresh = function(evt) {
    var card = evt.target.closest('.code-config');
    if (card === null) { return; }
    updateCardSummary(card);
    if (onChange) { onChange(); }
    // Choosing "a point on the page" with no point yet opens the page.
    if (evt.type === 'change' && evt.target.classList.contains('code-position')
        && evt.target.value === 'anchor' && card.querySelector('.code-anchor-point').value === '') {
      openPointPicker(evt.target);
    }
  };
  itemList.addEventListener('input', refresh);
  itemList.addEventListener('change', refresh);
  itemList.addEventListener('toggle', function(evt) {
    var card = evt.target;
    if (card.classList && card.classList.contains('code-config') && card.open) {
      startCodeEditor(card);
    }
  }, true);
  var openOnes = itemList.querySelectorAll('.code-config[open]');
  for (var i = 0; i < openOnes.length; i++) {
    startCodeEditor(openOnes[i]);
  }
}

function removeCustomCode(buttonEl) {
  var card = buttonEl.closest('.code-config');
  if (card === null) { return; }
  var itemName = card.querySelector('.code-name').value.trim();
  if (itemName === '') { itemName = t('admin_code_title'); }
  pbConfirm(t('admin_code_delete'), itemName, t('admin_code_delete'), 'danger',
    function() {
      card.remove();
      updateCustomCodeNote();
      if (pbPage('page', '') === 'editor') { markEditorDirty(); }
    });
}

// Reads a list of cards back into the snippets that are saved: the site's
// into config.json, an article's into the article.
function customCodeData(itemList, prefix) {
  var cards = customCodeCards(itemList);
  var payload = [];
  for (var i = 0; i < cards.length; i++) {
    var card = cards[i];
    var id = card.getAttribute('data-id');
    if (id === null || id === '') {
      // Written back on the card, so the next save sends the same id.
      id = newSnippetId(prefix);
      card.setAttribute('data-id', id);
    }
    var snippet = {
      id: id,
      name: card.querySelector('.code-name').value.trim(),
      enabled: card.querySelector('.code-active').checked,
      position: card.querySelector('.code-position').value,
      consent: card.querySelector('.code-consent').value,
      code: cardCode(card)
    };
    var pageScope = card.querySelector('.code-scope');
    if (pageScope !== null) { snippet.scope = pageScope.value; }
    // The point chosen on the page travels with the snippet even when another
    // position is picked for now: going back to it finds it again.
    var anchorEl = card.querySelector('.code-anchor-point');
    if (anchorEl !== null && anchorEl.value !== '') {
      snippet.anchor_selector = anchorEl.value;
      snippet.anchor_where = card.querySelector('.code-anchor-point-where').value || 'after';
      snippet.anchor_label = card.querySelector('.code-anchor-point-label-text').value;
      snippet.anchor_page = card.querySelector('.code-anchor-point-page').value;
    }
    payload.push(snippet);
  }
  return payload;
}

// --- Ready-made code for the common services ---------------------------------

// The fields of a template accept the id the way people copy it: with
// spaces around, in lower case, with or without its prefix. normalize puts
// it in the one shape pattern checks.
function adsensePublisherField() {
  return {
    labelText: t('js_template_field_pub'),
    example: 'pub-1234567890123456',
    pattern: /^pub-\d{10,20}$/,
    normalize: function(val) {
      val = val.toLowerCase().replace(/^ca-/, '');
      if (/^\d+$/.test(val)) { val = 'pub-' + val; }
      return val;
    }
  };
}

function upperCaseId(val) {
  return val.toUpperCase();
}

// Each service: the fields it needs and the cards it writes from them, with
// the position, the pages and the consent that suit it. The code is the one
// the service itself publishes, with the id put in. A template is a starting
// point: everything stays editable in the card.
function codeTemplates() {
  return {
    ga4: {
      fields: [{ labelText: t('js_template_field_ga4'), example: 'G-ABC123DEF4',
                pattern: /^G-[A-Z0-9]{4,15}$/, normalize: upperCaseId }],
      cardSet: function(values, itemName) {
        return [{ itemName: itemName, placement: 'head', pageScope: 'all', consentKind: 'statistics', snippetCode:
          '<!-- Google tag (gtag.js) -->\n' +
          '<script async src="https://www.googletagmanager.com/gtag/js?id=' + values[0] + '"></script>\n' +
          '<script>\n' +
          '  window.dataLayer = window.dataLayer || [];\n' +
          '  function gtag(){dataLayer.push(arguments);}\n' +
          "  gtag('js', new Date());\n" +
          '\n' +
          "  gtag('config', '" + values[0] + "');\n" +
          '</script>' }];
      }
    },
    // Tag Manager comes in two pieces, one for the head and one right after
    // <body>. It waits for the statistics consent: the tags it loads are
    // not known here, and the safe side is not to load them uninvited.
    gtm: {
      fields: [{ labelText: t('js_template_field_gtm'), example: 'GTM-ABC1234',
                pattern: /^GTM-[A-Z0-9]{4,12}$/, normalize: upperCaseId }],
      cardSet: function(values, itemName) {
        return [
          { itemName: itemName, placement: 'head', pageScope: 'all', consentKind: 'statistics', snippetCode:
            '<!-- Google Tag Manager -->\n' +
            "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':\n" +
            "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],\n" +
            "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=\n" +
            "'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);\n" +
            "})(window,document,'script','dataLayer','" + values[0] + "');</script>\n" +
            '<!-- End Google Tag Manager -->' },
          { itemName: itemName + ' (noscript)', placement: 'body_start', pageScope: 'all', consentKind: 'statistics', snippetCode:
            '<!-- Google Tag Manager (noscript) -->\n' +
            '<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=' + values[0] + '"\n' +
            'height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>\n' +
            '<!-- End Google Tag Manager (noscript) -->' }
        ];
      }
    },
    adsense_auto: {
      fields: [adsensePublisherField()],
      adsTxt: true,
      cardSet: function(values, itemName) {
        return [{ itemName: itemName, placement: 'head', pageScope: 'all', consentKind: 'marketing', snippetCode:
          '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-' + values[0] + '"\n' +
          '     crossorigin="anonymous"></script>' }];
      }
    },
    // One ad unit, in the sidebar to begin with: the place the layout keeps
    // for it. AdSense ignores its loader when the page already has one.
    adsense_unit: {
      fields: [adsensePublisherField(),
              { labelText: t('js_template_field_slot'), example: '1234567890', pattern: /^\d{6,12}$/ }],
      adsTxt: true,
      cardSet: function(values, itemName) {
        return [{ itemName: itemName, placement: 'sidebar', pageScope: 'all', consentKind: 'marketing', snippetCode:
          '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-' + values[0] + '"\n' +
          '     crossorigin="anonymous"></script>\n' +
          '<ins class="adsbygoogle"\n' +
          '     style="display:block"\n' +
          '     data-ad-client="ca-' + values[0] + '"\n' +
          '     data-ad-slot="' + values[1] + '"\n' +
          '     data-ad-format="auto"\n' +
          '     data-full-width-responsive="true"></ins>\n' +
          '<script>\n' +
          '     (adsbygoogle = window.adsbygoogle || []).push({});\n' +
          '</script>' }];
      }
    },
    google_ads: {
      fields: [{ labelText: t('js_template_field_aw'), example: 'AW-123456789',
                pattern: /^AW-\d{6,12}$/,
                normalize: function(val) {
                  val = val.toUpperCase();
                  if (/^\d+$/.test(val)) { val = 'AW-' + val; }
                  return val;
                } }],
      cardSet: function(values, itemName) {
        return [{ itemName: itemName, placement: 'head', pageScope: 'all', consentKind: 'marketing', snippetCode:
          '<!-- Google tag (gtag.js) -->\n' +
          '<script async src="https://www.googletagmanager.com/gtag/js?id=' + values[0] + '"></script>\n' +
          '<script>\n' +
          '  window.dataLayer = window.dataLayer || [];\n' +
          '  function gtag(){dataLayer.push(arguments);}\n' +
          "  gtag('js', new Date());\n" +
          '\n' +
          "  gtag('config', '" + values[0] + "');\n" +
          '</script>' }];
      }
    },
    meta_pixel: {
      fields: [{ labelText: t('js_template_field_pixel'), example: '1234567890123456',
                pattern: /^\d{10,20}$/ }],
      cardSet: function(values, itemName) {
        return [{ itemName: itemName, placement: 'head', pageScope: 'all', consentKind: 'marketing', snippetCode:
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
          "fbq('init', '" + values[0] + "');\n" +
          "fbq('track', 'PageView');\n" +
          '</script>\n' +
          '<noscript><img height="1" width="1" style="display:none"\n' +
          'src="https://www.facebook.com/tr?id=' + values[0] + '&ev=PageView&noscript=1"\n' +
          '/></noscript>\n' +
          '<!-- End Meta Pixel Code -->' }];
      }
    },
    clarity: {
      fields: [{ labelText: t('js_template_field_clarity'), example: 'abcd1234ef',
                pattern: /^[a-z0-9]{6,14}$/,
                normalize: function(val) { return val.toLowerCase(); } }],
      cardSet: function(values, itemName) {
        return [{ itemName: itemName, placement: 'head', pageScope: 'all', consentKind: 'statistics', snippetCode:
          '<script type="text/javascript">\n' +
          '    (function(c,l,a,r,i,t,y){\n' +
          '        c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};\n' +
          '        t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;\n' +
          '        y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);\n' +
          '    })(window, document, "clarity", "script", "' + values[0] + '");\n' +
          '</script>' }];
      }
    }
  };
}

// "Add code" opens the choice of templates in its place.
function openCodeTemplates() {
  var panel = document.getElementById('code-templates');
  if (panel === null) { return; }
  panel.hidden = false;
  document.getElementById('btn-add-code').hidden = true;
  updateCodeTemplateFields();
  document.getElementById('template-code').focus();
}

function closeCodeTemplates() {
  document.getElementById('code-templates').hidden = true;
  document.getElementById('btn-add-code').hidden = false;
}

// The fields of the chosen template, built with textContent: a label is a
// translated string, never markup.
function updateCodeTemplateFields() {
  var containerEl = document.getElementById('template-fields');
  containerEl.textContent = '';
  var template = codeTemplates()[document.getElementById('template-code').value];
  if (!template) { return; }
  for (var i = 0; i < template.fields.length; i++) {
    var labelText = document.createElement('label');
    labelText.setAttribute('for', 'template-field-' + i);
    labelText.textContent = template.fields[i].labelText;
    var fieldEl = document.createElement('input');
    fieldEl.type = 'text';
    fieldEl.id = 'template-field-' + i;
    fieldEl.placeholder = template.fields[i].example;
    fieldEl.spellcheck = false;
    fieldEl.autocomplete = 'off';
    containerEl.appendChild(labelText);
    containerEl.appendChild(fieldEl);
  }
}

// A card at the bottom of the Settings list, empty or filled from a template.
function addCustomCodeCard(cardEl) {
  var itemList = document.getElementById('list-box-code');
  var card = cloneBlankCard('code-template', 'snip');
  if (cardEl) {
    card.querySelector('.code-name').value = cardEl.itemName;
    card.querySelector('.code-position').value = cardEl.placement;
    card.querySelector('.code-scope').value = cardEl.pageScope;
    card.querySelector('.code-consent').value = cardEl.consentKind;
    card.querySelector('.code-text').value = cardEl.snippetCode;
  }
  itemList.appendChild(card);
  updateCardSummary(card);
  updateCustomCodeNote();
  startCodeEditor(card);
  return card;
}

// Adds a line to ads.txt unless it is there already. Says whether it did.
function addAdsTxtLine(row) {
  var fieldEl = document.getElementById('ads_txt');
  if (fieldEl === null) { return false; }
  var rows = fieldEl.value.split('\n');
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].replace(/\s+/g, '').toLowerCase() === row.replace(/\s+/g, '').toLowerCase()) {
      return false;
    }
  }
  var textValue = fieldEl.value.replace(/\s+$/, '');
  fieldEl.value = (textValue === '' ? '' : textValue + '\n') + row;
  return true;
}

function createCodeFromTemplate() {
  var dropdown = document.getElementById('template-code');
  var choiceValue = dropdown.value;
  if (choiceValue === 'free') {
    var empty = addCustomCodeCard(null);
    closeCodeTemplates();
    empty.querySelector('.code-name').focus();
    return;
  }

  // Two Google Analytics on the same page count every visit twice.
  if (choiceValue === 'ga4' && document.getElementById('analytics_id').value.trim() !== '') {
    pbToast(t('js_template_ga4_double'), 'warning');
    return;
  }

  var template = codeTemplates()[choiceValue];
  var values = [];
  for (var i = 0; i < template.fields.length; i++) {
    var definition = template.fields[i];
    var fieldEl = document.getElementById('template-field-' + i);
    var val = fieldEl.value.replace(/\s+/g, '');
    if (definition.normalize) { val = definition.normalize(val); }
    if (!definition.pattern.test(val)) {
      pbToast(t('js_template_not_valid').replace('{field}', definition.labelText)
                                        .replace('{example}', definition.example), 'warning');
      fieldEl.focus();
      return;
    }
    values.push(val);
  }

  var cardSet = template.cardSet(values, selectedLabel(dropdown));
  var before = null;
  for (var s = 0; s < cardSet.length; s++) {
    var card = addCustomCodeCard(cardSet[s]);
    if (before === null) { before = card; }
  }
  var message = t('js_template_created');
  if (template.adsTxt && addAdsTxtLine('google.com, ' + values[0] + ', DIRECT, f08c47fec0942fa0')) {
    message = message + '\n' + t('js_template_ads_txt');
  }
  closeCodeTemplates();
  before.scrollIntoView({ block: 'center' });
  pbToast(message, 'success');
}

// --- Consent banner -------------------------------------------------------------

// The consent version as saved, and the one the next save will send. "Ask
// everyone again" raises it by one; a visitor whose choice was made under an
// older number sees the banner again.
var savedConsentVersion = 1;
var consentVersion = 1;

function renewConsent() {
  consentVersion = savedConsentVersion + 1;
  markConfigDirty();
  pbToast(t('js_consent_renewed'), 'success');
}

// The admin address as last saved, and the one to go to after a save that
// moved the administration.
var savedAdminUrl = null;
var adminToReach = '';

// A new address for the administration is checked before anything is
// saved: the server makes sure the address leads to this very editor,
// otherwise the author would be sent to a page that does not exist. Then
// the author confirms the move.
function checkAdminAddress(buttonEl, address) {
  var continua = function() {
    buttonEl.dataset.adminVerified = '1';
    saveConfig(buttonEl);
  };
  if (address === '' || address === window.location.origin) {
    continua();
    return;
  }
  if (!/^https?:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/.test(address)) {
    pbToast(t('js_admin_url_not_valid'), 'danger');
    return;
  }
  pbBusy(buttonEl, true);
  pbPostJson('/check-admin-address', { url: address })
    .then(function(payload) {
      pbBusy(buttonEl, false);
      if (!payload || payload.ok !== true || payload.reaches !== true) { return Promise.reject(); }
      pbConfirm(t('js_admin_url_confirm_title'),
                t('js_admin_url_confirm_body').replace('{address}', address),
                t('js_admin_url_confirm'), 'primary', function() {
        adminToReach = address;
        continua();
      });
    })
    .catch(function() {
      pbBusy(buttonEl, false);
      pbToast(t('js_admin_url_unreachable').replace('{address}', address), 'danger');
    });
}

function saveConfig(buttonEl) {
  if (savedAdminUrl === null) { savedAdminUrl = pbPage('admin_url', ''); }
  var adminAddress = document.getElementById('admin_url').value.trim().replace(/\/+$/, '');
  if (adminAddress !== savedAdminUrl && !buttonEl.dataset.adminVerified) {
    checkAdminAddress(buttonEl, adminAddress);
    return;
  }
  delete buttonEl.dataset.adminVerified;
  // We collect the data of the homepage cards.
  var cardElements = document.querySelectorAll('.card-config');
  var cardData = [];
  for (var i = 0; i < cardElements.length; i++) {
    var element = cardElements[i];
    var activate = element.querySelector('.card-active').checked;
    var titleText = element.querySelector('.card-title').value;
    // The content comes from the Quill editor matching this card.
    var contentValue = editorCard[i].root.innerHTML;
    cardData.push({ active: activate, title: titleText, content: contentValue });
  }

  // Social profiles: from the textarea, one line per profile (blank lines excluded).
  var profileRows = document.getElementById('seo_profiles').value.split('\n');
  var socialProfiles = [];
  for (var p = 0; p < profileRows.length; p++) {
    var profileRow = profileRows[p].trim();
    if (profileRow !== '') {
      socialProfiles.push(profileRow);
    }
  }

  // How many words of each article the lists show when it has no preview.
  var previewWords = parseInt(document.getElementById('home_excerpt_words').value, 10);
  if (isNaN(previewWords) || previewWords < 10) {
    previewWords = 40;
  }

  var articlesPerPage = parseInt(document.getElementById('articles_for_page').value, 10);
  if (isNaN(articlesPerPage) || articlesPerPage < 0) {
    articlesPerPage = 10;
  }
  // 0 means "never scale down"; anything unreadable keeps the usual 1600.
  var imagesWidth = parseInt(document.getElementById('max_image_width').value, 10);
  if (isNaN(imagesWidth) || imagesWidth < 0) {
    imagesWidth = 1600;
  }

  var config = {
    site_title: document.getElementById('site_title').value,
    subtitle: document.getElementById('subtitle').value,
    subtitle_en: document.getElementById('subtitle_en').value.trim(),
    author: document.getElementById('author').value,
    base_url: document.getElementById('base_url').value,
    admin_url: adminAddress,
    analytics_id: document.getElementById('analytics_id').value.trim(),
    umami_url: document.getElementById('umami_url').value.trim(),
    umami_website_id: document.getElementById('umami_website_id').value.trim(),
    language: document.getElementById('language').value,
    home_intro_position: document.getElementById('home_intro_position').value,
    home_excerpt_words: previewWords,
    articles_per_page: articlesPerPage,
    home_featured: document.getElementById('home_featured').checked,
    article_cover: document.getElementById('article_cover').checked,
    share_buttons: document.getElementById('share_buttons').checked,
    max_image_width: imagesWidth,
    seo: {
      author_url: document.getElementById('seo_author_url').value.trim(),
      author_image: document.getElementById('seo_author_image').value.trim(),
      author_role: document.getElementById('seo_author_role').value.trim(),
      author_bio: document.getElementById('seo_author_bio').value.trim(),
      author_role_en: document.getElementById('seo_author_role_en').value.trim(),
      author_bio_en: document.getElementById('seo_author_bio_en').value.trim(),
      social_profiles: socialProfiles,
      logo: document.getElementById('seo_logo').value.trim(),
      twitter_site: document.getElementById('seo_twitter').value.trim(),
      favicon: document.getElementById('seo_favicon').value.trim(),
      backlink_site: document.getElementById('seo_backlink_site').value.trim()
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
    work_with_me: {
      enabled: document.getElementById('work_enabled').checked,
      url: document.getElementById('work_url').value.trim(),
      label: document.getElementById('work_label').value.trim(),
      label_en: document.getElementById('work_label_en').value.trim(),
      text: document.getElementById('work_text').value.trim(),
      text_en: document.getElementById('work_text_en').value.trim()
    },
    home_cards: cardData,
    custom_code: customCodeData(document.getElementById('list-box-code'), 'snip'),
    ads_txt: document.getElementById('ads_txt').value.trim(),
    consent: {
      enabled: document.getElementById('consent_enabled').checked,
      text: document.getElementById('consent_text').value.trim(),
      text_en: document.getElementById('consent_text_en').value.trim(),
      privacy_url: document.getElementById('consent_privacy_url').value.trim(),
      version: consentVersion
    },
    comments: document.getElementById('comments').value,
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
      llm_model: document.getElementById('llm_template').value,
      openai_api_key: document.getElementById('openai_api_key').value,
      openai_model: document.getElementById('openai_template').value,
      deepseek_api_key: document.getElementById('deepseek_api_key').value,
      deepseek_model: document.getElementById('deepseek_template').value
    }
  };

  pbBusy(buttonEl, true);
  pbStatus('save-status', t('admin_saving'));
  pbPostJson('/save-config', config)
    .then(function(res) {
      pbBusy(buttonEl, false);
      if (res.ok === true) {
        savedConsentVersion = config.consent.version;
        configChanged = false;
        pbToast(t('admin_config_saved_f'), 'success');
        savedAdminUrl = config.admin_url;
        if (adminToReach !== '') {
          // The administration now answers only there.
          window.location.href = adminToReach + '/login';
          return;
        }
        refreshSettingsPanel();
      } else {
        pbToast(t('js_error_prefix') + res.error, 'danger');
      }
      updateSaveBar();
    })
    .catch(function() {
      pbBusy(buttonEl, false);
      updateSaveBar();
      pbToast(t('admin_failure_saving'), 'danger');
    });
}

// Puts the original config back into the textarea (discards unsaved changes).
function restoreRawConfig() {
  document.getElementById('config-raw').value = initialRawConfig;
  pbStatus('config-raw-status', '');
}

// Saves the hand-edited config.json, after server-side validation.
function saveRawConfig(buttonEl) {
  var contentValue = document.getElementById('config-raw').value;

  // Preliminary browser-side check: warns immediately if the JSON is broken.
  try {
    JSON.parse(contentValue);
  } catch (e) {
    pbToast(t('err_invalid_json_prefix') + e.message, 'danger');
    return;
  }

  pbBusy(buttonEl, true);
  pbStatus('config-raw-status', t('admin_saving'));
  pbPostJson('/save-config-raw', { content: contentValue })
    .then(function(res) {
      pbBusy(buttonEl, false);
      pbStatus('config-raw-status', '');
      if (res.ok === true) {
        pbToast(t('admin_config_raw_saved_f'), 'success');
        // We update the "original" reference to the newly saved content.
        initialRawConfig = contentValue;
        refreshSettingsPanel();
      } else {
        pbToast(t('js_error_prefix') + res.error, 'danger');
      }
    })
    .catch(function() {
      pbBusy(buttonEl, false);
      pbStatus('config-raw-status', '');
      pbToast(t('admin_failure_saving'), 'danger');
    });
}

/* --- Page dispatch -------------------------------------------------------- */

// Each admin template declares which page it is; we run only its init.
document.addEventListener('DOMContentLoaded', function() {
  var page = pbPage('page', '');
  if (page === 'editor') {
    initEditorPage();
  } else if (page === 'config') {
    initConfigPage();
  } else if (page === 'dashboard') {
    showUpdateNotice();
  } else if (page === 'updates') {
    checkUpdates(false);
  }
});

/* --- Dashboard: sorting --------------------------------------------------- */

// Reorders the article cards in place. Sorting in the browser keeps the page
// static: no reload, no round trip, and the search filter stays applied.
function sortArticles() {
  var choiceValue = document.getElementById('sort-articles').value;
  var containerEl = document.getElementById('list-articles');
  if (!containerEl) { return; }

  var cardList = [];
  var elements = containerEl.querySelectorAll('.article-card');
  for (var i = 0; i < elements.length; i++) {
    cardList.push(elements[i]);
  }

  cardList.sort(function(a, b) {
    if (choiceValue === 'title') {
      return a.getAttribute('data-title').localeCompare(b.getAttribute('data-title'));
    }
    if (choiceValue === 'state') {
      // Drafts first, then the scheduled ones, then the published ones.
      var order = { '0': 0, 's': 1, '1': 2 };
      var stateA = order[a.getAttribute('data-state')];
      var stateB = order[b.getAttribute('data-state')];
      if (stateA !== stateB) {
        return stateA - stateB;
      }
      // Within one status, the newest first: the same order as the default.
      return b.getAttribute('data-date').localeCompare(a.getAttribute('data-date'));
    }
    var dataA = a.getAttribute('data-date');
    var dataB = b.getAttribute('data-date');
    if (choiceValue === 'oldest') {
      return dataA.localeCompare(dataB);
    }
    return dataB.localeCompare(dataA);
  });

  for (var j = 0; j < cardList.length; j++) {
    containerEl.appendChild(cardList[j]);
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

var pointCard = null;      // the card the window is choosing for
var blockPoints = [];       // the blocks of the page on show
var chosenPoint = null;      // the block chosen, or null

// The containers whose children can be chosen, from the outside in.
var POINT_CONTAINERS = ['body', '.layout-columns', 'main', '.column-main',
  'article.post', '.post-content', '.articles-section', '.articles-list',
  '.bar-side'];

function pointT(key, values) {
  var textValue = t(key);
  for (var itemName in (values || {})) { textValue = textValue.replace('{' + itemName + '}', values[itemName]); }
  return textValue;
}

function openPointPicker(sourceValue) {
  pointCard = sourceValue.closest('.code-config');
  var popup = pointPickerWindow();
  var choiceValue = document.getElementById('sp-page');
  choiceValue.innerHTML = '';
  var notice = document.getElementById('sp-notice');
  notice.textContent = '';
  var nellEditor = pbPage('page', '') === 'editor';
  var options = [];
  if (nellEditor) {
    var slug = pbPage('slug', '');
    if (slug === '') {
      notice.textContent = t('js_sp_save_first_one');
    } else {
      options.push({ val: slug, textValue: pointT('js_sp_article', { title: document.getElementById('title').value }) });
    }
  } else {
    options.push({ val: '', textValue: t('js_sp_home') });
    var articleList = pbPage('articles_for_point', []);
    for (var i = 0; i < articleList.length; i++) {
      options.push({ val: articleList[i].slug, textValue: pointT('js_sp_article', { title: articleList[i].title }) });
    }
    if (articleList.length === 0) { notice.textContent = t('js_sp_no_one_article'); }
  }
  for (var j = 0; j < options.length; j++) {
    var o = document.createElement('option');
    o.value = options[j].val;
    o.textContent = options[j].textValue;
    choiceValue.appendChild(o);
  }
  // Start from the page the point was chosen on, or the one the scope suggests.
  var savedPage = pointCard.querySelector('.code-anchor-point-page').value;
  var pageScope = pointCard.querySelector('.code-scope');
  var preferArticle = savedPage === 'article' ||
    (savedPage === '' && pageScope !== null && ['articles', 'optin'].indexOf(pageScope.value) !== -1);
  if (!nellEditor && preferArticle && choiceValue.options.length > 1) { choiceValue.selectedIndex = 1; }
  var where = pointCard.querySelector('.code-anchor-point-where').value || 'after';
  document.querySelector('input[name="sp-where"][value="' + where + '"]').checked = true;
  document.getElementById('sp-confirm').disabled = true;
  if (!popup.open) { popup.showModal(); }
  if (choiceValue.options.length > 0) {
    loadPointPage();
  } else {
    document.getElementById('sp-iframe').removeAttribute('src');
  }
}

// The window is built once, the first time it is needed.
function pointPickerWindow() {
  var popup = document.getElementById('choice-point');
  if (popup) { return popup; }
  popup = document.createElement('dialog');
  popup.id = 'choice-point';
  popup.className = 'choice-point';
  popup.setAttribute('aria-labelledby', 'sp-title');
  popup.innerHTML =
    '<div class="sp-header">' +
      '<div class="sp-header-text"><h2 id="sp-title"></h2><p class="help" id="sp-instructions"></p></div>' +
      '<div class="field sp-field-page"><label for="sp-page"></label><select class="field-input" id="sp-page"></select></div>' +
    '</div>' +
    '<p class="notice notice-danger" id="sp-notice" role="status"></p>' +
    '<div class="sp-body"><iframe id="sp-iframe"></iframe></div>' +
    '<div class="sp-foot">' +
      '<div class="field sp-field-lock"><label for="sp-list"></label><select class="field-input" id="sp-list"></select></div>' +
      '<fieldset class="sp-where"><legend></legend>' +
        '<label class="field-tick"><input type="radio" name="sp-where" value="before"> <span></span></label>' +
        '<label class="field-tick"><input type="radio" name="sp-where" value="after" checked> <span></span></label>' +
      '</fieldset>' +
      '<div class="actions sp-actions">' +
        '<button type="button" class="button" id="sp-cancel"></button>' +
        '<button type="button" class="button button-primary" id="sp-confirm" disabled></button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(popup);
  document.getElementById('sp-title').textContent = t('js_sp_title');
  document.getElementById('sp-instructions').textContent = t('js_sp_instructions');
  popup.querySelector('label[for="sp-page"]').textContent = t('js_sp_page');
  popup.querySelector('label[for="sp-list"]').textContent = t('js_sp_point');
  popup.querySelector('.sp-where legend').textContent = t('js_sp_where');
  var labels = popup.querySelectorAll('.sp-where span');
  labels[0].textContent = t('js_pd_first_one');
  labels[1].textContent = t('js_pd_after');
  document.getElementById('sp-cancel').textContent = t('admin_cancel');
  document.getElementById('sp-confirm').textContent = t('js_sp_put');
  document.getElementById('sp-iframe').title = t('js_sp_title');

  document.getElementById('sp-page').addEventListener('change', loadPointPage);
  document.getElementById('sp-list').addEventListener('change', function() {
    var idx = parseInt(this.value, 10);
    choosePointBlock(isNaN(idx) ? null : blockPoints[idx], true);
  });
  var radio = popup.querySelectorAll('input[name="sp-where"]');
  for (var i = 0; i < radio.length; i++) {
    radio[i].addEventListener('change', drawPointMark);
  }
  document.getElementById('sp-cancel').addEventListener('click', function() { popup.close(); });
  document.getElementById('sp-confirm').addEventListener('click', confirmPoint);
  document.getElementById('sp-iframe').addEventListener('load', preparePointPage);
  return popup;
}

function loadPointPage() {
  blockPoints = [];
  chosenPoint = null;
  document.getElementById('sp-list').innerHTML = '';
  document.getElementById('sp-confirm').disabled = true;
  var slug = document.getElementById('sp-page').value;
  document.getElementById('sp-iframe').src = '/pick-point' + (slug ? '?slug=' + encodeURIComponent(slug) : '');
}

// The page has loaded in the frame: list its blocks, light them up on hover,
// and stop its links and forms - here a click chooses, it does not go.
function preparePointPage() {
  var cornice = document.getElementById('sp-iframe');
  var doc = cornice.contentDocument;
  if (!doc || !doc.body) { return; }
  var stile = doc.createElement('style');
  stile.textContent =
    '.pb-sp-hover { outline:2px dashed #0066cc !important; outline-offset:3px; cursor:pointer !important; }' +
    '.pb-sp-chosen { outline:3px solid #0066cc !important; outline-offset:3px; }' +
    '.pb-sp-sign { margin:8px 0; padding:10px 14px; border:2px dashed #0066cc; border-radius:8px;' +
    ' background:#e8f1fb; color:#0057ad; font:600 14px/1.4 system-ui, sans-serif; text-align:center; }';
  doc.head.appendChild(stile);

  blockPoints = pointBlocksOf(doc);
  var listEl = document.getElementById('sp-list');
  listEl.innerHTML = '';
  var empty = document.createElement('option');
  empty.value = '';
  empty.textContent = t('js_sp_choose');
  listEl.appendChild(empty);
  for (var i = 0; i < blockPoints.length; i++) {
    var o = document.createElement('option');
    o.value = String(i);
    o.textContent = describeBlock(blockPoints[i]);
    listEl.appendChild(o);
  }

  var above = null;
  doc.addEventListener('mouseover', function(evt) {
    var blockEl = pointBlockFrom(evt.target);
    if (above && above !== blockEl) { above.classList.remove('pb-sp-hover'); }
    above = blockEl;
    if (blockEl) { blockEl.classList.add('pb-sp-hover'); }
  });
  doc.addEventListener('click', function(evt) {
    evt.preventDefault();
    evt.stopPropagation();
    var blockEl = pointBlockFrom(evt.target);
    if (blockEl) { choosePointBlock(blockEl, false); }
  }, true);
  doc.addEventListener('submit', function(evt) { evt.preventDefault(); }, true);

  // A point already saved is found again, when this page has it.
  var savedValue = pointCard ? pointCard.querySelector('.code-anchor-point').value : '';
  if (savedValue !== '') {
    var found = null;
    try { found = doc.querySelector(savedValue); } catch (e) { found = null; }
    if (found && blockPoints.indexOf(found) !== -1) { choosePointBlock(found, true); }
  }
}

// The blocks that can be chosen: the children of the main containers that
// have a size, in the order of the page.
function pointBlocksOf(doc) {
  var blocks = [];
  for (var i = 0; i < POINT_CONTAINERS.length; i++) {
    var containers = doc.querySelectorAll(POINT_CONTAINERS[i]);
    for (var c = 0; c < containers.length; c++) {
      var childItems = containers[c].children;
      for (var f = 0; f < childItems.length; f++) {
        var el = childItems[f];
        var itemName = el.tagName.toLowerCase();
        if (['script', 'style', 'template', 'link', 'meta', 'dialog'].indexOf(itemName) !== -1) { continue; }
        if (el.classList.contains('skip-to-content') || el.classList.contains('pb-sp-sign')) { continue; }
        if (el.id === 'pb-consent') { continue; }
        // The containers themselves are not chosen: their children are.
        var isContainer = false;
        for (var k = 0; k < POINT_CONTAINERS.length; k++) {
          if (el.matches(POINT_CONTAINERS[k])) { isContainer = true; }
        }
        if (isContainer) { continue; }
        var r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) { continue; }
        if (blocks.indexOf(el) === -1) { blocks.push(el); }
      }
    }
  }
  blocks.sort(function(a, b) {
    return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
  });
  return blocks;
}

function pointBlockFrom(node) {
  while (node && node.nodeType === 1) {
    if (blockPoints.indexOf(node) !== -1) { return node; }
    node = node.parentElement;
  }
  return null;
}

function choosePointBlock(blockEl, scrollAlong) {
  var previous = chosenPoint;
  if (previous) { previous.classList.remove('pb-sp-chosen'); }
  chosenPoint = blockEl;
  document.getElementById('sp-confirm').disabled = blockEl === null;
  document.getElementById('sp-list').value = blockEl ? String(blockPoints.indexOf(blockEl)) : '';
  if (blockEl) {
    blockEl.classList.add('pb-sp-chosen');
    if (scrollAlong) { blockEl.scrollIntoView({ block: 'center' }); }
  }
  drawPointMark();
}

// The dashed box that shows where the code will go.
function drawPointMark() {
  var doc = document.getElementById('sp-iframe').contentDocument;
  if (!doc) { return; }
  var oldValue = doc.querySelector('.pb-sp-sign');
  if (oldValue) { oldValue.parentNode.removeChild(oldValue); }
  if (!chosenPoint) { return; }
  var sign = doc.createElement('div');
  sign.className = 'pb-sp-sign';
  var itemName = pointCard ? pointCard.querySelector('.code-name').value.trim() : '';
  sign.textContent = pointT('js_sp_here', { name: itemName || t('admin_code_without_name') });
  if (pointSide() === 'before') {
    chosenPoint.parentNode.insertBefore(sign, chosenPoint);
  } else {
    chosenPoint.parentNode.insertBefore(sign, chosenPoint.nextSibling);
  }
}

function pointSide() {
  var chosen = document.querySelector('input[name="sp-where"]:checked');
  return chosen ? chosen.value : 'after';
}

// A selector that names the block the same way on every page of its kind:
// an id or a class found once on the page, otherwise its place among the
// elements of the same tag inside such a parent.
function pointSelector(el) {
  var doc = el.ownerDocument;
  var itemName = el.tagName.toLowerCase();
  if (itemName === 'body') { return 'body'; }
  if (el.id && el.id !== 'content' && doc.querySelectorAll('#' + CSS.escape(el.id)).length === 1) {
    return '#' + CSS.escape(el.id);
  }
  for (var i = 0; i < el.classList.length; i++) {
    var cls = el.classList[i];
    if (cls.indexOf('pb-sp-') === 0) { continue; }
    var candidate = itemName + '.' + CSS.escape(cls);
    if (doc.querySelectorAll(candidate).length === 1) { return candidate; }
  }
  var spot = 1;
  for (var sibling = el.previousElementSibling; sibling; sibling = sibling.previousElementSibling) {
    if (sibling.tagName === el.tagName && !sibling.classList.contains('pb-sp-sign')) { spot++; }
  }
  return pointSelector(el.parentElement) + ' > ' + itemName + ':nth-of-type(' + spot + ')';
}

// The place of an element among the ones of its tag in its parent.
function pointOrdinal(el) {
  var spot = 1;
  for (var f = el.previousElementSibling; f; f = f.previousElementSibling) {
    if (f.tagName === el.tagName && !f.classList.contains('pb-sp-sign')) { spot++; }
  }
  return spot;
}

// A name for a block that the author recognises on any page of its kind.
function describeBlock(el) {
  var c = el.classList;
  var itemName = el.tagName.toLowerCase();
  var parentEl = el.parentElement;
  if (itemName === 'header') { return t('js_pd_masthead'); }
  if (itemName === 'footer') { return t('js_pd_foot'); }
  if (c.contains('bar-topics')) { return t('js_pd_topics'); }
  if (c.contains('home-intro')) { return t('js_pd_introduction'); }
  if (c.contains('home-biography')) { return t('js_pd_biography'); }
  if (c.contains('home-projects')) { return t('js_pd_projects'); }
  if (c.contains('articles-section')) { return t('js_pd_list'); }
  if (c.contains('articles-head')) { return t('js_pd_masthead_area_list'); }
  if (c.contains('art-row')) { return pointT('js_pd_article_n', { n: pointOrdinal(el) }); }
  if (c.contains('pagination')) { return t('js_pd_pagination'); }
  if (c.contains('box')) {
    var titleText = el.querySelector('.box-title');
    if (titleText && titleText.textContent.trim() !== '') {
      return pointT('js_pd_box', { title: titleText.textContent.trim() });
    }
    return pointT('js_pd_box_n', { n: pointOrdinal(el) });
  }
  if (c.contains('language-switcher')) { return t('js_pd_languages'); }
  if (c.contains('breadcrumbs')) { return t('js_pd_path'); }
  if (itemName === 'h1') { return t('js_pd_title'); }
  if (c.contains('meta')) { return t('js_pd_meta'); }
  if (c.contains('article-cover')) { return t('js_pd_cover'); }
  if (c.contains('toc-phone')) { return t('js_pd_toc_index'); }
  if (c.contains('post-content')) { return t('js_pd_text'); }
  if (c.contains('author-box')) { return t('js_pd_author'); }
  if (c.contains('article-nav')) { return t('js_pd_navigation'); }
  if (c.contains('post-back')) { return t('js_pd_return'); }
  if (c.contains('related-articles')) { return t('js_pd_related'); }
  if (c.contains('comments')) { return t('js_pd_comments'); }
  if (parentEl && parentEl.classList.contains('post-content')) {
    var n = pointOrdinal(el);
    if (itemName === 'p') {
      if (el.querySelector('img') && el.textContent.trim() === '') { return pointT('js_pd_picture', { n: n }); }
      return pointT('js_pd_paragraph', { n: n });
    }
    if (/^h[2-6]$/.test(itemName)) {
      var textValue = el.textContent.trim();
      if (textValue.length > 40) { textValue = textValue.slice(0, 40) + '…'; }
      return pointT('js_pd_small_heading', { n: n, text: textValue });
    }
    if (itemName === 'ul' || itemName === 'ol') { return pointT('js_pd_list_text', { n: n }); }
    if (itemName === 'figure' || itemName === 'img') { return pointT('js_pd_picture', { n: n }); }
    if (itemName === 'pre') { return pointT('js_pd_code', { n: n }); }
    if (itemName === 'blockquote') { return pointT('js_pd_quote', { n: n }); }
    if (itemName === 'table') { return pointT('js_pd_table', { n: n }); }
  }
  return pointT('js_pd_lock', { n: pointOrdinal(el), tag: itemName });
}

// "Put it here": the card gets the point, its summary says where, and the
// form knows something changed.
function confirmPoint() {
  if (!chosenPoint || !pointCard) { return; }
  var side = pointSide();
  var labelText = t(side === 'before' ? 'js_pd_first_one' : 'js_pd_after') + ' · ' + describeBlock(chosenPoint);
  pointCard.querySelector('.code-anchor-point').value = pointSelector(chosenPoint);
  pointCard.querySelector('.code-anchor-point-where').value = side;
  pointCard.querySelector('.code-anchor-point-label-text').value = labelText;
  pointCard.querySelector('.code-anchor-point-page').value =
    document.getElementById('sp-page').value === '' ? 'home' : 'article';
  pointCard.querySelector('.code-point-text').textContent = labelText;
  var placement = pointCard.querySelector('.code-position');
  placement.value = 'anchor';
  placement.dispatchEvent(new Event('change', { bubbles: true }));
  document.getElementById('choice-point').close();
  pointCard.querySelector('.code-point .button').focus();
}


/* --- Earlier versions of an article --------------------------------------- */

// The window lists the versions kept by the saves, newest first; choosing
// one shows it, and "Bring back into the editor" puts its texts in the
// fields. Nothing is saved: the author saves to keep it, as with any edit.
// The address, the status and the article's own code stay as they are.

var shownVersion = null;

function versionsWindow() {
  var popup = document.getElementById('window-versions');
  if (popup) { return popup; }
  popup = document.createElement('dialog');
  popup.id = 'window-versions';
  popup.className = 'window-versions';
  popup.setAttribute('aria-labelledby', 'versions-title');
  popup.innerHTML =
    '<div class="fv-header"><h2 id="versions-title"></h2>' +
      '<button type="button" class="button button-text" id="fv-close"></button></div>' +
    '<div class="fv-body">' +
      '<ul class="fv-list" id="fv-list"></ul>' +
      '<div class="fv-view" id="fv-view" tabindex="-1">' +
        '<p class="help" id="fv-empty"></p>' +
        '<div id="fv-content" hidden>' +
          '<p class="fv-when" id="fv-when"></p><h3 id="fv-title-article"></h3>' +
          '<div class="ql-snow"><div class="ql-editor fv-text" id="fv-text"></div></div>' +
        '</div>' +
      '</div>' +
    '</div>' +
    '<div class="fv-foot"><button type="button" class="button button-primary" id="fv-restore" disabled></button></div>';
  document.body.appendChild(popup);
  document.getElementById('versions-title').textContent = t('admin_versions');
  document.getElementById('fv-close').textContent = t('admin_close');
  document.getElementById('fv-restore').textContent = t('js_version_restore');
  document.getElementById('fv-close').addEventListener('click', function() { popup.close(); });
  document.getElementById('fv-restore').addEventListener('click', restoreVersion);
  return popup;
}

function versionStatusLabel(state) {
  if (state === 'published') { return t('admin_state_published'); }
  if (state === 'scheduled') { return t('admin_state_scheduled'); }
  return t('admin_state_draft');
}

function openVersions() {
  var popup = versionsWindow();
  shownVersion = null;
  document.getElementById('fv-restore').disabled = true;
  document.getElementById('fv-content').hidden = true;
  document.getElementById('fv-empty').textContent = '';
  var listEl = document.getElementById('fv-list');
  listEl.innerHTML = '';
  popup.showModal();
  fetch('/versions?slug=' + encodeURIComponent(originalSlug), { credentials: 'same-origin' })
    .then(function(r) { return r.json(); })
    .then(function(res) {
      var versions = res.versions || [];
      if (versions.length === 0) {
        document.getElementById('fv-empty').textContent = t('js_versions_empty_m');
        return;
      }
      document.getElementById('fv-empty').textContent = t('js_version_choose');
      for (var i = 0; i < versions.length; i++) {
        var v = versions[i];
        var entryEl = document.createElement('li');
        var buttonEl = document.createElement('button');
        buttonEl.type = 'button';
        buttonEl.className = 'fv-item';
        buttonEl.setAttribute('aria-pressed', 'false');
        buttonEl.dataset.id = v.id;
        var when = document.createElement('span');
        when.className = 'fv-item-when';
        when.textContent = formatMoment(v.saved_at);
        var detailsEl = document.createElement('span');
        detailsEl.className = 'fv-item-details';
        detailsEl.textContent = versionStatusLabel(v.status) + ' · ' +
          t('js_version_words').replace('{n}', v.words) + ' · ' + v.title;
        buttonEl.appendChild(when);
        buttonEl.appendChild(detailsEl);
        buttonEl.addEventListener('click', showVersion);
        entryEl.appendChild(buttonEl);
        listEl.appendChild(entryEl);
      }
      listEl.querySelector('.fv-item').focus();
    })
    .catch(function() { document.getElementById('fv-empty').textContent = t('js_version_failure'); });
}

function showVersion(evt) {
  var buttonEl = evt.currentTarget;
  var entries = document.querySelectorAll('#fv-list .fv-item');
  for (var i = 0; i < entries.length; i++) { entries[i].setAttribute('aria-pressed', entries[i] === buttonEl ? 'true' : 'false'); }
  fetch('/version?slug=' + encodeURIComponent(originalSlug) + '&id=' + encodeURIComponent(buttonEl.dataset.id),
        { credentials: 'same-origin' })
    .then(function(r) { return r.json(); })
    .then(function(res) {
      if (!res.ok) { pbToast(t('js_version_failure'), 'danger'); return; }
      shownVersion = res.version;
      shownVersion._when = buttonEl.querySelector('.fv-item-when').textContent;
      document.getElementById('fv-empty').textContent = '';
      document.getElementById('fv-content').hidden = false;
      document.getElementById('fv-when').textContent = shownVersion._when + ' · ' + versionStatusLabel(shownVersion.status);
      document.getElementById('fv-title-article').textContent = shownVersion.title || '';
      // The article's own HTML, written by the author: the same trust as
      // the editor, and the admin CSP stops any script in it.
      document.getElementById('fv-text').innerHTML = shownVersion.content || '';
      document.getElementById('fv-restore').disabled = false;
    })
    .catch(function() { pbToast(t('js_version_failure'), 'danger'); });
}

function restoreVersion() {
  if (!shownVersion) { return; }
  var applyIt = function() {
    var v = shownVersion;
    var fields = { title: 'title', description: 'description', preview: 'reader_preview', tags: 'tags',
                  series: 'series', series_number: 'series_number', kind: 'kind', lab_of: 'lab_of',
                  repo_url: 'repo_url', stack: 'stack', run_steps: 'run_steps', original_url: 'original_url',
                  image: 'image', title_en: 'title_en', description_en: 'description_en', preview_en: 'preview_en' };
    for (var key in fields) {
      var fieldEl = document.getElementById(fields[key]);
      if (fieldEl) { fieldEl.value = v[key] || ''; }
    }
    quill.root.innerHTML = v.content || '';
    quillEn.root.innerHTML = v.content_en || '';
    document.getElementById('translation_authorized').checked = v.translation_authorized === true;
    document.getElementById('translation_confirmed').checked = v.translation_confirmed === true;
    document.getElementById('original_canonical').checked = v.original_canonical === true;
    toggleKindFields();
    updateTranslationSection();
    updateCoverPreview();
    updateDescriptionCounter();
    updatePreviewCounter();
    markEditorDirty();
    var popup = document.getElementById('window-versions');
    if (popup.open) { popup.close(); }
    pbToast(t('js_version_restored_f').replace('{date}', v._when), 'success');
    document.getElementById('title').focus();
  };
  if (editorDirty) {
    // A <dialog> sits above everything, the confirmation window included:
    // it closes first, so the question can be seen and answered.
    document.getElementById('window-versions').close();
    pbConfirm(t('js_version_restore'), t('js_version_lose'), t('js_version_restore'), 'primary', applyIt);
  } else {
    applyIt();
  }
}


/* --- Newsletter ------------------------------------------------------------ */

// The newsletter fields of the Settings, as saved. An empty password keeps
// the one already saved (the server sees to that).
function newsletterData() {
  var val = function(id) { return document.getElementById(id).value.trim(); };
  return {
    enabled: document.getElementById('nl_enabled').checked,
    in_sidebar: document.getElementById('nl_in_sidebar').checked,
    after_article: document.getElementById('nl_after_article').checked,
    send_on_publish: document.getElementById('nl_send_on_publish').checked,
    title: val('nl_title'),
    text: val('nl_text'),
    sender_name: val('nl_sender_name'),
    sender_email: val('nl_sender_email'),
    smtp_host: val('nl_smtp_host'),
    smtp_port: parseInt(val('nl_smtp_port'), 10) || 587,
    smtp_security: document.getElementById('nl_smtp_security').value,
    smtp_user: val('nl_smtp_user'),
    smtp_password: document.getElementById('nl_smtp_password').value
  };
}

// A test email with what is written in the form, saved or not.
function sendNewsletterTest(buttonEl) {
  pbBusy(buttonEl, true);
  pbStatus('nl-test-state', '');
  pbPostJson('/newsletter-test', newsletterData())
    .then(function(res) {
      pbBusy(buttonEl, false);
      if (res.ok) {
        pbToast(t('js_nl_test_ok').replace('{to}', res.to), 'success');
      } else {
        pbToast(t('js_nl_test_failure').replace('{error}', res.error), 'danger');
      }
    })
    .catch(function() {
      pbBusy(buttonEl, false);
      pbToast(t('js_nl_test_failure').replace('{error}', ''), 'danger');
    });
}

function removeSubscriber(buttonEl) {
  var email = buttonEl.getAttribute('data-email');
  pbConfirm(t('js_nl_remove_title'), email, t('admin_nl_remove'), 'danger', function() {
    pbPostJson('/newsletter-remove', { email: email })
      .then(function(res) {
        if (res.ok) {
          buttonEl.closest('li').remove();
          pbToast(t('js_nl_removed').replace('{email}', email), 'success');
        }
      });
  });
}

// In the editor: whether the subscribers hear about this article.
// Opens and closes the Details panel. It slides over the page from the
// right on a wide screen and covers a phone's; Escape and the veil close it.
function toggleDetails(openIt) {
  var panel = document.getElementById('panel-details');
  var buttonEl = document.getElementById('btn-details');
  if (!panel || !buttonEl) { return; }
  if (openIt === undefined || openIt === null || typeof openIt !== 'boolean') {
    openIt = !document.body.classList.contains('details-open');
  }
  document.body.classList.toggle('details-open', openIt);
  buttonEl.setAttribute('aria-expanded', openIt ? 'true' : 'false');
  if (openIt) {
    document.getElementById('btn-details-close').focus();
  } else if (panel.contains(document.activeElement)) {
    buttonEl.focus();
  }
}
document.addEventListener('keydown', function(evt) {
  if (evt.key === 'Escape' && document.body.classList.contains('details-open')) {
    toggleDetails(false);
  }
});

// A closed group of the column says what it holds: the tags, the series
// and the part, whether the description is there, how far the translation
// is. The texts are rebuilt whenever a field of the column changes.
function updateGroupSummaries() {
  function write(id, textValue, toDo) {
    var row = document.getElementById('summary-' + id);
    if (!row) { return; }
    row.textContent = textValue;
    row.classList.toggle('to-do', toDo === true);
  }
  function val(id) {
    var fieldEl = document.getElementById(id);
    return fieldEl ? fieldEl.value.trim() : '';
  }
  var detailsEl = val('tags') || t('js_summary_without_tag');
  if (val('image') !== '') { detailsEl = detailsEl + ' \u00b7 ' + t('js_summary_cover'); }
  write('details', detailsEl);

  var kindValue = document.getElementById('kind');
  var seriesValue = val('series');
  if (seriesValue !== '' && val('series_number') !== '') {
    seriesValue = seriesValue + ', ' + t('js_summary_part') + ' ' + val('series_number');
  }
  var kindName = kindValue ? kindValue.options[kindValue.selectedIndex].text : '';
  write('series', seriesValue === '' ? kindName : seriesValue + ' \u00b7 ' + kindName);

  if (val('description') === '') {
    write('preview', t('js_summary_missing_one_description'), true);
  } else {
    write('preview', t('js_summary_description_ok'));
  }

  var confirmed = document.getElementById('translation_confirmed');
  var authorized = document.getElementById('translation_authorized');
  if (confirmed && confirmed.checked) {
    write('english', t('js_summary_translation_of_ok'));
  } else if (authorized && authorized.checked) {
    write('english', t('js_summary_draft_translation_of'), true);
  } else {
    write('english', t('js_summary_not_translated_m'));
  }
}

// Which groups are open is remembered in this browser, so the column comes
// back the way the author left it.
function rememberOpenGroups() {
  var groups = document.querySelectorAll('.group-editor');
  for (var i = 0; i < groups.length; i++) {
    var savedValue = null;
    try { savedValue = localStorage.getItem('pb-' + groups[i].id); } catch (err) { savedValue = null; }
    if (savedValue === '1') { groups[i].open = true; }
    if (savedValue === '0') { groups[i].open = false; }
    groups[i].addEventListener('toggle', function() {
      try { localStorage.setItem('pb-' + this.id, this.open ? '1' : '0'); } catch (err) { /* private window */ }
    });
  }
  var column = document.querySelector('.editor-sidebar');
  if (column) {
    column.addEventListener('input', updateGroupSummaries);
    column.addEventListener('change', updateGroupSummaries);
  }
  updateGroupSummaries();
}

// The article a lab or a practical version starts from shows for those two
// kinds only; the project fields for a lab only.
function toggleKindFields() {
  var kindValue = document.getElementById('kind').value;
  document.getElementById('fields-reference').hidden = kindValue === '';
  document.getElementById('fields-lab').hidden = kindValue !== 'lab';
}

function notifySubscribers() {
  var tick = document.getElementById('notify_subscribers');
  return tick ? tick.checked : true;
}
