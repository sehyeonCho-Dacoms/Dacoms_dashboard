"""사진 자동 검색어·노션 블록 테스트 (네트워크 불필요)."""

from __future__ import annotations

from pipeline import photos


def test_queries_from_topic():
    # 제목에서 먼저 나온 주제어가 먼저 (T-003·N-003·N-002·T-002 실제 제목)
    q = photos.queries_for("의사 연봉 네트와 그로스, 뭐가 다를까? 계약서에 꼭 적을 5가지")
    assert q[:4] == ["salary", "calculator", "money", "tax"] and q[-3:] == photos.FALLBACK
    assert photos.queries_for("면접 때 들은 조건이 계약서에서 바뀌었다면?")[:2] == ["job interview", "interview"]
    assert photos.queries_for("봉직의 근로계약서, 서명 전에 꼭 확인할 8가지")[0] == "contract signing"
    assert photos.queries_for("의사 헤드헌팅과 매칭 플랫폼, 뭐가 다를까? 이직 경로")[0] == "business handshake"
    assert photos.queries_for("아무 관련 없는 제목") == photos.FALLBACK


def test_candidates_dedupe_and_stop(monkeypatch):
    calls = []

    def fake(q, limit=1):
        calls.append(q)
        return [{"url": f"u{i}", "page": f"p{i}", "license": "CC0", "artist": "a", "title": f"t{i}"}
                for i in range(2)]

    monkeypatch.setattr(photos.images, "find_photo", fake)
    found = photos.candidates(["a", "b", "c"], want=3, pause=0)
    assert len(found) == 2 and calls == ["a", "b", "c"]   # 같은 파일은 한 번만


def test_blocks_and_marker():
    found = [{"url": "https://upload.wikimedia.org/x.jpg", "page": "https://commons.wikimedia.org/wiki/File:x.jpg",
              "license": "CC0", "artist": "Kim", "title": "File:x.jpg", "query": "job interview"},
             {"url": "u2", "page": "https://commons.wikimedia.org/wiki/File:y.jpg", "license": "Public domain",
              "artist": "Lee", "title": "File:y.jpg", "query": "job interview"}]
    blocks = photos.blocks_for(found)
    assert blocks[1]["image"]["external"]["url"].endswith("x.jpg")
    assert "Wikimedia Commons (CC0)" in blocks[1]["image"]["caption"][0]["text"]["content"]
    assert "photo_url: https://upload.wikimedia.org/x.jpg" in blocks[3]["code"]["rich_text"][0]["text"]["content"]
    assert photos.has_marker(blocks) and not photos.has_marker(blocks[1:])


def test_used_photo_reads_section():
    found = [{"url": "u", "page": "https://commons.wikimedia.org/wiki/File:x.jpg", "license": "CC0",
              "artist": "a", "title": "File:x.jpg", "query": "q"}]
    blocks = [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "본문"}]}}] + photos.blocks_for(found)
    assert photos.marker_index(blocks) == 1
    assert photos.used_photo(blocks) == "https://commons.wikimedia.org/wiki/File:x.jpg"


def test_candidates_skip_other_posts_photo(monkeypatch):
    monkeypatch.setattr(photos.images, "find_photo", lambda q, limit=1: [
        {"url": f"u{i}", "page": f"p{i}", "license": "CC0", "artist": "a", "title": f"t{i}"} for i in range(3)])
    found = photos.candidates(["a"], want=2, pause=0, exclude={"p0"})
    assert [f["page"] for f in found] == ["p1", "p2"]
