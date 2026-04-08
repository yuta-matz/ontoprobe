"""Entry point: python -m ontoprobe"""

import sys

from ontoprobe.orchestrator import run_pipeline

if __name__ == "__main__":
    demo = "--demo" in sys.argv
    run_pipeline(demo=demo)
