import type { PreferenceAxis, RouteLeg } from "../../../shared/types/api";

/** 5축 표시 정보. 순서는 PreferenceAxis 정의 순서(동결). */
export const AXES: { key: PreferenceAxis; label: string; low: string; high: string }[] = [
  { key: "activity_level", label: "활동량", low: "푹 쉬기", high: "많이 걷기" },
  { key: "crowd_tolerance", label: "사람 많은 곳", low: "한적하게", high: "북적여도 OK" },
  { key: "nature_vs_urban", label: "풍경", low: "자연·공원", high: "도심·미술관" },
  { key: "food_priority", label: "식사 비중", low: "간단히", high: "맛집이 핵심" },
  { key: "pace", label: "일정 속도", low: "여유롭게", high: "빠르게 많이" },
];

export const CATEGORY_LABEL: Record<string, string> = {
  cafe: "카페",
  restaurant: "식사",
  culture: "미술관·전시",
  nature: "공원·자연",
  attraction: "명소",
};

export const CATEGORY_ICON: Record<string, string> = {
  cafe: "☕",
  restaurant: "🍽️",
  culture: "🖼️",
  nature: "🌳",
  attraction: "📍",
};

/** 0~1 → "72%" */
export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** 요금 "2.55 EUR". 통화가 없으면 숫자만. */
export function fare(amount: number, currency?: string | null): string {
  if (!amount) return "무료";
  const text = Number.isInteger(amount) ? String(amount) : amount.toFixed(2);
  return currency ? `${text} ${currency}` : text;
}

/** RFC3339(UTC) → 여행지 현지 "HH:MM". timeZone 이 없으면 브라우저 시간대. */
export function localTime(rfc3339: string | null | undefined, timeZone?: string): string | null {
  if (!rfc3339) return null;
  const date = new Date(rfc3339);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone,
  }).format(date);
}

/** 탑승 leg 한 줄 요약. */
export function legLabel(leg: RouteLeg): string {
  if (leg.mode === "walk") return `도보 ${leg.durationMin}분`;
  const kind = leg.mode === "subway" ? "지하철·기차" : "버스·트램";
  return `${kind} ${leg.lineName ?? ""}`.trim();
}

/** 실패 확률 → 신호등 색과 문구. */
export function riskLevel(probability: number): { tone: string; text: string } {
  if (probability >= 0.3) return { tone: "bg-rose-100 text-rose-700", text: "주의" };
  if (probability >= 0.15) return { tone: "bg-amber-100 text-amber-700", text: "보통" };
  return { tone: "bg-emerald-100 text-emerald-700", text: "안정" };
}

/** 오늘 + n일 "YYYY-MM-DD" (현지 달력 기준). */
export function dateAfter(days: number, from: Date = new Date()): string {
  const date = new Date(from.getTime() + days * 86_400_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export const CITY_TIMEZONE: Record<string, string> = {
  paris: "Europe/Paris",
  taipei: "Asia/Taipei",
};
