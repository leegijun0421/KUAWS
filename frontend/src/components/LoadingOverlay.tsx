import { useEffect, useState } from "react";

const STEPS = [
  "모두의 취향을 겹쳐 보는 중…",
  "가장 손해 보는 사람이 없도록 장소를 고르는 중…",
  "실제 대중교통 시간표로 동선을 맞추는 중…",
  "환승 여유와 영업시간을 확인하는 중…",
];

/** 일정 생성은 실경로 조회 때문에 10초 이상 걸릴 수 있다 — 무엇을 하는지 보여준다. */
export default function LoadingOverlay({ message }: { message?: string }) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setStep((s) => (s + 1) % STEPS.length), 2500);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="fixed inset-0 z-30 flex flex-col items-center justify-center bg-white/85 backdrop-blur-sm">
      <div className="h-12 w-12 animate-spin rounded-full border-4 border-indigo-200 border-t-indigo-600" />
      <p className="mt-4 text-slate-700">{message ?? STEPS[step]}</p>
    </div>
  );
}
