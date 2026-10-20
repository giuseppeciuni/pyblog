#!/usr/bin/env python3
"""
Checks on choosing a file from the media library inside the editors.

    python3 tests/test_media_picker.py

The picker lists the uploaded files through /media-library-items and puts
the chosen one into the text at the cursor, or into the cover field, without
uploading it again. The files live in a temporary folder.
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import media_library, server  # noqa: E402

PASSED = 0
FAILED = 0
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
ROOT = pathlib.Path(__file__).resolve().parent.parent


def check(description, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ok    {description}")
    else:
        FAILED += 1
        print(f"  FAIL  {description}" + (f"  ({detail})" if detail else ""))


def test_items():
    print("\nthe list of files")
    folder = tempfile.TemporaryDirectory()
    saved = (media_library.MEDIA_DIR, media_library.load_articles, media_library.load_config)
    try:
        media_library.MEDIA_DIR = pathlib.Path(folder.name)
        media_library.load_articles = lambda: [{"slug": "a", "content": '<img src="/media/photo.png">'}]
        media_library.load_config = lambda: {}
        (media_library.MEDIA_DIR / "photo.png").write_bytes(PNG)
        (media_library.MEDIA_DIR / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
        (media_library.MEDIA_DIR / ".hidden.png").write_bytes(PNG)
        result = server.media_library_items()
        names = sorted(item["name"] for item in result["items"])
        check("lists the uploaded files, not the hidden ones", names == ["clip.mp4", "photo.png"], str(names))
        by_name = {item["name"]: item for item in result["items"]}
        check("each file comes with its address, its kind and its uses",
              by_name["photo.png"] == {"name": "photo.png", "url": "/media/photo.png", "kind": "image",
                                       "size": "1 KB", "used": 1, "resizable": True, "sized": False}
              and by_name["clip.mp4"]["kind"] == "video" and by_name["clip.mp4"]["used"] == 0,
              str(by_name))
    finally:
        media_library.MEDIA_DIR, media_library.load_articles, media_library.load_config = saved
        folder.cleanup()
    check("the list is an administration page, behind the login",
          "/media-library-items" in server.ADMIN_GET_ROUTES)


def test_buttons():
    print("\nthe buttons")
    editor = server.editor_page(None, "TOKEN")
    check("the article editor offers the library for the text and for the cover",
          editor.count("openMediaPicker('editor')") == 1 and editor.count("openMediaPicker('cover')") == 1)
    settings = server.config_page("TOKEN")
    check("the homepage introduction offers it too", "openMediaPicker('editor')" in settings)
    script = (ROOT / "static" / "admin.js").read_text()
    check("the window is a native dialog, built on first use",
          "document.createElement('dialog')" in script and "dialog.showModal()" in script)
    check("a cover is never offered a video",
          "mediaPickerTarget === 'cover' && item.kind !== 'image'" in script)
    check("names reach the page as text, never as markup",
          "name.textContent = item.name" in script)


def main():
    test_items()
    test_buttons()
    print(f"\n{PASSED} passed, {FAILED} failed")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
