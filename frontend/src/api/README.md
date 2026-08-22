# API 레이어

목 → 실제 API 전환 지점을 한곳에 모으기 위한 폴더다.

```ts
// 1~2주차
export async function fetchItinerary(): Promise<Itinerary> {
  return mockItinerary;
}

// 3주차 — 이 함수 내부만 바꾸면 전환 완료
export async function fetchItinerary(): Promise<Itinerary> {
  const res = await fetch("/api/planner/itinerary");
  return res.json();
}
```
