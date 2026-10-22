"""사진 자동 검색어·노션 블록 테스트 (네트워크 불필요)."""

from __future__ import annotations

from pipeline import photos


def test_queries_from_topic():
    assert photos.queries_for("의사 연봉 네트와 그로스, 뭐가 다를까?") == [
        "tax calculator", "calculator money", photos.FALLBACK]
    assert photos.queries_for("면접 때 들은 조건이 계약서에서 바뀌었다면?")[:2] == [
        "signing contract document", "job interview"]
    assert photos.queries_for("아무 관련 없는 제목") == [photos.FALLBACK]


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
