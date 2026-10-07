import argparse
import json
from pathlib import Path
import sys
from .contract import ContractError, Order, Refund, summarize


def main():
    parser = argparse.ArgumentParser(description="Evaluate the synthetic DEMO-CASHFLOW contract")
    parser.add_argument("input", type=Path)
    parser.add_argument("--month", required=True)
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        result = summarize([Order(**o) for o in data["orders"]],
                           [Refund(**r) for r in data["refunds"]], args.month,
                           complete_sources=data["complete_sources"])
    except (ContractError, KeyError, TypeError, ValueError, OSError) as exc:
        print(f"Unavailable: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
