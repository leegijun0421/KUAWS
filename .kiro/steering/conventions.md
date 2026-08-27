---
title: 코딩 컨벤션
inclusion: always
---

# 공통

- 주석과 문서는 **한국어**, 코드 식별자는 **영어**.
- 제출 코드 평가 항목이 있으므로 "동작하는 코드"가 아니라
  **"읽고 이해할 수 있는 코드"** 를 목표로 한다.
- 함수는 40줄, 파일은 300줄을 넘지 않게 한다. 넘으면 분리한다.

# Python

- 모든 public 함수에 타입 힌트와 한 줄 docstring.
- 데이터 구조는 dict 대신 Pydantic 모델을 쓴다.
- 예외는 삼키지 않는다. `except Exception: pass` 금지.
- 로깅은 `backend/common/logging.py` 의 로거만 사용. `print()` 금지.
- 모듈 진입점 함수는 파일 상단에, 헬퍼는 하단에 배치한다.

```python
def score_poi(poi: Poi, profile: GroupProfile) -> PoiScore:
    """POI가 그룹 성향에 얼마나 맞는지 점수와 실패 확률을 계산한다."""
```

# TypeScript / React

- 함수형 컴포넌트 + hooks만 사용. 클래스 컴포넌트 금지.
- props에 `any` 금지. 타입은 `shared/types/api.ts` 에서 import.
- API 호출은 컴포넌트에 직접 쓰지 않고 `frontend/src/api/` 를 경유한다.
- 상태는 우선 `useState`. 전역 상태 라이브러리 도입 금지.

# LLM 호출

- 프롬프트는 `backend/common/prompts/*.md` 파일로 분리한다.
- LLM 응답이 JSON이어야 하면 **반드시** 파싱 실패 처리와 재시도(1회)를 넣는다.
- LLM 출력을 검증 없이 그대로 사용자에게 노출하지 않는다.
- 토큰 비용이 크므로 동일 입력에 대한 결과는 캐싱한다.

# 커밋 메시지

```
<type>(<scope>): <요약>

type : feat | fix | docs | refactor | test | chore
scope: intake | scoring | planner | routing | share | frontend | data | kiro
```

예) `feat(scoring): POI 실패 확률 산정 로직 추가`

# 테스트

- 새 비즈니스 로직에는 최소 1개의 테스트를 함께 작성한다.
- 외부 API(Claude API, 경로 API) 호출은 테스트에서 반드시 목으로 대체한다.
