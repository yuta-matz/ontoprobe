"""Entry point: python -m ontoprobe"""

import sys

def _parse_trials() -> int:
    num_trials = 5
    for i, arg in enumerate(sys.argv):
        if arg == "--trials" and i + 1 < len(sys.argv):
            num_trials = int(sys.argv[i + 1])
    return num_trials


if __name__ == "__main__":
    if "--compare" in sys.argv:
        from ontoprobe.evaluation.comparison import run_comparison

        run_comparison(num_trials=_parse_trials())
    elif "--chain-compare" in sys.argv:
        from ontoprobe.evaluation.chain_comparison import run_chain_comparison

        run_chain_comparison(num_trials=_parse_trials())
    elif "--hop-compare" in sys.argv:
        from ontoprobe.evaluation.hop_comparison import run_hop_comparison

        run_hop_comparison(num_trials=_parse_trials())
    else:
        from ontoprobe.orchestrator import run_pipeline

        demo = "--demo" in sys.argv
        run_pipeline(demo=demo)
