"""Blind double-scoring of confirmatory trials.

For each trial, feed ONLY the LLM analysis text (no hid/level/verdict) to
a scorer agent that applies the rubric mechanically. Two independent
scorers per trial for inter-rater reliability.
"""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import time
from pathlib import Path

from ontoprobe.evaluation.confirmatory import (
    DATA_DIR,
    SCORER_RUBRIC,
    SCORER_SYSTEM,
    SCORER_OUTPUT_SPEC,
    ScoreRecord,
    TrialRecord,
    mask_for_scorer,
)
from ontoprobe.hypotheses.llm_backend import extract_json


def build_scorer_input(masked_analysis: str) -> str:
    """Return the full prompt for a blind scorer (system + user merged)."""
    return (
        f"{SCORER_SYSTEM}\n\n"
        f"{SCORER_RUBRIC}\n"
        f"---\n"
        f"## Analysis to score\n"
        f"```\n{masked_analysis}\n```\n"
        f"---\n"
        f"{SCORER_OUTPUT_SPEC}"
    )


def score_one(trial: TrialRecord, scorer_id: str, model: str = "opus", timeout: int = 180) -> ScoreRecord:
    # Mask: we pass ONLY the analysis text, no metadata, no verdict, no evidence_summary
    analysis_text = mask_for_scorer(trial.runner_json.get("analysis", ""))
    prompt = build_scorer_input(analysis_text)

    t0 = time.time()
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text", "--model", model],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    dt = time.time() - t0

    if result.returncode != 0:
        raise RuntimeError(f"scorer failed ({dt:.1f}s): {result.stderr.strip()}")

    raw = result.stdout.strip()
    parsed = extract_json(raw)

    rec = ScoreRecord(
        trial_uuid=trial.trial_uuid,
        scorer_id=scorer_id,
        q_quant=int(parsed["q_quant"]),
        q_quant_rationale=parsed.get("q_quant_rationale", ""),
        q_aware=int(parsed["q_aware"]),
        q_aware_rationale=parsed.get("q_aware_rationale", ""),
    )
    rec.save()
    return rec


def main() -> int:
    trials: list[TrialRecord] = []
    for p in sorted(DATA_DIR.glob("trial_*.json")):
        if p.name.startswith("trial_plan"):
            continue
        trials.append(TrialRecord.load(p))

    score_dir = DATA_DIR / "scores"
    score_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[TrialRecord, str]] = []
    for t in trials:
        for sid in ("scorer_a", "scorer_b"):
            expected = score_dir / f"score_{t.trial_uuid}_{sid}.json"
            if not expected.exists():
                jobs.append((t, sid))

    print(f"Trials: {len(trials)}, scoring jobs remaining: {len(jobs)}")
    if not jobs:
        return 0

    errors: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(score_one, t, sid): (t, sid) for (t, sid) in jobs}
        for i, fut in enumerate(concurrent.futures.as_completed(futs), 1):
            t, sid = futs[fut]
            try:
                rec = fut.result()
                print(f"[{i}/{len(jobs)}] OK {rec.trial_uuid} {sid}  q_quant={rec.q_quant} q_aware={rec.q_aware}")
            except Exception as e:
                msg = f"{t.trial_uuid} {sid}: {e}"
                print(f"[{i}/{len(jobs)}] ERR {msg}")
                errors.append(msg)

    print(f"\nDone. errors={len(errors)}")
    for e in errors:
        print(f"  - {e}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
