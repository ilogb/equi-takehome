from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_ok():
    client = TestClient(create_app(Settings(_env_file=None, database_url="postgresql+psycopg://x/x")))
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
