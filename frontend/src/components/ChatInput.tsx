import { useState } from "react";
import chat1 from "../../../mocks/chats/01_paris_foodie_allergy.txt?raw";
import chat2 from "../../../mocks/chats/02_paris_family.txt?raw";
import chat3 from "../../../mocks/chats/03_paris_conflict.txt?raw";
import chat4 from "../../../mocks/chats/04_taipei_night_market.txt?raw";
import chat5 from "../../../mocks/chats/05_taipei_quiet.txt?raw";

/** 데모·테스트용 예시 대화(가상 인물). mocks/chats/README.md 참고. */
const SAMPLES = [
  { label: "파리 · 먹방 + 알레르기", city: "paris", text: chat1 },
  { label: "파리 · 가족여행", city: "paris", text: chat2 },
  { label: "파리 · 정반대 두 사람", city: "paris", text: chat3 },
  { label: "타이베이 · 야시장", city: "taipei", text: chat4 },
  { label: "타이베이 · 힐링", city: "taipei", text: chat5 },
];

interface Props {
  busy: boolean;
  onSubmitChat: (text: string) => void;
  onSubmitMembers: (members: { name: string; text: string }[]) => void;
  onPickCity: (city: string) => void;
}

/** 취향 입력 — 단톡방 대화 붙여넣기(기본) 또는 한 명씩 자유 텍스트. */
export default function ChatInput({ busy, onSubmitChat, onSubmitMembers, onPickCity }: Props) {
  const [mode, setMode] = useState<"chat" | "members">("chat");
  const [chatText, setChatText] = useState("");
  const [rows, setRows] = useState([{ name: "", text: "" }]);

  const updateRow = (index: number, patch: Partial<{ name: string; text: string }>) =>
    setRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const validRows = rows.filter((row) => row.name.trim() && row.text.trim().length >= 10);

  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <h2 className="text-lg font-semibold text-slate-800">2. 다들 어떤 여행을 원하나요?</h2>
      <div className="mt-3 inline-flex rounded-xl bg-slate-100 p-1 text-sm">
        {(["chat", "members"] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setMode(key)}
            className={`rounded-lg px-3 py-1.5 ${mode === key ? "bg-white shadow-sm" : "text-slate-500"}`}
          >
            {key === "chat" ? "단톡방 대화 붙여넣기" : "한 명씩 적기"}
          </button>
        ))}
      </div>

      {mode === "chat" ? (
        <div className="mt-4">
          <p className="text-sm text-slate-500">
            카카오톡 대화 내보내기 텍스트나 “이름: 메시지” 형식이면 됩니다. 말한 사람별로 취향을
            나눠 읽어요.
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {SAMPLES.map((sample) => (
              <button
                key={sample.label}
                type="button"
                onClick={() => {
                  setChatText(sample.text);
                  onPickCity(sample.city);
                }}
                className="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700 hover:bg-indigo-100"
              >
                예시: {sample.label}
              </button>
            ))}
          </div>
          <textarea
            value={chatText}
            onChange={(e) => setChatText(e.target.value)}
            rows={9}
            placeholder={"[민지] [오후 8:02] 루브르는 꼭 가자\n[서연] [오후 8:03] 나는 빵집 투어!"}
            className="mt-3 w-full rounded-xl border border-slate-300 p-3 font-mono text-sm"
          />
          <button
            type="button"
            disabled={busy || chatText.trim().length < 10}
            onClick={() => onSubmitChat(chatText)}
            className="mt-3 w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white disabled:opacity-40"
          >
            {busy ? "취향 읽는 중…" : "대화에서 취향 읽기"}
          </button>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {rows.map((row, index) => (
            <div key={index} className="grid gap-2 sm:grid-cols-[8rem_1fr_auto]">
              <input
                value={row.name}
                onChange={(e) => updateRow(index, { name: e.target.value })}
                placeholder="이름"
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              <input
                value={row.text}
                onChange={(e) => updateRow(index, { text: e.target.value })}
                placeholder="예) 조용한 공원 산책이 좋고, 맛집은 꼭 가고 싶어요"
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              <button
                type="button"
                onClick={() => setRows(rows.filter((_, i) => i !== index))}
                className="rounded-lg px-2 text-sm text-slate-400 hover:text-rose-500"
                aria-label="삭제"
              >
                ✕
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setRows([...rows, { name: "", text: "" }])}
            className="text-sm text-indigo-600"
          >
            + 사람 추가
          </button>
          <button
            type="button"
            disabled={busy || validRows.length === 0}
            onClick={() => onSubmitMembers(validRows)}
            className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white disabled:opacity-40"
          >
            {busy ? "취향 읽는 중…" : `${validRows.length}명 취향 읽기`}
          </button>
          <p className="text-xs text-slate-400">한 사람당 10자 이상 적어 주세요.</p>
        </div>
      )}
    </section>
  );
}
