"""태깅 배치 — 계약(길이 5·0~1) 검증과 실패 POI 건너뛰기."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("data/scripts").resolve()))

import tag_pois  # noqa: E402

from shared.types.models import LLMCompletion  # noqa: E402

POI = {
    "poi_id": "p1", "name": 'Café "Flore"', "lat": 48.85, "lng": 2.33, "tags": {},
    "category": "cafe", "avg_duration_min": 40, "open_hours": None,
}


class Fake:
    name = "fake"
    model = "fake"

    def __init__(self, text):
        self.text = text

    def complete(self, prompt, *, system=None, max_tokens=1024, temperature=0.7):
        assert '\\"Flore\\"' in prompt  # 따옴표가 이스케이프돼 JSON 이 깨지지 않는다
        return LLMCompletion(text=self.text)


def test_tag_one_builds_contract_record():
    body = '{"axis_features": [0.1, 0.2, 0.9, 0.7, 0.3], "confidence": [1,1,1,1,1], "reasons": ["카페"]}'
    record = tag_pois.tag_one(POI, Fake(body))
    assert record["axis_features"] == [0.1, 0.2, 0.9, 0.7, 0.3]
    assert record["reasons"] == ["카페"] and "tags" not in record


@pytest.mark.parametrize("features", ["[0.1, 0.2]", "[0.1, 0.2, 0.3, 0.4, 1.5]"])
def test_tag_one_skips_contract_violation(features):
    assert tag_pois.tag_one(POI, Fake(f'{{"axis_features": {features}}}')) is None
