"""게시물 메타데이터 레지스트리 (post_id ↔ topic/sport_category/format).

Instagram Graph API는 "이 게시물이 어떤 카드뉴스 기획/종목인지" 모른다. 이
정보는 card-news-designer/디자인팀이 실제로 게시할 때 사람이 기록해야 한다.
CSV 한 장을 사람이 직접 관리하는 가장 단순한 형태로 시작하고, 필요해지면
구글시트(card_news_pipeline과 동일한 백엔드 추상화)로 옮길 수 있다.

컬럼: post_id,topic,sport_category,format
(post_id는 Instagram media id — 게시 후 카드뉴스 디자인팀/게시 담당자가 확인해
기록한다)
"""

from __future__ import annotations

import csv
from pathlib import Path


def load_registry(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return {
            (row.get("post_id") or "").strip(): {
                "topic": (row.get("topic") or "").strip(),
                "sport_category": (row.get("sport_category") or "").strip(),
                "format": (row.get("format") or "").strip(),
            }
            for row in reader
            if (row.get("post_id") or "").strip()
        }
