import { describe, expect, it } from "vitest";
import { dateAfter, fare, legLabel, localTime, percent, riskLevel } from "./format";

describe("format", () => {
  it("percent rounds", () => {
    expect(percent(0.678)).toBe("68%");
  });

  it("fare keeps cents and currency", () => {
    expect(fare(2.55, "EUR")).toBe("2.55 EUR");
    expect(fare(25, "TWD")).toBe("25 TWD");
    expect(fare(0, "EUR")).toBe("무료");
  });

  it("localTime converts UTC schedule to city time", () => {
    expect(localTime("2026-10-14T08:37:00Z", "Europe/Paris")).toBe("10:37");
    expect(localTime(null)).toBeNull();
  });

  it("legLabel describes walk and transit", () => {
    const base = { fromName: "", toName: "", description: "" };
    expect(legLabel({ ...base, mode: "walk", durationMin: 5 })).toBe("도보 5분");
    expect(legLabel({ ...base, mode: "bus", lineName: "72", durationMin: 15 })).toBe(
      "버스·트램 72",
    );
  });

  it("riskLevel thresholds", () => {
    expect(riskLevel(0.05).text).toBe("안정");
    expect(riskLevel(0.2).text).toBe("보통");
    expect(riskLevel(0.4).text).toBe("주의");
  });

  it("dateAfter pads", () => {
    expect(dateAfter(1, new Date(2026, 8, 30))).toBe("2026-10-01");
  });
});
