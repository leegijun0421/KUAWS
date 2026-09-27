# 프론트엔드

React 18 + TypeScript + Vite + Tailwind CSS(v4). 화면 3종: **입력 → 취향 확인 → 결과(상세 모달)**,
그리고 공유 링크 열람(`/s/<id>`).

## 실행 (PowerShell, `C:\project\KUAWS\frontend`)

```powershell
npm install            # 처음 한 번 (.npmrc 의 legacy-peer-deps 로 peer 충돌을 피한다)
npm run dev            # http://localhost:5173 — /api 는 백엔드(:8000)로 프록시된다
```

백엔드는 리포 루트에서 `uvicorn backend.main:app --reload` 로 먼저 띄운다(루트 README 참고).

| 명령 | 설명 |
|------|------|
| `npm run build` | 타입 체크(`tsc -b`) + 프로덕션 빌드 |
| `npm test` | vitest 단위 테스트 (`src/lib/format.test.ts`) |
| `npm run format` | prettier |

## 환경변수

`frontend/.env.local` (커밋 금지, `.env.example` 참고)

```
VITE_GOOGLE_MAPS_JS_API_KEY=   # 키 B — Maps JavaScript API 전용, HTTP 리퍼러 제한
```

키가 없으면 지도 자리에 안내 문구만 나오고 나머지 화면은 그대로 동작한다.
**키 A(Routes·Places)는 절대 프론트에 두지 않는다.** 경로 조회는 전부 백엔드가 한다.

## 구조

```
src/
  api/client.ts        백엔드 호출은 전부 여기 경유 (컴포넌트에서 fetch 금지)
  lib/format.ts        축 라벨·시간대 변환·요금·위험도 표시 규칙 (+ 테스트)
  lib/googleMaps.ts    Maps JS 로더 (키 B)
  pages/PlannerPage    입력 → 취향 확인 → 결과 상태 관리
  pages/SharePage      /s/<id> 공유 링크 열람
  components/          TripSetup · ChatInput · MemberCard/AxisSlider · ConstraintPanel ·
                       ResultView · SatisfactionPanel · MapView · StopCard · StopDetail ·
                       RouteCard · ShareBox · LoadingOverlay
```

타입은 `shared/types/api.ts` 에서만 import 한다(프론트에서 새로 만들지 않는다).

## 약관 표기 (Google Maps Platform)

- 경로 카드 하단에 **대중교통 운영기관 이름·URL**(응답 값 그대로)과 “경로 데이터 © Google”.
- 지도를 띄우면 Google 로고·저작권은 지도가 직접 표시한다.
- 모의 경로(`ROUTING_MOCK=1`)일 때는 운영기관 칸에 “모의 경로(실제 운행 정보 아님)”이 뜬다.
