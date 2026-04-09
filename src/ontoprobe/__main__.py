"""Entry point: python -m ontoprobe"""

import sys

if __name__ == "__main__":
    if "--compare" in sys.argv:
        num_trials = 5
        for i, arg in enumerate(sys.argv):
            if arg == "--trials" and i + 1 < len(sys.argv):
                num_trials = int(sys.argv[i + 1])
        from ontoprobe.evaluation.comparison import run_comparison

        run_comparison(num_trials=num_trials)
    else:
        from ontoprobe.orchestrator import run_pipeline

        demo = "--demo" in sys.argv
        run_pipeline(demo=demo)
