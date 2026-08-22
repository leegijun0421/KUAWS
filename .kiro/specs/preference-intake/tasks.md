# preference-intake — 작업 목록

> 체크박스는 구현 완료 시점에 갱신한다. 이게 진행률 지표다.
> 태스크 2~3개마다 커밋하고, 브랜치는 2일 안에 머지한다.

- [ ] 1. `schema.py` 에 Pydantic 모델 정의 (`shared/types` 와 일치 확인)
- [ ] 2. Bedrock 클라이언트 래퍼를 `backend/common/bedrock.py` 에 작성
- [ ] 3. 추출 프롬프트를 `backend/common/prompts/extract_profile.md` 로 작성
- [ ] 4. `extractor.py` — 자유 텍스트 → 축별 값·신뢰도 (JSON 파싱 실패 재시도 포함)
- [ ] 5. `extractor.py` 단위 테스트 (Bedrock 호출은 목 처리)
- [ ] 6. `followup.py` — 신뢰도 낮은 축에 대한 정량 질문 생성
- [ ] 7. `profile.py` — 응답 병합 및 3회 제한 로직
- [ ] 8. `profile.py` — 그룹 단위 집계 함수
- [ ] 9. `router.py` — 엔드포인트 3개 연결
- [ ] 10. 응답 캐싱 적용 (동일 입력 재호출 방지)
- [ ] 11. `mocks/intake.json` 을 실제 응답 형태와 맞추고 프론트에 공유
