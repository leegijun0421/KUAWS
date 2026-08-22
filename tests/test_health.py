"""CI가 처음부터 초록불이 되도록 하는 최소 테스트."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    """헬스 엔드포인트가 정상 응답하는지 확인한다."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
