"""Verify the Cloudflare Tunnel -> Traefik -> dashboard ingress contract."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]

class TraefikRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
        cls.dashboard = cls.compose["services"]["dashboard"]
        cls.labels = dict(label.split("=", 1) for label in cls.dashboard["labels"])

    def test_router_hostname_https_port_and_network(self):
        labels = self.labels
        self.assertEqual(labels["traefik.enable"], "true")
        self.assertEqual(labels["traefik.docker.network"], "coolify")
        prefix = "traefik.http.routers.job-ia-dashboard."
        self.assertEqual(labels[prefix + "rule"], "Host(`jobs-ia.didaxus.com`)")
        self.assertEqual(labels[prefix + "entrypoints"], "https")
        self.assertEqual(labels[prefix + "tls"], "true")
        self.assertEqual(labels[prefix + "service"], "job-ia-dashboard")
        self.assertEqual(labels["traefik.http.services.job-ia-dashboard.loadbalancer.server.port"], "3000")
        self.assertEqual(labels["traefik.http.services.job-ia-dashboard.loadbalancer.server.scheme"], "http")
        self.assertEqual(self.compose["networks"]["coolify"], {"external": True})
        self.assertIn("coolify", self.dashboard["networks"])
        self.assertIn("default", self.dashboard["networks"])

    def test_worker_not_routed_to_public(self):
        worker = self.compose["services"]["pipeline"]
        self.assertNotIn("labels", worker)
        self.assertNotIn("ports", worker)
        self.assertNotIn("networks", worker)

    def test_http_hardening_and_local_diagnostic_port(self):
        prefix = "traefik.http.routers.job-ia-dashboard."
        middlewares = self.labels[prefix + "middlewares"].split(",")
        self.assertEqual(middlewares, ["job-ia-dashboard-headers", "job-ia-dashboard-rate-limit"])
        for field in ("stsSeconds", "contentTypeNosniff", "frameDeny", "referrerPolicy"):
            self.assertIn("traefik.http.middlewares.job-ia-dashboard-headers.headers." + field, self.labels)
        self.assertEqual(self.dashboard["ports"], ["127.0.0.1:13030:3000"])

if __name__ == "__main__":
    unittest.main()
