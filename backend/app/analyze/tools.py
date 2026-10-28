"""The app's own `analyze`-tagged GET routes as model tools, called in-process as the asking user."""

import json
import re
from urllib.parse import quote

import httpx
from fastapi import FastAPI

from app.auth.deps import INTERNAL_TOKEN_HEADER, INTERNAL_USER_HEADER

TAG = "analyze"
TOOL_TIMEOUT_S = 30.0
MAX_TOOL_OUTPUT_CHARS = 60_000


class AnalyzeToolError(Exception):
    """A tool call the model asked for cannot run (unknown tool, bad arguments)."""


def _operations(app: FastAPI) -> dict[str, tuple[str, dict]]:
    """operation id -> (path, OpenAPI operation) for GET operations tagged `analyze`.

    Raises RuntimeError (at startup, from create_app) when such a route has no explicit
    operation_id (FastAPI's generated one ends in ``<path>_get``) or no docstring.
    """
    out: dict[str, tuple[str, dict]] = {}
    for path, methods in app.openapi()["paths"].items():
        op = methods.get("get")
        if not op or TAG not in op.get("tags", []):
            continue
        if op["operationId"].endswith(re.sub(r"\W", "_", path) + "_get"):
            raise RuntimeError(f"`{TAG}` route {path} needs an explicit operation_id")
        if not (op.get("description") or "").strip():
            raise RuntimeError(f"`{TAG}` route {path} needs a docstring (it is the tool description)")
        out[op["operationId"]] = (path, op)
    return out


def build_tools(app: FastAPI) -> list[dict]:
    """OpenAI function tools from the `analyze` GET operations (query and path parameters only)."""
    tools = []
    for name, (_, op) in _operations(app).items():
        props: dict[str, dict] = {}
        required: list[str] = []
        for p in op.get("parameters", []):
            if p["in"] not in ("query", "path"):
                continue
            schema = dict(p.get("schema", {}))
            schema.pop("title", None)
            if p.get("description"):
                schema["description"] = p["description"]
            props[p["name"]] = schema
            if p.get("required"):
                required.append(p["name"])
        description = "\n\n".join(x for x in (op.get("summary"), op.get("description")) if x)
        tools.append(
            {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": props, "required": required},
                "strict": False,  # optional parameters are not strict-compatible
            }
        )
    return tools


def _request_for(app: FastAPI, name: str, args: dict) -> tuple[str, dict]:
    ops = _operations(app)
    if name not in ops:
        raise AnalyzeToolError(f"unknown tool {name!r}; available: {', '.join(sorted(ops))}")
    path, op = ops[name]
    params: dict = {}
    for p in op.get("parameters", []):
        value = args.get(p["name"])
        if p["in"] == "path":
            if value is None or value == "":
                raise AnalyzeToolError(f"{name} needs {p['name']}")
            path = path.replace("{" + p["name"] + "}", quote(str(value), safe=""))
        elif p["in"] == "query" and value is not None:
            params[p["name"]] = value
    return path, params


async def call_tool(app: FastAPI, user_id: int, name: str, args: dict) -> dict:
    """Run one tool as `user_id` via an in-process GET; errors come back as `{"error": ...}`."""
    try:
        path, params = _request_for(app, name, args if isinstance(args, dict) else {})
    except AnalyzeToolError as err:
        return {"error": str(err)}
    headers = {INTERNAL_USER_HEADER: str(user_id), INTERNAL_TOKEN_HEADER: app.state.internal_token}
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://app", timeout=TOOL_TIMEOUT_S) as client:
            resp = await client.get(path, params=params, headers=headers)
    except httpx.HTTPError as err:
        return {"error": f"{name} failed: {type(err).__name__}"}
    try:
        body = resp.json()
    except ValueError:
        body = resp.text[:1000]
    if resp.status_code >= 400:
        return {"error": f"{name} returned HTTP {resp.status_code}", "detail": body}
    return body


def tool_output(result: dict) -> str:
    """The JSON string handed back to the model, truncated if it is huge."""
    text = json.dumps(result, default=str)
    if len(text) > MAX_TOOL_OUTPUT_CHARS:
        text = json.dumps(
            {"truncated": True, "note": "result too large; narrow the filters or lower limit",
             "partial": text[:MAX_TOOL_OUTPUT_CHARS]}  # fmt: skip
        )
    return text
