import unittest
from types import SimpleNamespace
from claude_utils import prepare_message, message_text, create_message
from consolidate_articles import plan, repeated_body


class ModelMigrationTests(unittest.TestCase):
    def test_installed_sdk_sends_the_migration_settings(self):
        import json
        import anthropic
        import httpx
        captured = []
        def respond(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "msg_offline", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5", "content": [{"type": "text", "text": "OK"}], "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})
        with anthropic.Anthropic(api_key="offline", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(respond))) as client:
            create_message(client, model="claude-sonnet-5-5", max_tokens=32, messages=[{"role": "user", "content": "offline"}], log=lambda _: None)
        self.assertEqual(captured[0]["thinking"], {"type": "between_tools"})
        self.assertEqual(captured[0]["output_config"]["effort"], "medium")
    def test_consolidation_keeps_original_and_flattens_redirects(self):
        text = "---\ntitle: Example\n---\n" + " ".join("word" + str(i) for i in range(500))
        rows = [{"slug": "original", "date": "2026-01-01", "title": "A guide", "text": text}, {"slug": "copy", "date": "2026-02-01", "title": "A guide!", "text": text}, {"slug": "renamed", "date": "2026-03-01", "title": "Different title", "text": text}]
        self.assertEqual(plan(rows), {"copy": "original", "renamed": "original"})
        self.assertEqual(repeated_body(text, [("original", text)]), "original")

    def test_writer_and_utility_do_not_enable_default_thinking(self):
        for model, mode in (("claude-sonnet-5-5", "between_tools"), ("claude-haiku-5-5", "disabled")):
            original = {"model": model, "max_tokens": 3200, "temperature": .8}
            settings = prepare_message(original)
            self.assertEqual(settings["extra_body"]["thinking"]["type"], mode)
            self.assertEqual(settings["extra_body"]["output_config"]["effort"], "medium")
            self.assertNotIn("temperature", settings)
            self.assertIn("temperature", original)

    def test_text_extraction_skips_thinking_and_rejects_incomplete_posts(self):
        response = SimpleNamespace(content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text="Article")], stop_reason="end_turn")
        self.assertEqual(message_text(response), "Article")
        response.stop_reason = "max_tokens"
        with self.assertRaises(ValueError):
            message_text(response)

    def test_tool_research_retains_bounded_adaptive_thinking(self):
        extra = prepare_message({"model": "claude-sonnet-5-5", "tools": [{}]})["extra_body"]
        self.assertEqual(extra["thinking"]["type"], "adaptive")
        self.assertEqual(extra["output_config"]["effort"], "low")


if __name__ == "__main__":
    unittest.main()
