import type { ItineraryStop } from "../../../shared/types/api";
import { CATEGORY_ICON, CATEGORY_LABEL, percent, riskLevel } from "../lib/format";

interface Props {
  stop: ItineraryStop;
  index: number;
  onOpen: () => void;
}

/** 일정의 장소 카드 한 장. 누르면 상세(멤버별 만족도·위험 요인)가 열린다. */
export default function StopCard({ stop, index, onOpen }: Props) {
  const risk = riskLevel(stop.score.failureProbability);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-start gap-3 rounded-2xl bg-white p-4 text-left shadow-sm ring-1 ring-slate-200 transition hover:ring-indigo-300"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-indigo-600 font-semibold text-white">
        {index}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs text-slate-500">
          {stop.arriveAt}–{stop.departAt} · {stop.stayMin}분 머물기
        </div>
        <div className="truncate font-semibold text-slate-800">
          {CATEGORY_ICON[stop.poi.category] ?? "📍"} {stop.poi.name}
        </div>
        <div className="mt-1 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">
            {CATEGORY_LABEL[stop.poi.category] ?? stop.poi.category}
          </span>
          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700">
            그룹 적합도 {percent(stop.score.fitScore)}
          </span>
          <span className={`rounded-full px-2 py-0.5 ${risk.tone}`}>
            실패 위험 {percent(stop.score.failureProbability)} · {risk.text}
          </span>
        </div>
      </div>
    </button>
  );
}
