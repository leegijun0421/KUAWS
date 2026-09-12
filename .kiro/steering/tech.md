---
title: 기술 스택 및 제약
inclusion: always
---

# 스택 (변경 시 PM 승인 필요)

| 영역 | 선택 | 비고 |
|------|------|------|
| 백엔드 | Python 3.11 + FastAPI | 타입 힌트 필수 |
| 데이터 검증 | Pydantic v2 | 모든 API 입출력은 Pydantic 모델 |
| LLM | Anthropic Claude API (`anthropic` SDK) | 모델: `claude-sonnet-5` · 키는 .env 로만 주입 |
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

- **Anthropic Claude API**: LLM 추론. 프롬프트는 `backend/common/prompts/` 에 파일로 분리한다.
  코드 안에 프롬프트 문자열을 하드코딩하지 말 것.
  - **사용 모델**: `claude-sonnet-5` (2026-08-27 확정, 첫 호출 검증 완료)
    - 선정 이유: 속도·성능 균형이 좋아 예선 PoC의 반복 개발에 적합. 컨텍스트 1M 토큰.
    - 단가: 입력 $2 / 출력 $10 per MTok
  - 모델 ID는 코드에 하드코딩하지 않는다. `backend/common/config.py` 의
    `DEFAULT_ANTHROPIC_MODEL` 을 기본값으로 쓰고, 필요 시 `.env` 의 `ANTHROPIC_MODEL` 로 덮어쓴다.
  - 모델 변경은 스택 변경에 해당하므로 PM 승인 + `docs/DECISIONS.md` 기록이 필요하다.
- **대중교통 경로 API**: `backend/routing/provider.py` 의 `RouteProvider` 인터페이스를
  경유한다. 구체 API 를 모듈 밖에서 직접 부르지 말 것.
  - **국내**: ODsay (`ODSAY_API_KEY`) — 도보·환승·요금 상세가 정확하다.
  - **해외**: Google **Routes API v2** (`GOOGLE_BACKEND_API_KEY`) — 글로벌 커버리지.
    구버전 Directions API 를 쓰지 말 것. v2 만 실제 편성 출발·도착 시각을 준다.
    요청에 `X-Goog-FieldMask` 헤더가 **필수**다(누락 시 빈 응답). `*` 는 비용 때문에 금지.
  - 분기 기준: 출발·도착이 모두 한국 경계 상자 안이면 ODsay, 아니면 Google.
  - ⚠️ Google 은 **대한민국에서 도보·자동차·자전거 경로를 공식 미지원**이다
    (고정밀 지도 반출 제한). 국내 구간에 Google 을 쓰지 말 것.
  - **캐싱 정책은 프로바이더마다 다르다.** `RouteProvider.cacheable` 로 강제한다.
    - **Google = 캐싱 금지.** 약관이 응답의 사전 페칭·저장·캐싱을 금지한다
      (Place ID·위경도만 예외적으로 영구 저장 가능). 응답 JSON 을 리포에 커밋하지 말 것.
    - **ODsay = 로컬 캐싱 허용** (`data/processed/cache/routes/`).
      Basic 무료 30회/일이라 캐시 없이는 개발 중 한도를 넘긴다. 캐시 파일은 커밋 금지.
  - 호출 수 절감의 1차 수단은 캐시가 아니라 **좌표 기반 사전 필터링(Haversine)** 이다.
    후보를 줄인 뒤 호출한다.
- **POI 데이터**: 공공 관광 API + 지도 서비스 API 사용.
  포털 사이트 스크래핑은 법적·기술적 리스크로 **금지**.

## 비밀 정보

- API 키는 `.env` 에만 둔다. `.env` 는 절대 커밋하지 않는다.
- 새 환경변수를 추가하면 `.env.example` 에도 같은 키를 빈 값으로 추가한다.
- 코드/문서/커밋 메시지에 키를 절대 노출하지 않는다.
