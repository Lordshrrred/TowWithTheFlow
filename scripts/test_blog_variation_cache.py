#!/usr/bin/env python3
"""Regression tests for cached daily blog syndication variations."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import syndicate_post as sp


SLUG = "test-roadside-guide"
BODY = (
    "## First steps\n\n"
    + "Stay calm, move away from traffic, and document what happened. " * 80
    + "\n\n---\n\n"
    "*Need more roadside help? Visit [Tow With The Flow](https://towwiththeflow.com/test-roadside-guide/) "
    "for complete guides on car breakdowns and towing.*"
)


def model_message(text: str, model: str = "test-model"):
    return SimpleNamespace(
        model=model,
        usage=SimpleNamespace(cache_read_input_tokens=0, cache_creation_input_tokens=0),
        content=[SimpleNamespace(text=text)],
    )


class BlogVariationCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.cache_file = self.tmp_path / "blog_variation_cache.json"
        self.log_file = self.tmp_path / "syndication_log.txt"
        self.cache_patch = patch.object(sp, "BLOG_VARIATION_CACHE_FILE", self.cache_file)
        self.log_patch = patch.object(sp, "LOG_FILE", self.log_file)
        self.cache_patch.start()
        self.log_patch.start()
        for key in sp.VARIATION_RUN_STATS:
            sp.VARIATION_RUN_STATS[key] = 0

    def tearDown(self):
        self.cache_patch.stop()
        self.log_patch.stop()
        self.tmp.cleanup()

    def generated_body(self, slug: str = SLUG) -> str:
        return (
            "## Rewritten roadside guidance\n\n"
            + "This is a useful rewritten version for syndication with practical safety details. " * 80
            + f"\n\nRead the original guide at https://towwiththeflow.com/{slug}/"
        )

    def test_generation_is_cached_and_retry_reuses_without_claude(self):
        with patch.object(sp, "ANTHROPIC_API_KEY", "test-key"), \
             patch.object(sp, "make_client", return_value=object()), \
             patch.object(sp, "create_message", return_value=model_message(self.generated_body())):
            first = sp.get_variation(BODY, "Blogger", SLUG)

        self.assertIn("Rewritten roadside guidance", first)
        self.assertEqual(sp.VARIATION_RUN_STATS["generated"], 1)

        with patch.object(sp, "create_message", side_effect=AssertionError("Claude should not be called")):
            second = sp.get_variation(BODY, "Blogger", SLUG)

        self.assertEqual(first, second)
        self.assertEqual(sp.VARIATION_RUN_STATS["reused"], 1)
        cache = json.loads(self.cache_file.read_text(encoding="utf-8"))
        self.assertEqual(len(cache["items"]), 1)

    def test_source_change_invalidates_cache_key(self):
        key1 = sp.blog_variation_cache_key(BODY, "Blogger", SLUG)
        key2 = sp.blog_variation_cache_key(BODY + "\n\nNew material.", "Blogger", SLUG)
        self.assertNotEqual(key1, key2)

    def test_slug_and_platform_prevent_cross_article_reuse(self):
        key1 = sp.blog_variation_cache_key(BODY, "Blogger", SLUG)
        key2 = sp.blog_variation_cache_key(BODY, "WordPress", SLUG)
        key3 = sp.blog_variation_cache_key(BODY.replace(SLUG, "other-guide"), "Blogger", "other-guide")
        self.assertNotEqual(key1, key2)
        self.assertNotEqual(key1, key3)

    def test_empty_model_response_falls_back_without_cache_write(self):
        with patch.object(sp, "ANTHROPIC_API_KEY", "test-key"), \
             patch.object(sp, "make_client", return_value=object()), \
             patch.object(sp, "create_message", return_value=model_message("")):
            result = sp.get_variation(BODY, "Tumblr", SLUG)
        self.assertEqual(result, BODY)
        self.assertEqual(sp.VARIATION_RUN_STATS["failed"], 1)
        self.assertFalse(self.cache_file.exists())

    def test_generation_cap_skips_uncached_variation(self):
        with patch.object(sp, "ANTHROPIC_API_KEY", "test-key"), \
             patch.object(sp, "BLOG_VARIATION_MAX_GENERATIONS", 0), \
             patch.object(sp, "create_message", side_effect=AssertionError("Claude should not be called")):
            result = sp.get_variation(BODY, "Feeder", SLUG)
        self.assertEqual(result, BODY)
        self.assertEqual(sp.VARIATION_RUN_STATS["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
