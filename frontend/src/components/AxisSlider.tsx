import type { AxisValue, FollowUpQuestion } from "../../../shared/types/api";
import { AXES } from "../lib/format";

interface Props {
  value: AxisValue;
  question?: FollowUpQuestion;
  onChange: (value: number) => void;
  onCommit: (value: number) => void;
}

/** 취향 축 하나. AI 확신이 낮으면(후속 질문 대상) 노란 테두리와 질문을 보여준다. */
export default function AxisSlider({ value, question, onChange, onCommit }: Props) {
  const meta = AXES.find((axis) => axis.key === value.axis)!;
  const unsure = Boolean(question);
  return (
    <div className={`rounded-lg p-2 ${unsure ? "bg-amber-50 ring-1 ring-amber-300" : ""}`}>
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span className="font-medium text-slate-700">{meta.label}</span>
        <span>{unsure ? "확인해 주세요" : `AI 확신 ${Math.round(value.confidence * 100)}%`}</span>
      </div>
      {question && <p className="mt-1 text-xs text-amber-800">{question.prompt.split(" (")[0]}</p>}
      {question?.kind === "choice" && question.choices ? (
        <div className="mt-2 flex gap-1">
          {question.choices.map((choice) => (
            <button
              key={choice.label}
              type="button"
              onClick={() => onCommit(choice.value)}
              className="flex-1 rounded-md bg-white px-2 py-1 text-xs ring-1 ring-amber-300 hover:bg-amber-100"
            >
              {choice.label}
            </button>
          ))}
        </div>
      ) : (
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={value.value}
          aria-label={meta.label}
          onChange={(e) => onChange(Number(e.target.value))}
          onPointerUp={(e) => onCommit(Number((e.target as HTMLInputElement).value))}
          onKeyUp={(e) => onCommit(Number((e.target as HTMLInputElement).value))}
          className="mt-1 w-full accent-indigo-600"
        />
      )}
      <div className="flex justify-between text-[11px] text-slate-400">
        <span>{meta.low}</span>
        <span>{meta.high}</span>
      </div>
    </div>
  );
}
