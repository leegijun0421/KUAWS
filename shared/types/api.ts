/**
 * 백엔드·프론트엔드 공통 API 계약.
 * 이 파일과 shared/types/models.py 는 항상 같은 구조를 유지한다.
 * 수정은 PM만 한다.
 */

// ---------- 공통 ----------

/**
 * 취향 축: 5개로 확정·동결 (절단 3, 2026-09-04). 이후 변경 금지.
 * 스키마 변경 시 태깅 전량 재실행이 발생하므로 배치 전에 반드시 확정한다.
 */
export type PreferenceAxis =
  | "activity_level"   // 정적 ↔ 활동적
  | "crowd_tolerance"  // 한적함 ↔ 북적임 선호
  | "nature_vs_urban"  // 자연 ↔ 도심
  | "food_priority"    // 식사 비중 낮음 ↔ 높음
  | "pace";            // 여유 ↔ 빡빡

/** 경로 선호 유형. 최단 경로만이 아니라 경치 우회도 후보로 둔다. */
export type RoutePreference = "fastest" | "fewest_transfers" | "scenic";

// ---------- 취향 입력 ----------

export interface AxisValue {
  axis: PreferenceAxis;
  /** 0.0 ~ 1.0 */
  value: number;
  /** 0.0 ~ 1.0. 임계값 미만이면 후속 질문 대상. */
  confidence: number;
}

export interface PreferenceProfile {
  memberId: string;
  memberName: string;        // 익명 기능 없음 — 이름은 항상 존재한다
  axes: AxisValue[];
  rawText: string;
  updatedAt: string;         // ISO 8601
}

/** 신뢰도가 낮은 축을 보강하기 위한 정량 질문. */
export interface FollowUpQuestion {
  questionId: string;
  axis: PreferenceAxis;
  prompt: string;
  kind: "slider" | "choice";
  choices?: { label: string; value: number }[];
}

export interface IntakeMessageResponse {
  profile: PreferenceProfile;
  followUps: FollowUpQuestion[];
  /** 대화를 이어갈 수 있도록 AI가 덧붙이는 말 */
  assistantMessage: string;
}

// ---------- 장소 ----------

export interface Poi {
  poiId: string;
  name: string;
  category: string;
  lat: number;
  lng: number;
  address: string;
}

/** 실패 확률은 객관 지표만으로 산정한다. 인기도를 페널티로 쓰지 않는다. */
export interface PoiScore {
  poiId: string;
  /** 그룹 적합도 0.0 ~ 1.0 */
  fitScore: number;
  /** 실망할 확률 0.0 ~ 1.0 */
  failureProbability: number;
  /** 근거가 된 객관 지표 (표시용) */
  reasons: string[];
  /** 멤버별 만족도 — 누가 손해 보는지 드러내기 위함 */
  perMemberFit: { memberId: string; fit: number }[];
}

// ---------- 일정 ----------

export interface RouteLeg {
  mode: "walk" | "bus" | "subway" | "transfer";
  lineName?: string;
  fromName: string;
  toName: string;
  durationMin: number;
  description: string;
}

export interface RouteSegment {
  fromPoiId: string;
  toPoiId: string;
  preference: RoutePreference;
  totalDurationMin: number;
  totalFare: number;
  legs: RouteLeg[];
}

export interface ItineraryStop {
  order: number;
  poi: Poi;
  score: PoiScore;
  arriveAt: string;   // "HH:MM"
  stayMin: number;
}

export interface ItineraryDay {
  dayNumber: number;
  stops: ItineraryStop[];
  segments: RouteSegment[];
}

export interface Itinerary {
  planId: string;
  city: string;
  days: ItineraryDay[];
  members: { memberId: string; memberName: string }[];
  /** 그룹 최저 만족도 — 아무도 소외되지 않았는지 보여주는 지표 */
  minMemberSatisfaction: number;
  /** LLM이 생성한 일정 요약 브리핑 */
  briefing: string;
}

// ---------- 공유 ----------

export interface ShareLinkResponse {
  planId: string;
  /** 플랫폼 비종속. 링크 하나로 끝낸다. */
  url: string;
  expiresAt: string | null;
}

// ---------- 오류 ----------

export interface ApiError {
  code: string;
  message: string;
  retryable: boolean;
}


// ======================================================================
// 확장: 특성 벡터 + Provider 인터페이스 (models.py 와 동일 구조 유지)
// 구현 없이 타입/인터페이스만 정의한다.
// ======================================================================

// ---------- 스코어링 입력 벡터 ----------

export interface PoiVector {
  poiId: string;
  /** 취향 축과 정렬된 특성값 0.0~1.0 (PreferenceAxis 순서) */
  axisFeatures: number[];
  // --- provider별 편차. 없으면 생략(graceful degradation) ---
  popularity?: number;      // 0.0~1.0
  avgStayMin?: number;
  priceLevel?: number;      // 0~4
  embedding?: number[];     // 의미 임베딩(있는 provider만)
  source?: string;
}

/** PoiScore 와 동일 개념. 이름만 다르게 노출. */
export type MatchResult = PoiScore;

/** ItineraryStop 과 동일 개념. */
export type ScheduledStop = ItineraryStop;

/** 기존 라우팅 타입 별칭 */
export type Route = RouteSegment;
export type TransitLeg = RouteLeg;

// ---------- LLM 응답 표준형 ----------

/** LLM 응답 표준형. provider별 부가 정보는 Optional. */
export interface LLMCompletion {
  text: string;
  modelId?: string;
  inputTokens?: number;
  outputTokens?: number;
  finishReason?: string;
}

// ---------- Provider 인터페이스 ----------

/** 도시별 라우팅 백엔드 교체용 계약. */
export interface RoutingProvider {
  city: string;
  route(
    fromPoi: Poi,
    toPoi: Poi,
    preference: RoutePreference,
  ): Route | Promise<Route>;
  supports(city: string): boolean;
}

/** 모델 호출을 인터페이스 뒤로 격리. Bedrock/기타 구현체 교체 가능. */
export interface LLMProvider {
  name: string; // "bedrock" | "anthropic" | "mock" ...
  complete(
    prompt: string,
    opts?: {
      system?: string;
      maxTokens?: number;
      temperature?: number;
    },
  ): LLMCompletion | Promise<LLMCompletion>;
}
