"""구글 시트 '카드뉴스 결과물' 공용 클라이언트.

가이드북 2편 2-5절의 22열(A~V) 스키마를 그대로 따른다. thumbnail_agent.py,
body_agent.py, image_agent.py, figma_agent.py, orchestrator.py가 이 모듈을
공유해서 각자 SHEET_URL/CREDS_FILE을 따로 들고 있지 않도록 한다.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

WORKSHEET_TITLE = "카드뉴스 결과물"

# 열 순서(A~V) — 가이드북 2-5절 표와 정확히 일치해야 한다.
HEADERS: list[str] = [
    "날짜",                # A
    "폴더명",              # B
    "페르소나",             # C
    "욕구",                # D
    "인지단계",             # E
    "펀넬",                # F
    "앵글",                # G
    "Card01 헤드라인",      # H
    "Card01 칩1",          # I
    "Card01 칩2",          # J
    "썸네일 상태",          # K
    "Card02 섹션타이틀",     # L
    "Card02 인풋텍스트",     # M
    "Card03 섹션타이틀",     # N
    "Card03 인풋텍스트",     # O
    "Card04 섹션타이틀",     # P
    "Card04 인풋텍스트",     # Q
    "Card05 CTA 유도문구",   # R
    "컨셉",                # S
    "기대반응",             # T
    "본문 상태",            # U
    "PNG 폴더",            # V
]

STATUS_THUMBNAIL_WAIT = "썸네일 대기"
STATUS_THUMBNAIL_APPROVED = "썸네일 승인"
STATUS_BODY_WAIT = "본문 대기"
STATUS_BODY_APPROVED = "본문 승인"
STATUS_IMAGE_IN_PROGRESS = "이미지 생성 중"
STATUS_FIGMA_DONE = "Figma 생성 완료"


def _extract_sheet_id(sheet_url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sheet_url)
    if not m:
        raise RuntimeError(f"SHEET_URL에서 시트 ID를 찾을 수 없습니다: {sheet_url}")
    return m.group(1)


class SheetClient:
    """gspread 기반 22열 시트 클라이언트."""

    def __init__(self, sheet_url: Optional[str] = None, creds_file: Optional[str] = None):
        self.sheet_url = sheet_url or os.getenv("SHEET_URL")
        self.creds_file = creds_file or os.getenv("CREDS_FILE", "./service_account.json")
        if not self.sheet_url:
            raise RuntimeError("SHEET_URL이 .env에 설정되지 않았습니다.")
        self._ws = None

    def _connect(self):
        import gspread
        from google.oauth2.service_account import Credentials

        if not os.path.exists(self.creds_file):
            raise RuntimeError(
                f"서비스 계정 JSON 키 파일을 찾을 수 없습니다: {self.creds_file}\n"
                "Google Cloud 콘솔에서 다운로드한 JSON 키를 이 경로에 저장하세요."
            )
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        creds = Credentials.from_service_account_file(self.creds_file, scopes=scopes)
        gc = gspread.authorize(creds)
        sheet_id = _extract_sheet_id(self.sheet_url)
        return gc.open_by_key(sheet_id)

    def worksheet(self):
        if self._ws is not None:
            return self._ws
        sh = self._connect()
        import gspread

        try:
            ws = sh.worksheet(WORKSHEET_TITLE)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=WORKSHEET_TITLE, rows=1000, cols=len(HEADERS))
        self._ws = ws
        return ws

    def ensure_headers(self) -> None:
        ws = self.worksheet()
        first_row = ws.row_values(1)
        if first_row != HEADERS:
            ws.update("A1", [HEADERS])

    def append_rows(self, rows: list[dict]) -> None:
        """dict(헤더명→값) 리스트를 시트 맨 아래에 추가한다."""
        ws = self.worksheet()
        values = [[row.get(h, "") for h in HEADERS] for row in rows]
        ws.append_rows(values, value_input_option="USER_ENTERED")

    def read_all(self) -> list[dict]:
        """행 인덱스(2-based, 헤더 제외)를 포함한 dict 리스트."""
        ws = self.worksheet()
        values = ws.get_all_values()[1:]
        out = []
        for i, row in enumerate(values, start=2):
            padded = row + [""] * (len(HEADERS) - len(row))
            d = {h: padded[j] for j, h in enumerate(HEADERS)}
            d["_row"] = i
            out.append(d)
        return out

    def find_by_status(self, status_column: str, status_value: str) -> list[dict]:
        return [r for r in self.read_all() if r.get(status_column, "").strip() == status_value]

    def update_row(self, row_index: int, updates: dict) -> None:
        """row_index(2-based)의 셀들을 헤더명 기준으로 갱신한다."""
        ws = self.worksheet()
        for header, value in updates.items():
            col = HEADERS.index(header) + 1  # 1-based
            ws.update_cell(row_index, col, value)
