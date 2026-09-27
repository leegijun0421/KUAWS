import type { ItineraryStop, Member } from "../../../shared/types/api";
import { CATEGORY_LABEL, percent } from "../lib/format";

interface Props {
  stop: ItineraryStop;
  members: Member[];
  onClose: () => void;
}

/** 장소 상세 — 누가 만족하고 누가 손해 보는지, 실패 위험의 근거. */
export default function StopDetail({ stop, members, onClose }: Props) {
  const name = (id: string) => members.find((m) => m.memberId === id)?.memberName ?? id;
  const fitReasons = stop.score.reasons.filter((r) => !r.startsWith("위험 요인"));
  const riskReasons = stop.score.reasons
    .filter((r) => r.startsWith("위험 요인"))
    .map((r) => r.replace("위험 요인: ", ""));
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(stop.poi.name)}&query_place_id=${stop.poi.poiId}`;

  return (
    <div
      className="fixed inset-0 z-20 flex items-end justify-center bg-slate-900/40 sm:items-center"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white p-5 sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-slate-500">
              {CATEGORY_LABEL[stop.poi.category] ?? stop.poi.category} · {stop.arriveAt}–
              {stop.departAt}
            </p>
            <h3 className="text-lg font-semibold text-slate-800">{stop.poi.name}</h3>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400" aria-label="닫기">
            ✕
          </button>
        </div>

        <h4 className="mt-4 text-sm font-semibold text-slate-700">멤버별 만족도</h4>
        <ul className="mt-2 space-y-2">
          {stop.score.perMemberFit.map((fit) => (
            <li key={fit.memberId} className="text-sm">
              <div className="flex justify-between text-slate-600">
                <span>{name(fit.memberId)}</span>
                <span>{percent(fit.fit)}</span>
              </div>
              <div className="mt-1 h-2 rounded-full bg-slate-100">
                <div
                  className="h-2 rounded-full bg-indigo-500"
                  style={{ width: percent(fit.fit) }}
                />
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-1 text-[11px] text-slate-400">
          각자에게 이 도시에서 가장 잘 맞는 장소를 100%로 본 값이에요.
        </p>

        {fitReasons.length > 0 && (
          <ul className="mt-3 list-inside list-disc text-sm text-slate-600">
            {fitReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}

        <h4 className="mt-4 text-sm font-semibold text-slate-700">
          실패 위험 {percent(stop.score.failureProbability)}
        </h4>
        {riskReasons.length ? (
          <ul className="mt-1 list-inside list-disc text-sm text-slate-600">
            {riskReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-slate-500">눈에 띄는 위험 요인이 없어요.</p>
        )}
        <p className="mt-1 text-[11px] text-slate-400">
          실제 시간표의 환승 여유·영업 종료·식사 피크 같은 객관 지표만 써요. 유명하다고 감점하지
          않아요.
        </p>

        <a
          href={mapsUrl}
          target="_blank"
          rel="noreferrer"
          className="mt-4 block text-center text-sm text-indigo-600 underline"
        >
          Google 지도에서 보기
        </a>
      </div>
    </div>
  );
}
