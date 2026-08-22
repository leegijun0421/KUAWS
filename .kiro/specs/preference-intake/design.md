# preference-intake — 설계

> 상태: 초안. Kiro로 생성/보강한 뒤 담당자가 확정한다.

## 흐름

```
사용자 자유 텍스트
      │
      ▼
[extract_profile]  Bedrock 호출 → 축별 값 + 신뢰도(JSON)
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

요청/응답 스키마는 `shared/types/api.schema.json` 을 단일 기준으로 한다.

## 실패 처리

| 상황 | 처리 |
|------|------|
| LLM JSON 파싱 실패 | 1회 재시도 → 실패 시 정량 입력 폼으로 폴백 |
| Bedrock 타임아웃 | 사용자에게 재시도 버튼 노출, 입력 내용은 보존 |
| 후속 질문 3회 초과 | 남은 축은 중립값으로 채우고 진행 |
