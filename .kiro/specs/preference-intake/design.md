# preference-intake — 설계

> 상태: 구현 완료 (2026-09-27). 요청/응답 스키마의 단일 기준은 `shared/types/models.py`.

## 흐름

```
사용자 자유 텍스트
      │
      ▼
[extract_profile]  Claude API 호출 → 축별 값 + 신뢰도(JSON)
      │
      ├─ 모든 축 신뢰도 충분 ──────────────► PreferenceProfile 확정
      │
      └─ 낮은 축 존재
             ▼
      [build_followup]  낮은 축에 대한 정량 질문 생성 (슬라이더/선택지)
             ▼
      사용자 응답 → 프로필 병합 → 최대 3회 반복
```

## 모듈 구성 (`backend/intake/`)

| 파일 | 책임 |
|------|------|
| `router.py` | FastAPI 엔드포인트 |
| `extractor.py` | 자유 텍스트 → 축별 값·신뢰도 |
| `followup.py` | 신뢰도 낮은 축 → 정량 질문 생성 |
| `profile.py` | 프로필 병합, 그룹 집계 |
| `schema.py` | Pydantic 모델 (shared/types와 일치해야 함) |

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/intake/message` | 자유 텍스트 전송, 프로필 초안 + 후속 질문 반환 |
| POST | `/api/intake/answer` | 정량 질문 응답 전송 |
| GET | `/api/intake/profile/{member_id}` | 현재 프로필 조회 |

| POST | `/api/intake/chat` | 단톡방 대화 전체 → 화자별 프로필 + 그룹 하드 제약 |

요청/응답 스키마는 `shared/types/models.py`(= `api.ts`)를 단일 기준으로 한다.

## 실패 처리

| 상황 | 처리 |
|------|------|
| LLM JSON 파싱 실패 | 1회 재시도 → 실패 시 키워드 규칙 추출(신뢰도 0.5) + 슬라이더 보강 |
| Claude API 타임아웃·오류 | 규칙 추출로 폴백(서비스 무중단), 입력 내용은 보존 |
| 후속 질문 3회 초과 | 남은 축은 중립값으로 채우고 진행 |
