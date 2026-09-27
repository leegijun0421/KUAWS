"""intake — 화자 분리, LLM 추출(목), 규칙 폴백, 후속 질문·라운드 제한."""

import json

from fastapi.testclient import TestClient

from backend.common.llm import complete_json, parse_json_object, render_prompt
from backend.intake import profile as store
from backend.intake.chat_parser import parse_chat
from backend.intake.extractor import extract_profiles
from backend.intake.followup import build_followups
from backend.main import app
from shared.types.models import AxisValue, LLMCompletion

CHAT = """--------------- 2026년 9월 20일 토요일 ---------------
[민지] [오후 3:01] 파리 가면 루브르는 꼭 가고 싶어
[민지] [오후 3:01] 근데 나 갑각류 알레르기 있어서
해산물 식당은 좀 피해야 해
[준호] [오후 3:02] 난 많이 걷는 거 좋아! 공원 산책 최고
[준호] [오후 3:03] 사진
민지님이 나갔습니다.
"""


class FakeProvider:
    """정해진 응답을 순서대로 돌려주는 LLM 목."""

    name = "fake"
    model = "fake-1"

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.calls = 0

    def complete(self, prompt, *, system=None, max_tokens=1024, temperature=0.7):
        self.calls += 1
        return LLMCompletion(text=self.texts.pop(0))


def _llm_json(**overrides) -> str:
    member = {
        "name": "민지",
        "axes": {
            "activity_level": {"value": 0.3, "confidence": 0.8},
            "crowd_tolerance": {"value": None, "confidence": 0.1},
            "nature_vs_urban": {"value": 0.9, "confidence": 0.7},
            "food_priority": {"value": 1.4, "confidence": 0.9},
            "pace": {"value": 0.4, "confidence": 0.5},
        },
        "exclude_categories": ["culture", "spa"],
        "avoid_keywords": ["seafood", " "],
        "constraint_notes": ["갑각류 알레르기"],
        "must_visit": ["루브르 박물관"],
        "summary": "미술관 좋아함",
    }
    member.update(overrides)
    return json.dumps({"members": [member], "assistant_message": "정리했어요"}, ensure_ascii=False)


def test_parse_chat_groups_by_speaker_and_skips_noise():
    speakers = parse_chat(CHAT)
    assert list(speakers) == ["민지", "준호"]
    assert speakers["민지"][1].endswith("해산물 식당은 좀 피해야 해")  # 여러 줄 메시지 이어붙임
    assert speakers["준호"] == ["난 많이 걷는 거 좋아! 공원 산책 최고"]  # '사진' 제외


def test_parse_chat_supports_mobile_and_simple_formats():
    text = "2026년 9월 20일 오후 3:01, 민지 : 조용한 데 좋아\n준호: 맛집!"
    assert parse_chat(text) == {"민지": ["조용한 데 좋아"], "준호": ["맛집!"]}


def test_extract_validates_llm_output():
    provider = FakeProvider(_llm_json())
    result = extract_profiles({"민지": ["..."]}, "파리", provider=provider)
    member = result.members[0]
    values = {axis.axis: axis for axis in member.axes}
    assert values["food_priority"].value == 1.0  # 범위 밖 값은 잘라낸다
    assert values["crowd_tolerance"].value == 0.5  # null → 중립
    assert member.constraints.exclude_categories == ["culture"]  # 허용 key 외 버림
    assert member.constraints.avoid_keywords == ["seafood"]
    assert member.must_visit == ["루브르 박물관"]
    assert result.method == "llm"


def test_extract_retries_once_on_broken_json():
    provider = FakeProvider("이건 JSON 이 아니다", _llm_json())
    result = extract_profiles({"민지": ["..."]}, "파리", provider=provider)
    assert provider.calls == 2
    assert result.method == "llm"


def test_extract_falls_back_to_rules_after_two_failures():
    provider = FakeProvider("x", "y")
    result = extract_profiles({"민지": ["갑각류 알레르기 있어요. 공원 산책 좋아"]}, "파리", provider)
    assert result.method == "rules"
    member = result.members[0]
    assert "seafood" in member.constraints.avoid_keywords
    nature = next(a for a in member.axes if a.axis == "nature_vs_urban")
    assert nature.value < 0.5 and nature.confidence == 0.5


def test_llm_results_are_cached():
    first = FakeProvider('{"a": 1}')
    assert complete_json(first, "같은 입력") == {"a": 1}
    second = FakeProvider("호출되면 안 됨")
    assert complete_json(second, "같은 입력") == {"a": 1}
    assert second.calls == 0


def test_parse_json_object_strips_fences():
    assert parse_json_object('```json\n{"x": [1]}\n```') == {"x": [1]}


def test_render_prompt_fills_all_placeholders():
    system, user = render_prompt("extract_profile", city_label="파리", speakers_json="{}")
    assert "5개 축" in system and "{{" not in user and "파리" in user


def test_followups_only_for_weak_axes_sorted_by_confidence():
    axes = [
        AxisValue(axis="pace", value=0.5, confidence=0.4),
        AxisValue(axis="food_priority", value=0.5, confidence=0.1),
        AxisValue(axis="activity_level", value=0.5, confidence=0.9),
    ]
    questions = build_followups("m1", axes)
    assert [q.axis for q in questions] == ["food_priority", "pace"]
    assert questions[0].kind == "choice" and questions[1].kind == "slider"


def test_api_chat_then_answer_offline(monkeypatch):
    """키가 없으면 규칙 폴백으로라도 끝까지 동작한다."""
    store.reset_states()
    client = TestClient(app)
    res = client.post("/api/intake/chat", json={"chatText": CHAT})
    assert res.status_code == 200
    body = res.json()
    assert [m["profile"]["memberName"] for m in body["members"]] == ["민지", "준호"]
    assert "seafood" in body["constraints"]["avoidKeywords"]

    member_id = body["members"][0]["profile"]["memberId"]
    res = client.post(
        "/api/intake/answer", json={"memberId": member_id, "axis": "pace", "value": 0.2}
    )
    pace = next(a for a in res.json()["profile"]["axes"] if a["axis"] == "pace")
    assert pace == {"axis": "pace", "value": 0.2, "confidence": 1.0, "evidence": None}


def test_rounds_limit_fills_neutral(monkeypatch):
    store.reset_states()
    client = TestClient(app)
    member_id = None
    for _ in range(4):
        payload = {"memberName": "민지", "text": "음... 잘 모르겠어", "memberId": member_id}
        body = client.post("/api/intake/message", json=payload).json()
        member_id = body["profile"]["memberId"]
    assert body["followUps"] == []
    assert all(a["confidence"] >= 0.6 for a in body["profile"]["axes"])


def test_answer_unknown_member_is_404():
    client = TestClient(app)
    res = client.post("/api/intake/answer", json={"memberId": "nope", "axis": "pace", "value": 0.2})
    assert res.status_code == 404


def test_mock_chats_parse_expected_speakers():
    """가짜 카톡 대화 5종이 화자 수대로 분리된다(데모 입력 회귀 방지)."""
    from pathlib import Path

    expected = {"01": 3, "02": 3, "03": 3, "04": 3, "05": 3}
    for path in sorted(Path("tests/fixtures/conversations").glob("*.txt")):
        speakers = parse_chat(path.read_text(encoding="utf-8"))
        assert len(speakers) == expected[path.name[:2]], path.name


def test_rules_detect_type_refusal_without_false_positive():
    from backend.intake.rules import extract_by_rules

    assert extract_by_rules("박물관이나 미술관은 절대 안 갈래")[1].exclude_categories == ["culture"]
    assert extract_by_rules("공원 좋아, 사람 많은 곳은 싫어")[1].exclude_categories == []
    assert "peanut" in extract_by_rules("땅콩 알레르기 있어요")[1].avoid_keywords


def test_llm_unknown_axis_name_falls_back_to_rules():
    bad = _llm_json(axes={"activity": {"value": 0.9, "confidence": 0.9}})
    result = extract_profiles({"민지": ["공원 산책 좋아"]}, "파리", provider=FakeProvider(bad))
    assert result.method == "rules"


def test_llm_evidence_and_trip_facts_are_kept():
    data = json.loads(_llm_json())
    data["members"][0]["axes"]["pace"]["evidence"] = "하루에 너무 많이 돌면 기억도 안 남더라"
    data["trip"] = {"city": "파리", "days": 3, "start_date": "2026-10-15",
                    "earliest_start": "11:00", "latest_end": "25:00"}
    result = extract_profiles({"민지": ["..."]}, "파리",
                              provider=FakeProvider(json.dumps(data, ensure_ascii=False)))
    pace = next(a for a in result.members[0].axes if a.axis == "pace")
    assert pace.evidence.startswith("하루에")
    assert result.trip.city == "paris" and result.trip.city_supported and result.trip.days == 3
    assert result.earliest_start == "11:00" and result.latest_end is None  # 잘못된 시각은 버림


def test_rules_extract_time_constraint_and_trip_from_fixture():
    from pathlib import Path

    text = Path("tests/fixtures/conversations/03_constraints.txt").read_text(encoding="utf-8")
    client = TestClient(app)
    body = client.post("/api/intake/chat", json={"chatText": text}).json()
    assert body["constraints"]["earliestStart"] == "11:00"
    assert body["trip"] == {"city": "paris", "citySupported": True, "days": 2, "startDate": None}
    assert any("seafood" == k for k in body["constraints"]["avoidKeywords"])


def test_unsupported_city_is_flagged():
    from backend.intake.trip import facts_from_llm

    facts, _, _ = facts_from_llm({"city": "도쿄", "days": 2})
    assert facts.city == "도쿄" and facts.city_supported is False
