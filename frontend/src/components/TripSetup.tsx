import type { CityInfo } from "../../../shared/types/api";

interface Props {
  cities: CityInfo[];
  city: string;
  startDate: string;
  days: number;
  onChange: (next: { city?: string; startDate?: string; days?: number }) => void;
}

/** 도시(화이트리스트)·출발일·일수 선택. */
export default function TripSetup({ cities, city, startDate, days, onChange }: Props) {
  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <h2 className="text-lg font-semibold text-slate-800">1. 어디로, 언제 가나요?</h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <div className="sm:col-span-3">
          <p className="mb-2 text-sm text-slate-500">
            데이터 품질을 검증한 도시만 지원해요 — 실제 대중교통 시간표가 제공되는 곳입니다.
          </p>
          <div className="flex flex-wrap gap-2">
            {cities.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => onChange({ city: item.key })}
                className={`rounded-xl px-4 py-2 text-sm font-medium ring-1 transition ${
                  item.key === city
                    ? "bg-indigo-600 text-white ring-indigo-600"
                    : "bg-white text-slate-700 ring-slate-300 hover:ring-indigo-400"
                }`}
              >
                {item.label}
                <span className="ml-2 text-xs opacity-75">장소 {item.poiCount}곳</span>
              </button>
            ))}
          </div>
        </div>
        <label className="text-sm text-slate-600">
          출발일(현지)
          <input
            type="date"
            value={startDate}
            onChange={(e) => onChange({ startDate: e.target.value })}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="text-sm text-slate-600">
          여행 일수
          <select
            value={days}
            onChange={(e) => onChange({ days: Number(e.target.value) })}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
          >
            {[1, 2, 3].map((n) => (
              <option key={n} value={n}>
                {n}일
              </option>
            ))}
          </select>
        </label>
      </div>
    </section>
  );
}
