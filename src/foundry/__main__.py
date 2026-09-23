"""Small command-line entry point for the foundation release."""
import argparse
import json
import sys
from foundry.data.validation import DataError, validate_file


def main():
    parser = argparse.ArgumentParser(description="Foundry data validation")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate an exchange JSON file")
    validate.add_argument("path")
    args = parser.parse_args()
    try:
        counts = validate_file(args.path)
    except (DataError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1
    print("Validation passed: " + ", ".join(f"{name}={count}" for name, count in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
