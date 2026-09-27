"""scoring — maximin 매칭, 하드 제약 필터, must_visit 매칭, 영업시간 파싱."""

from backend.common.opening_hours import parse_weekly_hours
from backend.common.poi_data import TaggedPoi, load_city
from backend.scoring.candidates import build_candidates, match_must_visit
from backend.scoring.filters import apply_hard_constraints
from backend.scoring.matcher import group_score, member_fit, score_pois
from shared.types.models import AxisValue, HardConstraints, PreferenceProfile

AXES = ("activity_level", "crowd_tolerance", "nature_vs_urban", "food_priority", "pace")


def profile(member_id: str, values: list[float], confidence: float = 0.9) -> PreferenceProfile:
    return PreferenceProfile(
        member_id=member_id, member_name=member_id, raw_text="", updated_at="",
        axes=[AxisValue(axis=a, value=v, confidence=confidence) for a, v in zip(AXES, values)],
    )


def poi(poi_id: str, features: list[float], category: str = "attraction", name: str = "") -> TaggedPoi:
    return TaggedPoi(poi_id=poi_id, name=name or poi_id, category=category, lat=0, lng=0,
                     axis_features=features)


def test_member_fit_prefers_matching_direction():
    ones = [1.0] * 5
    assert member_fit([0.9] * 5, ones, [0.9] * 5) > member_fit([0.9] * 5, ones, [0.1] * 5)
    assert 0.0 <= member_fit([0.5] * 5, ones, [0.5] * 5) <= 1.0  # 중립끼리도 범위 안


def test_maximin_beats_average_for_conflicting_group():
    """평균 1위(한 명만 극단적으로 만족)보다 둘 다 무난한 곳이 위로 온다."""
    a = profile("a", [0.9, 0.9, 0.9, 0.2, 0.9])
    b = profile("b", [0.1, 0.1, 0.1, 0.8, 0.1])
    polar = poi("polar", [0.95, 0.95, 0.95, 0.2, 0.95])  # a 만 좋아함
    middle = poi("middle", [0.5, 0.5, 0.5, 0.8, 0.5])  # 둘 다 그럭저럭 + 식사
    scores = score_pois([polar, middle], [a, b])
    assert scores[0].poi_id == "middle"
    assert group_score([0.9, 0.1]) < group_score([0.5, 0.5])


def test_fits_are_normalized_to_each_members_best():
    scores = score_pois([poi("x", [0.9] * 5), poi("y", [0.1] * 5)], [profile("a", [0.9] * 5)])
    assert max(s.per_member_fit[0].fit for s in scores) == 1.0


def test_hard_constraints_exclude_category_and_food_keywords():
    pois = [
        poi("sea", [0.5] * 5, "restaurant", "Le Dôme Fruits de Mer"),
        poi("bistro", [0.5] * 5, "restaurant", "Bistro Paul"),
        poi("museum", [0.5] * 5, "culture", "Musée"),
        poi("seafood-park", [0.5] * 5, "nature", "Seafood Park"),  # 명소 이름은 키워드로 안 뺀다
    ]
    outcome = apply_hard_constraints(
        pois, HardConstraints(exclude_categories=["culture"], avoid_keywords=["FRUITS DE MER"])
    )
    assert [p.poi_id for p in outcome.kept] == ["bistro", "seafood-park"]
    assert len(outcome.notes()) == 2


def test_must_visit_matches_across_accents_and_generic_words():
    pois = [poi("louvre", [0.5] * 5, name="Musée du Louvre"),
            poi("orsay", [0.5] * 5, name="Musée d'Orsay"),
            poi("101", [0.5] * 5, name="Taipei 101 Observatory")]
    assert match_must_visit(["Musee du Louvre"], pois) == {"louvre"}
    assert match_must_visit(["Louvre"], pois) == {"louvre"}
    assert match_must_visit(["Taipei 101"], pois) == {"101"}
    assert match_must_visit(["museum"], pois) == set()


def test_candidates_respect_category_quotas_and_must_visit():
    data = load_city("paris")
    by_id = {p.poi_id: p for p in data.pois}
    scores = score_pois(data.pois, [profile("a", [0.5] * 5)])
    chosen, must = build_candidates(scores, by_id, 1, ["Musée du Louvre"])
    assert must == ["seed-fr-louvre"]
    assert next(c for c in chosen if c.poi_id == "seed-fr-louvre").group_score == 1.0
    assert sum(1 for c in chosen if by_id[c.poi_id].category == "restaurant") <= 4


def test_parse_weekly_hours_handles_google_formats():
    text = ("Monday: 7:30 AM – 1:30 AM | Tuesday: Closed | "
            "Wednesday: 12:00 – 1:30 PM, 7:30 – 9:30 PM | "
            "Thursday: Open 24 hours | Friday: 11:00 – 2:00 PM")
    weekly = parse_weekly_hours(text)
    assert weekly[0] == [("07:30", "24:00")]
    assert weekly[1] == []
    assert weekly[2] == [("12:00", "13:30"), ("19:30", "21:30")]
    assert weekly[3] == [("00:00", "24:00")]
    assert weekly[4] == [("11:00", "14:00")]
    assert parse_weekly_hours(None) is None


def test_must_visit_picks_single_best_match_in_real_like_data():
    """실데이터처럼 '루브르'가 여러 곳이면 가장 비슷한 1곳만 고른다."""
    pois = [poi("pyramid", [0.5] * 5, name="Louvre Pyramid"),
            poi("caves", [0.5] * 5, name="Les Caves du Louvre"),
            poi("museum", [0.5] * 5, name="Louvre Museum"),
            poi("tour", [0.5] * 5, name="Tourism France Louvre")]
    assert match_must_visit(["Musée du Louvre"], pois) == {"museum"}


def test_must_visit_requires_same_place_type():
    pois = [poi("park", [0.5] * 5, name="Shilin Residence Park"),
            poi("market", [0.5] * 5, name="Raohe Night Market")]
    assert match_must_visit(["Shilin Night Market"], pois) == set()
    assert match_must_visit(["Raohe Street Night Market"], pois) == {"market"}  # street 는 일반 명사
    assert match_must_visit(["Raohe Night Market"], pois) == {"market"}


def test_group_score_is_exactly_min_of_member_fits():
    data = load_city("paris")
    members = [profile("a", [0.9, 0.9, 0.9, 0.1, 0.9]), profile("b", [0.1, 0.1, 0.1, 0.9, 0.1])]
    for score in score_pois(data.pois, members):
        assert score.fit_score == round(min(f.fit for f in score.per_member_fit), 3)
