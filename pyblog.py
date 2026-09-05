#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyBlog - a static blog generator in pure Python (standard library only).

    python3 pyblog.py serve [port] [host]   start the WYSIWYG editor
    python3 pyblog.py build                 regenerate the static HTML
    python3 pyblog.py password              change the admin password
    python3 pyblog.py import-md <path>      import Markdown files
    python3 pyblog.py export-md <folder>    export every article to Markdown

This file is only the entry point: it parses the arguments and dispatches.
The engine lives in core/ (see core/__init__.py for the map), the HTML in
templates/, the CSS and JavaScript in static/.

Philosophy: zero external dependencies, lightweight HTML, static pages served
by nginx. Comments are delegated to Giscus or Disqus.
"""
import sys

from core.articles import export_markdown, import_markdown
from core.auth import set_password
from core.build import build
from core.config import OUTPUT_DIR, PASSWORD_FILE, PORT
from core.server import serve

USAGE = ("Usage: python3 pyblog.py "
         "[serve [port] [host] | build | password | import-md <path> | export-md <folder>]")


def command_build():
    """Regenerate the whole static site."""
    n = build()
    print(f"Generated {n} articles in {OUTPUT_DIR}")


def command_serve(argv):
    """
    Start the editor.
    Examples: serve              -> localhost:8000
              serve 9000         -> localhost:9000
              serve 8000 0.0.0.0 -> reachable from the network (not recommended)
    """
    chosen_port = PORT
    chosen_host = "127.0.0.1"
    if len(argv) > 2:
        try:
            chosen_port = int(argv[2])
        except ValueError:
            print(f"Invalid port: {argv[2]}")
            sys.exit(1)
    if len(argv) > 3:
        chosen_host = argv[3]
    serve(chosen_host, chosen_port)


def command_import_md(argv):
    """Import one Markdown file, or every .md file of a folder."""
    if len(argv) < 3:
        print("Usage: python3 pyblog.py import-md <file.md | folder>")
        sys.exit(1)
    n = import_markdown(argv[2])
    if n > 0:
        build()
        print(f"Imported {n} articles and rebuilt the site.")
        print("Note: articles without 'status: published' in the front matter")
        print("were imported as drafts, to be reviewed in the editor.")
    else:
        print("No .md files imported.")


def command_export_md(argv):
    """Export every article to Markdown files with front matter."""
    if len(argv) < 3:
        print("Usage: python3 pyblog.py export-md <folder>")
        sys.exit(1)
    n = export_markdown(argv[2])
    print(f"Exported {n} articles to {argv[2]}")


def command_password():
    """
    Change the administration password from the command line
    (useful over SSH if you forget it).
    """
    import getpass
    print("Set a new administration password.")
    new_value = getpass.getpass("New password: ")
    if len(new_value) < 6:
        print("Error: the password must be at least 6 characters long.")
        sys.exit(1)
    confirmed = getpass.getpass("Confirm password: ")
    if new_value != confirmed:
        print("Error: the passwords do not match.")
        sys.exit(1)
    set_password(new_value)
    print(f"Password updated. Stored (as a hash) in {PASSWORD_FILE}")


def main(argv):
    """Parse the command line and run the requested command."""
    if len(argv) > 1:
        command = argv[1]
    else:
        command = "serve"

    if command == "build":
        command_build()
    elif command == "serve":
        command_serve(argv)
    elif command == "import-md":
        command_import_md(argv)
    elif command == "export-md":
        command_export_md(argv)
    elif command == "password":
        command_password()
    else:
        print(USAGE)


if __name__ == "__main__":
    main(sys.argv)
