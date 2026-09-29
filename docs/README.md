# 문서 색인

처음 보는 분은 **POC → ARCHITECTURE → DECISIONS** 순서로 읽으면 전체 그림이 잡힌다.

## 서비스와 결과

| 문서 | 내용 |
|---|---|
| [POC.md](POC.md) | 문제 정의, 핵심 기능, 데이터 활용, 실측 결과, 평가 항목 대응 |
| [SERVICE_INTRO.md](SERVICE_INTRO.md) | 대중평가용 소개 문구, 데모 장면 설명 |
| [DEMO.md](DEMO.md) | 데모 시나리오 3종, 리허설, 3분 영상 대본 |
| [EXTRACTION_EVAL.md](EXTRACTION_EVAL.md) | 대화 → 취향 추출 정답지 대조 (5/5 통과) |
| [TAGGING_REVIEW.md](TAGGING_REVIEW.md) | LLM 5축 태깅 수동 검수 30건 |
| [USER_TEST.md](USER_TEST.md) | 외부인 사용 테스트 진행 방법과 기록 |

## 설계와 결정

| 문서 | 내용 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 모듈 구조, maximin 수식, 스케줄러·위험도 설계 ([다이어그램 원본](architecture.mmd)) |
| [DECISIONS.md](DECISIONS.md) | 의사결정 기록(ADR) — 라우팅 공급자 전환, 도시 선정, 약관 대응 등 |
| [vector_schema.md](vector_schema.md) | 5축 성향 벡터 스키마 (동결) |
| [WIREFRAMES.md](WIREFRAMES.md) | 화면 3종 와이어프레임 |
| [odsay_field_check.md](odsay_field_check.md) | ODsay 응답 필드 점검 (국내 참조 구현) |

## 운영

| 문서 | 내용 |
|---|---|
| [DEPLOY.md](DEPLOY.md) | Google Cloud Run 배포 절차와 운영 메모 |
| [MEETING_NOTES.md](MEETING_NOTES.md) | 회의록 |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | 브랜치·파일 소유권·커밋 규칙 |
| [../.kiro/specs/](../.kiro/specs) | 기능별 요구사항·설계·태스크 (Kiro spec) |
