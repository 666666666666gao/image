import base64
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from mcp import Client, StdioServerParameters


SERVER = Path(__file__).resolve().parents[1] / "plugins" / "ryomc-image" / "server.py"
spec = importlib.util.spec_from_file_location("ryomc_image_server", SERVER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aC1sAAAAASUVORK5CYII=")
IMAGE_RESPONSE = {"data": [{"b64_json": base64.b64encode(PNG).decode()}]}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class FakeOpener:
    def __init__(self):
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return FakeResponse(json.dumps(IMAGE_RESPONSE).encode())


class ImageServerTests(unittest.TestCase):
    def test_config_stays_local_and_url_requires_https(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            module.save_config("https://api.ryomc.top/v1/", "sk-test", path)
            self.assertEqual(module.load_config(path), ("https://api.ryomc.top/v1", "sk-test"))
        with self.assertRaises(ValueError):
            module.normalize_base_url("http://api.ryomc.top/v1")

    def test_generate_uses_images_api_and_returns_preview_and_saved_file(self):
        opener = FakeOpener()
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(module, "load_config", return_value=(module.BASE_URL, "sk-test")), \
                patch.object(module, "OUTPUT_DIR", Path(folder)), \
                patch.object(module.urllib.request, "build_opener", return_value=opener):
            content = module.image_generate("a blue circle")
            saved = Path(content[0].text.removeprefix("Saved image: "))
            self.assertEqual(saved.read_bytes(), PNG)
            self.assertEqual(content[1].mime_type, "image/png")
            self.assertEqual(base64.b64decode(content[1].data), PNG)
        request, timeout = opener.requests[0]
        self.assertEqual(request.full_url, "https://api.ryomc.top/v1/images/generations")
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-test")
        self.assertEqual(timeout, 240)
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertEqual(payload["response_format"], "b64_json")
        self.assertEqual(payload["n"], 1)
        self.assertEqual(len(opener.requests), 1)

    def test_edit_sends_multipart_image_to_edits_route(self):
        opener = FakeOpener()
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.png"
            source.write_bytes(PNG)
            with patch.object(module, "load_config", return_value=(module.BASE_URL, "sk-test")), \
                    patch.object(module, "OUTPUT_DIR", Path(folder)), \
                    patch.object(module.urllib.request, "build_opener", return_value=opener):
                module.image_edit("make it green", str(source))
        request, _ = opener.requests[0]
        self.assertEqual(request.full_url, "https://api.ryomc.top/v1/images/edits")
        self.assertIn("multipart/form-data", request.get_header("Content-type"))
        self.assertIn(b'name="image"', request.data)
        self.assertIn(b'name="model"', request.data)
        self.assertIn(b"gpt-image-2", request.data)
        self.assertIn(PNG, request.data)
        self.assertEqual(len(opener.requests), 1)

    def test_no_redirect_and_no_file_on_missing_image(self):
        self.assertIsNone(module.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://other.example"))
        with tempfile.TemporaryDirectory() as folder, patch.object(module, "OUTPUT_DIR", Path(folder)):
            with self.assertRaises(ValueError):
                module.save_result({"data": [{"url": "https://example.com/image.png"}]})
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_server_registers_expected_tools(self):
        names = {tool.name for tool in module.mcp._tool_manager.list_tools()}
        self.assertEqual(names, {"image_generate", "image_edit", "server_info"})
        self.assertNotIn("api_key", module.server_info())

    def test_http_error_keeps_key_private_and_does_not_retry(self):
        error_body = io.BytesIO(b'{"error":{"message":"denied for sk-test"}}')
        error = urllib.error.HTTPError("https://api.ryomc.top/v1/images/generations", 403, "Forbidden", {"X-Oneapi-Request-Id": "req-123"}, error_body)

        class RejectingOpener:
            def __init__(self):
                self.calls = 0

            def open(self, request, timeout):
                self.calls += 1
                raise error

        opener = RejectingOpener()
        with patch.object(module, "load_config", return_value=(module.BASE_URL, "sk-test")), \
                patch.object(module.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(RuntimeError) as caught:
                module.image_generate("a blue circle")
        self.assertIn("HTTP 403", str(caught.exception))
        self.assertIn("req-123", str(caught.exception))
        self.assertNotIn("sk-test", str(caught.exception))
        self.assertEqual(opener.calls, 1)

    def test_mcp_client_can_call_server_info(self):
        async def check():
            async with Client(module.mcp) as client:
                tools = await client.list_tools()
                self.assertEqual({tool.name for tool in tools.tools}, {"image_generate", "image_edit", "server_info"})
                result = await client.call_tool("server_info", {})
                self.assertIn("gpt-image-2", result.content[0].text)

        asyncio.run(check())

    def test_mcp_client_receives_image_content(self):
        async def check():
            with tempfile.TemporaryDirectory() as folder, \
                    patch.object(module, "OUTPUT_DIR", Path(folder)), \
                    patch.object(module, "call_images_api", return_value=IMAGE_RESPONSE):
                async with Client(module.mcp) as client:
                    result = await client.call_tool("image_generate", {"prompt": "a blue circle"})
                    self.assertEqual([item.type for item in result.content], ["text", "image"])
                    self.assertEqual(base64.b64decode(result.content[1].data), PNG)

        asyncio.run(check())

    def test_stdio_server_connects_without_a_key(self):
        async def check():
            command = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
            async with Client(command) as client:
                result = await client.call_tool("server_info", {})
                self.assertIn("gpt-image-2", result.content[0].text)

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
