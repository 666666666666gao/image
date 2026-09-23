#!/usr/bin/env python3
"""Local Ryomc Images API MCP server. No API key is bundled with this repository."""

import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

from mcp.server import MCPServer
from mcp.types import ImageContent, TextContent


BASE_URL = "https://api.ryomc.top/v1"
IMAGE_MODEL = "gpt-image-2"
CONFIG_PATH = Path.home() / ".config" / "ryomc-image" / "config.json"
OUTPUT_DIR = Path.home() / "Pictures" / "RyomcImages"
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def normalize_base_url(value):
    parsed = urllib.parse.urlsplit(value.strip().rstrip("/"))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Base URL must be HTTPS without embedded credentials.")
    if parsed.query or parsed.fragment or not parsed.path.endswith("/v1"):
        raise ValueError("Base URL must end with /v1, without a query or fragment.")
    return urllib.parse.urlunsplit(parsed)


def save_config(base_url, api_key, path=CONFIG_PATH):
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("A Ryomc user API key is required.")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump({"base_url": normalize_base_url(base_url), "api_key": api_key}, output)
        output.write("\n")
    if os.name != "nt":
        os.chmod(path, 0o600)
    return path


def load_config(path=CONFIG_PATH):
    if not path.is_file():
        raise ValueError("Ryomc Image is not configured. Run server.py configure locally.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return normalize_base_url(data["base_url"]), data["api_key"]


def read_image(path):
    file_path = Path(path).expanduser()
    media_type = IMAGE_TYPES.get(file_path.suffix.lower())
    if media_type is None:
        raise ValueError("Input image must be PNG, JPEG, or WebP.")
    return "input" + file_path.suffix.lower(), media_type, file_path.read_bytes()


def multipart_body(fields, files):
    boundary = "ryomc-" + uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    for name, filename, media_type, data in files:
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\nContent-Type: {media_type}\r\n\r\n".encode())
        body.extend(data)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def call_images_api(endpoint, data, content_type):
    base_url, api_key = load_config()
    request = urllib.request.Request(
        base_url + endpoint,
        data=data,
        headers={"Authorization": "Bearer " + api_key, "Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=240) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read(4096).decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            detail = parsed.get("error", parsed)
            if isinstance(detail, dict):
                detail = detail.get("message", str(detail))
        except json.JSONDecodeError:
            detail = body
        detail = str(detail).replace(api_key, "[redacted]")[:400]
        request_id = error.headers.get("X-Oneapi-Request-Id", "")
        raise RuntimeError(f"Ryomc HTTP {error.code}: {detail}; request id: {request_id}. No retry was attempted.") from None


def save_result(response):
    items = response.get("data", [])
    encoded = items[0].get("b64_json") if items else None
    if not encoded:
        raise ValueError("No base64 image returned; check Ryomc usage logs before retrying.")
    data = base64.b64decode(encoded, validate=True)
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        extension, mime_type = ".png", "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        extension, mime_type = ".jpg", "image/jpeg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        extension, mime_type = ".webp", "image/webp"
    else:
        raise ValueError("The image response is not PNG, JPEG, or WebP.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"ryomc-image-{uuid.uuid4().hex}{extension}"
    with path.open("xb") as output:
        output.write(data)
    return [
        TextContent(type="text", text=f"Saved image: {path.resolve()}"),
        ImageContent(type="image", data=encoded, mime_type=mime_type),
    ]


mcp = MCPServer("Ryomc Image", version="1.0.0")


@mcp.tool()
def image_generate(prompt: str, size: str = "1024x1024", quality: str = "auto") -> list[TextContent | ImageContent]:
    """Generate one image from text via Ryomc /v1/images/generations. This is a paid call; never retry automatically."""
    if not prompt.strip():
        raise ValueError("A prompt is required.")
    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "response_format": "b64_json",
    }
    response = call_images_api("/images/generations", json.dumps(payload).encode(), "application/json")
    return save_result(response)


@mcp.tool()
def image_edit(prompt: str, image_path: str, size: str = "1024x1024", quality: str = "auto", mask_path: str | None = None) -> list[TextContent | ImageContent]:
    """Edit one local image via Ryomc /v1/images/edits. Optional PNG mask selects the editable region. This is a paid call; never retry automatically."""
    if not prompt.strip():
        raise ValueError("An edit instruction is required.")
    filename, media_type, source = read_image(image_path)
    files = [("image", filename, media_type, source)]
    if mask_path is not None:
        mask_name, mask_type, mask_data = read_image(mask_path)
        if mask_type != "image/png":
            raise ValueError("Mask must be PNG.")
        files.append(("mask", mask_name, mask_type, mask_data))
    body, content_type = multipart_body(
        {"model": IMAGE_MODEL, "prompt": prompt, "n": "1", "size": size, "quality": quality, "response_format": "b64_json"},
        files,
    )
    response = call_images_api("/images/edits", body, content_type)
    return save_result(response)


@mcp.tool()
def server_info() -> dict:
    """Show Ryomc image model, routes and local setup status without exposing the API key."""
    configured = CONFIG_PATH.is_file()
    base_url = load_config()[0] if configured else BASE_URL
    return {
        "base_url": base_url,
        "model": IMAGE_MODEL,
        "routes": ["/images/generations", "/images/edits"],
        "configured": configured,
        "output_dir": str(OUTPUT_DIR),
        "note": "Each generation/edit may incur charges. Real upstream success and pricing must be checked on Ryomc.",
    }


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "configure":
        parser = argparse.ArgumentParser(description="Save a Ryomc user API key locally")
        parser.add_argument("command")
        parser.add_argument("--base-url", default=BASE_URL)
        args = parser.parse_args()
        path = save_config(args.base_url, getpass.getpass("Ryomc user API key (hidden): "))
        print(f"Saved local configuration to {path}. Do not share this file.")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
