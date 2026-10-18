"""Offline regressions for evidence-based backlink status and recovery."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import seo_strategy_status as status
import audit_wordpress_site as wordpress


class BacklinkEvidenceTests(unittest.TestCase):
    def test_absent_records_are_missing_but_blocked_probes_are_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = Path(directory) / "audit.json"
            audit.write_text(json.dumps({"slugs": {"guide": {
                "dev": {"verified": False, "reason": "http_429"},
                "blog": {"verified": False, "reason": "site_unavailable"},
                "wordpress": {"verified": True},
                "feeder": {"verified": False, "reason": "slug_mismatch"},
            }}}))
            with patch.object(status, "BACKLINK_AUDIT_FILE", audit):
                result = status.backlink_inventory()
        self.assertEqual(result["backlogPosts"], 1)
        self.assertEqual(result["backlogUnits"], 2)
        self.assertEqual(result["verificationGaps"], 2)

    def test_incomplete_inventory_cannot_claim_completion(self):
        for inventory in ({"backlogUnits": None}, {"backlogUnits": 0, "verificationGaps": 7}):
            with patch.object(status, "backlink_inventory", return_value=inventory), \
                 patch.object(status, "recent_backlink_completions", return_value=20):
                result = status.backlink_throughput()
            self.assertIsNone(result["estimatedCatchUpDays"])
            self.assertFalse(result["reason"].startswith("Backlink backlog is clear"))

    def test_wordpress_suffix_allows_original_link_but_not_navigation(self):
        for html, expected in (
            ('<a href="https://towwiththeflow.com/guide/">Read</a>', True),
            ('<a href="https://towwiththeflow.com/">Home</a>', False),
            ('<a href="https://towwiththeflow.com/other-guide/">Related</a>', False),
        ):
            session = SimpleNamespace(get=lambda *a, **k: SimpleNamespace(ok=True, text=html))
            self.assertEqual(wordpress.verify_post("guide-2", "https://example.test/guide-2/", session)["verified"], expected)

    def test_wordpress_rate_limit_is_unknown(self):
        session = SimpleNamespace(get=lambda *a, **k: SimpleNamespace(ok=False, status_code=429))
        self.assertIsNone(wordpress.verify_post("guide", "https://example.test/guide/", session)["verified"])


if __name__ == "__main__":
    unittest.main()
