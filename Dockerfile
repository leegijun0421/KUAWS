# ─────────────────────────────────────────────────────────────────────────────
# 모두의 여행 — Cloud Run 배포 이미지 (컨테이너 1개 = 화면 + API)
#
#   1단계 frontend : React/Vite 빌드 → frontend/dist
#   2단계 runtime  : FastAPI(uvicorn)가 /api 와 빌드된 화면을 같은 출처로 서빙
#
# 지도 키
#   키 B(Maps JS 전용, 리퍼러 제한)는 frontend/.env.local 에서 Vite 가 빌드 시 읽는다.
#   브라우저에 노출되는 키라 번들에 들어가도 되며, 배포 주소를 리퍼러 허용 목록에 추가해야 지도가 뜬다.
# 런타임 환경변수 (이미지에 넣지 않는다 — gcloud run deploy 에서 주입)
#   ANTHROPIC_API_KEY, GOOGLE_BACKEND_API_KEY, PUBLIC_BASE_URL
# 배포 방법: scripts/deploy_cloudrun.ps1, docs/DEPLOY.md
# ─────────────────────────────────────────────────────────────────────────────

FROM node:22-slim AS frontend
WORKDIR /app
# 프론트는 ../../../shared/types 를 import 하므로 리포 구조를 그대로 둔다.
COPY shared ./shared
COPY mocks ./mocks
# 화면의 '예시 대화 불러오기' 버튼이 테스트 픽스처 대화를 ?raw 로 가져온다.
COPY tests/fixtures/conversations ./tests/fixtures/conversations
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci
COPY frontend ./frontend
RUN cd frontend && npm run build


FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY shared ./shared
COPY mocks ./mocks
# 수집·태깅된 POI(tagged.json). 없으면 mocks/poi_seed 로 동작한다(backend/common/poi_data.py).
# 원본 수집물·로그는 .dockerignore 로 제외하고 서비스에 필요한 tagged.json 만 넣는다.
COPY data ./data
COPY --from=frontend /app/frontend/dist ./frontend/dist

# 공유 링크 SQLite·LLM 캐시는 컨테이너 로컬 디스크(인스턴스 재시작 시 초기화 — 예선 데모 범위에서 허용)
RUN mkdir -p data/processed/cache/llm

EXPOSE 8080
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
