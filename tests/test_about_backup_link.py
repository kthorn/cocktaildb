from pathlib import Path


def test_about_page_has_backup_link_id():
    html = Path("src/web/about.html").read_text(encoding="utf-8")
    assert 'id="backup-download-link"' in html


def test_about_js_fetches_latest_marker():
    js = Path("src/web/js/about.js").read_text(encoding="utf-8")
    assert "latest.txt" in js
