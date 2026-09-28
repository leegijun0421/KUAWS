"""FastAPI 진입점.

각 모듈의 router 를 여기서만 등록한다.
모듈 담당자는 자기 모듈의 router.py 만 수정하고 이 파일은 건드리지 않는다.
router 등록 한 줄 추가가 필요하면 PR 본문에 명시한다.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.common.config import REPO_ROOT, get_settings
from backend.intake.router import router as intake_router
from backend.planner.router import router as planner_router
from backend.share.router import router as share_router

app = FastAPI(title="AI 여행 플래너", version="0.1.0")

# 로컬 개발 서버 + 배포 주소(PUBLIC_BASE_URL)만 허용한다.
# 배포 환경에서는 프론트를 같은 출처로 서빙하므로 CORS 가 실제로 쓰이지는 않는다.
_ALLOWED_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}
_ALLOWED_ORIGINS.add(get_settings().public_base_url.rstrip("/"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """헬스 체크."""
    return {"status": "ok"}


app.include_router(intake_router, prefix="/api/intake", tags=["intake"])
app.include_router(planner_router, prefix="/api/planner", tags=["planner"])
app.include_router(share_router, prefix="/api/share", tags=["share"])

# scoring·routing 은 planner 파이프라인 안에서 호출되므로 별도 공개 API 가 없다.


# ── 배포용: 빌드된 프론트엔드(frontend/dist)를 같은 출처로 서빙 ──────────────
# 로컬 개발(npm run dev)에서는 dist 가 없으므로 아무 것도 등록하지 않는다.
# Cloud Run 이미지(Dockerfile)에서는 dist 가 있으므로 컨테이너 하나로 화면+API 를 모두 제공한다.
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        """정적 파일이 있으면 그대로, 없으면 index.html (공유 링크 /s/{id} 등 SPA 라우팅)."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
