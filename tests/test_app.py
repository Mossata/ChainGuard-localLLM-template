import json
import httpx
import pytest
from fastapi.testclient import TestClient
from app import create_app

def client_for(handler):
    return TestClient(create_app(transport=httpx.MockTransport(handler)))

def chat(**updates):
    return {"model": "llama3.2:3b", "messages": [{"role": "user", "content": "Hello"}], **updates}

def output(content="Hello", **updates):
    return {"message": {"content": content}, "done": True, "done_reason": "stop", "prompt_eval_count": 4, "eval_count": 2, **updates}

def test_schema_translation():
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    def handler(request):
        body = json.loads(request.content)
        assert body["format"] == schema
        assert body["stream"] is False
        assert body["options"]["num_predict"] == 100
        return httpx.Response(200, json=output('{"ok": true}'))
    with client_for(handler) as client:
        response = client.post("/v1/chat/completions", json=chat(max_tokens=100, response_format={"type": "json_schema", "json_schema": {"name": "test", "strict": True, "schema": schema}}))
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == '{"ok": true}'
        assert response.json()["usage"]["total_tokens"] == 6

def test_models_and_readiness():
    with client_for(lambda r: httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})) as client:
        assert client.get("/ready").json()["models"] == ["llama3.2:3b"]
        assert client.get("/v1/models").json()["data"][0]["id"] == "llama3.2:3b"
    with client_for(lambda r: httpx.Response(200, json={"models": []})) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503

def test_auth(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-secret")
    with client_for(lambda r: httpx.Response(200, json=output())) as client:
        assert client.post("/v1/chat/completions", json=chat()).status_code == 401
        assert client.post("/v1/chat/completions", json=chat(), headers={"Authorization": "Bearer test-secret"}).status_code == 200

@pytest.mark.parametrize("updates", [{"stream": True}, {"tools": []}, {"max_tokens": 0}, {"response_format": {"type": "json_schema"}}, {"response_format": {"type": "unknown"}}, {"response_format": {"type": "json_schema", "json_schema": {"schema": {"type": "wrong"}}}}])
def test_invalid_requests(updates):
    def handler(request):
        pytest.fail("Invalid requests must not reach the model")
    with client_for(handler) as client:
        assert client.post("/v1/chat/completions", json=chat(**updates)).status_code == 400

@pytest.mark.parametrize("content", ['not JSON', '{"ok": "wrong"}'])
def test_invalid_output(content):
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    with client_for(lambda r: httpx.Response(200, json=output(content))) as client:
        assert client.post("/v1/chat/completions", json=chat(response_format={"type": "json_schema", "json_schema": {"schema": schema}})).status_code == 502

def test_truncation():
    with client_for(lambda r: httpx.Response(200, json=output('{', done_reason="length"))) as client:
        assert client.post("/v1/chat/completions", json=chat(response_format={"type": "json_object"})).json()["choices"][0]["finish_reason"] == "length"

@pytest.mark.parametrize("status,expected", [(404, 404), (500, 502)])
def test_upstream_errors(status, expected):
    with client_for(lambda r: httpx.Response(status, text="private detail")) as client:
        response = client.post("/v1/chat/completions", json=chat())
        assert response.status_code == expected
        assert "private detail" not in response.text

@pytest.mark.parametrize("exception,expected", [(httpx.ConnectError, 503), (httpx.ReadTimeout, 504)])
def test_network_errors(exception, expected):
    def handler(request):
        raise exception("failure", request=request)
    with client_for(handler) as client:
        assert client.post("/v1/chat/completions", json=chat()).status_code == expected

@pytest.mark.parametrize("body", ["bad", [], {"message": {}, "done": True}, output(done=False)])
def test_malformed_response(body):
    with client_for(lambda r: httpx.Response(200, json=body)) as client:
        assert client.post("/v1/chat/completions", json=chat()).status_code == 502
