from __future__ import annotations

import argparse
import json
import os
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pandas as pd

# Allow running from repo root without installing.
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from fleet_pricing.resale.model import load_resale_model, predict_resale  # noqa: E402


class App(SimpleHTTPRequestHandler):
    # Served from /web as static root
    web_root: Path
    model_path: Path
    _model: Any | None = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            if not self.model_path.exists():
                raise FileNotFoundError(f"resale model not found at {self.model_path}")
            self._model = load_resale_model(str(self.model_path))
        return self._model

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        # Same-origin when serving UI + API together; still helpful for local experimentation.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> Any:
        n = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(n) if n > 0 else b""
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path.rstrip("/") == "/api/predict-resale":
                body = self._read_json_body()
                if not isinstance(body, dict):
                    return self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Expected JSON object body"})
                vehicle = body.get("vehicle")
                if not isinstance(vehicle, dict):
                    return self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Body must include vehicle object"})

                model = self._ensure_model()
                X = pd.DataFrame([vehicle])
                pred = float(predict_resale(model, X)[0])
                return self._send_json(HTTPStatus.OK, {"predicted_resale_value_end_per_vehicle": pred})

            return self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint"})
        except FileNotFoundError as e:
            return self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
        except Exception as e:  # pragma: no cover
            return self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"{type(e).__name__}: {e}"})

    def translate_path(self, path: str) -> str:
        # Serve static assets from web_root.
        # Special-case "/" to "/index.html".
        if path == "/":
            path = "/index.html"
        rel = path.lstrip("/")
        full = (self.web_root / rel).resolve()
        # Prevent directory traversal.
        if not str(full).startswith(str(self.web_root.resolve())):
            return str(self.web_root / "index.html")
        return str(full)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument(
        "--model",
        default=str(REPO_ROOT / "artifacts" / "resale_model.joblib"),
        help="Path to joblib resale model pipeline.",
    )
    args = ap.parse_args()

    web_root = REPO_ROOT / "web"
    if not web_root.exists():
        raise SystemExit(f"web root not found: {web_root}")

    # Bind handler class vars
    App.web_root = web_root
    App.model_path = Path(args.model)

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), App)
    print(f"Serving UI at http://127.0.0.1:{args.port}/ (static root: {web_root})")
    print(f"Resale model: {App.model_path}")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

