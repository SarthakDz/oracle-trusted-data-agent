"""Ask the agent a question from the command line.

    python -m tda.cli --persona manager "How many people report to me?"
"""

import argparse
import sys

from tda import tracing
from tda.agent.graph import ask
from tda.personas import PERSONAS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask the Trusted Data Agent a question.")
    parser.add_argument("--persona", choices=sorted(PERSONAS), default="employee")
    parser.add_argument("--config", choices=("A", "B", "C"), default="A", help="defense config")
    parser.add_argument("question")
    args = parser.parse_args(argv)

    tracing.setup_tracing()
    try:
        state = ask(args.question, args.persona, args.config, approver=_ask_person)
    finally:
        tracing.shutdown_tracing()  # flush the run's spans before the process exits
    print(f"persona : {args.persona} ({PERSONAS[args.persona].username})")
    print(f"intent  : {state.get('intent')}")
    if state.get("sql"):
        print(f"sql     : {state['sql']}")
    if "rows" in state:
        print(f"rows    : {len(state['rows'])}{' (truncated)' if state.get('truncated') else ''}")
    print(f"attempts: {state.get('attempts', 0)}")
    print(f"answer  : {state['answer']}")
    return 0


def _ask_person(preview: dict) -> str:
    """The human in the loop: show the proposed change and the rows it touches, then ask."""
    print(f"proposed: {preview['sql']}")
    if preview["columns"]:
        print("rows    : " + " | ".join(preview["columns"]))
        for row in preview["rows"][:20]:
            print("          " + " | ".join(str(v) for v in row))
        print(f"          (showing {min(20, len(preview['rows']))} of {preview['count']} rows)")
    return "approve" if input("Approve this change? [y/N] ").strip().lower() == "y" else "reject"


if __name__ == "__main__":
    sys.exit(main())
