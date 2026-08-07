"""Playwright로 브랜드 카드 템플릿(HTML)을 카드뉴스 PNG로 렌더링한다.

승인된 카피 1개당 5장의 카드(cover / P / D / A / CTA)를 생성한다.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import Config
from .imagery import generate_cover_image, image_to_data_uri
from .models import CopyAngle

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _slugify(text: str, maxlen: int = 40) -> str:
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"[^0-9A-Za-z가-힣\-_]", "", text)
    return text[:maxlen] or "card"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def _card_specs(angle: CopyAngle) -> list[dict]:
    """앵글 → 5장 카드(cover/P/D/A/CTA)의 렌더 스펙."""
    return [
        {
            "variant": "cover", "show_mark": True, "badge": angle.angle_name,
            "kicker": "", "headline": angle.hook, "head_size": 74,
            "footer": angle.topic, "step": "", "pill": "",
        },
        {
            "variant": "step", "show_mark": False, "badge": "", "step": "P",
            "kicker": "이런 고민, 있으셨죠?", "headline": angle.problem,
            "head_size": 58, "footer": "", "pill": "",
        },
        {
            "variant": "step", "show_mark": False, "badge": "", "step": "D",
            "kicker": "이렇게 달라질 수 있어요", "headline": angle.desire,
            "head_size": 58, "footer": "", "pill": "",
        },
        {
            "variant": "step", "show_mark": False, "badge": "", "step": "A",
            "kicker": "지금 이렇게 해보세요", "headline": angle.action,
            "head_size": 58, "footer": "", "pill": "",
        },
        {
            "variant": "cta", "show_mark": True, "badge": "", "step": "",
            "kicker": "", "headline": angle.cta, "head_size": 64,
            "footer": "", "pill": f"{angle.persona} 님을 위한 제안",
        },
    ]


def render_angle(
    config: Config,
    angle: CopyAngle,
    out_dir: Path,
    index: int = 0,
    make_image: bool = True,
) -> list[Path]:
    """하나의 앵글을 카드 PNG 5장으로 렌더링하고 저장 경로 리스트를 반환."""
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{index:02d}_{_slugify(angle.topic_id or angle.topic)}_{_slugify(angle.angle_name)}"
    template = _env().get_template("card.html")

    # 표지 배경 이미지(선택)
    cover_uri: Optional[str] = None
    if make_image:
        img_path = out_dir / f"{base}_cover.png"
        saved = generate_cover_image(config, angle.image_prompt, img_path)
        cover_uri = image_to_data_uri(saved)

    paths: list[Path] = []
    with sync_playwright() as p:
        launch_kwargs: dict = {"args": ["--no-sandbox"]}
        # 사전 설치된 Chromium 경로가 있으면 사용(playwright install 불필요한 환경 대응)
        exe = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or "/opt/pw-browsers/chromium"
        if Path(exe).exists():
            launch_kwargs["executable_path"] = exe
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page(
            viewport={"width": config.brand.card_width, "height": config.brand.card_height},
            device_scale_factor=2,
        )
        # 카드 1장 = 페이지 1개(뷰포트=카드 크기)로 렌더 → 정확한 전체 화면 캡처
        for i, spec in enumerate(_card_specs(angle), start=1):
            html = template.render(brand=config.brand, card=spec, cover_image=cover_uri)
            page.set_content(html, wait_until="load")
            page.wait_for_timeout(150)  # 폰트/그라디언트 페인트 안정화
            path = out_dir / f"{base}_{i:02d}.png"
            page.screenshot(path=str(path))
            paths.append(path)
        browser.close()

    return paths


def render_job_posting_card(data: dict, out_path: Path) -> Path:
    """드래프트온 채용공고 카드(무료형/유료형) 1장을 렌더링한다.

    P.D.A. 5앵글 카드뉴스와 별개의 카드 타입이다 — 실제 운영 중인
    "채용공고형" 카드 디자인(피그마 레퍼런스 기준, docs는
    .claude/agents/card-news-designer.md 참고)을 그대로 재현한다.

    data 필드:
        tier: "free" | "paid"
        company, job_title, category_tag, deadline
        dday: free 타입에서만 사용 (예: "D-12")
        responsibilities, qualifications: list[str]
        experience, location, employment_type: str
        company_logo_url, hero_image_url(paid만), cta_text: 선택
    """
    from playwright.sync_api import sync_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)
    template = _env().get_template("job_posting_card.html")
    html = template.render(**data)

    with sync_playwright() as p:
        launch_kwargs: dict = {"args": ["--no-sandbox"]}
        exe = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or "/opt/pw-browsers/chromium"
        if Path(exe).exists():
            launch_kwargs["executable_path"] = exe
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=2)
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(150)
        page.screenshot(path=str(out_path))
        browser.close()

    return out_path
