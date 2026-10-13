import http.client
import json
import threading

from helpers import Sandbox

from personalos.web.server import create_server


class WebUI(Sandbox):
    def setUp(self):
        super().setUp()
        self.index()
        self.srv, self.port, self.token = create_server(self.cfg, port=0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def req(self, method, path, body=None, headers=None, token=True):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = {"Host": f"127.0.0.1:{self.port}"}
        if token:
            h["X-PersonalOS-Token"] = self.token
        if body is not None:
            h["Content-Type"] = "application/json"
            body = json.dumps(body)
        h.update(headers or {})
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        try:
            return r.status, json.loads(data), r
        except ValueError:
            return r.status, data, r

    def test_static_and_security_headers(self):
        s, body, r = self.req("GET", "/", token=False)
        self.assertEqual(s, 200)
        self.assertIn("default-src 'self'", r.getheader("Content-Security-Policy"))
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        self.assertEqual(self.req("GET", "/../config/config.json", token=False)[0], 404)

    def test_token_host_and_csrf_checks(self):
        self.assertEqual(self.req("GET", "/api/status", token=False)[0], 401)
        self.assertEqual(self.req("GET", "/api/status", headers={"X-PersonalOS-Token": "wrong"})[0], 401)
        self.assertEqual(self.req("GET", "/api/status", headers={"Host": "attacker.example"})[0], 403)
        self.assertEqual(self.req("POST", "/api/capture", {"text": "x"}, headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/api/capture", {"text": "x"}, headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.req("OPTIONS", "/api/status")[0], 405)
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        c.request("POST", "/api/capture", body="text=x", headers={"Host": f"127.0.0.1:{self.port}",
                  "X-PersonalOS-Token": self.token, "Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(c.getresponse().status, 415)
        self.assertEqual(self.req("POST", "/api/capture", {"text": "x" * 70000})[0], 413)

    def test_every_view_endpoint(self):
        for ep in ["status", "tree", "inbox", "projects", "goals", "archive", "reports", "health", "settings",
                   "integrations", "search?q=sourdough", "resolve?name=Crop_Rotation"]:
            s, body, _ = self.req("GET", "/api/" + ep)
            self.assertEqual(s, 200, (ep, body))
        _, res, _ = self.req("GET", "/api/search?q=crop%20rotation")
        self.assertEqual(res["tier1"][0]["title"], "Crop_Rotation")
        self.assertEqual(res["tier1"][0]["rel"], "04_Knowledge/Gardening/Crop_Rotation.md")
        _, note, _ = self.req("GET", "/api/note?rel=04_Knowledge/Gardening/Crop_Rotation.md")
        self.assertIn("Legumes", note["text"])
        self.assertEqual(self.req("GET", "/api/note?rel=../config/config.json")[0], 400)
        self.assertEqual(self.req("GET", "/api/nope")[0], 404)

    def test_capture_index_maintain_and_confirmations(self):
        s, r, _ = self.req("POST", "/api/capture", {"text": "Order seed potatoes"})
        self.assertEqual(s, 200)
        _, res, _ = self.req("GET", "/api/search?q=seed%20potatoes")
        self.assertTrue(res["tier1"])
        self.assertEqual(self.req("POST", "/api/index", {"rebuild": True})[0], 400)
        self.assertEqual(self.req("POST", "/api/index", {"rebuild": True, "confirm": True})[0], 200)
        s, rep, _ = self.req("POST", "/api/maintain", {})
        self.assertEqual(s, 200)
        self.assertIn("Balcony_Herb_Box", rep["report"])
        self.assertEqual(self.req("POST", "/api/integrations", {"name": "mcp", "enabled": True})[0], 400)
        self.assertEqual(self.req("POST", "/api/integrations", {"name": "mcp", "enabled": True, "confirm": True})[0], 200)
        self.assertTrue(self.reload().integration("mcp")["enabled"])

    def test_settings_whitelist_and_validation(self):
        ok = {"confirm": True, "changes": [{"key": "search.limit", "value": 8}]}
        self.assertEqual(self.req("POST", "/api/settings", ok)[0], 200)
        self.assertEqual(self.reload().data["search"]["limit"], 8)
        for change in [{"key": "vault", "value": "C:/"}, {"key": "search.limit", "value": 999},
                       {"key": "privacy.log_queries", "value": "yes"}]:
            self.assertEqual(self.req("POST", "/api/settings", {"confirm": True, "changes": [change]})[0], 400)
        self.assertEqual(self.req("POST", "/api/settings", {"changes": ok["changes"]})[0], 400)
