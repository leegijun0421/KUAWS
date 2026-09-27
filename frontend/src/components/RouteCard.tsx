import { useState, type ReactNode } from "react";
import type { RouteSegment } from "../../../shared/types/api";
import { fare, legLabel, localTime } from "../lib/format";

interface Props {
  segment: RouteSegment;
  timeZone: string;
}

/**
 * 두 스톱 사이 이동 카드. 실제 편성 시각·환승·요금·경고 배지와
 * 약관 필수 표기(운영기관 이름·URL, Google)를 함께 보여준다.
 */
export default function RouteCard({ segment, timeZone }: Props) {
  const [showScenic, setShowScenic] = useState(segment.recommended === "scenic");
  const shown = showScenic && segment.scenic ? segment.scenic.segment : segment;
  const isMock = segment.operators.some((op) => op.name.startsWith("모의"));
  // 가까운 구간은 외부 호출 없이 도보로 계산한다 — 이때는 Google 표기가 필요 없다.
  const walkOnly = shown.legs.every((leg) => leg.mode === "walk");

  return (
    <div className="ml-5 border-l-2 border-dashed border-slate-300 py-2 pl-6">
      <div className="rounded-xl bg-slate-50 p-3 text-sm ring-1 ring-slate-200">
        <div className="flex flex-wrap items-center gap-2 text-slate-700">
          <span className="font-semibold">
            {walkOnly ? "🚶" : "🚇"} {shown.totalDurationMin}분
          </span>
          {!walkOnly && (
            <>
              <span className="text-slate-400">·</span>
              <span>환승 {shown.transferCount ?? segment.transferCount ?? 0}회</span>
              <span className="text-slate-400">·</span>
              <span>{fare(shown.totalFare, shown.fareCurrency)}</span>
            </>
          )}
          {segment.advisories.map((advisory) => (
            <span
              key={advisory.code}
              className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800"
            >
              ⚠ {advisory.message}
            </span>
          ))}
        </div>

        {segment.scenic && (
          <div className="mt-2 flex flex-wrap gap-2">
            <Toggle active={!showScenic} onClick={() => setShowScenic(false)}>
              ⚡ 최단 {segment.totalDurationMin}분{segment.recommended === "fastest" && " · 추천"}
            </Toggle>
            <Toggle active={showScenic} onClick={() => setShowScenic(true)}>
              🌿 경치 +{segment.scenic.extraMin}분
              {segment.recommended === "scenic" && " · 우리 그룹 추천"}
            </Toggle>
          </div>
        )}
        {showScenic && segment.scenic && segment.scenic.highlights.length > 0 && (
          <p className="mt-1 text-xs text-emerald-700">
            지나가는 곳: {segment.scenic.highlights.join(", ")}
          </p>
        )}

        <ol className="mt-2 space-y-1">
          {shown.legs.map((leg, index) => {
            const depart = localTime(leg.departAt, timeZone);
            const arrive = localTime(leg.arriveAt, timeZone);
            return (
              <li key={index} className="flex gap-2 text-xs text-slate-600">
                <span className="w-24 shrink-0 font-medium text-slate-700">{legLabel(leg)}</span>
                {leg.mode !== "walk" && (
                  <span>
                    {leg.fromName} → {leg.toName}
                    {depart && arrive && (
                      <span className="ml-1 text-indigo-600">
                        ({depart} 출발 · {arrive} 도착)
                      </span>
                    )}
                  </span>
                )}
              </li>
            );
          })}
        </ol>

        {!walkOnly && (
          <footer className="mt-2 border-t border-slate-200 pt-2 text-[11px] text-slate-400">
            {segment.operators.length > 0 && (
              <span>
                운행 정보:{" "}
                {segment.operators.map((op, index) => (
                  <span key={op.name}>
                    {index > 0 && ", "}
                    {op.url ? (
                      <a href={op.url} target="_blank" rel="noreferrer" className="underline">
                        {op.name}
                      </a>
                    ) : (
                      op.name
                    )}
                  </span>
                ))}
              </span>
            )}
            {!isMock && <span className="ml-2">· 경로 데이터 © Google</span>}
          </footer>
        )}
      </div>
    </div>
  );
}

function Toggle({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs ring-1 ${
        active
          ? "bg-indigo-600 text-white ring-indigo-600"
          : "bg-white text-slate-600 ring-slate-300"
      }`}
    >
      {children}
    </button>
  );
}
