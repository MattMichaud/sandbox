"""Run an incremental sync from the terminal:

    poetry run python sync_cli.py
"""

from __future__ import annotations

import sys

from parking.sync import sync


def _progress(new_items: int, scanned: int, rows_inserted: int) -> None:
    sys.stdout.write(
        f"\r  new snapshots: {new_items:,} | scanned: {scanned:,} | rows: {rows_inserted:,}"
    )
    sys.stdout.flush()


def main() -> None:
    print("Syncing new parking snapshots from DynamoDB -> DuckDB ...")
    result = sync(progress=_progress)
    print()
    if result.get("rows_pruned"):
        print(f"Pruned {result['rows_pruned']:,} rows before the start-date cutoff.")
    if result["new_items"] == 0:
        print("Already up to date. Nothing new to fetch.")
    else:
        print(
            f"Done: {result['new_items']:,} new snapshots, "
            f"{result['rows_inserted']:,} rows inserted."
        )
    print(f"Cache now holds {result['total_rows']:,} rows.")


if __name__ == "__main__":
    main()
