"""Claude Code CLI–backed agent loop for ontology-driven root cause analysis.

Implements the Slide 5.4 flow without calling the Anthropic API directly.
Each turn spawns a `claude -p` subprocess with `--tools ""`, no session
persistence, and a sanitized working directory, so the agent runs in an
isolated process that cannot read the project files or leak context.

Protocol:
  - System prompt instructs Claude to respond with exactly one JSON
    action per turn (list_parent_causes / compare_metric_round /
    report_root_cause), wrapped in a ```json code fence.
  - The orchestrator parses the JSON, executes the tool locally (via
    src.ontoprobe.rootcause.tools), and rebuilds the full conversation
    history as a single stateless prompt for the next turn.
  - Loop terminates on report_root_cause, parse failure, or MAX_ITERATIONS.

Both system prompts expose metrics only as opaque IDs (m_101…m_1NN) with
neutral descriptions, so the no-ontology baseline cannot lean on friendly
names like "total_discount" to infer causal structure.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ontoprobe.rootcause.tools import (
    METRIC_ALIAS,
    CausalFormat,
    OntologyMode,
    build_causal_payload,
    compare_metric_round,
    list_parent_causes,
    metric_catalog,
)

MAX_ITERATIONS = 15
DEFAULT_MODEL = "sonnet"
DEFAULT_SANDBOX = Path("/tmp")
TURN_TIMEOUT_SEC = 180
MAX_CLAUDE_RETRIES = 3
RETRY_BACKOFF_SEC = 2.0


def _catalog_block() -> str:
    return "\n".join(
        f"  - {m['metric_id']}: {m['description']}" for m in metric_catalog()
    )


_CATALOG_BLOCK = _catalog_block()


SYSTEM_PROMPT_WITH_ONTOLOGY = f"""You are a data analyst agent performing ontology-driven root cause analysis on an e-commerce metrics warehouse.

An anomaly has been detected on a business metric. You do NOT have access to any built-in tools (no Bash, no Read, no search). Instead, the orchestrator exposes three virtual tools that you invoke by emitting a JSON action. Each of your turns MUST contain exactly ONE JSON object in a ```json ... ``` fenced code block, with this shape:

{{"action": "<name>", "args": {{ ... }}}}

Valid actions:

  1. list_parent_causes
       args: {{"concept_label": "<ontology concept label, e.g. 'Revenue'>"}}
       Returns upstream causes of the given concept from the domain ontology.
       Each parent includes the rule label, expected magnitude, description,
       and — when available — the opaque metric_id you can query directly.

  2. compare_metric_round
       args: {{"metric_id": "<opaque id, e.g. 'm_101'>",
               "round_a": "<id>", "round_b": "<id>"}}
       Returns the round-over-round delta of the metric.

  3. report_root_cause
       args: {{"root_cause_concept": "<ontology concept>",
               "evidence_chain": ["step 1", "step 2", ...],
               "recommendation": "<concrete next action>"}}
       Terminates the investigation.

Available metric catalog (both the with-ontology and no-ontology agents see this same list; metric ids are opaque and neutral by design):
{_CATALOG_BLOCK}

Procedure:
  (a) Verify the reported anomaly with compare_metric_round.
  (b) Call list_parent_causes on the anomaly concept to enumerate upstream candidates from the ontology.
  (c) For each candidate with a metric_id, call compare_metric_round to see whether it moved in the direction the rule predicts.
  (d) If a candidate moved strongly in the expected direction, recurse: list_parent_causes on that candidate and repeat.
  (e) Call report_root_cause with the ordered evidence chain and a concrete next-round recommendation.

Rules:
  - Be efficient. Prioritize the largest observed delta. Do not query every branch.
  - You may write one short sentence of reasoning BEFORE the JSON block; the block must be last.
  - Exactly ONE action per turn.
  - Do not ask clarifying questions. Decide and act.
"""


SYSTEM_PROMPT_WITHOUT_ONTOLOGY = f"""You are a data analyst agent performing root cause analysis on an e-commerce metrics warehouse.

An anomaly has been detected on a business metric. You have NO access to any domain ontology, causal graph, or list of expected causal relationships. You also do NOT have built-in tools (no Bash, no Read, no search). The orchestrator exposes two virtual tools that you invoke by emitting a JSON action. Each of your turns MUST contain exactly ONE JSON object in a ```json ... ``` fenced code block, with this shape:

{{"action": "<name>", "args": {{ ... }}}}

Valid actions:

  1. compare_metric_round
       args: {{"metric_id": "<opaque id, e.g. 'm_101'>",
               "round_a": "<id>", "round_b": "<id>"}}
       Returns the round-over-round delta of the metric.

  2. report_root_cause
       args: {{"root_cause_concept": "<concept>",
               "evidence_chain": ["step 1", "step 2", ...],
               "recommendation": "<concrete next action>"}}
       Terminates the investigation.

Available metric catalog (metric ids are opaque and neutral by design — you must decide which are plausibly related to the anomaly using your own general e-commerce knowledge of what each description means):
{_CATALOG_BLOCK}

Procedure:
  (a) Verify the reported anomaly with compare_metric_round.
  (b) Based on your own knowledge of e-commerce, decide which other metrics might plausibly explain the movement, and check them.
  (c) Call report_root_cause once you are confident you know the root cause.

Rules:
  - Be efficient. Prioritize the largest observed delta. Do not query every metric blindly.
  - You may write one short sentence of reasoning BEFORE the JSON block; the block must be last.
  - Exactly ONE action per turn.
  - Do not ask clarifying questions. Decide and act.
"""


SYSTEM_PROMPT_PUSH_TEMPLATE = """You are a data analyst agent performing root cause analysis on an e-commerce metrics warehouse.

An anomaly has been detected on a business metric. You do NOT have access to any built-in tools (no Bash, no Read, no search). The orchestrator exposes two virtual tools that you invoke by emitting a JSON action. Each of your turns MUST contain exactly ONE JSON object in a ```json ... ``` fenced code block, with this shape:

{{"action": "<name>", "args": {{ ... }}}}

Valid actions:

  1. compare_metric_round
       args: {{"metric_id": "<opaque id>",
               "round_a": "<id>", "round_b": "<id>"}}
       Returns the round-over-round delta of the metric.

  2. report_root_cause
       args: {{"root_cause_concept": "<concept>",
               "evidence_chain": ["step 1", "step 2", ...],
               "recommendation": "<concrete next action>"}}
       Terminates the investigation.

{info_block}

Procedure:
  (a) Verify the reported anomaly with compare_metric_round.
  (b) Use the metric catalog and causal relationship information above to decide which upstream metrics to check.
  (c) If a candidate moved strongly in the direction the rule predicts, recurse: check its own upstream causes.
  (d) Call report_root_cause with an ordered evidence chain and a concrete next-round recommendation.

Rules:
  - Be efficient. Prioritize the largest observed delta. Do not query every metric blindly.
  - You may write one short sentence of reasoning BEFORE the JSON block; the block must be last.
  - Exactly ONE action per turn.
  - Do not ask clarifying questions. Decide and act.
"""


def _format_rules_json(rules: list[dict[str, Any]]) -> str:
    return json.dumps({"causal_rules": rules}, ensure_ascii=False, indent=2)


def _format_rules_prose(rules: list[dict[str, Any]]) -> str:
    lines = ["Causal relationships known in this domain:"]
    for r in rules:
        cause_mid = f" ({r['cause_metric_id']})" if r["cause_metric_id"] else ""
        effect_mid = f" ({r['effect_metric_id']})" if r["effect_metric_id"] else ""
        mag = (
            f" Expected magnitude: {r['expected_magnitude']}."
            if r.get("expected_magnitude")
            else ""
        )
        lines.append(
            f'- {r["cause_concept"]}{cause_mid} drives '
            f'{r["effect_concept"]}{effect_mid}: '
            f'"{r["rule_label"]}".{mag}'
        )
        lines.append(f"    {r['description']}")
    return "\n".join(lines)


def _format_rules_dbt_meta(rules: list[dict[str, Any]]) -> str:
    parents_by_metric: dict[str, list[dict[str, Any]]] = {}
    for r in rules:
        eid = r["effect_metric_id"]
        if eid:
            parents_by_metric.setdefault(eid, []).append(r)

    lines: list[str] = []
    for m in metric_catalog():
        mid = m["metric_id"]
        lines.append(f"  - {mid}: {m['description']}")
        if mid in parents_by_metric:
            lines.append("      causal_parents (from domain knowledge):")
            for r in parents_by_metric[mid]:
                cm = f" ({r['cause_metric_id']})" if r["cause_metric_id"] else ""
                mag = (
                    f" (expected: {r['expected_magnitude']})"
                    if r.get("expected_magnitude")
                    else ""
                )
                lines.append(
                    f"        * {r['cause_concept']}{cm} — "
                    f'"{r["rule_label"]}"{mag}'
                )
    return "\n".join(lines)


def build_push_prompt(causal_format: CausalFormat) -> str:
    rules = build_causal_payload()

    if causal_format == CausalFormat.JSON_PUSH:
        info_block = (
            f"Available metric catalog (opaque ids, neutral descriptions):\n"
            f"{_CATALOG_BLOCK}\n\n"
            f"Causal rules (pre-computed from the domain knowledge base):\n\n"
            f"```json\n{_format_rules_json(rules)}\n```"
        )
    elif causal_format == CausalFormat.PROSE_PUSH:
        info_block = (
            f"Available metric catalog (opaque ids, neutral descriptions):\n"
            f"{_CATALOG_BLOCK}\n\n"
            f"{_format_rules_prose(rules)}"
        )
    elif causal_format == CausalFormat.DBT_META:
        info_block = (
            "Available metric catalog (each metric is annotated with its "
            "upstream causal parents from domain knowledge, mirroring dbt "
            "Semantic Layer meta fields):\n"
            f"{_format_rules_dbt_meta(rules)}"
        )
    else:
        raise ValueError(
            f"build_push_prompt only handles push formats, got {causal_format}"
        )

    return SYSTEM_PROMPT_PUSH_TEMPLATE.format(info_block=info_block)


@dataclass
class AgentTrace:
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    final_report: dict[str, Any] | None = None
    iterations: int = 0
    stopped_reason: str = ""
    assistant_raw: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0


JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
JSON_FALLBACK_RE = re.compile(r"(\{[^{}]*\"action\"[^{}]*\})", re.DOTALL)


def _parse_action(text: str) -> dict[str, Any] | None:
    m = JSON_BLOCK_RE.search(text)
    if m is None:
        m = JSON_FALLBACK_RE.search(text)
    if m is None:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _render_history(history: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for turn in history:
        role = turn["role"]
        content = turn["content"]
        if role == "user":
            lines.append(f"=== ORCHESTRATOR ===\n{content}")
        elif role == "assistant":
            lines.append(f"=== YOUR PREVIOUS RESPONSE ===\n{content}")
        elif role == "tool_result":
            lines.append(f"=== TOOL RESULT ===\n{content}")
    lines.append(
        "=== ORCHESTRATOR ===\n"
        "Emit the next JSON action now (inside a ```json code fence). "
        "If you have enough evidence, call report_root_cause to finish."
    )
    return "\n\n".join(lines)


def _claude_call(
    prompt: str, model: str, cwd: Path, system_prompt: str
) -> tuple[str, float]:
    cmd = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--tools",
        "",
        "--model",
        model,
        "--no-session-persistence",
        "--system-prompt",
        system_prompt,
    ]
    last_err: str = ""
    for attempt in range(MAX_CLAUDE_RETRIES):
        try:
            completed = subprocess.run(
                cmd,
                input=prompt,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=TURN_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired as e:
            last_err = f"timeout after {TURN_TIMEOUT_SEC}s"
            time.sleep(RETRY_BACKOFF_SEC * (attempt + 1))
            continue

        if completed.returncode != 0:
            last_err = (
                f"exit {completed.returncode}: "
                f"{completed.stderr[:300] or completed.stdout[:300] or '(empty)'}"
            )
            time.sleep(RETRY_BACKOFF_SEC * (attempt + 1))
            continue

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as e:
            last_err = f"json decode: {e}; stdout={completed.stdout[:300]}"
            time.sleep(RETRY_BACKOFF_SEC * (attempt + 1))
            continue

        if payload.get("is_error"):
            last_err = f"is_error payload: {str(payload)[:300]}"
            time.sleep(RETRY_BACKOFF_SEC * (attempt + 1))
            continue

        return payload["result"], float(payload.get("total_cost_usd", 0.0))

    raise RuntimeError(
        f"claude CLI failed after {MAX_CLAUDE_RETRIES} attempts: {last_err}"
    )


def _dispatch(
    action: dict[str, Any],
    mode: OntologyMode,
    ontology_variant: str | None = None,
) -> tuple[dict[str, Any], bool]:
    name = action.get("action")
    args = action.get("args", {}) or {}
    if name == "list_parent_causes":
        if mode == OntologyMode.NONE:
            return (
                {
                    "error": (
                        "list_parent_causes is not available in this mode. "
                        "Only compare_metric_round and report_root_cause can be used."
                    )
                },
                False,
            )
        concept = args.get("concept_label", "")
        return (
            list_parent_causes(
                concept, mode=mode, ontology_variant=ontology_variant
            ),
            False,
        )
    if name == "compare_metric_round":
        return compare_metric_round(**args), False
    if name == "report_root_cause":
        return {"status": "reported"}, True
    return {"error": f"unknown action '{name}'"}, False


def run_rootcause_agent(
    anomaly_metric_id: str,
    round_a: str,
    round_b: str,
    model: str = DEFAULT_MODEL,
    sandbox_cwd: Path = DEFAULT_SANDBOX,
    ontology_mode: OntologyMode = OntologyMode.FULL,
    causal_format: CausalFormat | None = None,
    ontology_variant: str | None = None,
) -> AgentTrace:
    """Run the agent loop on a detected anomaly between two rounds.

    ``ontology_mode`` selects which ontology properties are surfaced to
    the agent via list_parent_causes. NONE removes the tool entirely and
    switches to the no-ontology system prompt; all other modes use the
    with-ontology system prompt but filter the tool output.

    ``causal_format`` overrides the interaction pattern for the format
    comparison experiment. Only ONTOLOGY uses the tool; the three push
    formats (JSON_PUSH, PROSE_PUSH, DBT_META) embed the same causal
    information directly in the system prompt and force ontology_mode
    to NONE (no tool call). When left as ``None`` the function behaves
    identically to before.
    """
    trace = AgentTrace()

    if causal_format is not None and causal_format != CausalFormat.ONTOLOGY:
        # Push-format mode: tool unavailable, info pre-embedded in prompt
        ontology_mode = OntologyMode.NONE
        system_prompt = build_push_prompt(causal_format)
    else:
        system_prompt = (
            SYSTEM_PROMPT_WITHOUT_ONTOLOGY
            if ontology_mode == OntologyMode.NONE
            else SYSTEM_PROMPT_WITH_ONTOLOGY
        )
    # Resolve metric id to its description for the orchestrator framing.
    description = ""
    if anomaly_metric_id in METRIC_ALIAS:
        from ontoprobe.rootcause.tools import METRIC_DESCRIPTIONS

        description = f' ({METRIC_DESCRIPTIONS[anomaly_metric_id]})'

    initial_user = (
        f"ANOMALY DETECTED: metric '{anomaly_metric_id}'{description} has changed "
        f"unexpectedly between round '{round_a}' and round '{round_b}'. "
        f"Investigate via your virtual tools and report the root cause."
    )
    history: list[dict[str, str]] = [{"role": "user", "content": initial_user}]

    for i in range(MAX_ITERATIONS):
        trace.iterations = i + 1
        prompt = _render_history(history)
        raw, cost = _claude_call(prompt, model, sandbox_cwd, system_prompt)
        trace.assistant_raw.append(raw)
        trace.total_cost_usd += cost

        action = _parse_action(raw)
        if action is None:
            trace.stopped_reason = "parse failure — could not extract JSON action"
            history.append({"role": "assistant", "content": raw})
            break

        history.append({"role": "assistant", "content": raw})

        result, terminated = _dispatch(action, ontology_mode, ontology_variant)
        trace.tool_calls.append(
            {
                "tool": action.get("action"),
                "input": action.get("args", {}) or {},
                "result": result,
            }
        )
        history.append(
            {
                "role": "tool_result",
                "content": json.dumps(result, ensure_ascii=False, default=str),
            }
        )

        if terminated:
            trace.final_report = action.get("args", {}) or {}
            trace.stopped_reason = "root cause reported"
            break
    else:
        trace.stopped_reason = f"hit max iterations ({MAX_ITERATIONS})"

    return trace
