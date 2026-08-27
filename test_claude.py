"""
Anthropic Claude API 연결 테스트 스크립트

.env 파일의 ANTHROPIC_API_KEY를 로드해서 Claude API가
정상적으로 호출되는지 확인하는 간단한 스모크 테스트입니다.

실행:
    python test_claude.py
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드 (ANTHROPIC_API_KEY 등)
# encoding="utf-8-sig": Windows PowerShell 의 Set-Content 가 붙이는
# UTF-8 BOM 이 첫 번째 키 이름에 섞여 들어가는 문제를 방지한다.
load_dotenv(encoding="utf-8-sig")

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise RuntimeError(
        "ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요."
    )

# 사용할 모델. .env 의 ANTHROPIC_MODEL 로 덮어쓸 수 있다.
# (기본값은 backend/common/config.py 의 DEFAULT_ANTHROPIC_MODEL 과 일치시킨다)
model = os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-5"

# Anthropic 클라이언트 생성
client = Anthropic(api_key=api_key)

# 간단한 메시지 호출 테스트
response = client.messages.create(
    model=model,
    max_tokens=20,
    messages=[
        {"role": "user", "content": "테스트 메시지입니다. 'OK'라고만 답해주세요."}
    ],
)

print(f"[{model}] {response.content[0].text}")
