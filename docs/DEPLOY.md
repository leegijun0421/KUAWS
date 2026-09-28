# 배포 — Google Cloud Run

예선 제출용 공개 주소. 컨테이너 1개가 빌드된 화면(`frontend/dist`)과 API(`/api/*`)를 **같은 출처**로 제공한다.

```
브라우저 ──► Cloud Run (asia-northeast3)
              ├─ /            React 빌드 결과 (SPA, 공유 링크 /s/{id} 포함)
              ├─ /api/*       FastAPI
              └─ /health      헬스 체크
                   │
                   ├─► Anthropic API   (대화 → 취향, 요청당 1회)
                   └─► Google Routes/Places (실제 편성 시각)
```

## 무엇이 이미지에 들어가고 무엇이 안 들어가나

| 항목 | 이미지 | 비고 |
|------|:-----:|------|
| `backend/`, `shared/`, `mocks/`, 대화 예시(`tests/fixtures/conversations`) | ⬤ | |
| 태깅된 POI `data/processed/pois/<city>/tagged.json` | ⬤ | Git 에는 없음(약관·용량). 로컬 PC 에서 업로드된다 — `.gcloudignore` 가 필요한 이유 |
| 지도 키 B (`frontend/.env.local`) | ⬤ (JS 번들) | 원래 브라우저에 노출되는 키. 리퍼러 제한으로 보호 |
| `ANTHROPIC_API_KEY`, 백엔드 Google 키 | ✗ | Cloud Run 환경변수로만 주입 (`scripts/deploy_cloudrun.ps1`) |
| `.env`, 원본 수집물·로그·캐시·share.db | ✗ | `.dockerignore` / `.gcloudignore` |

## 처음 한 번 (PowerShell)

1. Google Cloud SDK 설치 — https://cloud.google.com/sdk/docs/install → 새 PowerShell 창
2. `gcloud auth login` (브라우저 로그인)
3. **배포용 백엔드 키 만들기** — Cloud Run 은 나가는 IP 가 고정되지 않아 IP 제한 키 A 는 403 이 난다.
   GCP 콘솔 › API 및 서비스 › 사용자 인증 정보 › 키 만들기 → **애플리케이션 제한 없음 / API 제한: Routes API, Places API (New)**.
   값을 `.env` 에 `GOOGLE_CLOUDRUN_API_KEY=...` 로 추가한다(Kiro 에디터로, Set-Content 금지).

## 배포 — `C:\project\KUAWS` 에서

```powershell
.\scripts\deploy_cloudrun.ps1 -ProjectId <GCP 프로젝트 ID>
```

처음에는 Artifact Registry 저장소 생성 여부를 묻는다 → `Y`. 빌드 5~8분.
끝나면 `https://kuaws-xxxx.asia-northeast3.run.app` 형태의 주소가 출력된다.

**마지막 한 단계:** 키 B(Maps JS)의 HTTP 리퍼러 허용 목록에 `https://<출력된 주소>/*` 추가 → 지도 표시.

## 확인

```powershell
curl.exe https://<주소>/health          # {"status":"ok"}
curl.exe https://<주소>/api/planner/cities   # paris·taipei, dataSource: collected
```

브라우저에서 “예시 대화 불러오기 → 일정 만들기”까지 한 번 돌리고, 공유 링크가 `https://<주소>/s/...` 로 열리는지 본다.

## 운영 메모

- `min-instances 1` — 심사 기간 콜드 스타트 제거. 대회 종료 후 `gcloud run services update kuaws --region asia-northeast3 --min-instances 0` 로 비용을 0 에 가깝게.
- `max-instances 2` — 트래픽 폭주 시 LLM·Routes 요금 상한 역할. Anthropic 키 spend limit, GCP 예산 알림은 그대로 유지.
- 공유 링크 DB(SQLite)는 컨테이너 로컬 디스크 — 새 리비전 배포 시 초기화된다(예선 범위에서 허용, 본선에서 Cloud SQL/Firestore 검토).
- 코드 수정 후 재배포는 같은 스크립트를 다시 실행하면 된다.
