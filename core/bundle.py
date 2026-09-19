"""
Build the single-file distribution, pyblog_standalone.py.

Development happens in this package: nine modules, a folder of templates and
a folder of CSS and JavaScript. Some people would rather download one file and
run it, so "python3 pyblog.py bundle" flattens all of that into a single
script with the module sources, the templates and the static files embedded as
strings.

The bundle is not a rewrite of the engine: it is exactly these sources, plus a
small import hook that serves them from memory. That means there is one
codebase to fix, and the bundle is regenerated rather than maintained.
"""
import datetime
import pathlib

from core.config import BASE_DIR

# The name of the file the bundle is written to, unless the caller asks for
# another one.
DEFAULT_BUNDLE_NAME = "pyblog_standalone.py"

# The modules that go into the bundle, in dependency order. The order is not
# strictly required (the import hook resolves whatever is asked for, whenever
# it is asked for), but keeping it readable makes the generated file easier
# to follow if anyone opens it.
BUNDLED_MODULES = (
    ("core", "core/__init__.py"),
    ("core.config", "core/config.py"),
    ("core.i18n", "core/i18n.py"),
    ("core.render", "core/render.py"),
    ("core.images", "core/images.py"),
    ("core.articles", "core/articles.py"),
    ("core.ai", "core/ai.py"),
    ("core.auth", "core/auth.py"),
    ("core.docx_import", "core/docx_import.py"),
    ("core.build", "core/build.py"),
    ("core.server", "core/server.py"),
)

# core/bundle.py itself is left out on purpose: a bundle that could rebuild
# itself would need the templates and static folders it was created to
# replace. The standalone therefore has every command except "bundle".

HEADER = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyBlog - single-file distribution.

    python3 pyblog_standalone.py serve      start the editor on localhost:8000
    python3 pyblog_standalone.py build      regenerate the static site
    python3 pyblog_standalone.py password   set the admin password
    python3 pyblog_standalone.py import-md <path>    import Markdown
    python3 pyblog_standalone.py import-docx <path>  import Word documents
    python3 pyblog_standalone.py export-md <folder>  export to Markdown

GENERATED FILE - DO NOT EDIT.
Generated on {timestamp} by "python3 pyblog.py bundle".
Every line below comes from the PyBlog sources: the modules of core/, the
templates of templates/ and the CSS and JavaScript of static/. To change
anything, edit those and generate this file again.

It needs nothing but Python {python_requires}: no pip, no folders next to it.
The articles it writes (posts/), the site it generates (output/), the
configuration (config.json) and the password digest (admin_password.txt) are
created in the folder you run it from, exactly as with the full version.
"""
import importlib.abc
import importlib.util
import pathlib
import sys

'''

INSTALLER = '''

# ---------------------------------------------------------------------------
# THE IMPORT HOOK
# ---------------------------------------------------------------------------
# The module sources above are strings, not files, so "import core.config" has
# nothing to find on disk. A finder on sys.meta_path answers those imports
# from the dictionary instead. Everything else - the standard library - is
# left to the normal machinery.

_BUNDLE_DIR = pathlib.Path(__file__).resolve().parent


class _EmbeddedLoader(importlib.abc.Loader):
    """Executes a module whose source is a string in this file."""

    def __init__(self, source, filename):
        self.source = source
        self.filename = filename

    def create_module(self, spec):
        return None  # the default module object is fine

    def exec_module(self, module):
        # __file__ has to be set by hand: the import machinery only fills it
        # in for a module it found on disk, and core/config.py needs it to
        # work out where posts/ and output/ are.
        module.__file__ = self.filename
        code = compile(self.source, self.filename, "exec")
        exec(code, module.__dict__)


class _EmbeddedFinder(importlib.abc.MetaPathFinder):
    """Resolves the bundled module names, and nothing else."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in EMBEDDED_MODULES:
            return None
        # The filename we hand the loader is the path the module WOULD have
        # had in a normal checkout. It never has to exist: it only feeds
        # __file__, and core/config.py derives BASE_DIR from it, which is how
        # the bundle knows where posts/ and output/ live.
        if fullname == "core":
            relative = "core/__init__.py"
        else:
            relative = fullname.replace(".", "/") + ".py"
        filename = str(_BUNDLE_DIR / relative)

        loader = _EmbeddedLoader(EMBEDDED_MODULES[fullname], filename)
        spec = importlib.util.spec_from_loader(fullname, loader, origin=filename)
        if fullname == "core":
            # A package needs this list to exist, even empty, or Python will
            # refuse to import anything under it.
            spec.submodule_search_locations = []
        return spec


sys.meta_path.insert(0, _EmbeddedFinder())

# The templates and the static files are handed to the engine the same way:
# core.render prefers these dictionaries over the folders, which are not here.
import core.render  # noqa: E402  (the hook above has to be installed first)

core.render.EMBEDDED_TEMPLATES.update(EMBEDDED_TEMPLATES)
core.render.EMBEDDED_STATIC.update(EMBEDDED_STATIC)


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
# The command line is the same one pyblog.py has, run from its own source so
# the two can never disagree about what "build" means.

if __name__ == "__main__":
    exec(compile(_MAIN_SOURCE, str(_BUNDLE_DIR / "pyblog.py"), "exec"),
         {"__name__": "__main__", "__file__": str(_BUNDLE_DIR / "pyblog.py")})
'''


def _as_literal(text):
    """
    Render a string as a Python literal the generated file can hold.

    repr() is the right tool: it escapes quotes, backslashes and newlines
    correctly for any content, which matters because the sources we embed are
    full of all three.
    """
    return repr(text)


def _collect_dictionary(name, entries, comment):
    """Render one embedded dictionary, one entry per line."""
    lines = [comment, name + " = {"]
    for key in sorted(entries):
        lines.append("    " + _as_literal(key) + ": " + _as_literal(entries[key]) + ",")
    lines.append("}")
    return "\n".join(lines)


def collect_templates(root=None):
    """Read every .html of templates/ into {relative name: source}."""
    if root is None:
        root = BASE_DIR / "templates"
    templates = {}
    for path_value in sorted(root.rglob("*.html")):
        name = path_value.relative_to(root).as_posix()
        templates[name] = path_value.read_text(encoding="utf-8")
    return templates


def collect_static(root=None):
    """Read every .css and .js of static/ into {file name: source}."""
    if root is None:
        root = BASE_DIR / "static"
    static = {}
    for pattern in ("*.css", "*.js"):
        for path_value in sorted(root.glob(pattern)):
            static[path_value.name] = path_value.read_text(encoding="utf-8")
    return static


def collect_modules(root=None):
    """Read the bundled module sources into {module name: source}."""
    if root is None:
        root = BASE_DIR
    modules = {}
    for module_name, relative in BUNDLED_MODULES:
        modules[module_name] = (root / relative).read_text(encoding="utf-8")
    return modules


def build_bundle(destination=None):
    """
    Write the single-file distribution and return its path.

    Everything is read fresh from disk, so the bundle always matches the
    working tree it was generated from.
    """
    if destination is None:
        destination = BASE_DIR / DEFAULT_BUNDLE_NAME
    destination = pathlib.Path(destination)

    modules = collect_modules()
    templates = collect_templates()
    static = collect_static()
    main_source = (BASE_DIR / "pyblog.py").read_text(encoding="utf-8")

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    pieces = [HEADER.format(timestamp=timestamp, python_requires="3.8 or newer")]

    pieces.append(_collect_dictionary(
        "EMBEDDED_MODULES", modules,
        "# The sources of core/, one entry per module."))
    pieces.append("")
    pieces.append(_collect_dictionary(
        "EMBEDDED_TEMPLATES", templates,
        "# The contents of templates/, keyed by their path under it."))
    pieces.append("")
    pieces.append(_collect_dictionary(
        "EMBEDDED_STATIC", static,
        "# The contents of static/: the CSS and JavaScript of both the public\n"
        "# site and the administration area."))
    pieces.append("")
    pieces.append("# The command line of pyblog.py, executed at the bottom of this file.")
    pieces.append("_MAIN_SOURCE = " + _as_literal(main_source))
    pieces.append(INSTALLER)

    text = "\n".join(pieces)
    destination.write_text(text, encoding="utf-8")
    # Make it executable, since the point of it is to be run directly.
    try:
        destination.chmod(0o755)
    except OSError:
        pass

    return destination, len(modules), len(templates), len(static)
