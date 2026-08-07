"""인스타그램(Meta Graph API) 카드뉴스 성과 어댑터.

- 문서: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api
- 인증: 인스타그램 프로페셔널(비즈니스/크리에이터) 계정 + 연결된 페이스북 페이지의
  장기 액세스 토큰(IG_ACCESS_TOKEN), 계정 ID(IG_BUSINESS_ACCOUNT_ID).
- 키가 없으면 config.enabled_source_keys()에서 자동 제외되므로 여기선 자격증명
  존재를 가정한다.

중요한 한계 (지어내지 않고 명시):
  - `impressions`는 API/미디어 타입에 따라 지원이 계속 바뀌어 왔다(2024년 이후
    다수 표면에서 폐지·"views"로 대체). 요청한 지표 중 특정 미디어에서 거부되는
    것이 있으면 그 지표만 개별 재시도하고, 그래도 안 되면 조용히 None으로 둔다.
  - `profile_visits`는 `profile_activity` 지표를 시도하지만, 이 지표는 계정/지역/
    API 버전에 따라 아예 없을 수 있다 — 없으면 절대 계정 전체 프로필 방문수를
    개별 게시물 값으로 대체하지 않는다(귀속 오류이므로).
  - `clicks`/`apply_clicks`는 Instagram 자체 지표가 아니다. 링크 클릭 트래킹
    (예: bit.ly/UTM)을 별도로 붙이기 전까지는 항상 None + data_gaps 사유로 남는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .. import _http
from ..models import CardNewsMetric
from .base import BaseSource

# 게시물 단위로 신뢰성 있게 얻을 수 있는 지표 (attribution 문제 없음)
RELIABLE_MEDIA_METRICS = {"reach", "saved", "shares", "likes", "comments", "total_interactions"}
# 시도는 하되 미지원이면 조용히 포기하는 지표 (attribution 애매하거나 폐지 이력 있음)
BEST_EFFORT_METRICS = {"impressions", "profile_activity"}


class InstagramSource(BaseSource):
    key = "instagram"
    name = "인스타그램"

    def _base_url(self, path: str) -> str:
        return f"https://graph.facebook.com/{self.config.ig_api_version}/{path}"

    def fetch(self) -> list[dict]:
        cfg = self.config
        since = (
            datetime.now(timezone.utc) - timedelta(days=cfg.ig_lookback_days)
        ).strftime("%Y-%m-%dT%H:%M:%S+0000")

        media_list = self._list_media(since)
        out: list[dict] = []
        for media in media_list:
            insights = self._fetch_insights(media["id"], media.get("media_product_type"))
            out.append({**media, "insights": insights})
            _http.polite_sleep(self.config.request_delay_sec)
        return out

    def _list_media(self, since: str) -> list[dict]:
        url = self._base_url(f"{self.config.ig_business_account_id}/media")
        params = {
            "fields": "id,caption,timestamp,media_type,media_product_type,permalink",
            "since": since,
            "access_token": self.config.ig_access_token,
            "limit": 50,
        }
        items: list[dict] = []
        while url:
            data = _http.get_json(url, params=params)
            items.extend(data.get("data", []))
            next_page = (data.get("paging") or {}).get("next")
            url = next_page
            params = None  # next 링크에 이미 쿼리스트링 포함됨
        return items

    def _fetch_insights(self, media_id: str, media_product_type: str | None) -> dict:
        """요청 지표 중 거부되는 게 있어도 부분 성공을 허용한다.

        Graph API는 지표 하나라도 해당 미디어 타입에서 미지원이면 전체 요청을
        에러로 반환하므로, 먼저 한 번에 시도하고 실패하면 지표별 개별 조회로
        폴백한다.
        """
        metrics = self.config.ig_metrics
        url = self._base_url(f"{media_id}/insights")

        try:
            data = _http.get_json(
                url,
                params={"metric": ",".join(metrics), "access_token": self.config.ig_access_token},
            )
            return {d["name"]: d.get("values", [{}])[-1].get("value") for d in data.get("data", [])}
        except _http.GraphAPIError:
            pass  # 폴백: 지표별 개별 조회

        result: dict = {}
        for m in metrics:
            try:
                data = _http.get_json(
                    url,
                    params={"metric": m, "access_token": self.config.ig_access_token},
                )
                items = data.get("data", [])
                if items:
                    result[m] = items[0].get("values", [{}])[-1].get("value")
            except _http.GraphAPIError:
                continue  # 이 지표는 이 미디어에서 미지원 — None으로 남김
            _http.polite_sleep(self.config.request_delay_sec)
        return result

    def normalize(self, raw: dict) -> CardNewsMetric | None:
        metric = normalize_media(raw)
        if metric is None:
            return None
        return self.apply_registry(metric)


def normalize_media(raw: dict) -> CardNewsMetric | None:
    """Instagram media+insights raw dict → CardNewsMetric.

    InstagramSource와 SampleSource(오프라인 픽스처)가 공유하는 순수 함수 —
    실제 API 응답과 샘플 데이터를 동일한 로직으로 검증한다.
    """
    media_id = str(raw.get("id", "")).strip()
    if not media_id:
        return None

    insights = raw.get("insights") or {}
    metric = CardNewsMetric(
        post_id=media_id,
        date=(raw.get("timestamp") or "")[:10],
        permalink=raw.get("permalink", ""),
        raw=raw,
    )

    for name in RELIABLE_MEDIA_METRICS:
        _assign(metric, name, insights.get(name))

    # impressions는 신뢰 지표 목록에 없음 — best-effort로만 채움
    if "impressions" in insights:
        metric.impressions = _as_int(insights["impressions"])

    # profile_activity → profile_visits. 없으면 절대 다른 값으로 대체하지 않는다.
    if "profile_activity" in insights and insights["profile_activity"] is not None:
        metric.profile_visits = _as_int(insights["profile_activity"])
    else:
        metric.data_gaps.append(
            "profile_visits: Instagram profile_activity 지표 미제공(계정/API 버전 한계). "
            "계정 전체 profile_views로 대체하지 않음(귀속 오류 방지)."
        )

    metric.data_gaps.append(
        "clicks/apply_clicks: Instagram 자체 지표가 아님 — 링크 클릭 트래킹"
        "(UTM/bit.ly 등) 미연동. 현재 항상 데이터 없음."
    )

    return metric


def _assign(metric: CardNewsMetric, name: str, value) -> None:
    mapped = {"saved": "saves", "shares": "shares", "reach": "reach",
              "likes": "likes", "comments": "comments"}.get(name)
    if mapped is None:
        return
    if value is None:
        metric.data_gaps.append(f"{mapped}: 이 미디어 타입/버전에서 지표 미지원")
        return
    setattr(metric, mapped, _as_int(value))


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
