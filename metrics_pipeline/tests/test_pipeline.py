"""파이프라인 핵심 로직 테스트 (네트워크 불필요 — sample 소스/순수 함수만)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from pipeline.config import Config
from pipeline.export import unregistered_post_ids, write_metrics_csv
from pipeline.models import CSV_FIELDS, CardNewsMetric
from pipeline.registry import load_registry
from pipeline.sources.instagram import normalize_media
from pipeline.sources.sample import SampleSource
from pipeline.store import load_metrics, merge, save_metrics


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
def test_load_registry(tmp_path: Path):
    p = tmp_path / "registry.csv"
    p.write_text(
        "post_id,topic,sport_category,format\n"
        "abc123,축구단 채용,축구,채용공고형\n",
        encoding="utf-8",
    )
    reg = load_registry(p)
    assert reg["abc123"]["topic"] == "축구단 채용"
    assert reg["abc123"]["sport_category"] == "축구"


def test_load_registry_missing_file_returns_empty(tmp_path: Path):
    assert load_registry(tmp_path / "nope.csv") == {}


# --------------------------------------------------------------------------- #
# normalize_media — 신뢰 지표/추정 금지 원칙 검증
# --------------------------------------------------------------------------- #
def test_normalize_media_maps_reliable_metrics():
    raw = {
        "id": "1",
        "timestamp": "2026-07-28T09:00:00+0000",
        "permalink": "https://instagram.com/p/x",
        "insights": {"reach": 100, "saved": 10, "shares": 5, "likes": 20, "comments": 2},
    }
    m = normalize_media(raw)
    assert m.post_id == "1"
    assert m.date == "2026-07-28"
    assert m.reach == 100
    assert m.saves == 10
    assert m.shares == 5


def test_normalize_media_never_fabricates_profile_visits():
    """profile_activity 지표가 없으면 profile_visits는 반드시 None이어야 한다.

    (계정 전체 프로필 방문수를 게시물 값으로 잘못 귀속시키지 않는다는
    핵심 설계 원칙 — 이 테스트가 깨지면 회귀다.)
    """
    raw = {"id": "1", "insights": {"reach": 100}}
    m = normalize_media(raw)
    assert m.profile_visits is None
    assert any("profile_visits" in g for g in m.data_gaps)


def test_normalize_media_never_fabricates_apply_clicks():
    raw = {"id": "1", "insights": {"reach": 100}}
    m = normalize_media(raw)
    assert m.apply_clicks is None
    assert m.clicks is None
    assert any("apply_clicks" in g for g in m.data_gaps)


def test_normalize_media_flags_missing_reliable_metric():
    """reach 등 신뢰 지표라도 이 미디어에서 값이 없으면 None + data_gaps."""
    raw = {"id": "1", "insights": {"reach": 100}}  # saves/shares/likes/comments 없음
    m = normalize_media(raw)
    assert m.saves is None
    assert any("saves" in g for g in m.data_gaps)


def test_normalize_media_requires_id():
    assert normalize_media({"insights": {}}) is None


# --------------------------------------------------------------------------- #
# sample 소스 → 레지스트리 적용
# --------------------------------------------------------------------------- #
def test_sample_source_applies_registry(tmp_path: Path):
    sample_path = tmp_path / "raw.json"
    sample_path.write_text(
        json.dumps([{"id": "abc123", "timestamp": "2026-07-28T00:00:00+0000",
                      "insights": {"reach": 100}}]),
        encoding="utf-8",
    )
    registry_path = tmp_path / "registry.csv"
    registry_path.write_text(
        "post_id,topic,sport_category,format\nabc123,축구단 채용,축구,채용공고형\n",
        encoding="utf-8",
    )
    cfg = Config(sources=["sample"], sample_path=sample_path, post_registry_path=registry_path)
    metrics = SampleSource(cfg).collect()
    assert len(metrics) == 1
    assert metrics[0].topic == "축구단 채용"
    assert metrics[0].registered is True


def test_sample_source_flags_unregistered_post(tmp_path: Path):
    sample_path = tmp_path / "raw.json"
    sample_path.write_text(
        json.dumps([{"id": "unknown-1", "timestamp": "2026-07-28T00:00:00+0000",
                      "insights": {"reach": 100}}]),
        encoding="utf-8",
    )
    cfg = Config(sources=["sample"], sample_path=sample_path,
                 post_registry_path=tmp_path / "nope.csv")
    metrics = SampleSource(cfg).collect()
    assert metrics[0].registered is False
    assert any("미등록" in g for g in metrics[0].data_gaps)


def test_bundled_sample_data_and_registry_round_trip():
    """저장소에 실제로 들어간 sample_data 픽스처가 정상 동작하는지 확인."""
    cfg = Config(
        sources=["sample"],
        sample_path=Path("sample_data/raw_metrics_sample.json"),
        post_registry_path=Path("sample_data/post_registry_sample.csv"),
    )
    metrics = SampleSource(cfg).collect()
    assert len(metrics) == 4
    unreg = unregistered_post_ids(metrics)
    # 마지막 샘플 게시물은 의도적으로 레지스트리 미등록 상태로 만들어 두었다.
    assert len(unreg) == 1
    assert unreg[0] == "17895512233440044"


# --------------------------------------------------------------------------- #
# store 병합
# --------------------------------------------------------------------------- #
def test_merge_overwrites_with_latest_metrics():
    old = CardNewsMetric(post_id="1", reach=100)
    new = CardNewsMetric(post_id="1", reach=250)
    merged = merge([old], [new])
    assert len(merged) == 1
    assert merged[0].reach == 250


def test_store_round_trip(tmp_path: Path):
    path = tmp_path / "metrics.json"
    metrics = [CardNewsMetric(post_id="1", topic="t", reach=100, data_gaps=["x"])]
    save_metrics(path, metrics)
    loaded = load_metrics(path)
    assert len(loaded) == 1
    assert loaded[0].post_id == "1"
    assert loaded[0].data_gaps == ["x"]


# --------------------------------------------------------------------------- #
# export — metrics-analyzer 계약 (test-data/dummy-metrics.csv 와 동일 스키마)
# --------------------------------------------------------------------------- #
def test_export_csv_matches_metrics_analyzer_schema(tmp_path: Path):
    metrics = [
        CardNewsMetric(post_id="1", date="2026-07-28", topic="축구단 채용",
                        sport_category="축구", format="채용공고형",
                        reach=100, saves=10, shares=5),
    ]
    out = tmp_path / "out.csv"
    write_metrics_csv(out, metrics)
    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == CSV_FIELDS
    assert rows[0]["post_id"] == "1"
    assert rows[0]["reach"] == "100"
    # 확보하지 못한 값은 빈 문자열이어야 한다(0이나 추정치로 채우지 않음)
    assert rows[0]["profile_visits"] == ""
    assert rows[0]["apply_clicks"] == ""


def test_enabled_sources_skip_without_credentials():
    cfg = Config(sources=["instagram", "sample"])
    assert cfg.enabled_source_keys() == ["sample"]
