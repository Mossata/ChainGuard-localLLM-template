"""Small OpenAI-compatible text server backed by a local Ollama runtime."""
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jsonschema import Draft202012Validator, ValidationError, SchemaError
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "Explain a blockchain in one sentence."}],
        "max_tokens": 100,
        "stream": False,
    }})
    model: str = Field(min_length=1)
    messages: list[Message] = Field(min_length=1)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    stream: bool = False
    response_format: dict | None = None


class ServiceError(Exception):
    def __init__(self, status, message, kind="server_error"):
        self.status, self.message, self.kind = status, message, kind


def create_app(transport=None):
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "")
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "300"))
    context_tokens = int(os.getenv("LLM_CONTEXT_TOKENS", "16384"))

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport) as client:
            app.state.client = client
            yield

    app = FastAPI(title="ChainGuard Local LLM", lifespan=lifespan)

    @app.exception_handler(ServiceError)
    async def service_error(request, error):
        return JSONResponse(status_code=error.status, content={"error": {
            "message": error.message, "type": error.kind, "code": error.status}})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        details = [{"field": ".".join(str(part) for part in item["loc"]),
                    "message": item["msg"]} for item in error.errors()]
        return JSONResponse(status_code=400, content={"error": {
            "message": "Invalid request. Use text messages and the documented request fields.",
            "type": "invalid_request_error", "code": 400, "details": details}})

    async def authorize(request: Request):
        if api_key and not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {api_key}"):
            raise ServiceError(401, "Missing or incorrect API key.", "authentication_error")

    async def upstream(method, path, **kwargs):
        try:
            response = await app.state.client.request(method, path, **kwargs)
        except httpx.TimeoutException:
            raise ServiceError(504, "The model took too long. Try a smaller model or increase LLM_TIMEOUT_SECONDS.")
        except httpx.RequestError:
            raise ServiceError(503, "Cannot reach Ollama. Check that the ollama service is running.")
        if response.status_code == 404:
            raise ServiceError(404, "Model not found. Download it with docker compose exec ollama ollama pull MODEL.", "invalid_request_error")
        if response.is_error:
            raise ServiceError(502, "Ollama could not process the request. Check docker compose logs ollama.")
        try:
            return response.json()
        except ValueError:
            raise ServiceError(502, "Ollama returned an invalid response.")

    async def models():
        data = await upstream("GET", "/api/tags")
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise ServiceError(502, "Ollama returned an invalid model list.")
        return [item["name"] for item in data["models"] if isinstance(item, dict) and isinstance(item.get("name"), str)]

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready", dependencies=[Depends(authorize)])
    async def ready():
        available = await models()
        if not available:
            raise ServiceError(503, "Ollama is running but no model is installed. Download a model first.")
        return {"status": "ready", "models": available}

    @app.get("/v1/models", dependencies=[Depends(authorize)])
    async def list_models():
        return {"object": "list", "data": [{"id": name, "object": "model", "created": 0, "owned_by": "local"} for name in await models()]}

    @app.post("/v1/chat/completions", dependencies=[Depends(authorize)])
    async def complete(body: ChatRequest):
        if body.stream:
            raise ServiceError(400, "Streaming is not supported. Set stream to false.", "invalid_request_error")
        payload = {"model": body.model, "messages": [m.model_dump() for m in body.messages],
                   "stream": False, "options": {"temperature": body.temperature,
                   "num_predict": body.max_tokens, "num_ctx": context_tokens}}
        schema = None
        output_format = body.response_format
        if output_format:
            kind = output_format.get("type")
            if kind == "json_object":
                payload["format"] = "json"
            elif kind == "json_schema":
                details = output_format.get("json_schema")
                schema = details.get("schema") if isinstance(details, dict) else None
                if not isinstance(schema, dict):
                    raise ServiceError(400, "json_schema must contain a schema object.", "invalid_request_error")
                try:
                    Draft202012Validator.check_schema(schema)
                except SchemaError:
                    raise ServiceError(400, "The supplied JSON schema is invalid.", "invalid_request_error")
                payload["format"] = schema
            elif kind != "text":
                raise ServiceError(400, "Supported formats: text, json_object, json_schema.", "invalid_request_error")
        data = await upstream("POST", "/api/chat", json=payload)
        if not isinstance(data, dict):
            raise ServiceError(502, "Ollama returned an invalid chat response.")
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip() or data.get("done") is not True:
            raise ServiceError(502, "The model did not return a complete text response.")
        finish_reason = "length" if data.get("done_reason") == "length" else "stop"
        if finish_reason != "length" and output_format and output_format.get("type") in {"json_object", "json_schema"}:
            try:
                parsed = json.loads(content)
                if schema is not None:
                    Draft202012Validator(schema).validate(parsed)
                elif not isinstance(parsed, dict):
                    raise ValueError()
            except (ValueError, ValidationError):
                raise ServiceError(502, "The model output did not match the requested JSON format. Try a stronger model.")
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)
        return {"id": f"chatcmpl-{uuid4().hex}", "object": "chat.completion", "created": int(time.time()),
                "model": body.model, "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason}], "usage": {"prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens}}

    return app


app = create_app()
