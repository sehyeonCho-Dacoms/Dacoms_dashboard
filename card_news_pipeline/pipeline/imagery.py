"""OpenAI 이미지 API로 카드 표지 배경 이미지를 생성한다.

API 키가 없거나 생성에 실패하면 None을 반환하고, 렌더러가 브랜드 그라디언트
배경으로 대체한다(파이프라인이 멈추지 않도록).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from .config import Config


def generate_cover_image(config: Config, prompt: str, out_path: Path) -> Optional[Path]:
    """프롬프트로 표지 배경 이미지를 생성해 PNG로 저장. 실패 시 None."""
    if not config.openai_api_key:
        return None
    if not prompt.strip():
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=config.openai_api_key)
        styled_prompt = (
            f"{prompt}. Brand mood, clean, modern, high quality, "
            f"no text, no letters, no watermark."
        )
        result = client.images.generate(
            model=config.image_model,
            prompt=styled_prompt,
            size=config.image_size,
            n=1,
        )
        data = result.data[0]
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if getattr(data, "b64_json", None):
            out_path.write_bytes(base64.b64decode(data.b64_json))
            return out_path

        url = getattr(data, "url", None)
        if url:
            import urllib.request

            with urllib.request.urlopen(url) as resp:  # noqa: S310
                out_path.write_bytes(resp.read())
            return out_path
    except Exception as exc:  # 이미지 실패가 파이프라인을 막지 않도록
        print(f"  ⚠️  이미지 생성 실패({exc}). 그라디언트 배경으로 대체합니다.")
        return None

    return None


def image_to_data_uri(path: Optional[Path]) -> Optional[str]:
    """저장된 PNG를 HTML에 인라인할 data URI로 변환."""
    if not path or not Path(path).exists():
        return None
    raw = Path(path).read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"
