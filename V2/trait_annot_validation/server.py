"""Validation server for the Wagner trait-review interface.

Serves validate.html + bundle.json AND persists each reviewer's decisions to
files inside the run folders, so 3 reviewers can work independently and their
answers land next to the data they reviewed:

    extraction/runs/<species>/<model_key>/validation/<reviewer>.json

Design choices:
  - stdlib only (http.server + json) => `python3 server.py`, nothing to pip-install.
  - decisions are keyed by REVIEWER, so three reviewers never overwrite each other
    (three files per species, one per reviewer).
  - the browser autosaves after every action via POST /api/decisions; it also keeps
    a localStorage copy as an offline fallback, but the server files are the source
    of truth and survive browser clears / different machines.

Endpoints:
  GET  /                          -> validate.html
  GET  /bundle.json               -> the data bundle
  GET  /api/reviewers             -> {"reviewers": [...names with saved files...]}
  GET  /api/decisions?reviewer=NM -> {"<species>": {<decisions>}}  (all species)
  POST /api/decisions             -> body {reviewer, species, decisions}; writes the file

Run:
    python3 trait_annot_validation/server.py            # serves on 0.0.0.0:8000
    python3 trait_annot_validation/server.py 9000       # custom port
"""

from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RUNS = REPO / "extraction" / "runs"

# model_key the bundle was built for — decisions are stored under this run folder.
# Read it from the bundle so the server and the data always agree.
def _model_key() -> str:
    try:
        return json.loads((HERE / "bundle.json").read_text())["model_key"]
    except Exception:
        return "gpt-5.4-mini-medium"

MODEL_KEY = _model_key()

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")
def _safe(name: str) -> str:
    """Sanitize a reviewer/species name into a safe filename component."""
    return _SAFE.sub("_", (name or "").strip()) or "anon"


def _decisions_path(species: str, reviewer: str) -> Path:
    d = RUNS / _safe(species) / MODEL_KEY / "validation"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_safe(reviewer)}.json"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    # ---- static files ----
    def _serve_file(self, rel: str):
        # only serve the two known static files (no directory traversal)
        allowed = {"": "validate.html", "validate.html": "validate.html",
                   "bundle.json": "bundle.json"}
        fname = allowed.get(rel.lstrip("/"))
        if fname is None:
            return self._send(404, b"not found", "text/plain")
        p = HERE / fname
        if not p.exists():
            return self._send(404, f"{fname} missing".encode(), "text/plain")
        ctype = "text/html; charset=utf-8" if fname.endswith(".html") else "application/json"
        self._send(200, p.read_bytes(), ctype)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/reviewers":
            return self._json({"reviewers": self._known_reviewers()})
        if u.path == "/api/decisions":
            q = parse_qs(u.query)
            reviewer = (q.get("reviewer", [""])[0])
            return self._json(self._load_all(reviewer))
        return self._serve_file(u.path)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/decisions":
            return self._send(404, b"not found", "text/plain")
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            reviewer = payload["reviewer"]
            species = payload["species"]
            decisions = payload.get("decisions", {})
        except Exception as e:
            return self._json({"error": f"bad request: {e}"}, 400)
        path = _decisions_path(species, reviewer)
        path.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._json({"ok": True, "wrote": str(path.relative_to(REPO))})

    # ---- helpers ----
    def _known_reviewers(self) -> list[str]:
        names = set()
        for p in RUNS.glob(f"*/{MODEL_KEY}/validation/*.json"):
            names.add(p.stem)
        return sorted(names)

    def _load_all(self, reviewer: str) -> dict:
        """All of one reviewer's saved decisions, keyed by species."""
        out = {}
        if not reviewer:
            return out
        rf = _safe(reviewer)
        for p in RUNS.glob(f"*/{MODEL_KEY}/validation/{rf}.json"):
            species = p.parent.parent.parent.name
            try:
                out[species] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return out

    def log_message(self, fmt, *args):  # quieter logging
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Wagner validation server on http://0.0.0.0:{port}")
    print(f"  model: {MODEL_KEY}")
    print(f"  decisions saved to: extraction/runs/<species>/{MODEL_KEY}/validation/<reviewer>.json")
    print(f"  open:  http://localhost:{port}/validate.html")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
