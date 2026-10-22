"""블로그 이미지 계획·템플릿 테스트 (브라우저·네트워크 불필요)."""

from __future__ import annotations

from pathlib import Path

from pipeline import images
from pipeline.draft import load, parse

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "draft_sample.md"


def _no_fonts(monkeypatch):
    monkeypatch.setattr(images, "_fonts", lambda: ("", ""))


def test_plan_cover_table_card(monkeypatch):
    _no_fonts(monkeypatch)
    d = load(SAMPLE)
    jobs = images.plan(d)
    names = [n for n, _, _ in jobs]
    assert names[0] == "1_cover.png"
    assert "2_table.png" in names
    cover = jobs[0][1]
    assert d.title.split()[0] in cover and images.BRAND in cover
    table = dict((n, h) for n, h, _ in jobs)["2_table.png"]
    assert "<th>구분</th>" in table and "다시 그림" in table


def test_plan_places_under_heading_and_escapes(monkeypatch):
    _no_fonts(monkeypatch)
    d = parse("---\ntitle: <제목>\n---\n첫 문장입니다. 둘째.\n\n## 체크리스트\n- **하나**\n- 둘 <b>\n")
    jobs = images.plan(d)
    assert [n for n, _, _ in jobs] == ["1_cover.png", "3_card.png"]
    card_name, card, place = jobs[1]
    assert place == "'체크리스트' 소제목 아래"
    assert "하나" in card and "**" not in card and "둘 &lt;b&gt;" in card
    assert "&lt;제목&gt;" in jobs[0][1] and "첫 문장입니다." in jobs[0][1]


def test_first_sentence_skips_notes_and_trims():
    d = parse("※ 참고 문구\n\n" + "가" * 80 + ". 다음 문장.")
    s = images._first_sentence(d)
    assert s.endswith("…") and len(s) == 69


def test_card_uses_longest_list(monkeypatch):
    _no_fonts(monkeypatch)
    d = parse("---\ntitle: t\n---\n## 예시\n- 가\n- 나\n\n## 꼭 적을 3가지\n- 하나\n- 둘\n- 셋\n")
    name, card, place = images.plan(d)[-1]
    assert name == "3_card.png" and place == "'꼭 적을 3가지' 소제목 아래" and "셋" in card
