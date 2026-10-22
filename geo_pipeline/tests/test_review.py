"""원고(G5) 형식 · 채널별 완성본 · G6 자동 검수 · 노션 행 테스트 (네트워크 불필요)."""

from __future__ import annotations

from pathlib import Path

from pipeline import _http, notion, render
from pipeline.draft import load, parse
from pipeline.review import CHECK, VIOLATION, from_draft, from_html, review, verdict

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "draft_sample.md"


def _rules(findings, level):
    return {f.rule for f in findings if f.level == level}


def test_draft_parse_blocks_and_meta():
    d = load(SAMPLE)
    assert d.meta["channel"] == "tistory" and d.meta["question"] == "GQ-6"
    assert d.tags == ["의사이직", "헤드헌팅", "매칭플랫폼"]
    kinds = [b.kind for b in d.blocks]
    assert {"heading", "para", "table", "image", "list"} <= set(kinds)
    table = next(b for b in d.blocks if b.kind == "table")
    assert table.rows[0] == ["구분", "헤드헌팅", "매칭 플랫폼"] and len(table.rows) == 3   # 구분선 제외
    assert len(d.links()) == 2


def test_renderers():
    d = load(SAMPLE)
    t = render.to_tistory(d)
    assert "<h2>두 방식은 어떻게 다른가요?</h2>" in t and "<table>" in t
    assert '<a href="https://example.org/a" target="_blank" rel="noopener">예시 출처 A</a>' in t
    n = render.to_naver(d)
    assert 'font-size:24px"><b>두 방식은' in n
    assert "#의사이직 #헤드헌팅 #매칭플랫폼" in n
    assert "<script" not in render.inline("<script>x</script>")          # 이스케이프


def test_good_sample_passes():
    findings = review(from_draft(load(SAMPLE)))
    assert not _rules(findings, VIOLATION), findings
    assert verdict(findings).startswith("합격")


_BAD = """---
title: 검체검사 수가 인하 총정리
channel: tistory
---
정부가 수가를 낮춥니다. 시행은 12월입니다.

## 근거

![매일경제 기사 캡처: 표본 45곳 중 6곳](https://x/1.png)

국회 보건복지위원장 이만희 의원이 지적했습니다. 이만희 의원은 보완을 요구했습니다. 대부분 의사에게 악재입니다.

## 출처

- 매일경제 https://www.mk.co.kr/news/1
- 의학신문 https://www.bosa.co.kr/news/2
"""


def test_bad_draft_catches_10_22_issues():
    findings = review(from_draft(parse(_BAD)))
    msgs = " ".join(f.message for f in findings)
    assert {"2 근거·출처", "3 기사 복제"} <= _rules(findings, VIOLATION)
    assert "글자로만" in msgs                                            # 클릭 안 되는 주소
    assert "'이만희' 직함이 글 안에서 다릅니다" in msgs                    # 보건복지위원장 / 의원
    assert "입장(DR-MKT-02)" in _rules(findings, CHECK)
    assert verdict(findings).startswith("불합격")


def test_clinic_word_is_not_a_person():
    findings = review(from_draft(parse("---\ntitle: t\n---\n검진 의원과 우리 의원은 매출이 줄어듭니다. 1개.")))
    assert not any(f.rule == "사실 확인" for f in findings)


def test_cross_channel_overlap():
    a = from_draft(parse("---\ntitle: t\n---\n" + "위탁관리료 폐지로 검사료 1만 원짜리는 건당 1천 원이 사라집니다. " * 1
                         + "개원을 준비한다면 사업계획서의 검사 수익 추정치를 다시 계산해야 합니다. "
                         + "12월 시행은 정부 목표이며 연기 요구가 있습니다."))
    b = from_draft(parse("---\ntitle: t\n---\n위탁관리료 폐지로 검사료 1만 원짜리는 건당 1천 원이 사라져요. "
                         "개원을 준비한다면 사업계획서의 검사 수익 추정치를 다시 계산하세요. "
                         "12월 시행은 정부 목표이고 연기 요구가 있어요."))
    assert "6 복붙" in _rules(review(a, b), VIOLATION)


def test_from_html_reads_links_images_and_captions():
    html = ('<div class="tt_article_useless_p_margin"><h2>제목</h2><p>본문 1개.</p>'
            '<img src="a.png" alt=""><p>출처: 매일경제 (2026.10.21)</p>'
            '<p><a href="https://press.example/1">기사</a></p></div>')
    doc = from_html(html, "https://doctoronhr.tistory.com/1")
    assert doc.channel == "tistory" and doc.links == [("기사", "https://press.example/1")]
    assert doc.images == [("", "출처: 매일경제 (2026.10.21)")]
    findings = review(doc)
    assert any(f.rule == "3 기사 복제" and f.level == CHECK for f in findings)


def test_notion_push_needs_token_and_builds_page(monkeypatch):
    d = load(SAMPLE)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    assert notion.push(d, "<p>t</p>", "<p>n</p>", "r", "합격") is None

    sent = {}

    def fake_post(url, payload, headers=None, timeout=15):
        sent.update(url=url, payload=payload, headers=headers)
        return {"url": "https://notion.so/page"}

    monkeypatch.setenv("NOTION_TOKEN", "secret-test")
    monkeypatch.setattr(_http, "post_json", fake_post)
    assert notion.push(d, "<p>" + "x" * 5000 + "</p>", "<p>n</p>", "r", "불합격 · 수정 1건") == "https://notion.so/page"
    props = sent["payload"]["properties"]
    assert props["상태"]["select"]["name"] == "사람확인"
    assert props["채널"]["select"]["name"] == "티스토리" and props["타깃"]["select"]["name"] == "의사"
    assert sent["headers"]["Authorization"] == "Bearer secret-test"
    code = sent["payload"]["children"][3]["code"]["rich_text"]
    assert all(len(c["text"]["content"]) <= 2000 for c in code) and len(code) > 1   # 2000자 조각


def test_notion_check_reports_without_leaking_token(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    assert notion.check().startswith("❌ NOTION_TOKEN")

    monkeypatch.setenv("NOTION_TOKEN", "secret-test")
    monkeypatch.setattr(_http, "get_json", lambda url, headers=None, **k: {
        "title": [{"plain_text": "블로그 GEO 체인"}],
        "properties": {n: {} for n in ["글 번호", "제목", "상태", "검수 결과", "대상 질문", "채널", "타깃"]}})
    out = notion.check()
    assert out.startswith("✅") and "secret-test" not in out

    class E(Exception):
        code = 404

    def boom(*a, **k):
        raise E("nf")

    monkeypatch.setattr(_http, "get_json", boom)
    assert "연결되지 않음" in notion.check()
