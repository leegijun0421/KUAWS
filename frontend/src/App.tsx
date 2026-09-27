import PlannerPage from "./pages/PlannerPage";
import SharePage from "./pages/SharePage";

/**
 * 라우팅은 두 갈래뿐이라 라이브러리 없이 경로로 나눈다.
 *   /s/<planId>  → 공유 링크 열람
 *   그 외         → 입력 → 결과 흐름
 */
export default function App() {
  const match = window.location.pathname.match(/^\/s\/([\w-]+)/);
  return match ? <SharePage planId={match[1]} /> : <PlannerPage />;
}
