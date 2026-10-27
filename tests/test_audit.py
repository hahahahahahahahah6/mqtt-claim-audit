import contextlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from mqtt_claim_audit.audit import audit, claims, evidence, normalize, pattern, MQTT, NOMQTT
from mqtt_claim_audit.__main__ import main

ROOT = Path(__file__).resolve().parents[1]
GOOD = 'import paho.mqtt.client as mqtt\nclient = mqtt.Client()\nclient.publish("t", "v")\n'

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main([str(self.root)] + list(args))
        return code, out.getvalue()

    def case(self, source, claim="mqtt support", severity=None):
        self.put("README.md", claim)
        if source is not None:
            self.put("app.py", source)
        result = audit(self.root)
        self.assertEqual(result["findings"], [] if severity is None else [dict(rule="documented-mqtt-claim-false", severity=severity, message="Documented transport capability lacks production creation and publish/subscribe evidence.")])
        self.assertEqual(self.run_cli()[0], 2 if severity == "HIGH" else 0)
        return result

    def test_01_good_publish(self):
        self.case(GOOD)

    def test_02_subscribe_alias(self):
        self.case('import paho.mqtt.client as mc\nc = mc.Client()\nc.subscribe("t")', "mqtt client")

    def test_03_from_import(self):
        self.case('from paho.mqtt.client import Client\nc = Client()\nc.publish("t")', "uses mqtt")

    def test_04_chained(self):
        self.case('import paho.mqtt.client as mqtt\nmqtt.Client().publish("t")', "mqtt broker")

    def test_05_self_attribute(self):
        self.case('from mqtt import Client\nclass App:\n def go(self):\n  self.client = Client()\n  self.client.subscribe("t")', "mqtt interface")

    def test_06_from_alias(self):
        self.case('from paho.mqtt.client import Client as MQTTClient\nc = MQTTClient()\nc.publish("t")', "supports mqtt")

    def test_07_bare_import(self):
        self.case('import paho.mqtt.client', severity="HIGH")

    def test_08_creation_only(self):
        self.case('from mqtt import Client\nc = Client()', severity="HIGH")

    def test_09_publish_only(self):
        self.case('def publish(x): print(x)\npublish("t")\nhelper.publish("t")', severity="HIGH")

    def test_10_subscribe_only(self):
        self.case('helper.subscribe("t")', severity="HIGH")

    def test_11_connect_only(self):
        self.case('from mqtt import Client\nclient = Client()\nclient.connect("host")', severity="HIGH")

    def test_12_callback_only(self):
        self.case('from mqtt import Client\nclient = Client()\nclient.on_message = lambda *a: None', severity="HIGH")

    def test_13_websocket_only(self):
        self.case('import websockets\nwebsockets.serve(handler, "localhost", 80)', severity="HIGH")

    def test_14_module_boundary(self):
        self.put("other.py", 'client.publish("t")')
        self.case('from mqtt import Client\nclient = Client()', severity="HIGH")

    def test_15_negative(self):
        self.put("README.md", "no mqtt support")
        self.put("app.py", GOOD)
        findings = audit(self.root)["findings"]
        self.assertEqual([(f["rule"], f["severity"]) for f in findings], [("documented-no-mqtt-claim-false", "HIGH")])
        self.assertEqual(self.run_cli()[0], 2)

    def test_16_no_claim(self):
        self.case(GOOD, "A useful utility.")

    def test_17_bare_noun(self):
        self.case('import mqtt', "the mqtt chapter explains messaging")

    def test_18_rest(self):
        self.case('@app.get("/")\ndef api(): return {"ok": True}', "rest api")

    def test_19_websocket(self):
        self.case('websockets.serve(handler)', "websocket server")

    def test_20_grpc(self):
        self.case('channel = grpc.insecure_channel("host")\nstub = Stub(channel)', "grpc api")

    def test_21_no_source(self):
        self.case(None, severity="HIGH")
        self.put("README.md", "no mqtt support")
        self.assertEqual(audit(self.root)["findings"], [])

    def test_22_test_only(self):
        self.put("tests/evidence.py", GOOD)
        self.case(None, severity="MEDIUM")
        self.assertEqual(self.run_cli("--fail-on", "MEDIUM")[0], 2)

    def test_23_fences_inline(self):
        self.case(None, '```text\nmqtt support\n```')
        self.put("README.md", 'inline `mqtt support`')
        self.assertEqual(audit(self.root)["findings"][0]["severity"], "HIGH")

    def test_24_negation(self):
        self.assertEqual(claims("does not support mqtt"), (False, True))
        self.assertEqual(claims("doesn't support mqtt"), (False, True))

    def test_25_self_audit(self):
        result = audit(ROOT)
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["claims"], dict(positive=False, negative=False))
        paths = [ROOT / "README.md"] + list(ROOT.glob("**/docs/**/*.md"))
        for path in paths:
            self.assertIsNone(pattern(MQTT + NOMQTT).search(normalize(path.read_text())), str(path))

    def test_26_cli(self):
        self.put("docs/assertion.md", "mqtt support")
        self.assertEqual(self.run_cli("--ignore", "docs/*")[0], 0)
        code, output = self.run_cli("--json")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)["verdict"], "FAIL")
        self.put("app.py", GOOD)
        self.assertIn("app.py", self.run_cli("--verbose")[1])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit) as cm:
                main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), "0.1.0")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.root / "absent")]), 1)
            with self.assertRaises(SystemExit) as cm:
                main(["--unknown"])
        self.assertEqual(cm.exception.code, 1)

    def test_27_env_guard(self):
        self.put(".env", "ENV_READ_GUARD_MARKER")
        original = Path.read_text
        def guarded(path, *args, **kwargs):
            self.assertNotEqual(path.name, ".env")
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", guarded):
            audit(self.root)
            audit(ROOT / "tests" / "fixtures")

    def test_28_packaging(self):
        for path in list((ROOT / "mqtt_claim_audit").glob("*.py")) + list((ROOT / "tests").rglob("*.py")) + [ROOT / "README.md"]:
            self.assertIsNone(re.search(r"\b" + "py" + r"thon\b", path.read_text()), str(path))
        config = (ROOT / "pyproject.toml").read_text()
        self.assertIn('license = "MIT"', config)
        self.assertIn('setuptools>=77', config)
        self.assertIn('recursive-include tests', (ROOT / "MANIFEST.in").read_text())

    def test_29_other_non_evidence(self):
        for source in ['from mqtt import Client\nc=Client()\nc.loop_start()\nc.loop_forever()', 'url="mqtt://host"\nqos=1\nretain=True', 'Client(transport="websockets")', 'def mqtt_handler(): return "mqtt"', '# mqtt.Client().publish("t")', 's="mqtt.Client().publish()"', 'from notmqtt import Client\nc=Client()\nc.publish("t")', 'from mqtt import Client\nc=Client()\nother.publish("t")']:
            with self.subTest(source=source):
                self.assertFalse(evidence(source))

    def test_30_import_and_assignment_forms(self):
        for source in ['import paho.mqtt.client\nc=paho.mqtt.client.Client()\nc.subscribe("t")', 'import mqtt\napp.client=mqtt.Client()\napp.client.publish("t")', 'from mqtt import Client\nc: object = Client()\nc.subscribe("t")']:
            self.assertTrue(evidence(source))

    def test_31_scope(self):
        self.put("README.md", "mqtt support")
        for name in ["fixtures/app.py", "docs/app.py", "examples/app.py"]:
            self.put(name, GOOD)
        self.assertEqual(audit(self.root)["findings"][0]["severity"], "HIGH")
        self.put("one_test.py", GOOD)
        self.assertEqual(audit(self.root)["findings"][0]["severity"], "MEDIUM")

    def test_32_phrase_normalization(self):
        for phrase in MQTT:
            self.assertEqual(claims(phrase.upper().replace(" ", "-")), (True, False))
        for phrase in NOMQTT:
            self.assertEqual(claims(phrase), (False, True))
        self.assertEqual(claims("mqtt\nsupport"), (True, False))
        self.assertEqual(claims("mqtt\n\nsupport"), (False, False))
        self.assertEqual(claims("amqtt supportively"), (False, False))

    def test_33_negative_docs_asymmetry(self):
        self.put("tests/docs/note.md", "without mqtt")
        self.put("app.py", GOOD)
        self.assertEqual(audit(self.root)["findings"][0]["severity"], "HIGH")

    def test_34_symlinks(self):
        self.put("README.md", "mqtt support")
        outside = self.root.parent / (self.root.name + "_outside.py")
        outside.write_text(GOOD)
        self.addCleanup(outside.unlink)
        (self.root / "linked.py").symlink_to(outside)
        self.assertEqual(audit(self.root)["evidence"], [])

    def test_35_two_families(self):
        self.assertEqual(claims("no mqtt support. Also mqtt client."), (True, True))

if __name__ == "__main__":
    unittest.main()
