import { useEffect, useState } from "react";
import type { Itinerary, ItineraryStop, PlanRequest } from "../../../shared/types/api";
import { CITY_TIMEZONE } from "../lib/format";
import MapView from "./MapView";
import RouteCard from "./RouteCard";
import SatisfactionPanel from "./SatisfactionPanel";
import ShareBox from "./ShareBox";
import StopCard from "./StopCard";
import StopDetail from "./StopDetail";

interface Props {
  itinerary: Itinerary;
  request: PlanRequest | null;
  onRestart?: () => void;
}

const CITY_LABEL: Record<string, string> = { paris: "파리", taipei: "타이베이" };

/** 결과 화면 — 요약(만족도·브리핑·주의) + 일차별 지도·타임라인 + 공유. */
export default function ResultView({ itinerary, request, onRestart }: Props) {
  const [dayIndex, setDayIndex] = useState(0);
  const [detail, setDetail] = useState<ItineraryStop | null>(null);

  // 상세는 /poi/<id> 주소를 가진다 — 뒤로 가기로 닫힌다.
  const openDetail = (stop: ItineraryStop) => {
    window.history.pushState({ poi: stop.poi.poiId }, "", `/poi/${stop.poi.poiId}`);
    setDetail(stop);
  };
  const closeDetail = () => {
    if (window.location.pathname.startsWith("/poi/")) window.history.back();
    setDetail(null);
  };
  useEffect(() => {
    const onPop = () => {
      if (!window.location.pathname.startsWith("/poi/")) setDetail(null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const day = itinerary.days[dayIndex];
  const timeZone = CITY_TIMEZONE[itinerary.city];

  return (
    <div className="space-y-4">
      <header className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-500">
            {itinerary.startDate} 출발 · {itinerary.days.length}일 · {itinerary.members.length}명
          </p>
          <h1 className="text-2xl font-bold text-slate-900">
            {CITY_LABEL[itinerary.city] ?? itinerary.city} 여행
          </h1>
        </div>
        {onRestart && (
          <button type="button" onClick={onRestart} className="text-sm text-slate-500 underline">
            처음부터
          </button>
        )}
      </header>

      {itinerary.dataSource === "seed" && (
        <p className="rounded-xl bg-slate-100 p-3 text-xs text-slate-500">
          ℹ️ 지금은 내장 예시 장소 데이터로 동작 중이에요(수집·태깅본 없음).
        </p>
      )}

      <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="text-sm font-semibold text-slate-500">코스 브리핑</h2>
        <p className="mt-1 leading-relaxed text-slate-800">{itinerary.briefing}</p>
        {itinerary.riskSummary && (
          <p className="mt-3 border-t border-slate-100 pt-3 text-sm text-slate-600">
            🚦 {itinerary.riskSummary}
          </p>
        )}
      </section>

      <SatisfactionPanel itinerary={itinerary} />

      {(itinerary.warnings.length > 0 || itinerary.excludedNotes.length > 0) && (
        <section className="space-y-2 text-sm">
          {itinerary.warnings.map((warning) => (
            <p
              key={warning}
              className="rounded-xl bg-amber-50 p-3 text-amber-800 ring-1 ring-amber-200"
            >
              ⚠ {warning}
            </p>
          ))}
          {itinerary.excludedNotes.map((note) => (
            <p key={note} className="rounded-xl bg-slate-100 p-3 text-slate-600">
              🚫 {note}
            </p>
          ))}
        </section>
      )}

      <nav className="flex gap-2">
        {itinerary.days.map((item, index) => (
          <button
            key={item.dayNumber}
            type="button"
            onClick={() => setDayIndex(index)}
            className={`rounded-full px-4 py-1.5 text-sm ${
              index === dayIndex
                ? "bg-slate-900 text-white"
                : "bg-white text-slate-600 ring-1 ring-slate-300"
            }`}
          >
            {item.dayNumber}일차
          </button>
        ))}
      </nav>

      {day && (
        <>
          <MapView stops={day.stops} />
          <ol className="space-y-0">
            {day.stops.map((stop, index) => {
              const inbound = day.segments.find((seg) => seg.toPoiId === stop.poi.poiId);
              return (
                <li key={stop.poi.poiId}>
                  {index > 0 && inbound && <RouteCard segment={inbound} timeZone={timeZone} />}
                  <StopCard
                    stop={stop}
                    index={index + 1}
                    members={itinerary.members}
                    onOpen={() => openDetail(stop)}
                  />
                </li>
              );
            })}
          </ol>
          {day.stops.length === 0 && (
            <p className="text-sm text-slate-500">이 날은 배치된 장소가 없어요.</p>
          )}
        </>
      )}

      <ShareBox itinerary={itinerary} request={request} />

      {itinerary.stats && (
        <p className="text-center text-[11px] text-slate-400">
          후보 {itinerary.stats.candidateCount}곳 · 경로 조회 {itinerary.stats.providerCalls}회 ·{" "}
          {(itinerary.stats.elapsedMs / 1000).toFixed(1)}초
        </p>
      )}
      {detail && <StopDetail stop={detail} members={itinerary.members} onClose={closeDetail} />}
    </div>
  );
}
