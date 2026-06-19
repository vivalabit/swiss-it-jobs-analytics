from __future__ import annotations

import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Iterable

INDEX_HTML_PATH = Path(__file__).with_name("local_search_web.html")
ASSETS_DIR = Path(__file__).with_name("assets")
STATIC_CACHE_CONTROL = "no-cache"
STATIC_ASSETS = {
    "/assets/styles.css": (ASSETS_DIR / "styles.css", "text/css; charset=utf-8"),
    "/assets/app.js": (ASSETS_DIR / "app.js", "application/javascript; charset=utf-8"),
    "/assets/resume_matcher.js": (ASSETS_DIR / "resume_matcher.js", "application/javascript; charset=utf-8"),
}

def _json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _html_response(handler: BaseHTTPRequestHandler, content: str, status: int = 200) -> None:
    data = content.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _text_response(handler: BaseHTTPRequestHandler, content: str, status: int = 200) -> None:
    data = content.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _static_response(
    handler: BaseHTTPRequestHandler,
    asset_path: Path,
    content_type: str,
    *,
    include_body: bool = True,
) -> None:
    try:
        data = asset_path.read_bytes()
        status = HTTPStatus.OK
    except OSError:
        data = b"Not found"
        status = HTTPStatus.NOT_FOUND
        content_type = "text/plain; charset=utf-8"

    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", STATIC_CACHE_CONTROL)
    handler.end_headers()
    if include_body:
        handler.wfile.write(data)


def _head_response(handler: BaseHTTPRequestHandler, content_type: str, status: int = 200) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.end_headers()

def render_index(database_paths: Iterable[Path]) -> str:
    database_list = "\n".join(
        f"<li>{html.escape(str(path))}</li>" for path in database_paths
    )
    index_html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    return index_html.replace("__DATABASE_LIST__", database_list)


def _static_asset(path: str) -> tuple[Path, str] | None:
    return STATIC_ASSETS.get(path)
