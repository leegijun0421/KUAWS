import { useEffect, useState } from "react";
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

  useEffect(() => {
    fetchCities().then(setCities, (reason: Error) => setError(reason.message));
  }, []);

  const run = async (label: string, task: () => Promise<void>) => {
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
      setStep("review");
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
      setStep("review");
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
      setItinerary(await createPlan(request));
      setLastRequest(request);
      setStep("result");
      window.scrollTo({ top: 0 });
    });

  return (
    <main className="mx-auto max-w-3xl space-y-4 px-4 py-6">
      {step !== "result" && <Hero />}
      {error && (
        <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700 ring-1 ring-rose-200">
          {error}
        </p>
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
              onClick={() => setStep("input")}
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
        <ResultView
          itinerary={itinerary}
          request={lastRequest}
          onRestart={() => setStep("input")}
        />
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
