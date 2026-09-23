import base64
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "plugins" / "ryomc-image" / "skills" / "ryomc-image" / "scripts" / "ryomc_image.py"
spec = importlib.util.spec_from_file_location("ryomc_image", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aC1sAAAAASUVORK5CYII=")


class ImageToolTests(unittest.TestCase):
    def test_base_url_and_secret_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            module.save_config("https://api.ryomc.top/v1/", "sk-test", path)
            self.assertEqual(module.load_config(path), {
                "base_url": "https://api.ryomc.top/v1",
                "api_key": "sk-test",
            })
            self.assertNotIn("sk-test", str(path))
        with self.assertRaises(ValueError):
            module.normalize_base_url("http://api.ryomc.top/v1")

    def test_text_to_image_request(self):
        payload = module.make_payload("a blue circle", "gpt-6-sol", "low")
        self.assertEqual(payload["model"], "gpt-6-sol")
        self.assertEqual(payload["tools"][0]["model"], "gpt-image-2")
        self.assertEqual(payload["tool_choice"], {"type": "image_generation"})
        self.assertFalse(payload["store"])
        self.assertFalse(payload["stream"])

    def test_redirect_is_rejected_to_keep_key_on_configured_host(self):
        self.assertIsNone(module.NoRedirect().redirect_request(
            None, None, 302, "Found", {}, "https://another.example/v1/responses"
        ))

    def test_image_edit_request(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "source.png"
            image.write_bytes(PNG)
            payload = module.make_payload("Make it green", "gpt-6-astra", "low", image)
        self.assertEqual(payload["tools"][0]["action"], "edit")
        source = payload["input"][0]["content"][1]
        self.assertEqual(source["type"], "input_image")
        self.assertEqual(base64.b64decode(source["image_url"].split(",", 1)[1]), PNG)

    def test_response_saves_image_and_does_not_reuse_filename(self):
        response = {"status": "completed", "output": [
            {"type": "image_generation_call", "result": base64.b64encode(PNG).decode("ascii")}
        ]}
        with tempfile.TemporaryDirectory() as folder:
            first = module.save_image(response, Path(folder))
            second = module.save_image(response, Path(folder))
            self.assertEqual(first.read_bytes(), PNG)
            self.assertNotEqual(first, second)

    def test_network_request_uses_configured_key_and_endpoint(self):
        response = {"status": "completed", "output": [
            {"type": "image_generation_call", "result": base64.b64encode(PNG).decode("ascii")}
        ]}

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

        class FakeOpener:
            def open(self, request, timeout):
                self_request["request"] = request
                self_request["timeout"] = timeout
                return FakeResponse(json.dumps(response).encode("utf-8"))

        self_request = {}
        config = {"base_url": "https://api.ryomc.top/v1", "api_key": "sk-test"}
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(module.urllib.request, "build_opener", return_value=FakeOpener()) as mocked:
                path = module.generate("A cat", "gpt-6-sol", "low", None, Path(folder), config)
            self.assertEqual(path.read_bytes(), PNG)
        request = self_request["request"]
        self.assertEqual(request.full_url, "https://api.ryomc.top/v1/responses")
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-test")
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "gpt-6-sol")
        self.assertEqual(payload["tools"][0]["model"], "gpt-image-2")
        self.assertEqual(self_request["timeout"], 240)
        self.assertIs(mocked.call_args.args[0], module.NoRedirect)

    def test_cli_passes_current_chat_model_to_request(self):
        config = {"base_url": "https://api.ryomc.top/v1", "api_key": "sk-test"}
        with patch.object(module, "load_config", return_value=config), \
                patch.object(module, "generate", return_value=Path("image.png")) as generate, \
                patch("sys.stdout", new_callable=io.StringIO):
            result = module.main(["generate", "--prompt", "A cat", "--model", "gpt-6-sol"])
        self.assertEqual(result, 0)
        self.assertEqual(generate.call_args.args[0:3], ("A cat", "gpt-6-sol", "low"))

    def test_failed_or_invalid_response_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for response in (
                {"status": "failed"},
                {"status": "completed", "output": []},
                {"status": "completed", "output": [{"type": "image_generation_call", "result": base64.b64encode(b"bad").decode()}]},
            ):
                with self.assertRaises(ValueError):
                    module.save_image(response, directory)
            self.assertEqual(list(directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
