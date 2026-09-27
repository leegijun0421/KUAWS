import { useState, type ReactNode } from "react";
import type { HardConstraints } from "../../../shared/types/api";
import { CATEGORY_LABEL } from "../lib/format";

interface Props {
  constraints: HardConstraints;
  mustVisit: string[];
  onChange: (constraints: HardConstraints, mustVisit: string[]) => void;
}

/** 대화에서 뽑은 '절대 조건'과 '꼭 가고 싶은 곳'. 잘못 읽었으면 지울 수 있다. */
export default function ConstraintPanel({ constraints, mustVisit, onChange }: Props) {
  const removeCategory = (key: string) =>
    onChange(
      { ...constraints, excludeCategories: constraints.excludeCategories.filter((c) => c !== key) },
      mustVisit,
    );
  const clearKeywords = () => onChange({ ...constraints, avoidKeywords: [] }, mustVisit);
  const removeMust = (name: string) =>
    onChange(
      constraints,
      mustVisit.filter((item) => item !== name),
    );
  const [draft, setDraft] = useState("");
  const addKeyword = () => {
    const word = draft.trim();
    if (!word) return;
    onChange(
      { ...constraints, avoidKeywords: [...new Set([...constraints.avoidKeywords, word])] },
      mustVisit,
    );
    setDraft("");
  };
  const clearTime = () =>
    onChange({ ...constraints, earliestStart: null, latestEnd: null }, mustVisit);
  const empty =
    !constraints.excludeCategories.length &&
    !constraints.avoidKeywords.length &&
    !mustVisit.length &&
    !constraints.earliestStart &&
    !constraints.latestEnd;

  return (
    <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <h3 className="font-semibold text-slate-800">대화에서 찾은 조건</h3>
      {empty && <p className="mt-2 text-sm text-slate-400">특별한 제외 조건은 없었어요.</p>}
      <div className="mt-2 flex flex-wrap gap-2 text-sm">
        {mustVisit.map((name) => (
          <Chip key={name} tone="bg-indigo-50 text-indigo-700" onRemove={() => removeMust(name)}>
            ⭐ 꼭 가기: {name}
          </Chip>
        ))}
        {constraints.excludeCategories.map((key) => (
          <Chip key={key} tone="bg-rose-50 text-rose-700" onRemove={() => removeCategory(key)}>
            🚫 {CATEGORY_LABEL[key] ?? key} 제외
          </Chip>
        ))}
        {(constraints.earliestStart || constraints.latestEnd) && (
          <Chip tone="bg-sky-50 text-sky-700" onRemove={clearTime}>
            ⏰ {constraints.earliestStart ? `${constraints.earliestStart} 이후 시작` : ""}
            {constraints.earliestStart && constraints.latestEnd ? " · " : ""}
            {constraints.latestEnd ? `${constraints.latestEnd} 전에 종료` : ""}
          </Chip>
        )}
        {constraints.avoidKeywords.length > 0 && (
          <Chip tone="bg-rose-50 text-rose-700" onRemove={clearKeywords}>
            🚫 이름에 “{constraints.avoidKeywords.slice(0, 3).join(", ")}”
            {constraints.avoidKeywords.length > 3
              ? ` 외 ${constraints.avoidKeywords.length - 3}개`
              : ""}{" "}
            들어간 식당 제외
          </Chip>
        )}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addKeyword()}
          placeholder="빼야 할 음식·식당 키워드 추가 (예: seafood, 땅콩)"
          className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        <button
          type="button"
          onClick={addKeyword}
          className="rounded-lg bg-slate-800 px-3 text-sm text-white"
        >
          + 추가
        </button>
      </div>
      {constraints.notes.length > 0 && (
        <ul className="mt-2 list-inside list-disc text-xs text-slate-500">
          {constraints.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Chip({
  children,
  tone,
  onRemove,
}: {
  children: ReactNode;
  tone: string;
  onRemove: () => void;
}) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 ${tone}`}>
      {children}
      <button
        type="button"
        onClick={onRemove}
        className="opacity-60 hover:opacity-100"
        aria-label="삭제"
      >
        ✕
      </button>
    </span>
  );
}
