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
  /** 이 값의 근거가 된 발화(인용) */
  evidence?: string | null;
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

/** 대화에서 뽑은 하드 제약. 점수가 아니라 제외 규칙이다(알레르기·기피 장소 등). */
export interface HardConstraints {
  /** 제외할 category 키 (cafe / restaurant / culture / nature / attraction) */
  excludeCategories: string[];
  /** 장소 이름에 들어 있으면 제외할 키워드 */
  avoidKeywords: string[];
  /** 사람이 읽는 원문 근거 */
  notes: string[];
  /** 시간 제약 "HH:MM" — 이 시각 이후 시작 / 이전 종료 */
  earliestStart?: string | null;
  latestEnd?: string | null;
}

/** 대화에서 확정된 여행 정보. 없으면 null — 화면에서 채운다. */
export interface TripFacts {
  city: string | null;
  citySupported: boolean;
  days: number | null;
  startDate: string | null;
}

export interface IntakeMessageRequest {
  memberId?: string | null;
  memberName: string;
  text: string;
}

export interface IntakeAnswerRequest {
  memberId: string;
  axis: PreferenceAxis;
  value: number;
}

export interface IntakeMessageResponse {
  profile: PreferenceProfile;
  followUps: FollowUpQuestion[];
  /** 대화를 이어갈 수 있도록 AI가 덧붙이는 말 */
  assistantMessage: string;
  constraints: HardConstraints;
  /** "루브르는 꼭" 처럼 확정된 방문 희망 장소 */
  mustVisit: string[];
}

export interface ChatIntakeRequest {
  chatText: string;
}

export interface ChatIntakeResponse {
  members: IntakeMessageResponse[];
  constraints: HardConstraints;
  mustVisit: string[];
  assistantMessage: string;
  trip: TripFacts;
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

/** 대중교통 운영기관. Google 약관상 이름·URL 표기 의무. */
export interface Operator {
  name: string;
  url: string | null;
}

/** 구간 위험 표시 — 사람이 읽는 문장이 본체 */
export interface RiskFlag {
  level: "low" | "medium" | "high";
  reason: string;
  suggestion?: string | null;
}

export interface RouteAdvisory {
  code: "long_duration" | "many_transfers";
  message: string;
}

export interface RouteLeg {
  mode: "walk" | "bus" | "subway" | "transfer";
  lineName?: string | null;
  fromName: string;
  toName: string;
  durationMin: number;
  /** 실제 편성 출발·도착 시각(RFC3339). 제공자가 주는 경우에만. */
  departAt?: string | null;
  arriveAt?: string | null;
  description: string;
}

export interface RouteSegment {
  fromPoiId: string;
  toPoiId: string;
  preference: RoutePreference;
  totalDurationMin: number;
  /** 주 단위 실수 (2.55 EUR). 통화는 fareCurrency */
  totalFare: number;
  fareCurrency?: string | null;
  legs: RouteLeg[];
  // --- 표시용 부가 정보(선택) ---
  transferCount?: number | null;
  operators: Operator[];
  advisories: RouteAdvisory[];
  /** 성향별 경로 추천 — 최단 대신 고를 수 있는 '경치' 대안 */
  scenic?: ScenicOption | null;
  recommended?: RoutePreference | null;
  riskFlags: RiskFlag[];
}

export interface ScenicOption {
  segment: RouteSegment;
  extraMin: number;
  scenicScore: number;
  highlights: string[];
  /** 추천 이유 문장 */
  reason: string;
}

export interface ItineraryStop {
  order: number;
  poi: Poi;
  score: PoiScore;
  arriveAt: string;   // "HH:MM"
  stayMin: number;
  departAt?: string | null; // "HH:MM"
}

export interface ItineraryDay {
  dayNumber: number;
  stops: ItineraryStop[];
  segments: RouteSegment[];
}

export interface Member {
  memberId: string;
  memberName: string;
}

export interface Itinerary {
  planId: string;
  city: string;
  days: ItineraryDay[];
  members: Member[];
  /** 그룹 최저 만족도 — 아무도 소외되지 않았는지 보여주는 지표 */
  minMemberSatisfaction: number;
  /** 일정 요약 브리핑 (예선: 규칙 기반 템플릿 — 런타임 LLM 호출 없음) */
  briefing: string;
  /** 멤버별 만족도(혼자 갔을 때의 최적 일정 대비). 최저값 = minMemberSatisfaction */
  memberSatisfaction: { memberId: string; fit: number }[];
  warnings: string[];
  /** 위험 구간 한 줄 요약 */
  riskSummary: string;
  excludedNotes: string[];
  /** "collected" = Google Places 수집·태깅본, "seed" = 내장 예시 */
  dataSource?: string | null;
  startDate?: string | null;
  stats?: PlanStats | null;
}

export interface PlanStats {
  candidateCount: number;
  routingCalls: number;
  providerCalls: number;
  attempts: number;
  elapsedMs: number;
}

export interface PlanRequest {
  city: string;
  days: number;
  /** "YYYY-MM-DD" 현지 기준 */
  startDate: string;
  members: PreferenceProfile[];
  constraints: HardConstraints;
  mustVisit: string[];
}

export interface CityInfo {
  key: string;
  label: string;
  timezone: string;
  poiCount: number;
  dataSource: string;
}

// ---------- 공유 ----------

export interface ShareLinkResponse {
  planId: string;
  /** 플랫폼 비종속. 링크 하나로 끝낸다. */
  url: string;
  expiresAt: string | null;
}

/** 공유 링크 생성 요청. 경로가 아닌 '입력 + 장소 순서'만 저장한다(Google 약관). */
export interface ShareRequest {
  request: PlanRequest;
  dayOrders: string[][];
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

// 라우팅 provider 계약은 backend(RouteProvider)가 실체다. shared/types 에
// 별도 RoutingProvider/Route 별칭을 두지 않는다 (중복·불일치 방지).

// ---------- LLM 응답 표준형 ----------

/** LLM 응답 표준형. provider별 부가 정보는 Optional. */
export interface LLMCompletion {
  text: string;
  modelId?: string;
  inputTokens?: number;
  outputTokens?: number;
  finishReason?: string;
}

// ---------- LLM Provider 인터페이스 ----------

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
