import type { IntakeMessageResponse, PreferenceAxis } from "../../../shared/types/api";
import { AXES } from "../lib/format";
import AxisSlider from "./AxisSlider";

interface Props {
  member: IntakeMessageResponse;
  onAxisChange: (axis: PreferenceAxis, value: number, commit: boolean) => void;
}

/** 참가자 1명의 5축 취향 확인·수정 카드(슬라이더 5축, 절단 3). */
export default function MemberCard({ member, onAxisChange }: Props) {
  const { profile, followUps, assistantMessage } = member;
  const questionFor = (axis: PreferenceAxis) => followUps.find((q) => q.axis === axis);
  return (
    <article className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <header className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100 font-semibold text-indigo-700">
          {profile.memberName.slice(0, 1)}
        </div>
        <div>
          <h3 className="font-semibold text-slate-800">{profile.memberName}</h3>
          {assistantMessage && <p className="text-xs text-slate-500">{assistantMessage}</p>}
        </div>
      </header>
      <div className="mt-3 space-y-2">
        {AXES.map(({ key }) => {
          const value = profile.axes.find((axis) => axis.axis === key) ?? {
            axis: key,
            value: 0.5,
            confidence: 0,
          };
          return (
            <AxisSlider
              key={key}
              value={value}
              question={questionFor(key)}
              onChange={(next) => onAxisChange(key, next, false)}
              onCommit={(next) => onAxisChange(key, next, true)}
            />
          );
        })}
      </div>
      {followUps.length > 0 && (
        <p className="mt-2 text-xs text-amber-700">
          노란 칸은 대화만으로는 확실하지 않은 취향이에요. 움직여서 확정해 주세요.
        </p>
      )}
    </article>
  );
}
