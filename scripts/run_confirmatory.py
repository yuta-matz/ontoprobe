"""Driver that executes confirmatory trials via `claude -p` subprocess.

Reads data/confirmatory/trial_plan.json, runs any trial whose TrialRecord
JSON is not yet present, and saves the result. Safe to re-run (idempotent).
"""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import time
from pathlib import Path

from ontoprobe.evaluation.confirmatory import DATA_DIR, TrialRecord
from ontoprobe.hypotheses.llm_backend import extract_json

WRAPPER = """\
You are acting as a pure LLM analyst. Do NOT use any tools (no Read, no Bash, no file access). \
Read the analysis task inside <task> and return ONLY the JSON response specified — no preamble, \
no markdown fences, no commentary.

<task>
{prompt}
</task>
"""


def run_trial(plan_entry: dict, model: str = "opus", timeout: int = 180) -> TrialRecord:
    full_prompt = WRAPPER.format(prompt=plan_entry["prompt"])
    t0 = time.time()
    result = subprocess.run(
        ["claude", "-p", full_prompt, "--output-format", "text", "--model", model],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    dt = time.time() - t0
    if result.returncode != 0:
        err = result.stderr.strip()
        rec = TrialRecord(
            trial_uuid=plan_entry["uuid"],
            hid=plan_entry["hid"],
            level=plan_entry["level"],
            trial_index=plan_entry["idx"],
            runner_prompt=plan_entry["prompt"],
            runner_raw_output="",
            runner_json={},
            error=f"subprocess failed (dt={dt:.1f}s): {err}",
        )
        rec.save()
        return rec

    raw = result.stdout.strip()
    try:
        parsed = extract_json(raw)
        error = None
    except Exception as e:
        parsed = {}
        error = f"json parse failed: {e}"

    rec = TrialRecord(
        trial_uuid=plan_entry["uuid"],
        hid=plan_entry["hid"],
        level=plan_entry["level"],
        trial_index=plan_entry["idx"],
        runner_prompt=plan_entry["prompt"],
        runner_raw_output=raw,
        runner_json=parsed,
        error=error,
    )
    rec.save()
    return rec


def main() -> int:
    plan_path = DATA_DIR / "trial_plan.json"
    plan: list[dict] = json.loads(plan_path.read_text())

    to_run = [t for t in plan if not (DATA_DIR / f"trial_{t['uuid']}.json").exists()]
    print(f"Plan: {len(plan)} trials, {len(to_run)} remaining")

    if not to_run:
        print("Nothing to run.")
        return 0

    max_workers = 8
    errors: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(run_trial, t): t for t in to_run}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            t = futures[fut]
            try:
                rec = fut.result()
                tag = "OK" if not rec.error else "ERR"
                print(f"[{i}/{len(to_run)}] {tag} {rec.trial_uuid} {rec.hid} L{rec.level} idx{rec.trial_index}")
                if rec.error:
                    errors.append(f"{rec.trial_uuid}: {rec.error}")
            except Exception as e:
                print(f"[{i}/{len(to_run)}] EXCEPTION {t['uuid']}: {e}")
                errors.append(f"{t['uuid']}: exception {e}")

    print(f"\nDone. errors={len(errors)}")
    for e in errors:
        print(f"  - {e}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
