"""LLM backend abstraction: API or Claude Code CLI."""

import json
import subprocess


def call_claude_code(prompt: str, system: str = "") -> str:
    """Call Claude Code CLI as a subprocess and return the text response."""
    full_prompt = prompt
    if system:
        full_prompt = f"{system}\n\n{prompt}"

    result = subprocess.run(
        ["claude", "-p", full_prompt, "--output-format", "text"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude Code CLI failed: {result.stderr}")
    return result.stdout.strip()


def call_api(prompt: str, system: str = "", max_tokens: int = 4096) -> str:
    """Call the Anthropic API and return the text response."""
    import anthropic

    client = anthropic.Anthropic()
    kwargs: dict = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text


def extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text)
