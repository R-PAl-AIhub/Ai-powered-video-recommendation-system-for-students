"""Study material beyond videos: passages, web pages, and readings per topic."""

from __future__ import annotations

import pytest

from app.routers import projects as projects_router
from app.services import readings
from app.services.documents import DocumentError, Unit, extract_html

from .conftest import make_course, register, run_jobs, topic_by_name

BOOK = """\
# Storage systems

## RAID levels
RAID (redundant array of independent disks) combines several disks into one logical unit.
RAID level 0 stripes blocks across disks for speed but has no redundancy. RAID level 1
mirrors every block onto a second disk. RAID levels 4 and 5 keep parity blocks, so the
contents of a failed disk can be rebuilt from the parity and the surviving disks; level 5
spreads the parity across all disks so no single parity disk becomes a bottleneck. RAID 6
adds a second parity block and survives two disk failures.

## Access control lists
An access control list attaches to each file the list of users and the operations each
user may perform on it, such as read, write and execute. The operating system checks the
list on every access. Access control lists are flexible but can grow long, so many systems
combine them with owner, group and world permission bits.

# Memory

## Paging
Paging divides physical memory into fixed-size frames and logical memory into pages of the
same size. A page table maps each page number to a frame number, so a process's memory need
not be contiguous and external fragmentation disappears.
"""

ARTICLE = """<!doctype html>
<html><head><title>RAID explained - Example Wiki</title>
<meta charset="utf-8"></head>
<body>
<nav><ul><li><a href="/">Home</a><li><a href="/a">All articles about storage and disks</a></ul></nav>
<header><h1>Site banner that is not content</h1></header>
<main>
<h1>RAID</h1>
<p>RAID is a way of combining several physical disks into one logical unit for redundancy,
performance or both. The different schemes are called RAID levels.</p>
<h2>Standard levels</h2>
<p>RAID 0 consists of striping without mirroring or parity. RAID 1 consists of mirroring
without parity or striping. RAID 5 consists of block-level striping with distributed parity,
so a single failed disk can be rebuilt from the parity of the others.</p>
<p>Edit</p>
</main>
<aside><p>Related: an advertisement about buying more disks for your computer today.</p></aside>
<footer><p>Copyright notice and the terms of use of this example website.</p></footer>
</body></html>
"""


# ---------------------------------------------------------------- passages


def test_passages_follow_headings_and_never_span_two():
    passages = readings.build_passages([Unit(BOOK)], pdf=False)
    headings = [p.heading for p in passages]
    assert "RAID levels" in headings and "Access control lists" in headings
    raid = next(p for p in passages if p.heading == "RAID levels")
    assert "parity" in raid.text and "access control" not in raid.text.lower()
    assert all(p.page_start == 0 for p in passages)


def test_pdf_pages_are_kept_on_passages():
    words = " ".join(["Paging maps pages to frames."] * 30)
    units = [
        Unit(words, page=1, page_label="xi", heading="Paging"),
        Unit(words, page=2, heading="Paging"),
        Unit(words, page=3, heading="Segmentation"),
    ]
    passages = readings.build_passages(units, pdf=True)
    assert passages[0].page_start == 1 and passages[0].page_label == "xi"
    assert max(p.page_end for p in passages if p.heading == "Paging") == 2
    assert all(p.page_start == 3 for p in passages if p.heading == "Segmentation")


def test_html_keeps_main_content_only():
    title, extracted = extract_html(ARTICLE)
    assert title == "RAID explained - Example Wiki"
    text = extracted.text
    assert "distributed parity" in text
    for noise in ("Home", "Site banner", "advertisement", "Copyright", "Edit"):
        assert noise not in text
    assert [u.heading for u in extracted.units] == ["RAID", "Standard levels"]


# --------------------------------------------------------- address safety


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://example.org/x", "https://user:pw@example.org/", "javascript:alert(1)"],
)
def test_rejects_non_web_addresses(url):
    with pytest.raises(readings.UnsafeURL):
        readings.normalise_url(url)


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "localhost", "10.1.2.3", "192.168.0.10", "169.254.169.254", "::1", "0.0.0.0"]
)
def test_refuses_internal_hosts(host):
    with pytest.raises(readings.UnsafeURL):
        readings.public_address(host, 80)


def _fake_web(monkeypatch, pages: dict[str, tuple[int, dict, bytes]]):
    """Serve ``pages`` (by URL path) for example.org; other hosts resolve for real."""
    real = readings.public_address

    def resolve(host: str, port: int) -> str:
        return "93.184.215.14" if host == "example.org" else real(host, port)

    def download(url: str, address: str):
        assert address == "93.184.215.14"
        path = url.split("example.org", 1)[-1] if "example.org" in url else url.split("/", 3)[-1]
        return pages[path]

    monkeypatch.setattr(readings, "public_address", resolve)
    monkeypatch.setattr(projects_router, "public_address", resolve)
    monkeypatch.setattr(readings, "_download", download)


def test_redirects_are_checked_at_every_hop(monkeypatch):
    _fake_web(monkeypatch, {"/go": (302, {"Location": "http://127.0.0.1/admin"}, b"")})
    with pytest.raises(readings.UnsafeURL):
        readings.fetch_page("https://example.org/go")


def test_non_page_content_is_refused(monkeypatch):
    _fake_web(monkeypatch, {"/x.zip": (200, {"content-type": "application/zip"}, b"PK\x03\x04")})
    with pytest.raises(DocumentError):
        readings.fetch_page("https://example.org/x.zip")


# ------------------------------------------------------------------ the API


def test_reading_fills_a_gap_and_never_adds_topics(client):
    register(client)
    project_id = make_course(client)
    before = client.get(f"/api/projects/{project_id}/path").json()
    assert topic_by_name(before, "RAID levels")["status"] == "gap"

    response = client.post(
        f"/api/projects/{project_id}/documents/text",
        json={"kind": "reading", "title": "Storage textbook", "text": BOOK},
    )
    assert response.status_code == 201, response.text
    assert client.post(f"/api/projects/{project_id}/process").status_code == 202
    assert run_jobs() == 1

    path = client.get(f"/api/projects/{project_id}/path").json()
    assert [t["name"] for t in path["topics"]] == [t["name"] for t in before["topics"]]
    raid = topic_by_name(path, "RAID levels")
    assert raid["status"] == "gap"  # still no video; the book is offered instead
    assert raid["readings"], raid
    assert raid["readings"][0]["document"] == "Storage textbook"
    assert raid["readings"][0]["heading"] == "RAID levels"
    acl = topic_by_name(path, "Access control lists")
    assert acl["readings"] and acl["readings"][0]["heading"] == "Access control lists"
    assert not topic_by_name(path, "Public key cryptography")["readings"]
    assert path["stats"]["gaps_with_reading"] >= 2

    detail = client.get(f"/api/projects/{project_id}").json()
    book = next(d for d in detail["documents"] if d["kind"] == "reading")
    assert book["passages"] >= 3

    # Removing the material removes its readings.
    assert client.delete(f"/api/projects/{project_id}/documents/{book['id']}").status_code == 204
    path = client.get(f"/api/projects/{project_id}/path").json()
    assert not topic_by_name(path, "RAID levels")["readings"]


def test_web_page_is_read_and_linked_to_its_section(client, monkeypatch):
    _fake_web(
        monkeypatch,
        {"/wiki/RAID": (200, {"content-type": "text/html; charset=utf-8"}, ARTICLE.encode())},
    )
    register(client)
    project_id = make_course(client)

    refused = client.post(
        f"/api/projects/{project_id}/documents/url", json={"url": "http://169.254.169.254/latest"}
    )
    assert refused.status_code == 422

    added = client.post(
        f"/api/projects/{project_id}/documents/url", json={"url": "example.org/wiki/RAID"}
    )
    assert added.status_code == 201, added.text
    assert added.json()["source_url"] == "https://example.org/wiki/RAID"
    duplicate = client.post(
        f"/api/projects/{project_id}/documents/url", json={"url": "https://example.org/wiki/RAID"}
    )
    assert duplicate.status_code == 409

    assert client.post(f"/api/projects/{project_id}/process").status_code == 202
    assert run_jobs() == 1
    detail = client.get(f"/api/projects/{project_id}").json()
    page = next(d for d in detail["documents"] if d["kind"] == "reading")
    assert page["status"] == "ready" and page["filename"] == "RAID explained - Example Wiki"

    raid = topic_by_name(client.get(f"/api/projects/{project_id}/path").json(), "RAID levels")
    assert raid["readings"], raid
    assert raid["readings"][0]["url"].startswith("https://example.org/wiki/RAID#:~:text=")


def test_new_topic_gets_readings_without_reprocessing(client):
    register(client)
    project_id = make_course(client)
    client.post(
        f"/api/projects/{project_id}/documents/text",
        json={"kind": "reading", "title": "Storage textbook", "text": BOOK},
    )
    client.post(f"/api/projects/{project_id}/process")
    run_jobs()
    response = client.post(f"/api/projects/{project_id}/topics", json={"name": "Parity in RAID 5"})
    assert response.status_code == 201, response.text
    topic = topic_by_name(response.json(), "Parity in RAID 5")
    assert topic["readings"] and topic["readings"][0]["heading"] == "RAID levels"
