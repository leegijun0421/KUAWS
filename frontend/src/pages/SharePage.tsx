import { useEffect, useState } from "react";
import type { Itinerary } from "../../../shared/types/api";
import { fetchShared } from "../api/client";
import LoadingOverlay from "../components/LoadingOverlay";
import ResultView from "../components/ResultView";

/** 공유 링크 열람. 저장된 장소 순서로 경로만 다시 계산한 결과를 보여준다. */
export default function SharePage({ planId }: { planId: string }) {
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchShared(planId).then(setItinerary, (reason: Error) => setError(reason.message));
  }, [planId]);

  return (
    <main className="mx-auto max-w-3xl space-y-4 px-4 py-6">
      <p className="text-center text-sm text-slate-500">
        친구가 공유한 일정이에요 ·{" "}
        <a href="/" className="text-indigo-600 underline">
          우리 일정 만들기
        </a>
      </p>
      {error && <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      {itinerary && <ResultView itinerary={itinerary} request={null} />}
      {!itinerary && !error && (
        <LoadingOverlay message="최신 대중교통 시간표로 경로를 다시 불러오는 중…" />
      )}
    </main>
  );
}
