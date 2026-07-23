"""이미지 에이전트 — DALL-E 배경 생성 + 카드 5장 PNG 렌더링.

구글 시트에서 '본문 승인'이면서 아직 처리되지 않은(PNG 폴더가 빈) 행을 읽어와:
  1. prompt_builder로 헤드라인+페르소나 → DALL-E 프롬프트 변환
  2. DALL-E 3로 배경 이미지 1장 생성 (세트당 1장, 5장 카드가 공유)
  3. Playwright로 1080×1350 카드 배경 PNG 5장 렌더링 (Card01~05용)
  4. 처리 중에는 'PNG 폴더' 열을 '이미지 생성 중'으로 표시해 중복 실행 방지
"""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from sheet_client import SheetClient, STATUS_BODY_APPROVED, STATUS_IMAGE_IN_PROGRESS
from prompt_builder import build_dalle_prompt

OUTPUT_DIR = Path(__file__).parent / "output"
TEMPLATE_DIR = Path(__file__).parent / "templates"

# Card 순번 → (파일명, 마스터 프레임 매핑에 쓰이는 frame_name)
CARD_FILES = [
    ("01_thumbnail.png", "썸네일"),
    ("02_body1.png", "본문_1"),
    ("03_body2.png", "본문_2"),
    ("04_body3.png", "본문_1"),
    ("05_cta.png", "CTA"),
]


def _generate_dalle_image(openai_client, prompt: str, model: str = "dall-e-3") -> bytes:
    result = openai_client.images.generate(
        model=model, prompt=prompt, size="1024x1024", n=1,
    )
    data = result.data[0]
    if getattr(data, "b64_json", None):
        return base64.b64decode(data.b64_json)
    if getattr(data, "url", None):
        import urllib.request

        with urllib.request.urlopen(data.url) as resp:  # noqa: S310
            return resp.read()
    raise RuntimeError("DALL-E 응답에서 이미지 데이터를 찾지 못했습니다.")


def _render_card_backgrounds(raw_png: bytes, out_dir: Path) -> list[Path]:
    """DALL-E 원본(1024x1024)을 1080x1350 카드 배경 5장으로 렌더링."""
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    b64 = base64.b64encode(raw_png).decode("ascii")
    data_uri = f"data:image/png;base64,{b64}"

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html"])
    )
    template = env.get_template("background.html")

    paths = []
    with sync_playwright() as p:
        launch_kwargs = {"args": ["--no-sandbox"]}
        exe = "/opt/pw-browsers/chromium"
        if Path(exe).exists():
            launch_kwargs["executable_path"] = exe
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=2)

        for i, (filename, _frame_name) in enumerate(CARD_FILES):
            # CTA는 배경을 교체하지 않으므로 오버레이를 더 약하게(참고용)
            overlay = 0.15 if filename == "05_cta.png" else 0.55
            html = template.render(image_data_uri=data_uri, overlay_opacity=overlay)
            page.set_content(html, wait_until="load")
            page.wait_for_timeout(100)
            out_path = out_dir / filename
            page.screenshot(path=str(out_path))
            paths.append(out_path)
        browser.close()

    return paths


def process_approved_bodies(client=None, openai_client=None) -> list[dict]:
    """'본문 승인'이면서 미처리인 행들의 배경 이미지+카드 PNG를 생성한다."""
    import anthropic
    from openai import OpenAI

    client = client or anthropic.Anthropic()
    openai_client = openai_client or OpenAI()

    sheet = SheetClient()
    sheet.ensure_headers()

    targets = [
        r
        for r in sheet.read_all()
        if r.get("본문 상태") == STATUS_BODY_APPROVED and not r.get("PNG 폴더", "").strip()
    ]
    if not targets:
        print("이미지 생성 대상('본문 승인'이면서 미처리)이 없습니다.")
        return []

    print(f"🎨 이미지 에이전트 시작 — {len(targets)}개 세트 처리")
    processed = []
    for row in targets:
        sheet.update_row(row["_row"], {"PNG 폴더": STATUS_IMAGE_IN_PROGRESS})

        headline = row.get("Card01 헤드라인", "").replace("\n", " ")
        persona = row.get("페르소나", "")
        prompt = build_dalle_prompt(client, headline, persona)
        print(f"  [{row.get('앵글', '')}] DALL-E 프롬프트: {prompt[:80]}...")

        raw_png = _generate_dalle_image(openai_client, prompt)

        folder = row.get("폴더명") or f"set_{row['_row']}"
        out_dir = OUTPUT_DIR / folder
        paths = _render_card_backgrounds(raw_png, out_dir)
        print(f"  ✅ 카드 배경 {len(paths)}장 렌더링 완료 → {out_dir}")

        row_updated = {**row, "PNG 폴더": str(out_dir)}
        processed.append(row_updated)

    print(f"✅ 이미지 처리 완료 — {len(processed)}세트")
    return processed


def main():
    parser = argparse.ArgumentParser(description="이미지 에이전트")
    parser.parse_args()
    try:
        process_approved_bodies()
    except Exception as exc:
        print(f"❌ 이미지 생성 실패: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
