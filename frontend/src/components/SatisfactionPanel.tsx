import type { Itinerary } from "../../../shared/types/api";
import { percent } from "../lib/format";

/**
 * 그룹 최저 만족도(maximin 지표)와 멤버별 만족도.
 * 만족도 = "혼자 갔다면 받았을 일정" 대비 이 일정의 적합도. 가장 낮은 사람이 곧 그룹 점수다.
 */
export default function SatisfactionPanel({ itinerary }: { itinerary: Itinerary }) {
  const rows = itinerary.members.map((member) => ({
    name: member.memberName,
    value: itinerary.memberSatisfaction.find((s) => s.memberId === member.memberId)?.fit ?? 0,
  }));
  const lowest = Math.min(...rows.map((row) => row.value));

  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="whitespace-nowrap text-sm text-slate-500">그룹 최저 만족도</p>
          <p className="text-4xl font-bold text-indigo-600">
            {percent(itinerary.minMemberSatisfaction)}
          </p>
        </div>
        <p className="max-w-[15rem] text-right text-xs text-slate-400">
          평균이 아니라 <b>가장 아쉬운 사람</b> 기준이에요. “혼자 갔다면 받았을 일정” 대비 이만큼은
          만족해요.
        </p>
      </div>
      <ul className="mt-4 space-y-2">
        {rows.map(({ name, value }) => (
          <li key={name} className="text-sm">
            <div className="flex justify-between text-slate-600">
              <span>
                {name}
                {value === lowest && rows.length > 1 && (
                  <span className="ml-1 text-xs text-amber-600">(가장 아쉬움)</span>
                )}
              </span>
              <span>{percent(value)}</span>
            </div>
            <div className="mt-1 h-2 rounded-full bg-slate-100">
              <div className="h-2 rounded-full bg-indigo-400" style={{ width: percent(value) }} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
