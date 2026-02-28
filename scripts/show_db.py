"""JobPulse DB viewer – query stored offers from the command line."""

import argparse
import csv
import io
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path so `src` package is importable.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.storage.sqlite_store import SQLiteOfferStore, OfferQuery

_DISPLAY_COLUMNS = ("title", "company", "city", "salary", "source")
_CSV_COLUMNS = ("source", "title", "company", "city", "salary_min_pln", "salary_max_pln", "skills", "offer_url")


def _offer_query_from_args(args: argparse.Namespace) -> OfferQuery:
    """Map CLI args to an OfferQuery."""
    return OfferQuery(
        city=args.city,
        company=args.company,
        skill=args.skill,
        title=args.title,
        source=args.source,
        min_salary=args.min_salary,
        limit=args.limit,
    )


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _output_text(rows: list[dict], total: int, verbose: bool) -> None:
    """Default human-readable output."""
    print(f"Total rows in DB: {total}")
    print(f"Matching rows: {len(rows)}")
    print()

    for row in rows:
        salary = _format_salary(row["salary_min_pln"], row["salary_max_pln"])
        print(f"  {row['title']} | {row['company']} | {row['city'] or '?'} | {salary} | {row['source']}")
        if verbose:
            print(f"    skills: {row['skills']}")
            print(f"    url:    {row['offer_url']}")
        print()


def _output_csv(rows: list[dict]) -> None:
    """CSV output to stdout — pipe-friendly."""
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=_CSV_COLUMNS,
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)


def _output_json(rows: list[dict]) -> None:
    """JSON array output to stdout."""
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def _output_table(rows: list[dict]) -> None:
    """Aligned table output (no external dependency)."""
    if not rows:
        print("(no results)")
        return

    # Build display rows with formatted salary
    display_rows: list[dict[str, str]] = []
    for row in rows:
        display_rows.append({
            "title": row["title"],
            "company": row["company"],
            "city": row["city"] or "?",
            "salary": _format_salary(row["salary_min_pln"], row["salary_max_pln"]),
            "source": row["source"],
        })

    # Calculate column widths
    widths = {col: len(col) for col in _DISPLAY_COLUMNS}
    for dr in display_rows:
        for col in _DISPLAY_COLUMNS:
            widths[col] = max(widths[col], len(str(dr[col])))

    # Header
    header = " | ".join(col.upper().ljust(widths[col]) for col in _DISPLAY_COLUMNS)
    sep = "-+-".join("-" * widths[col] for col in _DISPLAY_COLUMNS)
    print(header)
    print(sep)

    # Rows
    for dr in display_rows:
        line = " | ".join(str(dr[col]).ljust(widths[col]) for col in _DISPLAY_COLUMNS)
        print(line)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(args: argparse.Namespace | None = None) -> None:
    if args is None:
        args = parse_args()

    db_file = Path(args.db)
    if not db_file.exists():
        print(f"Database not found: {db_file}", file=sys.stderr)
        sys.exit(1)

    store = SQLiteOfferStore(db_path=args.db)
    total = store.count()
    query = _offer_query_from_args(args)
    rows = store.query_offers(query)

    fmt = args.format
    if fmt == "csv":
        _output_csv(rows)
    elif fmt == "json":
        _output_json(rows)
    elif fmt == "table":
        _output_table(rows)
    else:
        _output_text(rows, total, args.verbose)


def _format_salary(sal_min: int | None, sal_max: int | None) -> str:
    if sal_min and sal_max:
        return f"{sal_min}-{sal_max} PLN"
    if sal_min:
        return f"od {sal_min} PLN"
    if sal_max:
        return f"do {sal_max} PLN"
    return "brak"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query JobPulse SQLite database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db", default="jobpulse.db", help="Path to SQLite database (default: jobpulse.db)"
    )
    parser.add_argument(
        "-n", "--limit", type=int, default=20, help="Max rows to display (default: 20)"
    )
    parser.add_argument("--city", help="Filter by city (substring match)")
    parser.add_argument("--company", help="Filter by company (substring match)")
    parser.add_argument("--skill", help="Filter by skill name (substring match in JSON)")
    parser.add_argument("--title", help="Filter by title (substring match)")
    parser.add_argument("--source", help="Filter by source (exact match)")
    parser.add_argument(
        "--min-salary", type=int, help="Minimum salary in PLN (checks both min and max)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show skills and URL for each offer (text format only)"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["text", "table", "csv", "json"],
        default="text",
        help="Output format (default: text)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
