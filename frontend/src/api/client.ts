/**
 * 백엔드 호출은 전부 여기를 거친다(컴포넌트에서 fetch 금지 — conventions.md).
 * 개발 서버는 /api 를 FastAPI(:8000)로 프록시한다(vite.config.ts).
 */
import type {
  ChatIntakeResponse,
  CityInfo,
  IntakeAnswerRequest,
  IntakeMessageRequest,
  IntakeMessageResponse,
  Itinerary,
  PlanRequest,
  ShareLinkResponse,
  ShareRequest,
} from "../../../shared/types/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : "요청을 처리하지 못했습니다.";
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const fetchCities = () => request<CityInfo[]>("/api/planner/cities");

export const intakeChat = (chatText: string, city: string) =>
  post<ChatIntakeResponse>(`/api/intake/chat?city=${city}`, { chatText });

export const intakeMessage = (body: IntakeMessageRequest, city: string) =>
  post<IntakeMessageResponse>(`/api/intake/message?city=${city}`, body);

export const intakeAnswer = (body: IntakeAnswerRequest) =>
  post<IntakeMessageResponse>("/api/intake/answer", body);

export const createPlan = (body: PlanRequest) => post<Itinerary>("/api/planner/plan", body);

export const createShareLink = (body: ShareRequest) => post<ShareLinkResponse>("/api/share", body);

export const fetchShared = (planId: string) => request<Itinerary>(`/api/share/${planId}`);
