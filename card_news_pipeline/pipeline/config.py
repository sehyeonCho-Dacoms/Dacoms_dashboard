"""환경변수 기반 설정 로더 및 브랜드 템플릿 설정."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv 미설치 시 무시
    pass


@dataclass
class BrandConfig:
    """카드뉴스에 적용할 브랜드 템플릿 값."""

    name: str = os.getenv("BRAND_NAME", "DACOMS")
    primary: str = os.getenv("BRAND_PRIMARY", "#2563eb")     # 메인 색
    secondary: str = os.getenv("BRAND_SECONDARY", "#1d4ed8")  # 보조 색
    accent: str = os.getenv("BRAND_ACCENT", "#60a5fa")
    ink: str = os.getenv("BRAND_INK", "#0f172a")             # 본문 텍스트
    surface: str = os.getenv("BRAND_SURFACE", "#ffffff")     # 카드 배경
    font_family: str = os.getenv(
        "BRAND_FONT",
        "'Pretendard', -apple-system, BlinkMacSystemFont, 'Malgun Gothic', sans-serif",
    )
    card_width: int = int(os.getenv("CARD_WIDTH", "1080"))
    card_height: int = int(os.getenv("CARD_HEIGHT", "1350"))


@dataclass
class Config:
    """파이프라인 실행에 필요한 전체 설정."""

    # 시트 백엔드: "google" | "local"
    backend: str = os.getenv("SHEET_BACKEND", "local")

    # 구글 시트 설정
    google_credentials: Optional[str] = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    spreadsheet_id: Optional[str] = os.getenv("SPREADSHEET_ID")
    topic_worksheet: str = os.getenv("TOPIC_WORKSHEET", "주제입력")
    draft_worksheet: str = os.getenv("DRAFT_WORKSHEET", "카피초안")

    # 로컬(CSV) 백엔드 경로
    local_dir: Path = field(
        default_factory=lambda: Path(os.getenv("LOCAL_DATA_DIR", "sample_data"))
    )

    # Anthropic (Claude)
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
    angles_per_topic: int = int(os.getenv("ANGLES_PER_TOPIC", "5"))

    # Google Gemini (기획/브레인스토밍 단계)
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    topics_per_plan: int = int(os.getenv("TOPICS_PER_PLAN", "5"))

    # OpenAI (이미지 생성)
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    image_model: str = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
    image_size: str = os.getenv("OPENAI_IMAGE_SIZE", "1024x1024")

    # 출력 경로
    output_dir: Path = field(
        default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "output"))
    )

    brand: BrandConfig = field(default_factory=BrandConfig)

    def require_anthropic(self) -> str:
        if not self.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일 또는 환경변수를 확인하세요."
            )
        return self.anthropic_api_key

    def require_gemini(self) -> str:
        if not self.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY가 설정되지 않았습니다. .env 파일 또는 환경변수를 확인하세요. "
                "https://aistudio.google.com/apikey 에서 발급받을 수 있습니다."
            )
        return self.gemini_api_key
