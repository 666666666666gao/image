#!/usr/bin/env python3
"""Generate or edit one image through a configured Ryomc-compatible Responses API."""

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


CONFIG_PATH = Path.home() / ".config" / "ryomc-image" / "config.json"
DEFAULT_BASE_URL = "https://api.ryomc.top/v1"
DEFAULT_MODEL = "gpt-6-astra"
IMAGE_MODEL = "gpt-image-2.5-sunburst"
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def normalize_base_url(value):
    parsed = urllib.parse.urlsplit(value.strip().rstrip("/"))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Base URL must be an HTTPS address without embedded credentials.")
    if parsed.query or parsed.fragment or not parsed.path.endswith("/v1"):
        raise ValueError("Base URL must end with /v1 and have no query or fragment.")
    return urllib.parse.urlunsplit(parsed)


def save_config(base_url, model, key, path=CONFIG_PATH):
    data = {"base_url": normalize_base_url(base_url), "model": model.strip(), "api_key": key.strip()}
    if not data["model"] or not data["api_key"]:
        raise ValueError("A model and API key are required.")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(data, output)
        output.write("\n")
    if os.name != "nt":
        os.chmod(path, 0o600)
    return path


def load_config(path=CONFIG_PATH):
    if not path.is_file():
        raise ValueError("Not configured. Run the configure command locally first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "base_url": normalize_base_url(data["base_url"]),
        "model": data["model"],
        "api_key": data["api_key"],
    }


def make_payload(prompt, model, quality, input_image=None):
    if not prompt.strip():
        raise ValueError("An image description is required.")
    tool = {
        "type": "image_generation",
        "model": IMAGE_MODEL,
        "quality": quality,
        "output_format": "png",
    }
    payload = {
        "model": model,
        "input": "Generate exactly one image. " + prompt,
        "tools": [tool],
        "tool_choice": {"type": "image_generation"},
        "stream": False,
        "store": False,
    }
    if input_image is not None:
        path = Path(input_image)
        media_type = IMAGE_TYPES.get(path.suffix.lower())
        if media_type is None:
            raise ValueError("Input image must be PNG, JPEG, or WebP.")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        payload["input"] = [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Edit the provided image. " + prompt},
                {"type": "input_image", "image_url": f"data:{media_type};base64,{encoded}"},
            ],
        }]
        tool["action"] = "edit"
    return payload


def save_image(response, directory):
    if response.get("status") != "completed":
        raise ValueError("The response did not complete. Check your usage log before retrying.")
    images = [
        item["result"] for item in response.get("output", [])
        if item.get("type") == "image_generation_call" and item.get("result")
    ]
    if not images:
        raise ValueError("No image was returned. Check your usage log before retrying.")
    data = base64.b64decode(images[0], validate=True)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("The returned image is not PNG.")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"ryomc-image-{uuid.uuid4().hex}.png"
    with path.open("xb") as output:
        output.write(data)
    return path.resolve()


def generate(prompt, quality, input_image, output_dir, config):
    payload = make_payload(prompt, config["model"], quality, input_image)
    request = urllib.request.Request(
        config["base_url"] + "/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + config["api_key"],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirect)
    with opener.open(request, timeout=240) as result:
        response = json.load(result)
    return save_image(response, output_dir)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure", help="Save this user's site key locally")
    configure.add_argument("--base-url", default=DEFAULT_BASE_URL)
    configure.add_argument("--model", default=DEFAULT_MODEL)
    create = commands.add_parser("generate", help="Generate or edit one image")
    create.add_argument("--prompt", required=True)
    create.add_argument("--input-image", type=Path)
    create.add_argument("--quality", choices=["low", "medium", "high"], default="low")
    create.add_argument("--output-dir", type=Path, default=Path.home() / "Pictures" / "RyomcImages")
    args = parser.parse_args(argv)

    try:
        if args.command == "configure":
            key = getpass.getpass("Your New API key (hidden): ")
            path = save_config(args.base_url, args.model, key)
            print(f"Saved configuration to {path}. Do not share this file.")
        else:
            path = generate(
                args.prompt, args.quality, args.input_image, args.output_dir, load_config()
            )
            print(json.dumps({"image_path": str(path)}, ensure_ascii=False))
    except urllib.error.HTTPError as error:
        print(f"HTTP {error.code}. No retry was attempted; check the site's usage log.", file=sys.stderr)
        return 1
    except (ValueError, OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
