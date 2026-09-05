"""
The template engine.

It is string.Template from the standard library, nothing more: templates use
$variable (or ${variable}) placeholders and are plain .html files under
templates/. Compared with the f-strings this project used before, the win is
that braces stay single, so the JavaScript and CSS inside a template are
ordinary JavaScript and CSS again.

Two rules apply to every value that reaches a template:

  - a value that ends up in HTML passes through html.escape();
  - a value that ends up inside JavaScript passes through json.dumps().

Both happen in the calling code, because only the caller knows which of the
two a given value is. The helpers at the bottom of this module make that
one function call instead of a hand-written pattern.
"""
import html
import json
import string

from core.config import TEMPLATES_DIR


# Templates read from disk, keyed by their name. A template file never changes
# while the server runs, so reading it once is enough; clear_cache() exists for
# the tests and for anyone editing templates with the server up.
_TEMPLATE_CACHE = {}


def load_template(name):
    """
    Return the compiled string.Template for a template file.
    The name is relative to templates/ (e.g. "base.html", "admin/login.html").
    """
    if name in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[name]

    path_value = (TEMPLATES_DIR / name).resolve()
    # A template name always comes from our own code, never from a request,
    # but the check costs nothing and documents the intent.
    try:
        path_value.relative_to(TEMPLATES_DIR.resolve())
    except ValueError:
        raise ValueError("Template outside the templates folder: " + name)

    text = path_value.read_text(encoding="utf-8")
    compiled = string.Template(text)
    _TEMPLATE_CACHE[name] = compiled
    return compiled


def clear_cache():
    """Forget every template read so far (useful while editing templates)."""
    _TEMPLATE_CACHE.clear()


def render(name, **context):
    """
    Render a template with the given context and return the resulting text.

    We use substitute(), not safe_substitute(): a placeholder with no value is
    a mistake, and it should fail loudly at build time rather than leave a
    stray "$something" in a published page. A literal dollar sign inside a
    template must therefore be written "$$".
    """
    return load_template(name).substitute(**context)


def esc(value):
    """Escape a value for insertion into HTML text or an attribute."""
    if value is None:
        return ""
    return html.escape(str(value))


def js(value):
    """
    Serialise a value for insertion inside a <script> block.

    json.dumps handles the quoting, so an Italian apostrophe ("un'immagine")
    or a double quote in a title can never break the JavaScript. The closing
    sequence "</script>" is neutralised as well: without it, a piece of user
    content containing that text would end the script element early.
    """
    text = json.dumps(value, ensure_ascii=False)
    return text.replace("</", "<\\/")
