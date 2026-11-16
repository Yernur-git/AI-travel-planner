"""Inspect the local catalogue without Streamlit or Gemini."""

import argparse
import json
import sys

from . import CatalogError, load_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="")
    parser.add_argument("--interest", action="append", default=[])
    parser.add_argument("--match", choices=["any", "all"], default="any")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--known-hours-only", action="store_true")
    args = parser.parse_args()
    try:
        result = load_catalog().search(
            query=args.query, interests=args.interest, match=args.match,
            start_date=args.start_date, end_date=args.end_date,
            include_unknown_hours=not args.known_hours_only,
        )
    except (CatalogError, ValueError) as exc:
        parser.error(str(exc))
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({
        "catalog_version": result.catalog_version,
        "places": [p.model_dump(mode="json") for p in result.places],
        "sources": [s.model_dump(mode="json") for s in result.sources],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
