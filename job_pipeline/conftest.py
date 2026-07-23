"""pytest 부트스트랩: job_pipeline 를 import 경로에 추가."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
