#!/usr/bin/env python3
"""Regression tests for cached Roadside Tool companion syndication.

These tests intentionally avoid network and Claude calls. They validate the
cost-control behavior that matters most: stable keys, source invalidation,
empty-response safety, platform policy, and retry reuse.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import syndicate_tools as st


def sample_tool(**updates):
    tool = {
        "slug": "engine-overheating-assistant",
        "title": "Engine Overheating Assistant",
        "description": "Answer a few quick questions about an overheating engine.",
        "whenToUse": "The moment the temperature gauge starts climbing",
        "problemSolved": "Know when to stop driving",
        "timeEstimate": "About 20 seconds",
        "relatedTopics": [{"label": "Engine & Mechanical", "url": "/clusters/engine-mechanical/"}],
        "priority": 20,
        "canonical_url": "https://towwiththeflow.com/tools/engine-overheating-assistant/",
    }
    tool.update(updates)
    return tool


class CacheHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.cache_file = self.tmp_path / "tool_companion_cache.json"
        self.log_file = self.tmp_path / "tool_syndication_log.txt"
        self.cache_patch = patch.object(st, "COMPANION_CACHE_FILE", self.cache_file)
        self.log_patch = patch.object(st, "LOG_FILE", self.log_file)
        self.cache_patch.start()
        self.log_patch.start()
        for key in st.RUN_STATS:
            st.RUN_STATS[key] = 0

    def tearDown(self):
        self.cache_patch.stop()
        self.log_patch.stop()
        self.tmp.cleanup()

    def test_policy_splits_long_form_and_teasers(self):
        self.assertTrue(st.uses_companion_article("blogger"))
        self.assertTrue(st.uses_companion_article("wordpress"))
        self.assertEqual(st.platform_format("tumblr"), "deterministic_teaser")
        self.assertEqual(st.platform_format("devto"), "deterministic_teaser")
        self.assertEqual(st.platform_format("feeder"), "canonical_source_copy")

    def test_cache_key_is_stable_and_source_hash_invalidates(self):
        tool = sample_tool()
        key1 = st.companion_cache_key(tool, "blogger")
        key2 = st.companion_cache_key(tool, "blogger")
        changed = sample_tool(description="Materially different source text.")
        key3 = st.companion_cache_key(changed, "blogger")
        self.assertEqual(key1, key2)
        self.assertNotEqual(key1, key3)

    def test_empty_model_response_marks_failed_without_crashing(self):
        tool = sample_tool()
        with patch.object(st.sp, "ANTHROPIC_API_KEY", "test-key"), \
             patch.object(st, "make_client", return_value=object()), \
             patch.object(st, "create_message", return_value=SimpleNamespace(model="test-model", content=[SimpleNamespace(text="")])):
            item, status, detail = st.get_or_generate_companion(tool, "blogger", max_generations=1)
        self.assertIsNone(item)
        self.assertEqual(status, "failed")
        self.assertIn("malformed", detail)
        self.assertEqual(st.RUN_STATS["companion_generation_failed"], 1)

    def test_generate_once_then_retry_reuses_cache(self):
        tool = sample_tool()
        payload = {
            "title": "What to Do When the Temperature Gauge Starts Climbing",
            "excerpt": "Safe first steps before an overheating engine becomes expensive.",
            "cta": "Check the interactive tool",
            "body_markdown": (
                "## What should you do first?\n\n"
                + "Pull over safely and shut the engine off. " * 90
                + f"\n\nFor a personalized next step, [use the Engine Overheating Assistant]({tool['canonical_url']})."
            ),
        }
        with patch.object(st.sp, "ANTHROPIC_API_KEY", "test-key"), \
             patch.object(st, "make_client", return_value=object()), \
             patch.object(st, "create_message", return_value=SimpleNamespace(model="test-model", content=[SimpleNamespace(text=json.dumps(payload))])):
            first, first_status, _ = st.get_or_generate_companion(tool, "blogger", max_generations=1)
        self.assertIsNotNone(first)
        self.assertEqual(first_status, "generated")
        self.assertEqual(st.RUN_STATS["companion_generated"], 1)

        with patch.object(st, "create_message", side_effect=AssertionError("Claude should not be called for cached retry")):
            second, second_status, _ = st.get_or_generate_companion(tool, "blogger", max_generations=1)
        self.assertIsNotNone(second)
        self.assertEqual(second_status, "reused")
        self.assertEqual(st.RUN_STATS["companion_reused"], 1)
        self.assertEqual(first["cache_key"], second["cache_key"])

    def test_generation_cap_skips_second_uncached_article(self):
        tool = sample_tool()
        item, status, detail = st.get_or_generate_companion(tool, "wordpress", max_generations=0)
        self.assertIsNone(item)
        self.assertEqual(status, "skipped")
        self.assertIn("cap", detail)


if __name__ == "__main__":
    unittest.main()
