/**
 * Google Maps JavaScript API 로더 — 프론트 전용 키(B, HTTP 리퍼러 제한)만 쓴다.
 * 키 A(Routes·Places)는 절대 브라우저로 내려오지 않는다(.env.example 주석 참고).
 */

// 공식 타입 패키지를 추가하지 않기 위해 필요한 만큼만 선언한다.
export interface MapsApi {
  Map: new (el: HTMLElement, options: Record<string, unknown>) => MapInstance;
  Marker: new (options: Record<string, unknown>) => { setMap: (map: MapInstance | null) => void };
  Polyline: new (options: Record<string, unknown>) => { setMap: (map: MapInstance | null) => void };
  LatLngBounds: new () => { extend: (p: { lat: number; lng: number }) => void };
}
export interface MapInstance {
  fitBounds: (bounds: unknown, padding?: number) => void;
}

declare global {
  interface Window {
    google?: { maps: MapsApi };
    __kuawsMapsReady?: () => void;
  }
}

const KEY = import.meta.env.VITE_GOOGLE_MAPS_JS_API_KEY as string | undefined;
let loading: Promise<MapsApi> | null = null;

export const hasMapsKey = () => Boolean(KEY);

/** 스크립트를 한 번만 넣고, 로드가 끝나면 maps 네임스페이스를 돌려준다. */
export function loadMaps(): Promise<MapsApi> {
  if (!KEY) return Promise.reject(new Error("VITE_GOOGLE_MAPS_JS_API_KEY 가 없습니다"));
  if (window.google?.maps) return Promise.resolve(window.google.maps);
  loading ??= new Promise((resolve, reject) => {
    window.__kuawsMapsReady = () => resolve(window.google!.maps);
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${KEY}&language=ko&callback=__kuawsMapsReady`;
    script.async = true;
    script.onerror = () => reject(new Error("Google Maps 스크립트를 불러오지 못했습니다"));
    document.head.appendChild(script);
  });
  return loading;
}
