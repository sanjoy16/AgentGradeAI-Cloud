"""Runtime dependency preflight; --require-all fails before an incomplete launch."""
import argparse
import json
from verification import tool_health, dependency_guidance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args()
    health = tool_health()
    print(json.dumps(health, indent=2))
    for message in dependency_guidance(health):
        print(message)
    return 1 if args.require_all and not all(health.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
