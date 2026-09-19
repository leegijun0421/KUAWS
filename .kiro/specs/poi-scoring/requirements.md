# poi-scoring — 요구사항

> 상태: 초안 (PM 작성, 담당자 검토 필요). 배치 태깅 착수 전 확정용 문서.
> 이 문서는 "POI를 5축으로 태깅하는 사전 배치"의 계약을 못박는다.
> 스코어링 런타임 엔진(`score_poi`)과는 별개 단계다.

## 목표

수집·정규화된 도시별 POI를 멤버 성향과 동일한 **5축**으로 태깅하여,
사람이 눈으로 납득할 수 있는 특성 벡터(`PoiVector.axis_features`)를 만든다.
목적은 태그가 사람 눈에 납득되는지 확인하는 것이지 모델 선정이 아니다.

## 배경 — 태깅 단계의 성격

- 태깅은 **사전 배치(1회성)** 다. 런타임 요청 경로가 아니다.
- 따라서 LLM provider는 `LLMProvider` 어댑터 뒤에서 자유롭게 교체 가능하다.
  (현재 배치는 Anthropic API 직접 사용으로 확정 — `docs/DECISIONS.md` 2026-08-28 참조)
- 태그 값은 동결된 5축에 매핑되므로 **스키마 변경이 없고**, 태깅 전량 재실행을 유발하지 않는다.

## 확정 사항 (팀원 4개 질문에 대한 답)

### C-1. 태깅 프롬프트
- 프롬프트는 코드에 하드코딩하지 않고 `backend/common/prompts/tag_poi.md` 로 분리한다
  (`backend/common/prompts/README.md` 작명 규칙: 함수명 = 파일명, 여기선 `tag_poi`).
- 프롬프트 파일 작성·확정은 `backend/common/` 소유자(백엔드 리드 A)가 한다.
- 확정 전까지는 "통과된 스파이크/확정 프롬프트"가 존재하지 않는다. 로컬 브랜치 산출물은
  main 병합 및 이 spec 반영 전까지 확정으로 간주하지 않는다.

### C-2. 태깅 입력 = POI 메타데이터 (리뷰 텍스트 사용 안 함)
- 입력은 **POI 메타데이터 필드**만 사용한다: `name`, `category`, `address`,
  그리고 정규화 단계에서 확보된 `avg_duration_min`, `open_hours`(있으면).
- **Google 리뷰 텍스트는 입력으로 쓰지 않는다.** 이유:
  - "실시간 현황 데이터 제외"(DECISIONS 2026-08-21)와 정합.
  - 리뷰 원문 저장에 따르는 약관·개인정보 리스크 회피 (data/README: 스크래핑 금지).
- 만약 이후 리뷰 텍스트를 쓰기로 바꾸면 제품 결정 사항이므로 PM 재확인 후 이 문서를 갱신한다.

### C-3. POI 태그 키 = 멤버 성향 5축 그대로
- POI 태그 축은 멤버 성향 5축과 **동일한 key·동일 순서**를 사용한다 (동결, 절단 3):
  1. `activity_level`
  2. `crowd_tolerance`
  3. `nature_vs_urban`
  4. `food_priority`
  5. `pace`
- 별도 `Poi.tags` dict를 만들지 않고, 기존 `PoiVector.axis_features`
  (길이 5, PreferenceAxis 정의 순서, 각 0.0~1.0)에 매핑한다.
- `activity / quiet / food_focus` 같은 다른 이름은 계약 위반이므로 사용 금지.
  (로컬 스파이크에 이런 키가 있다면 5축 key로 교체해야 한다.)

### C-4. 출력 형식·경로
- 배치 스크립트는 `data/scripts/` 에 둔다 (data/README: scripts만 커밋).
- 태깅 결과는 `data/processed/pois/<city>/tagged.json` 에 저장한다.
  - `data/processed/*` 는 `.gitignore` 대상이므로 **결과 파일은 커밋되지 않는다.**
    재현은 스크립트 재실행으로 한다(원본·산출물 미커밋 원칙).
- 결과 레코드 형식(결정 (a) — 계약 유지): 계약상 `Poi`는 6필드
  (`poi_id, name, category, lat, lng, address`)이고 여기에 필드를 추가하지 않는다.
  태깅 결과는 `Poi.tags` 같은 새 필드가 아니라 별도 `axis_features`(길이 5,
  PreferenceAxis 순서, 각 0.0~1.0)로 덧붙인다. 사람 검수를 위해 각 축 값 옆에
  한 줄 근거(`reasons`, 선택)를 함께 출력할 수 있다.
- **수집 데이터(8필드)와의 간극 처리**: W1 정규화 산출물은
  `poi_id, name, lat, lng, tags, category, avg_duration_min, open_hours`의 8필드다.
  이는 로컬 데이터 스키마일 뿐 `shared/types.Poi` 계약과 다르다. 조정 원칙:
  - `tags`(현재 `{}`)는 계약에 없는 필드다. 태깅 값을 `tags` dict에 채우지 말고
    `axis_features`(길이 5)로 출력한다. `tags`는 로컬 파일에 남겨도 되지만
    계약·파이프라인 입력으로는 쓰지 않는다.
  - `avg_duration_min` → 스코어링 입력이 필요하면 `PoiVector.avg_stay_min`에 매핑.
    `open_hours`는 계약에 없으므로 태깅 입력(메타데이터)으로만 쓰고 결과 계약엔 넣지 않는다.
  - 즉 계약(`Poi` 6필드 + `PoiVector.axis_features`)은 그대로 두고, 8필드 데이터는
    태깅 스크립트 내부 입력으로만 소비한다. `shared/types` 변경 없음 → 태깅 재실행 트리거 없음.

## 기능 요구사항

| ID | 요구사항 | 수용 기준 |
|----|----------|-----------|
| PS-1 | 도시별 POI를 5축으로 태깅한다 | 각 POI가 길이 5의 `axis_features`(0.0~1.0, PreferenceAxis 순서)를 가진다 |
| PS-2 | 태깅 입력은 POI 메타데이터만 사용한다 | 리뷰 텍스트를 입력·저장하지 않는다 |
| PS-3 | LLM 호출은 `LLMProvider` 어댑터 뒤로 격리한다 | 배치 코드가 provider 구현에 직접 의존하지 않는다 |
| PS-4 | 태그 축 key는 동결 5축과 일치한다 | 5개 key·순서가 `PreferenceAxis`와 정확히 일치 |
| PS-5 | LLM JSON 파싱 실패를 처리한다 | 1회 재시도 후 실패 시 해당 POI를 스킵·로깅하고 배치는 계속 |
| PS-6 | 동일 입력은 캐싱하여 중복 호출을 막는다 | 같은 POI 재실행 시 API를 재호출하지 않는다(`data/processed/cache/`) |
| PS-7 | 사람 검수용 출력을 만든다 | `data/processed/pois/<city>/tagged.json` 에 축 값(+근거)이 사람이 읽을 수 있게 저장 |
| PS-8 | 10건 스모크 → 전량 배치 순으로 진행한다 | 먼저 10건을 태깅해 육안 검수 통과 후 전량 실행 |

## 범위 밖

- 런타임 스코어링 엔진(`score_poi`) 구현 — 별도 태스크
- 모델 선정·벤치마크 (목적은 태그 납득성 확인)
- POI 수집·정규화 (W1에서 완료)
- 리뷰 기반 감성 분석

## 미결 사항 (담당자가 채울 것)

- [ ] 축별 값의 판정 기준 예시(프롬프트에 넣을 few-shot) — 백엔드 A
- [ ] 검수 통과 기준: 10건 중 몇 건 이상 납득되면 전량 진행할지
- [ ] `open_hours` 정규화 포맷(문자열/구조체) 최종 확인 — 데이터 리드

## 소유권 메모

- 축 key·`Poi`/`PoiVector` 계약 = `shared/types/` (PM 단독, 동결). 변경 시 PM만 반영.
- 태깅 프롬프트 = `backend/common/prompts/` (백엔드 리드 A).
- 배치 스크립트·출력 경로 = `data/` (데이터 리드).
- 이 spec 문서 = PM.
