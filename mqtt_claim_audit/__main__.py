"""Command line interface."""
import argparse
import json
import sys
from . import __version__
from .audit import audit

class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, "error: " + message + "\n")

def main(argv=None):
    parser = Parser(description="Audit documented messaging transport capabilities offline.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--ignore", action="append", default=[])
    parser.add_argument("--fail-on", choices=("HIGH", "MEDIUM"), default="HIGH")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        result = audit(args.root, args.ignore, args.fail_on)
    except (OSError, UnicodeError, ValueError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(result["verdict"])
        for finding in result["findings"]:
            print("{severity} {rule}: {message}".format(**finding))
        if args.verbose:
            print("Production evidence: " + (", ".join(result["evidence"]) or "none"))
            print("Test evidence: " + (", ".join(result["test_evidence"]) or "none"))
    return 2 if result["verdict"] == "FAIL" else 0

if __name__ == "__main__":
    sys.exit(main())
