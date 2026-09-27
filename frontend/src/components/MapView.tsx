import { useEffect, useRef, useState } from "react";
import type { ItineraryStop } from "../../../shared/types/api";
import { hasMapsKey, loadMaps } from "../lib/googleMaps";

interface Props {
  stops: ItineraryStop[];
}

/**
 * 그날 동선 지도. 번호 마커 + 순서대로 잇는 점선(실제 경로 모양이 아니라 순서 표시).
 * Google 지도 위에 경로 데이터를 보여주므로 로고·저작권 표기는 지도 자체가 담당한다.
 */
export default function MapView({ stops }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!hasMapsKey() || !ref.current || stops.length === 0) return;
    let cancelled = false;
    const cleanups: (() => void)[] = [];
    loadMaps()
      .then((maps) => {
        if (cancelled || !ref.current) return;
        const map = new maps.Map(ref.current, {
          center: { lat: stops[0].poi.lat, lng: stops[0].poi.lng },
          zoom: 13,
          mapTypeControl: false,
          streetViewControl: false,
        });
        const bounds = new maps.LatLngBounds();
        const path = stops.map((stop, index) => {
          const position = { lat: stop.poi.lat, lng: stop.poi.lng };
          bounds.extend(position);
          const marker = new maps.Marker({
            position,
            map,
            label: { text: String(index + 1), color: "white", fontWeight: "600" },
            title: stop.poi.name,
          });
          cleanups.push(() => marker.setMap(null));
          return position;
        });
        const line = new maps.Polyline({
          path,
          map,
          strokeOpacity: 0,
          icons: [
            {
              icon: { path: "M 0,-1 0,1", strokeOpacity: 0.8, scale: 3 },
              offset: "0",
              repeat: "14px",
            },
          ],
          strokeColor: "#4f46e5",
        });
        cleanups.push(() => line.setMap(null));
        map.fitBounds(bounds, 48);
      })
      .catch((reason: Error) => setError(reason.message));
    return () => {
      cancelled = true;
      cleanups.forEach((fn) => fn());
    };
  }, [stops]);

  if (!hasMapsKey() || error) {
    return (
      <div className="flex h-48 flex-col items-center justify-center rounded-2xl bg-slate-100 text-center text-sm text-slate-500">
        <span>🗺️ 지도를 표시하지 않고 있어요</span>
        <span className="mt-1 text-xs">
          {error ?? "frontend/.env.local 에 VITE_GOOGLE_MAPS_JS_API_KEY 를 넣으면 지도가 나타나요"}
        </span>
        <span className="mt-2 text-[11px] text-slate-400">경로 데이터 © Google</span>
      </div>
    );
  }
  return (
    <div ref={ref} className="h-72 w-full overflow-hidden rounded-2xl ring-1 ring-slate-200" />
  );
}
