# Specs 사용 규칙

- **1 spec = 1 브랜치 = 1 PR 묶음** 이다.
- spec 폴더는 담당자만 수정한다. 남의 spec은 읽기 전용.
- Kiro가 `requirements.md` → `design.md` → `tasks.md` 순으로 생성한다.
  세 문서를 **사람이 먼저 검토·수정한 뒤** 구현을 시작한다.
- `tasks.md` 의 체크박스는 구현이 끝날 때마다 갱신한다. 이게 진행률 지표다.
- spec 문서는 최종 발표 자료의 원재료다. 대충 쓰지 말 것.

## spec 목록과 담당

| spec | 담당 | 상태 |
|------|------|------|
| `preference-intake` | 백엔드 A | 미착수 |
| `poi-scoring` | 백엔드 A + 데이터 | 미착수 |
| `itinerary-scheduler` | 백엔드 B | 미착수 |
| `transit-routing` | 백엔드 B | 미착수 |
| `share-link` | 백엔드 B | 미착수 |
| `frontend-flow` | 프론트엔드 | 미착수 |

## 새 spec 시작 방법

Kiro 채팅에 아래와 같이 입력한다.

```
.kiro/specs/<spec-이름>/ 에 spec을 만들어줘.
목표: <한 문장>
범위: <포함되는 것>
범위 밖: <제외되는 것>
steering의 소유권 규칙을 지켜서 <담당 경로> 안에서만 작업할 것.
```
