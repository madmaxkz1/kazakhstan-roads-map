from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import json
import os


ROOT = Path(__file__).resolve().parent
CACHE_FILE = ROOT / "roads_republic_osm_cache_v3.json"
BOUNDARY_CACHE_FILE = ROOT / "kazakhstan_boundary_osm_cache.json"
HOST = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

OVERPASS_QUERY = """
[out:json][timeout:180];
area["ISO3166-1"="KZ"][admin_level=2]->.kz;
(
  way(area.kz)["highway"]["ref"~"(^|;|[[:space:]])K[AА]Z[ -]?[0-9]", i];
  relation(area.kz)["type"="route"]["route"="road"]["ref"~"^K[AА]Z[ -]?[0-9]", i];
)->.republicRoutes;
way(r.republicRoutes)(area.kz)->.republicRouteWays;
(
  way.republicRoutes;
  .republicRouteWays;
)->.roadsInKazakhstan;
(.roadsInKazakhstan;);
out body geom;
"""

BOUNDARY_QUERY = """
[out:json][timeout:120];
relation["ISO3166-1"="KZ"]["type"="boundary"]["boundary"="administrative"]["admin_level"="2"];
out body geom;
"""


class MapHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/republic-roads":
            self.send_roads()
            return

        if path == "/api/kazakhstan-boundary":
            self.send_boundary()
            return

        super().do_GET()

    def send_roads(self):
        if CACHE_FILE.exists():
            data = CACHE_FILE.read_text(encoding="utf-8")
            if has_overpass_elements(data):
                self.send_json(data)
                return
            CACHE_FILE.unlink()

        errors = []
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                data = fetch_overpass(endpoint)
                CACHE_FILE.write_text(data, encoding="utf-8")
                self.send_json(data)
                return
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                errors.append(f"{endpoint}: {exc}")

        body = json.dumps(
            {
                "error": "Не удалось загрузить данные Overpass",
                "details": errors,
            },
            ensure_ascii=False,
        )
        self.send_response(502)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def send_boundary(self):
        if BOUNDARY_CACHE_FILE.exists():
            data = BOUNDARY_CACHE_FILE.read_text(encoding="utf-8")
            if has_overpass_elements(data):
                self.send_json(data)
                return
            BOUNDARY_CACHE_FILE.unlink()

        errors = []
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                data = fetch_overpass(endpoint, BOUNDARY_QUERY)
                BOUNDARY_CACHE_FILE.write_text(data, encoding="utf-8")
                self.send_json(data)
                return
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                errors.append(f"{endpoint}: {exc}")

        body = json.dumps(
            {
                "error": "Не удалось загрузить границу Казахстана",
                "details": errors,
            },
            ensure_ascii=False,
        )
        self.send_response(502)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data.encode("utf-8"))


def fetch_overpass(endpoint, query=OVERPASS_QUERY):
    url = endpoint + "?data=" + quote(query)
    request = Request(
        url,
        headers={
            "User-Agent": "KazakhstanRepublicRoadsMap/1.0",
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=180) as response:
        return response.read().decode("utf-8")


def has_overpass_elements(data):
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return False

    return bool(parsed.get("elements"))


if __name__ == "__main__":
    os.chdir(ROOT)
    server = ThreadingHTTPServer((HOST, PORT), MapHandler)
    print(f"Map server started: http://{HOST}:{PORT}/index.html")
    print("Press Ctrl+C to stop")
    server.serve_forever()
