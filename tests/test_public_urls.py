#!/usr/bin/env python3
"""
Checks on the public addresses that went from Italian to English.

    python3 tests/test_public_urls.py

The card pages moved from /pagine/ to /pages/, the series from /serie/ to
/series/, and the newsletter's pages from /iscriviti, /conferma and
/disiscrivi to /subscribe, /confirm and /unsubscribe. The old addresses are
in emails already sent, in links people shared and in search results, so
each one must still lead to the right place.
"""
import http.server
import pathlib
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import build, server  # noqa: E402
from core.config import migrate_legacy_paths, migrate_legacy_selectors  # noqa: E402

PASSED = 0
FAILED = 0


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {description}")
    else:
        FAILED += 1
        print(f"  FAIL  {description}" + (f"  ({detail})" if detail else ""))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPEN = urllib.request.build_opener(NoRedirect).open


def request(base, path, method="GET", body=None):
    req = urllib.request.Request(base + path, data=body, method=method)
    try:
        with OPEN(req, timeout=30) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), ""


def test_newsletter_addresses():
    print("\nthe newsletter's addresses")
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, headers, _ = request(base, "/conferma?t=abc")
        check("an old confirmation link from an email moves on, token included",
              status == 301 and headers.get("Location") == "/confirm?t=abc", f"{status} {headers.get('Location')}")
        status, headers, _ = request(base, "/disiscrivi?t=xyz")
        check("and so does an old unsubscribe link",
              status == 301 and headers.get("Location") == "/unsubscribe?t=xyz")
        status, _, page = request(base, "/unsubscribe", "POST", b"language=it")
        check("the new address answers", status == 200 and page != "", str(status))
        status, _, page = request(base, "/disiscrivi", "POST", b"lingua=it")
        check("a form from a cached page still posts to the old address, with the old field names",
              status == 200 and page != "", str(status))
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_moved_folders():
    print("\nthe moved folders")
    page = build.legacy_redirect_page("/en/pages/biography.html")
    check("the page left at an old address sends the reader on at once",
          '<meta http-equiv="refresh" content="0; url=/en/pages/biography.html">' in page
          and 'location.replace("/en/pages/biography.html"' in page)
    check("and tells search engines where the page lives now",
          'rel="canonical"' in page and "/en/pages/biography.html" in page)
    config, changed = migrate_legacy_paths({
        "seo": {"author_url": "https://ciunix.com/en/pagine/biografia.html"},
        "work_with_me": {"url": "/pagine/lavora-con-me.html"}})
    check("the addresses saved in the Settings move to the new folder",
          changed and config["seo"]["author_url"] == "https://ciunix.com/en/pages/biografia.html"
          and config["work_with_me"]["url"] == "/pages/lavora-con-me.html")
    config, changed = migrate_legacy_paths({"seo": {"author_url": "https://www.linkedin.com/in/x"}})
    check("other addresses are left alone", not changed)
    config, changed = migrate_legacy_selectors({"custom_code": [
        {"anchor_selector": ".colonna-principale > .box-indice"}, {"anchor_selector": "article.art-lead"}]})
    check("the points chosen for external code follow the classes' new names",
          changed and config["custom_code"][0]["anchor_selector"] == ".column-main > .box-toc-index"
          and config["custom_code"][1]["anchor_selector"] == "article.art-lead")
    config, changed = migrate_legacy_selectors({"custom_code": [{"anchor_selector": "article.art-lead"}]})
    check("a selector already in English is left alone", not changed)
    for name in ("nginx.conf.example", "nginx.separate-admin.conf.example"):
        text = (pathlib.Path(__file__).resolve().parent.parent / name).read_text()
        check(f"{name} sends the old folders on with a 301",
              "rewrite ^(/en|/it)?/pagine/(.*)$ $1/pages/$2 permanent;" in text
              and "rewrite ^(/en|/it)?/serie/(.*)$ $1/series/$2 permanent;" in text)


def main():
    test_newsletter_addresses()
    test_moved_folders()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
