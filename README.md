# AI 그룹 여행 플래너

여러 명의 여행 취향을 모아 **한 개의 합의된 일정**을 만들어 주는 AI 여행 플래너.

> 고려대학교 x AWS AI Innovators Challenge (AI Tech Day 2026) 출품작
> 예선 8/18 ~ 9/29 · 본선 10/3 ~ 10/18 · 최종 발표 10/19

---

## 문제

그룹 여행에서 일정 조율은 카톡과 스프레드시트의 몫이다.
기존 플래너는 1인 취향을 전제하고, 여러 명의 취향을 단순 평균하면
**아무도 만족하지 않는 밋밋한 일정**이 나온다.

## 접근

1. **자유 텍스트 → 정량화 하이브리드 입력**
   자연어로 취향을 받고, 모호한 부분만 슬라이더·선택지로 보강한다.
   입력 중에도 AI와 대화를 이어갈 수 있다.
2. **성향 기반 경로 추천**
   최단 경로만 제시하지 않는다. 4분 더 걸려도 바다가 보이는 길을 후보로 올린다.
3. **장소 실패 확률 제시**
   객관 지표만으로 "이 그룹이 이 장소에서 실망할 확률"을 산출한다.
4. **최저 만족도 지표**
   평균이 아니라 **가장 손해 보는 사람의 만족도**를 지표로 삼는다.

## 설계 원칙

- 익명 기능 없음
- 실시간 현황 데이터 사용 안 함
- 객관적 기준만 사용
- 유명하다는 이유로 감점하지 않음
- 공유는 링크 하나로 충분 (플랫폼 비종속)

---

## 빠른 시작

```bash
git clone <이 리포 주소>
cd trip-planner

cp .env.example .env      # 키 값을 채운다

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload

# 확인
curl http://localhost:8000/health
```

프론트엔드는 `frontend/README.md` 참조.

---

## 구조

```
.kiro/          Kiro 에이전트 설정 — 팀 전원 공유 (가장 먼저 읽을 것)
  steering/       팀 규칙 = AI 규칙
  specs/          기능별 요구사항·설계·태스크
  hooks/          저장 시 자동 품질 점검
backend/        FastAPI 백엔드 (모듈별 소유자 지정됨)
frontend/       React + TypeScript UI
shared/types/   API 계약 — PM 단독 소유, 1주차 동결
data/           수집 스크립트 (원본 데이터는 커밋하지 않음)
mocks/          프론트 선행 개발용 목 응답
docs/           아키텍처, 의사결정 기록, 회의록
```

## 기술 스택

Python 3.11 · FastAPI · Pydantic v2 · AWS Bedrock ·
React 18 · TypeScript · Vite · Tailwind CSS

---

## 팀 (5인)

| 역할 | 담당 영역 |
|------|-----------|
| 백엔드 리드 A | `backend/intake/`, `backend/scoring/` |
| 백엔드 리드 B | `backend/planner/`, `backend/routing/`, `backend/share/` |
| 프론트엔드 리드 | `frontend/` |
| 데이터 리드 | `data/` |
| PM · 문서 리드 | `shared/types/`, `docs/`, `.kiro/steering/` |

## 기여 방법

[CONTRIBUTING.md](./CONTRIBUTING.md) 를 **먼저 읽는다.**
특히 파일 소유권 규칙과 브랜치 규칙은 머지 충돌을 막는 핵심이다.
