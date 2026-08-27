---
title: 프로젝트 구조 및 파일 소유권
inclusion: always
---

# 디렉토리 구조

```
backend/
  intake/     자유 텍스트 대화, 정량화 입력 보강
  scoring/    POI 성향 스코어링, 실패 확률 산정
  planner/    일정 배치 및 제약 해결
  routing/    경로 탐색 (최단 / 경치 우회 등 유형 분기)
  share/      결과 공유 링크
  common/     설정, Claude 클라이언트, 프롬프트, 로깅
frontend/     React UI
shared/types/ API 계약 (백엔드·프론트 공통)
data/         수집 스크립트 및 전처리 산출물
mocks/        프론트 선행 개발용 목 응답
docs/         아키텍처, 의사결정 기록, 회의록
```

# 모듈 소유권

| 경로 | 소유자 |
|------|--------|
| `backend/intake/`, `backend/scoring/` | 백엔드 리드 A |
| `backend/planner/`, `backend/routing/`, `backend/share/` | 백엔드 리드 B |
| `backend/common/` | 백엔드 리드 A (변경 시 B에게 공유) |
| `frontend/` | 프론트엔드 리드 |
| `data/` | 데이터 리드 |
| `shared/types/`, `docs/`, `.kiro/steering/` | PM(문서 리드) 단독 |

# 에이전트 작업 규칙 (필수)

1. **현재 spec의 소유 경로 밖 파일은 수정하지 않는다.**
2. 다른 모듈의 코드가 잘못되어 보여도 고치지 말고, 응답 마지막에
   `[다른 모듈 이슈] <경로>: <내용>` 형식으로 보고만 한다.
3. `shared/types/` 수정이 필요하면 파일을 바꾸지 말고
   **변경 제안을 텍스트로 출력**한다. PM이 직접 반영한다.
4. `.kiro/steering/` 은 어떤 경우에도 자동 수정하지 않는다.
5. 기존 함수 시그니처를 바꿔야 하는데 호출부가 소유 경로 밖에 있으면,
   기존 함수를 유지하고 새 함수를 추가한다.
6. `package-lock.json` / `uv.lock` 변경은 의존성 추가 시에만,
   그리고 **별도 커밋**으로 분리한다.
7. 한 번의 작업에서 **10개를 넘는 파일을 수정하지 않는다.**
   넘을 것 같으면 작업을 중단하고 분할 방안을 제안한다.

# 신규 파일 위치 판단

- 두 모듈이 함께 쓰는 로직 → 복사해서 각자 두지 말고 `backend/common/` 에 둔다.
- 어디에 둘지 애매하면 파일을 만들지 말고 사용자에게 물어본다.
