"""[W4] 데모 시나리오 3종 사전 실행 + 화면 녹화 (발표 중 API 장애 시 영상으로 대체).

Google 약관상 결과(경로 응답)를 파일로 저장해 두는 방식은 쓸 수 없다. 대신 시나리오를 실제로
돌리는 **화면을 녹화**해 둔다. 녹화 영상은 픽셀일 뿐 응답 데이터를 저장하지 않는다.

준비 (PowerShell, 프로젝트 루트)
    pip install playwright
    python -m playwright install chromium
    # 터미널 1: uvicorn backend.main:app --port 8000
    # 터미널 2: cd frontend; npm run dev
    # .env 에 ROUTING_MOCK / LLM_OFFLINE 이 켜져 있지 않은지 확인할 것(데모는 실데이터)

실행
    python scripts/record_demo.py                 # 3종 전부
    python scripts/record_demo.py --only 2_conflict   # 하나만

산출물  Claude outputs/demo/<시나리오>.webm  (+ 각 단계 스크린샷 .png, 소요 시간 로그)
        리포에 커밋하지 않는다(용량). 발표 PC 로 복사해 둔다.

자막을 화면에 직접 띄우므로 녹화본만으로 3분 데모 영상의 뼈대가 된다(docs/DEMO.md 대본과 동일).
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔 대비

from playwright.sync_api import Page, sync_playwright  # noqa: E402

BASE_URL = "http://localhost:5173"
OUT_DIR = Path(__file__).resolve().parents[1] / "Claude outputs" / "demo"
VIEWPORT = {"width": 1280, "height": 800}
PLAN_TIMEOUT_MS = 90_000  # 실경로 조회가 길어질 수 있다


@dataclass
class Scenario:
    """데모 시나리오 1종."""

    key: str
    title: str
    sample_label: str
    days: int
    captions: dict[str, str] = field(default_factory=dict)
    share: bool = False


SCENARIOS = [
    Scenario(
        key="1_clean",
        title="파리 3인 — 기본 흐름 전체 (발표 메인)",
        sample_label="예시: 파리 · 친구 3명",
        days=2,
        captions={
            "start": "① 파리 여행 단톡방 대화를 그대로 붙여넣습니다",
            "review": "② AI 가 사람별 취향 5가지와 꼭 가고 싶은 곳을 근거 문장과 함께 읽었습니다",
            "result": "③ 루브르부터 시작 · 12시·18시 식사 · 모두의 만족도를 함께",
            "route": "④ 이동은 실제 대중교통 시간표 — 몇 시 몇 분 출발·환승까지",
            "detail": "⑤ 장소마다 누가 만족하고, 무엇이 실패 위험인지",
        },
    ),
    Scenario(
        key="2_conflict",
        title="파리 3인 — 취향이 정반대인 그룹",
        sample_label="예시: 파리 · 취향이 정반대",
        days=1,
        captions={
            "start": "활동적 vs 휴식, 도심 vs 자연 — 정반대인 친구들",
            "review": "평균을 내면 모두 불만인 조합입니다",
            "result": "평균이 아니라 ‘가장 아쉬운 사람’의 만족도를 먼저 올립니다",
            "route": "경치 좋은 길이 있으면 최단 경로 옆에 이유와 함께 보여줍니다",
            "detail": "멤버별 만족도가 장소마다 보입니다",
        },
    ),
    Scenario(
        key="3_constraints",
        title="파리 가족 — 갑각류 알레르기 + 오전 11시 이전 불가 + 링크 공유",
        sample_label="예시: 파리 · 알레르기·시간 제약",
        days=2,
        captions={
            "start": "알레르기와 시간 제약이 있는 가족 여행",
            "review": "‘해산물 식당 제외’, ‘11시 이후 시작’을 조건으로 읽어냅니다",
            "result": "모든 날이 11시에 시작하고, 해산물 식당은 빠졌습니다",
            "route": "운영기관 표기까지 — 약관을 지킨 서비스",
            "detail": "링크 하나로 가족에게 공유",
        },
        share=True,
    ),
]


def main() -> None:
    """선택한 시나리오를 녹화한다."""
    parser = argparse.ArgumentParser(description="데모 시나리오 녹화")
    parser.add_argument("--only", choices=[s.key for s in SCENARIOS])
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [s for s in SCENARIOS if args.only in (None, s.key)]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(slow_mo=250)
        for scenario in targets:
            record(browser, scenario)
        browser.close()
    print(f"완료 → {OUT_DIR}")


def record(browser, scenario: Scenario) -> None:  # noqa: ANN001 — Playwright Browser
    """시나리오 1종을 녹화하고 단계별 소요 시간을 출력한다."""
    context = browser.new_context(
        viewport=VIEWPORT, record_video_dir=str(OUT_DIR), record_video_size=VIEWPORT
    )
    page = context.new_page()
    started = time.perf_counter()
    print(f"\n[{scenario.key}] {scenario.title}")
    try:
        run_steps(page, scenario)
    finally:
        video = page.video
        context.close()
        if video:
            target = OUT_DIR / f"demo_{scenario.key}.webm"
            target.unlink(missing_ok=True)
            Path(video.path()).rename(target)
            print(f"  녹화: {target.name} ({time.perf_counter() - started:.0f}초)")


def run_steps(page: Page, scenario: Scenario) -> None:
    """입력 → 취향 확인 → 결과 → 상세(→ 공유) 순서로 화면을 진행한다."""
    page.goto(BASE_URL)
    caption(page, scenario.captions["start"])
    page.get_by_text(scenario.sample_label).click()
    page.get_by_role("combobox").select_option(str(scenario.days))
    page.wait_for_timeout(2500)
    page.get_by_role("button", name="대화에서 취향 읽기").click()
    tick = time.perf_counter()
    page.get_by_text("이렇게 이해했어요").wait_for(timeout=60_000)
    print(f"  취향 추출: {time.perf_counter() - tick:.1f}초")
    caption(page, scenario.captions["review"])
    slow_scroll(page, 3)
    page.get_by_role("button", name="일정 만들기").click()
    tick = time.perf_counter()
    page.get_by_text("코스 브리핑").wait_for(timeout=PLAN_TIMEOUT_MS)
    print(f"  일정 생성: {time.perf_counter() - tick:.1f}초")
    caption(page, scenario.captions["result"])
    page.screenshot(path=str(OUT_DIR / f"{scenario.key}_result.png"), full_page=True)
    page.wait_for_timeout(3000)
    slow_scroll(page, 4)
    caption(page, scenario.captions["route"])
    slow_scroll(page, 4)
    page.locator("ol li button").first.click()
    caption(page, scenario.captions["detail"])
    page.wait_for_timeout(3500)
    page.keyboard.press("Escape")
    page.mouse.click(5, 5)
    if scenario.share:
        share(page)


def share(page: Page) -> None:
    """공유 링크를 만들고 그 링크를 열어 같은 일정이 뜨는 것을 보여준다."""
    page.get_by_role("button", name="친구들에게 링크로 공유").click()
    link = page.locator("input[readonly]").input_value(timeout=15_000)
    print(f"  공유 링크: {link}")
    page.wait_for_timeout(2000)
    page.goto(link)
    page.get_by_text("친구가 공유한 일정이에요").wait_for(timeout=PLAN_TIMEOUT_MS)
    page.get_by_text("코스 브리핑").wait_for(timeout=PLAN_TIMEOUT_MS)
    caption(page, "공유받은 친구 화면 — 최신 시간표로 경로를 다시 계산해 보여줍니다")
    page.wait_for_timeout(4000)


def caption(page: Page, text: str) -> None:
    """화면 하단에 자막을 띄운다(녹화본에 그대로 찍힌다)."""
    page.evaluate(
        """(text) => {
            let el = document.getElementById('__demo_caption');
            if (!el) {
                el = document.createElement('div');
                el.id = '__demo_caption';
                el.style.cssText = 'position:fixed;left:50%;bottom:32px;transform:translateX(-50%);'
                    + 'z-index:99999;background:rgba(15,23,42,.88);color:#fff;'
                    + 'padding:12px 22px;'
                    + 'border-radius:14px;font:600 20px/1.4 sans-serif;'
                    + 'max-width:80vw;text-align:center;'
                    + 'pointer-events:none';
                document.body.appendChild(el);
            }
            el.textContent = text;
        }""",
        text,
    )
    page.wait_for_timeout(2200)


def slow_scroll(page: Page, steps: int) -> None:
    """녹화에서 내용이 읽히도록 천천히 스크롤한다."""
    for _ in range(steps):
        page.mouse.wheel(0, 450)
        page.wait_for_timeout(900)


if __name__ == "__main__":
    main()
