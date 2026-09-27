# preference-intake — 작업 목록

> 체크박스는 구현 완료 시점에 갱신한다. 이게 진행률 지표다.
> 태스크 2~3개마다 커밋하고, 브랜치는 2일 안에 머지한다.

- [x] 1. `schema.py` 에 Pydantic 모델 정의 (`shared/types` 와 일치 확인) — API 모델은 shared/types 를 그대로 쓰고 내부 상태만 정의
- [x] 2. Claude 클라이언트 래퍼를 `backend/common/llm.py` 에 작성
- [x] 3. 추출 프롬프트를 `backend/common/prompts/extract_profile.md` 로 작성
- [x] 4. `extractor.py` — 자유 텍스트 → 축별 값·신뢰도 (JSON 파싱 실패 재시도 포함)
- [x] 5. `extractor.py` 단위 테스트 (Claude API 호출은 목 처리)
- [x] 6. `followup.py` — 신뢰도 낮은 축에 대한 정량 질문 생성
- [x] 7. `profile.py` — 응답 병합 및 3회 제한 로직
- [x] 8. `profile.py` — 그룹 단위 집계 함수
- [x] 9. `router.py` — 엔드포인트 3개 연결
- [x] 10. 응답 캐싱 적용 (동일 입력 재호출 방지)
- [x] 11. `mocks/intake.json` 을 실제 응답 형태와 맞추고 프론트에 공유

### 추가 (2026-09-27)

- [x] 12. `chat_parser.py` — 단톡방(카카오톡 내보내기) 대화 → 화자별 발화 분리 (규칙 기반)
- [x] 13. `rules.py` — LLM 불가 시 키워드 규칙 폴백 (신뢰도 0.5 → 슬라이더로 보강)
- [x] 14. `POST /api/intake/chat` — 대화 전체 1회 LLM 호출로 화자별 프로필 + 그룹 하드 제약
