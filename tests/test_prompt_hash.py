"""Test di bench.prompt_hash. Avvio: python -m unittest discover tests"""

import re
import unittest

from tokenrace import bench
from tokenrace.config import load_defaults, load_prompts

BASE = dict(max_tokens=512, temperature=0.0, seed=42, request_fields={"think": False})


def presets(lang: str) -> dict:
    target = load_defaults()["long_prompt"]["target_chars"]
    return bench.build_prompts(load_prompts()[lang], target)


class PromptHashTest(unittest.TestCase):
    def setUp(self):
        self.prompt = presets("en")["short"]
        self.h = bench.prompt_hash(self.prompt, **BASE)

    def test_format(self):
        self.assertRegex(self.h, re.compile(r"^[0-9a-f]{12}$"))

    def test_same_input_same_hash(self):
        self.assertEqual(self.h, bench.prompt_hash(self.prompt, **BASE))

    def test_every_preset_is_stable(self):
        for lang in ("en", "it"):
            for name, text in presets(lang).items():
                with self.subTest(lang=lang, preset=name):
                    self.assertEqual(bench.prompt_hash(text, **BASE),
                                     bench.prompt_hash(presets(lang)[name], **BASE))

    def test_one_word_changes_hash(self):
        self.assertNotEqual(self.h, bench.prompt_hash(self.prompt.replace("story", "tale", 1), **BASE))

    def test_language_changes_hash(self):
        self.assertNotEqual(self.h, bench.prompt_hash(presets("it")["short"], **BASE))

    def test_parameters_change_hash(self):
        for key, value in (("max_tokens", 513), ("temperature", 0.1), ("seed", 43),
                           ("request_fields", {"think": True}), ("request_fields", None)):
            with self.subTest(key=key, value=value):
                self.assertNotEqual(self.h, bench.prompt_hash(self.prompt, **{**BASE, key: value}))

    def test_request_field_order_does_not_matter(self):
        a = bench.prompt_hash(self.prompt, **{**BASE, "request_fields": {"a": 1, "b": {"x": 1, "y": 2}}})
        b = bench.prompt_hash(self.prompt, **{**BASE, "request_fields": {"b": {"y": 2, "x": 1}, "a": 1}})
        self.assertEqual(a, b)

    def test_hash_covers_the_messages_sent(self):
        # L'hash usa gli stessi messaggi che run_once invia al server
        self.assertEqual(bench.build_messages(self.prompt), [{"role": "user", "content": self.prompt}])


if __name__ == "__main__":
    unittest.main()
