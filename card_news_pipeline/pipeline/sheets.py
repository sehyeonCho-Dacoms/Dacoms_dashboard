"""시트 입출력 백엔드.

- GoogleSheetBackend: gspread + 서비스 계정으로 실제 구글 시트 연동
- LocalCsvBackend: 네트워크/자격증명 없이 CSV로 동일 인터페이스 제공(개발·테스트용)

두 백엔드 모두 아래 인터페이스를 구현한다:
    read_topics() -> list[Topic]
    append_copies(list[CopyAngle]) -> None
    read_approved_copies() -> list[CopyAngle]
    mark_topic_processed(Topic) -> None
    ensure_headers() -> None
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Protocol

from .config import Config
from .models import (
    DRAFT_HEADERS,
    TOPIC_HEADERS,
    CopyAngle,
    Topic,
    is_approved_value,
)


class SheetBackend(Protocol):
    def ensure_headers(self) -> None: ...
    def read_topics(self) -> list[Topic]: ...
    def append_copies(self, copies: list[CopyAngle]) -> None: ...
    def read_approved_copies(self) -> list[CopyAngle]: ...
    def mark_topic_processed(self, topic: Topic) -> None: ...


# --------------------------------------------------------------------------- #
# 공통: 행(row) → 도메인 객체 변환
# --------------------------------------------------------------------------- #
def _row_to_topic(row: list[str], row_index: int | None = None) -> Topic | None:
    cells = [c.strip() for c in row] + ["", "", "", ""]
    tid, topic, persona, status = cells[0], cells[1], cells[2], cells[3]
    if not topic and not persona:
        return None
    return Topic(id=tid, topic=topic, persona=persona, status=status, row_index=row_index)


def _row_to_copy(row: list[str], row_index: int | None = None) -> CopyAngle | None:
    cells = [c.strip() for c in row] + [""] * 12
    if not cells[1] and not cells[5]:  # 주제, 후킹 둘 다 비면 무시
        return None
    return CopyAngle(
        topic_id=cells[0],
        topic=cells[1],
        persona=cells[2],
        angle_name=cells[3],
        angle_description=cells[4],
        hook=cells[5],
        problem=cells[6],
        desire=cells[7],
        action=cells[8],
        cta=cells[9],
        image_prompt=cells[10],
        approved=is_approved_value(cells[11]),
        row_index=row_index,
    )


# --------------------------------------------------------------------------- #
# 로컬 CSV 백엔드
# --------------------------------------------------------------------------- #
class LocalCsvBackend:
    def __init__(self, config: Config):
        self.dir = Path(config.local_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.topic_path = self.dir / "topics.csv"
        self.draft_path = self.dir / "drafts.csv"

    def ensure_headers(self) -> None:
        if not self.topic_path.exists():
            self._write_rows(self.topic_path, [TOPIC_HEADERS])
        if not self.draft_path.exists():
            self._write_rows(self.draft_path, [DRAFT_HEADERS])

    @staticmethod
    def _read_rows(path: Path) -> list[list[str]]:
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8") as f:
            return [row for row in csv.reader(f)]

    @staticmethod
    def _write_rows(path: Path, rows: list[list[str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)

    def read_topics(self) -> list[Topic]:
        rows = self._read_rows(self.topic_path)[1:]  # 헤더 제외
        topics = []
        for i, row in enumerate(rows, start=2):  # 1=헤더
            t = _row_to_topic(row, row_index=i)
            if t:
                topics.append(t)
        return topics

    def append_copies(self, copies: list[CopyAngle]) -> None:
        self.ensure_headers()
        rows = self._read_rows(self.draft_path) or [DRAFT_HEADERS]
        for c in copies:
            rows.append(c.to_row())
        self._write_rows(self.draft_path, rows)

    def read_approved_copies(self) -> list[CopyAngle]:
        rows = self._read_rows(self.draft_path)[1:]
        out = []
        for i, row in enumerate(rows, start=2):
            c = _row_to_copy(row, row_index=i)
            if c and c.approved:
                out.append(c)
        return out

    def mark_topic_processed(self, topic: Topic) -> None:
        rows = self._read_rows(self.topic_path)
        if topic.row_index and 1 <= topic.row_index - 1 < len(rows):
            row = rows[topic.row_index - 1] + ["", "", "", ""]
            row = row[:4]
            row[3] = "처리됨"
            rows[topic.row_index - 1] = row
            self._write_rows(self.topic_path, rows)


# --------------------------------------------------------------------------- #
# 구글 시트 백엔드 (gspread)
# --------------------------------------------------------------------------- #
class GoogleSheetBackend:
    STATUS_COL = 4  # '상태' 열 (1-based: ID,주제,페르소나,상태)

    def __init__(self, config: Config):
        import gspread  # 지연 임포트: 로컬 모드에선 gspread 불필요
        from google.oauth2.service_account import Credentials

        if not config.google_credentials:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON 경로가 설정되지 않았습니다.")
        if not config.spreadsheet_id:
            raise RuntimeError("SPREADSHEET_ID가 설정되지 않았습니다.")

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        creds = Credentials.from_service_account_file(
            config.google_credentials, scopes=scopes
        )
        self.gc = gspread.authorize(creds)
        self.sh = self.gc.open_by_key(config.spreadsheet_id)
        self.topic_tab = config.topic_worksheet
        self.draft_tab = config.draft_worksheet

    def _ws(self, title: str, headers: list[str]):
        import gspread

        try:
            return self.sh.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self.sh.add_worksheet(title=title, rows=1000, cols=max(12, len(headers)))
            ws.update("A1", [headers])
            return ws

    def ensure_headers(self) -> None:
        self._ws(self.topic_tab, TOPIC_HEADERS)
        self._ws(self.draft_tab, DRAFT_HEADERS)

    def read_topics(self) -> list[Topic]:
        ws = self._ws(self.topic_tab, TOPIC_HEADERS)
        values = ws.get_all_values()[1:]
        topics = []
        for i, row in enumerate(values, start=2):
            t = _row_to_topic(row, row_index=i)
            if t:
                topics.append(t)
        return topics

    def append_copies(self, copies: list[CopyAngle]) -> None:
        ws = self._ws(self.draft_tab, DRAFT_HEADERS)
        ws.append_rows([c.to_row() for c in copies], value_input_option="USER_ENTERED")

    def read_approved_copies(self) -> list[CopyAngle]:
        ws = self._ws(self.draft_tab, DRAFT_HEADERS)
        values = ws.get_all_values()[1:]
        out = []
        for i, row in enumerate(values, start=2):
            c = _row_to_copy(row, row_index=i)
            if c and c.approved:
                out.append(c)
        return out

    def mark_topic_processed(self, topic: Topic) -> None:
        if not topic.row_index:
            return
        ws = self._ws(self.topic_tab, TOPIC_HEADERS)
        ws.update_cell(topic.row_index, self.STATUS_COL, "처리됨")


def get_backend(config: Config) -> SheetBackend:
    if config.backend == "google":
        return GoogleSheetBackend(config)
    return LocalCsvBackend(config)
