"""Übersetzungen: de.json und en.json deckungsgleich, Fehlermeldungen und Meldungstexte vorhanden."""
import json
import os
import re
import unittest

BASE = os.path.join(os.path.dirname(__file__), "..", "custom_components", "water_softener_refill_sensor")


def _load(lang):
    with open(os.path.join(BASE, "translations", f"{lang}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _keys(node, prefix=""):
    for key, value in node.items():
        if isinstance(value, dict):
            yield from _keys(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}"


def _source():
    text = ""
    for name in os.listdir(BASE):
        if name.endswith(".py"):
            with open(os.path.join(BASE, name), encoding="utf-8") as fh:
                text += fh.read()
    return text


class Translations(unittest.TestCase):
    def test_same_keys(self):
        self.assertEqual(sorted(_keys(_load("de"))), sorted(_keys(_load("en"))))

    def test_same_placeholders(self):
        de, en = _load("de"), _load("en")
        flat_en = dict(zip(_keys(en), _values(en)))
        for key, value in zip(_keys(de), _values(de)):
            self.assertEqual(set(re.findall(r"{(\w+)}", value)), set(re.findall(r"{(\w+)}", flat_en[key])), key)

    def test_every_service_error_has_a_text(self):
        used = set(re.findall(r'service_error\(\s*"(\w+)"', _source()))
        self.assertTrue(used)
        for lang in ("de", "en"):
            self.assertEqual(used, set(_load(lang)["exceptions"]), lang)

    def test_unit_notification_text(self):
        for lang in ("de", "en"):
            self.assertEqual(set(_load(lang)["issues"]["unknown_unit"]), {"title", "description"})

    def test_config_errors_are_reachable(self):
        source = _source()
        for lang in ("de", "en"):
            data = _load(lang)
            for section in ("config", "options"):
                for key in data[section].get("error", {}):
                    self.assertIn(f'"{key}"', source, f"{lang}: {section}.error.{key}")
            # Fehler, die der Optionsfluss nicht erzeugen kann, stehen dort nicht
            self.assertNotIn("stock_too_large", data["options"]["error"])


def _values(node):
    for value in node.values():
        if isinstance(value, dict):
            yield from _values(value)
        else:
            yield value


if __name__ == "__main__":
    unittest.main()
