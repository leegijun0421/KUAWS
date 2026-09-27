import { useState } from "react";
import type { Itinerary, PlanRequest } from "../../../shared/types/api";
import { createShareLink } from "../api/client";

interface Props {
  itinerary: Itinerary;
  request: PlanRequest | null;
}

/** 링크 하나로 공유(플랫폼 비종속). 장소 순서만 저장하고 경로는 열 때 다시 계산한다. */
export default function ShareBox({ itinerary, request }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  if (!request) return null;

  const share = async () => {
    setError(null);
    try {
      const dayOrders = itinerary.days.map((day) => day.stops.map((stop) => stop.poi.poiId));
      const link = await createShareLink({ request, dayOrders });
      const shareUrl = `${window.location.origin}/s/${link.planId}`;
      setUrl(shareUrl);
      await navigator.clipboard?.writeText(shareUrl).then(
        () => setCopied(true),
        () => undefined,
      );
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  return (
    <div className="rounded-2xl bg-indigo-50 p-4 ring-1 ring-indigo-100">
      {url ? (
        <div className="text-sm">
          <p className="font-medium text-indigo-800">
            {copied ? "링크를 복사했어요!" : "공유 링크"}
          </p>
          <input
            readOnly
            value={url}
            className="mt-2 w-full rounded-lg bg-white px-3 py-2 text-xs"
          />
          <p className="mt-1 text-xs text-indigo-500">
            30일 동안 열 수 있어요. 어떤 메신저에 붙여넣어도 돼요.
          </p>
        </div>
      ) : (
        <button
          type="button"
          onClick={share}
          className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white"
        >
          🔗 친구들에게 링크로 공유
        </button>
      )}
      {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
    </div>
  );
}
