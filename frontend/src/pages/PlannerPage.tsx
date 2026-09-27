import { useEffect, useRef, useState } from "react";
import type {
  CityInfo,
  HardConstraints,
  IntakeMessageResponse,
  Itinerary,
  PlanRequest,
  PreferenceAxis,
} from "../../../shared/types/api";
import { createPlan, fetchCities, intakeAnswer, intakeChat, intakeMessage } from "../api/client";
import ChatInput from "../components/ChatInput";
import ConstraintPanel from "../components/ConstraintPanel";
import LoadingOverlay from "../components/LoadingOverlay";
import MemberCard from "../components/MemberCard";
import ResultView from "../components/ResultView";
import TripSetup from "../components/TripSetup";
import { dateAfter } from "../lib/format";

type Step = "input" | "review" | "result";
const EMPTY: HardConstraints = { excludeCategories: [], avoidKeywords: [], notes: [] };

/** 단계별 주소. 결과(/result)와 장소 상세(/poi/<id>)는 뒤로 가기로 오갈 수 있다. */
const PATHS: Record<Step, string> = { input: "/", review: "/review", result: "/result" };

function stepFromPath(path: string): Step {
  if (path.startsWith("/poi/") || path === "/result") return "result";
  return path === "/review" ? "review" : "input";
}

/** 입력(도시·대화) → 취향 확인(슬라이더) → 결과. 상태는 이 페이지 하나에 모은다. */
export default function PlannerPage() {
  const [step, setStep] = useState<Step>("input");
  const [cities, setCities] = useState<CityInfo[]>([]);
  const [trip, setTrip] = useState({ city: "paris", startDate: dateAfter(18), days: 2 });
  const [members, setMembers] = useState<IntakeMessageResponse[]>([]);
  const [constraints, setConstraints] = useState<HardConstraints>(EMPTY);
  const [mustVisit, setMustVisit] = useState<string[]>([]);
  const [lastRequest, setLastRequest] = useState<PlanRequest | null>(null);
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastTask = useRef<(() => void) | null>(null);

  useEffect(() => {
    fetchCities().then(setCities, (reason: Error) => setError(reason.message));
    // 새로고침하면 메모리 상태가 사라지므로 입력 화면에서 다시 시작한다.
    if (window.location.pathname !== "/") window.history.replaceState(null, "", "/");
    const onPop = () => setStep(stepFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const goTo = (next: Step) => {
    setStep(next);
    if (window.location.pathname !== PATHS[next]) window.history.pushState(null, "", PATHS[next]);
  };

  const run = async (label: string, task: () => Promise<void>) => {
    lastTask.current = () => void run(label, task);
    setBusy(label);
    setError(null);
    try {
      await task();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const onChat = (text: string) =>
    run("대화에서 취향을 읽는 중…", async () => {
      const result = await intakeChat(text, trip.city);
      setMembers(result.members);
      setConstraints(result.constraints);
      setMustVisit(result.mustVisit);
      // 대화에서 확정된 여행 정보로 입력칸을 채운다(지원 도시일 때만 도시를 바꾼다).
      setTrip((current) => ({
        city: result.trip.citySupported && result.trip.city ? result.trip.city : current.city,
        days: result.trip.days ? Math.min(Math.max(result.trip.days, 1), 3) : current.days,
        startDate:
          result.trip.startDate && result.trip.startDate > dateAfter(0)
            ? result.trip.startDate
            : current.startDate,
      }));
      goTo("review");
    });

  const onMembers = (rows: { name: string; text: string }[]) =>
    run("취향을 읽는 중…", async () => {
      const results: IntakeMessageResponse[] = [];
      for (const row of rows) {
        results.push(await intakeMessage({ memberName: row.name, text: row.text }, trip.city));
      }
      setMembers(results);
      setConstraints(mergeConstraints(results));
      setMustVisit([...new Set(results.flatMap((r) => r.mustVisit))]);
      goTo("review");
    });

  const onAxisChange = (memberId: string, axis: PreferenceAxis, value: number, commit: boolean) => {
    setMembers((current) =>
      current.map((member) =>
        member.profile.memberId !== memberId
          ? member
          : {
              ...member,
              followUps: commit
                ? member.followUps.filter((q) => q.axis !== axis)
                : member.followUps,
              profile: {
                ...member.profile,
                axes: member.profile.axes.map((a) =>
                  a.axis === axis ? { ...a, value, confidence: commit ? 1 : a.confidence } : a,
                ),
              },
            },
      ),
    );
    // 서버 상태도 맞춰 둔다(대화를 이어갈 때 사용자가 고정한 값이 유지되도록). 실패해도 진행 가능.
    if (commit) intakeAnswer({ memberId, axis, value }).catch(() => undefined);
  };

  const onPlan = () =>
    run("", async () => {
      const request: PlanRequest = {
        ...trip,
        members: members.map((m) => m.profile),
        constraints,
        mustVisit,
      };
      console.info("일정 생성 요청(PlanRequest)", request);
      setItinerary(await createPlan(request));
      setLastRequest(request);
      goTo("result");
      window.scrollTo({ top: 0 });
    });

  return (
    <main className="mx-auto max-w-3xl space-y-4 px-4 py-6">
      {step !== "result" && <Hero />}
      {error && (
        <div className="flex items-center justify-between gap-3 rounded-xl bg-rose-50 p-3 text-sm text-rose-700 ring-1 ring-rose-200">
          <span>{error}</span>
          {lastTask.current && (
            <button
              type="button"
              onClick={() => lastTask.current?.()}
              className="shrink-0 rounded-lg bg-rose-600 px-3 py-1 text-white"
            >
              다시 시도
            </button>
          )}
        </div>
      )}

      {step === "input" && (
        <>
          <TripSetup cities={cities} {...trip} onChange={(next) => setTrip({ ...trip, ...next })} />
          <ChatInput
            busy={busy !== null}
            onSubmitChat={onChat}
            onSubmitMembers={onMembers}
            onPickCity={(city) => setTrip((t) => ({ ...t, city }))}
          />
        </>
      )}

      {step === "review" && (
        <>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-800">3. 이렇게 이해했어요 — 맞나요?</h2>
            <button
              type="button"
              onClick={() => goTo("input")}
              className="text-sm text-slate-500 underline"
            >
              다시 입력
            </button>
          </div>
          <ConstraintPanel
            constraints={constraints}
            mustVisit={mustVisit}
            onChange={(c, m) => {
              setConstraints(c);
              setMustVisit(m);
            }}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            {members.map((member) => (
              <MemberCard
                key={member.profile.memberId}
                member={member}
                onAxisChange={(axis, value, commit) =>
                  onAxisChange(member.profile.memberId, axis, value, commit)
                }
              />
            ))}
          </div>
          <button
            type="button"
            onClick={onPlan}
            className="sticky bottom-4 w-full rounded-xl bg-indigo-600 py-4 text-lg font-semibold text-white shadow-lg"
          >
            ✨ {members.length}명 모두를 위한 일정 만들기
          </button>
        </>
      )}

      {step === "result" && itinerary && (
        <ResultView itinerary={itinerary} request={lastRequest} onRestart={() => goTo("input")} />
      )}
      {busy !== null && <LoadingOverlay message={busy || undefined} />}
    </main>
  );
}

function Hero() {
  return (
    <header className="pt-2 text-center">
      <p className="text-sm font-medium text-indigo-600">AI 그룹 여행 플래너</p>
      <h1 className="mt-1 text-3xl font-bold text-slate-900">모두의 여행</h1>
      <p className="mt-2 text-slate-600">
        단톡방 대화를 붙여넣으면, <b>아무도 소외되지 않는</b> 여행 일정을
        <br className="hidden sm:block" /> 실제 대중교통 시간표에 맞춰 만들어 드려요.
      </p>
    </header>
  );
}

function mergeConstraints(results: IntakeMessageResponse[]): HardConstraints {
  return {
    excludeCategories: [...new Set(results.flatMap((r) => r.constraints.excludeCategories))],
    avoidKeywords: [...new Set(results.flatMap((r) => r.constraints.avoidKeywords))],
    notes: results.flatMap((r) => r.constraints.notes),
  };
}
