---
name: ryomc-image
description: Generate or edit images through the user's configured Ryomc New API key when they ask for Ryomc Image, the Ryomc image tool, or image generation through their relay.
---

# Ryomc Image

Use this skill for text-to-image and image-to-image requests routed through Ryomc. The bundled Python 3.10+ script uses the Responses API image generation tool; do not substitute Codex's built-in image generator when the user requested Ryomc billing.

The script is at `scripts/ryomc_image.py` relative to this SKILL.md. Resolve that path on the user's machine. Run its `generate` command with `--prompt` and, for editing, `--input-image` pointing to a local PNG, JPEG, or WebP. Use `--quality low|medium|high` only when the user specifies or it matters. The script prints JSON containing the absolute `image_path`; display the result in the conversation using Markdown image syntax with that absolute path.

If configuration is missing, ask the user to run the script's `configure` command in their own terminal once. It prompts for their **New API user key**, not a CPA management key. Never request the key in chat, inspect the saved key, or place it in a command line. The script reads it internally from the user's private config file.

For editing, use the attached image's local path when available. If the image has no accessible local path, ask the user to attach it as a local file or provide its path. Do not invent a path.

Each invocation submits one billable image request and does not retry. If it fails, report the error and check whether the request was charged before resubmitting. If the user requests multiple images, confirm the intended count and cost before separate calls.
