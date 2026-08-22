"""FastAPI 진입점.

각 모듈의 router 를 여기서만 등록한다.
모듈 담당자는 자기 모듈의 router.py 만 수정하고 이 파일은 건드리지 않는다.
router 등록 한 줄 추가가 필요하면 PR 본문에 명시한다.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI 여행 플래너", version="0.1.0")

# 예선 기간에는 로컬 개발 편의를 위해 전체 허용. 본선 배포 전 반드시 제한할 것.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """헬스 체크."""
    return {"status": "ok"}


# 각 모듈 구현이 끝나면 아래 주석을 해제한다.
# from backend.intake.router import router as intake_router
# from backend.scoring.router import router as scoring_router
# from backend.planner.router import router as planner_router
# from backend.routing.router import router as routing_router
# from backend.share.router import router as share_router
#
# app.include_router(intake_router, prefix="/api/intake", tags=["intake"])
# app.include_router(scoring_router, prefix="/api/scoring", tags=["scoring"])
# app.include_router(planner_router, prefix="/api/planner", tags=["planner"])
# app.include_router(routing_router, prefix="/api/routing", tags=["routing"])
# app.include_router(share_router, prefix="/api/share", tags=["share"])
