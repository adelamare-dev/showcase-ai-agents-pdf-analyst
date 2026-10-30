import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.mark.parametrize("path", ["/fixed/", "/dynamic/"])
def test_browser_request_is_refused_before_the_agent_runs(path):
    # A no-CORS POST from a web page: no Content-Type, so FastAPI would parse
    # the body as JSON and start a run if the request got through.
    response = client.post(
        path, content=b"{}", headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_preflight_gets_no_cors_grant():
    response = client.options(
        "/dynamic/",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_server_to_server_request_is_accepted():
    # The Next.js runtime sends no Origin header.
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["ok"] is True
