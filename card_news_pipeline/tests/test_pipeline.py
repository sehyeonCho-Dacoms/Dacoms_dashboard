"""네트워크·API 키 없이 실행 가능한 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.config import Config
from pipeline.models import CopyAngle, is_approved_value
from pipeline.sheets import LocalCsvBackend


def make_config(tmp_path: Path) -> Config:
    cfg = Config()
    cfg.backend = "local"
    cfg.local_dir = tmp_path
    return cfg


def sample_copy(approved: bool = False) -> CopyAngle:
    return CopyAngle(
        topic_id="T001",
        topic="회계 자동화 SaaS",
        persona="재무담당자",
        angle_name="공감형",
        angle_description="문제 공감으로 시작",
        hook="야근의 절반은 엑셀 탓이었습니다",
        problem="매월 마감마다 수기 대사에 밤을 새웁니다.",
        desire="클릭 한 번으로 대사가 끝난다면?",
        action="지금 30일 무료로 시작하세요.",
        cta="무료 체험 시작하기",
        image_prompt="modern office desk, soft light",
        approved=approved,
    )


def test_is_approved_value():
    assert is_approved_value("승인")
    assert is_approved_value(" Approved ")
    assert is_approved_value("O")
    assert not is_approved_value("")
    assert not is_approved_value("보류")


def test_copyangle_row_roundtrip():
    c = sample_copy(approved=True)
    row = c.to_row()
    assert row[0] == "T001"
    assert row[5] == "야근의 절반은 엑셀 탓이었습니다"
    assert row[-1] == "승인"


def test_local_backend_append_and_read_approved(tmp_path):
    cfg = make_config(tmp_path)
    backend = LocalCsvBackend(cfg)
    backend.ensure_headers()

    backend.append_copies([sample_copy(approved=False), sample_copy(approved=True)])
    approved = backend.read_approved_copies()

    assert len(approved) == 1
    assert approved[0].topic_id == "T001"
    assert approved[0].approved is True


def test_local_backend_read_topics_and_mark_processed(tmp_path):
    cfg = make_config(tmp_path)
    backend = LocalCsvBackend(cfg)
    backend._write_rows(
        backend.topic_path,
        [
            ["ID", "주제", "타겟페르소나", "상태"],
            ["T001", "주제A", "페르소나A", ""],
            ["T002", "주제B", "페르소나B", ""],
        ],
    )

    topics = backend.read_topics()
    assert len(topics) == 2
    assert topics[0].row_index == 2
    assert not topics[0].is_processed

    backend.mark_topic_processed(topics[0])
    reloaded = backend.read_topics()
    assert reloaded[0].is_processed
    assert not reloaded[1].is_processed


def test_empty_rows_ignored(tmp_path):
    cfg = make_config(tmp_path)
    backend = LocalCsvBackend(cfg)
    backend._write_rows(
        backend.topic_path,
        [["ID", "주제", "타겟페르소나", "상태"], ["", "", "", ""], ["T003", "주제C", "P", ""]],
    )
    topics = backend.read_topics()
    assert len(topics) == 1
    assert topics[0].id == "T003"
