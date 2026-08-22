---
title: 기술 스택 및 제약
inclusion: always
---

# 스택 (변경 시 PM 승인 필요)

| 영역 | 선택 | 비고 |
|------|------|------|
| 백엔드 | Python 3.11 + FastAPI | 타입 힌트 필수 |
| 데이터 검증 | Pydantic v2 | 모든 API 입출력은 Pydantic 모델 |
| LLM | AWS Bedrock (boto3) | 대회 제공 크레딧 사용 |
| 프론트엔드 | React 18 + TypeScript + Vite | |
| 스타일 | Tailwind CSS | 커스텀 CSS 파일 만들지 말 것 |
| 패키지 관리 | uv (Python) / npm (Node) | lock 파일 커밋 |
| 테스트 | pytest / vitest | |
| 포맷터 | ruff (Python) / prettier (TS) | 커밋 전 자동 실행 |

## 금지 사항

- 새 런타임·프레임워크 도입 금지 (Django, Next.js, Vue 등)
- 새 외부 의존성 추가 시 이유를 PR 본문에 기재
- Docker 도입은 예선 기간 중 금지 (본선에서 재검토)
- DB는 예선 동안 SQLite + 파일 캐시로 충분. RDS/DynamoDB 도입 금지

## 외부 API

- **AWS Bedrock**: LLM 추론. 프롬프트는 `backend/common/prompts/` 에 파일로 분리한다.
  코드 안에 프롬프트 문자열을 하드코딩하지 말 것.
- **대중교통 경로 API**: 호출 결과는 **반드시 캐싱**한다 (`data/processed/cache/`).
  무료 호출 한도가 있으므로 동일 파라미터 재호출 금지.
  좌표 기반 사전 필터링(Haversine)으로 후보를 줄인 뒤 호출한다.
- **POI 데이터**: 공공 관광 API + 지도 서비스 API 사용.
  포털 사이트 스크래핑은 법적·기술적 리스크로 **금지**.

## 비밀 정보

- API 키는 `.env` 에만 둔다. `.env` 는 절대 커밋하지 않는다.
- 새 환경변수를 추가하면 `.env.example` 에도 같은 키를 빈 값으로 추가한다.
- 코드/문서/커밋 메시지에 키를 절대 노출하지 않는다.
