"""드래프트온 채용 수집·스코어링 파이프라인.

수집(sources) → 정규화(normalize) → 스코어링(scoring) → 저장(store) →
대시보드 공급(export) 순으로 흐른다. 대시보드(dashboard.html)는 export가
생성한 JSON을 fetch 해서 실데이터로 렌더한다.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
