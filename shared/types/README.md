# API 계약 (Single Source of Truth)

**이 폴더는 PM 단독 소유다. 다른 사람은 직접 수정하지 않는다.**

머지 충돌이 가장 많이 나는 지점이자, 백엔드 2명 + 프론트 1명이 동시에 의존하는
유일한 파일이다. 규칙은 아래와 같다.

1. **1주차에 확정하고 동결한다.** 코드를 짜기 전에 계약부터 정한다.
2. 변경이 필요하면 팀 채팅에 올린다 → PM이 단독으로 수정 → 즉시 main 푸시
   → 전원 `git pull`. **이 폴더에 대해서는 브랜치를 쓰지 않는다.**
3. `api.ts` 와 `models.py` 는 항상 동일한 구조를 유지한다. 한쪽만 고치지 말 것.
4. Kiro 에이전트는 이 폴더를 수정하지 않고 변경 제안만 출력한다
   (`.kiro/steering/structure.md` 규칙 3).

## 확정 사항

- [x] 취향 축(axis) 개수와 이름 — **5축으로 확정·동결 (절단 3, 2026-09-04)**
  `activity_level`, `crowd_tolerance`, `nature_vs_urban`, `food_priority`, `pace`.
  이후 변경 금지. 스키마 변경 시 태깅 전량 재실행이므로 배치 전에 반드시 확정.

- [x] 경로 유형(route preference) 값 — `fastest` / `fewest_transfers` / `scenic` (2026-09-27)
- [x] 실패 확률 객관 지표 — 환승 연결 여유(실제 편성 시각), 환승 횟수, 영업 종료 여유,
  식사 피크 도착, 장거리 구간, 그룹 최저 적합도. 인기도·혼잡도는 쓰지 않는다
  (`backend/planner/risk.py`, 2026-09-27)

## 직렬화 규칙 (2026-09-27 추가)

모든 모델은 `ApiModel` 을 상속한다. API 응답은 **camelCase**(api.ts 와 동일)로 나가고,
요청은 camelCase·snake_case 를 모두 받는다. 백엔드 코드는 snake_case 로 쓰면 된다.

## v2 확장 (2026-09-27, 예선 통합)

기존 필드는 하나도 바꾸지 않고 **선택 필드만** 추가했다 — 태깅 재실행 트리거 없음.

| 추가 | 용도 |
|------|------|
| `HardConstraints`, `IntakeMessageRequest`, `IntakeAnswerRequest`, `ChatIntake*` | 대화 → 선호 벡터·하드 제약 추출 API |
| `Operator`, `RouteAdvisory` (routing 에서 이관) | 약관 표기·경고 배지를 프론트까지 전달 |
| `RouteSegment.transfer_count / operators / advisories / scenic / recommended` | 경로 카드 표시 + 성향별 경로 추천 |
| `ScenicOption` | 최단 대비 '경치' 대안 경로 |
| `ItineraryStop.depart_at`, `Itinerary.warnings / excluded_notes / data_source / stats` | 결과 화면 설명 가능성 |
| `PlanRequest`, `PlanStats`, `CityInfo`, `ShareRequest` | 일정 생성·도시 목록·공유 API |
