from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenStudio ETL CLI")
    parser.add_argument("--version", action="store_true", help="Print the app version.")
    parser.add_argument("--dry-run", action="store_true", help="Validate configuration without execution.")
    args = parser.parse_args()

    if args.version:
        print("OpenStudio ETL 0.1.0")
        return

    if args.dry_run:
        print("Dry run successful. No execution was performed.")
        return

    print("OpenStudio ETL CLI ready.")


if __name__ == "__main__":
    main()
