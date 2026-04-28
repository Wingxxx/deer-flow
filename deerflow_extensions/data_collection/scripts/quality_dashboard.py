import json
import os
import sys
from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone


DATA_ROOT = "/data/deerflow/training_logs"
ESTIMATED_BYTES_PER_SAMPLE = 2048


def generate_daily_report(date_str: str) -> dict:
    stats_path = os.path.join(DATA_ROOT, "aggregated", date_str, "stats.json")

    if not os.path.exists(stats_path):
        raise FileNotFoundError(
            f"Stats file not found: {stats_path}"
        )

    try:
        with open(stats_path, "r", encoding="utf-8") as f:
            stats = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise RuntimeError(
            f"Failed to read or parse stats file '{stats_path}': {e}"
        ) from e

    total_raw = stats.get("total_raw", 0)
    total_train = stats.get("total_train", 0)
    categories = stats.get("categories", {})
    if not isinstance(categories, dict):
        categories = {}

    cat_total = sum(categories.values()) if categories else 0
    category_distribution = {}
    if cat_total > 0:
        category_distribution = {
            k: round(v / cat_total * 100, 2)
            for k, v in sorted(categories.items())
        }

    disk_bytes = total_train * ESTIMATED_BYTES_PER_SAMPLE
    estimated_disk_mb = round(disk_bytes / (1024 * 1024), 2)

    return {
        "date": date_str,
        "total_raw": total_raw,
        "total_train": total_train,
        "categories": categories,
        "category_distribution": category_distribution,
        "estimated_disk_mb": estimated_disk_mb,
    }


def _format_table(report: dict) -> str:
    lines = []
    sep = "=" * 50
    lines.append(sep)
    lines.append(f"{'Quality Dashboard Report':^50}")
    lines.append(sep)
    lines.append("")
    lines.append(f"  {'Date':<20} {report['date']}")
    lines.append(f"  {'Total Raw Samples':<20} {report['total_raw']}")
    lines.append(f"  {'Total Train Samples':<20} {report['total_train']}")
    lines.append(f"  {'Estimated Disk (MB)':<20} {report['estimated_disk_mb']}")
    lines.append("")

    cats = report.get("categories", {})
    dist = report.get("category_distribution", {})
    if cats:
        lines.append(f"  {'Category Distribution':-^40}")
        lines.append("")
        for k in sorted(cats):
            count = cats[k]
            pct = dist.get(k, 0)
            bar_len = max(1, int(pct / 2))
            bar = "█" * bar_len
            lines.append(f"    {k:<25} {count:>6}  {pct:>5.1f}%  {bar}")
        lines.append("")

    lines.append(sep)
    return "\n".join(lines)


def main() -> None:
    parser = ArgumentParser(description="Generate daily data quality report.")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y%m%d")
    parser.add_argument(
        "--date", "-d",
        default=yesterday,
        help=f"Date in YYYYMMDD format (default: {yesterday})",
    )
    args = parser.parse_args()

    try:
        report = generate_daily_report(args.date)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print(_format_table(report))


if __name__ == "__main__":
    main()
