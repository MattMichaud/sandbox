"""Incremental sync: DynamoDB -> local DuckDB.

The table's partition key *is* ``request_timestamp``, so it can't be
range-queried; we use a filtered ``Scan`` (``request_timestamp > :last``). The
filter runs server-side after the read, so RCU cost doesn't shrink -- but the
big win is local: we only JSON-parse and store *new* snapshots, and the app
reads DuckDB instead of ever scanning DynamoDB.

The first run (empty cache) scans the whole table once to backfill.
"""

from __future__ import annotations

import json
from typing import Callable

import boto3

from . import store
from .config import AWS_REGION, START_DATE, TABLE_NAME
from .flatten import flatten_response

# Called after each scan page with cumulative (new_items, scanned, rows_inserted).
ProgressFn = Callable[[int, int, int], None]


def _client():
    return boto3.client("dynamodb", region_name=AWS_REGION)


def sync(db_path=None, progress: ProgressFn | None = None) -> dict:
    """Pull snapshots newer than what's cached into DuckDB. Returns a summary."""
    con = store.connect(read_only=False, db_path=db_path)
    try:
        store.init_schema(con)
        pruned = store.prune_before(con, START_DATE)
        last = store.get_last_timestamp(con)

        scan_kwargs: dict = {"TableName": TABLE_NAME}
        if last:
            # Incremental: only snapshots newer than what's cached.
            scan_kwargs["FilterExpression"] = "#ts > :last"
            scan_kwargs["ExpressionAttributeNames"] = {"#ts": "request_timestamp"}
            scan_kwargs["ExpressionAttributeValues"] = {":last": {"S": last}}
        elif START_DATE:
            # Backfill: don't even download pre-cutoff data. request_timestamp is
            # a UTC ISO string; a bare date sorts as its lexicographic prefix.
            scan_kwargs["FilterExpression"] = "#ts >= :start"
            scan_kwargs["ExpressionAttributeNames"] = {"#ts": "request_timestamp"}
            scan_kwargs["ExpressionAttributeValues"] = {":start": {"S": START_DATE.isoformat()}}

        client = _client()
        new_items = 0
        scanned = 0
        rows_inserted = 0

        while True:
            resp = client.scan(**scan_kwargs)
            items = resp.get("Items", [])
            scanned += resp.get("ScannedCount", len(items))

            rows: list[dict] = []
            for item in items:
                try:
                    ts = item["request_timestamp"]["S"]
                    api = json.loads(item["api_response"]["S"])
                except (KeyError, TypeError, json.JSONDecodeError):
                    continue
                rows.extend(flatten_response(api, ts))

            rows_inserted += store.insert_rows(con, rows)
            new_items += len(items)
            if progress:
                progress(new_items, scanned, rows_inserted)

            lek = resp.get("LastEvaluatedKey")
            if not lek:
                break
            scan_kwargs["ExclusiveStartKey"] = lek

        return {
            "last_before": last,
            "new_items": new_items,
            "rows_inserted": rows_inserted,
            "rows_pruned": pruned,
            "scanned": scanned,
            "total_rows": store.row_count(con),
        }
    finally:
        con.close()
