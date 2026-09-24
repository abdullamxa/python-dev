import sqlite3
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
import base64
import json

from app.db import get_conn

router = APIRouter()

def encode_cursor(data: dict) -> str:
    json_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(json_bytes).decode("ascii")


def decode_cursor(cursor: str) -> dict:
    try:
        if not cursor or len(cursor) > 4096:
            raise ValueError("invalid cursor length")

        json_bytes = base64.b64decode(
            cursor,
            altchars=b"-_",
            validate=True,
        )
        data = json.loads(json_bytes.decode("utf-8"))

        if not isinstance(data, dict):
            raise ValueError("cursor must contain an object")

        return data

    except (ValueError, UnicodeError) as exc:
        raise HTTPException(
            status_code=400,
            detail="invalid cursor",
        ) from exc


@router.get("/accounts/{account_id}")
def get_account(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute(
        "SELECT id, client_name, balance FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="account not found")
    return {"id": row["id"], "client_name": row["client_name"], "balance": f"{row['balance']:.2f}"}


@router.get("/accounts/{account_id}/positions")
def get_positions(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    if conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="account not found")
    positions = conn.execute(
        """
        SELECT p.fund_code, p.units, f.name, f.nav
        FROM positions AS p
        JOIN funds AS f ON p.fund_code = f.code
        WHERE p.account_id = ?
        ORDER BY p.fund_code
        """,
        (account_id,),
    ).fetchall()
    result = []
    for p in positions:
        result.append(
            {
                "fund_code": p["fund_code"],
                "fund_name": p["name"],
                "units": f"{p['units']:.4f}",
                "market_value": f"{p['units'] * p['nav']:.2f}",
            }
        )
    return {"account_id": account_id, "positions": result}

@router.get("/accounts/{account_id}/transactions")
def get_transactions(
    account_id: str,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    transaction_type: Literal[
        "deposit", "withdrawal", "transfer_in", "transfer_out"
    ] | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_conn),
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=422,
            detail="from must not be later than to",
        )

    account = conn.execute(
        "SELECT 1 FROM accounts WHERE id = ?",
        (account_id,),
    ).fetchone()

    if account is None:
        raise HTTPException(status_code=404, detail="account not found")

    filters = {
        "account": account_id,
        "from": from_date.isoformat() if from_date else None,
        "to": to_date.isoformat() if to_date else None,
        "type": transaction_type,
    }

    page = None

    if cursor is not None:
        page = decode_cursor(cursor)

        expected_fields = {
            "version", "account", "from", "to", "type",
            "snapshot_id", "last_id", "last_at",
        }

        if set(page) != expected_fields:
            raise HTTPException(status_code=400, detail="invalid cursor")

        if (
            type(page["version"]) is not int
            or page["version"] != 1
            or type(page["snapshot_id"]) is not int
            or type(page["last_id"]) is not int
            or not 0 < page["last_id"] <= page["snapshot_id"] <= 9223372036854775807
            or not isinstance(page["last_at"], str)
            or not page["last_at"]
        ):
            raise HTTPException(status_code=400, detail="invalid cursor")

        if any(page[key] != value for key, value in filters.items()):
            raise HTTPException(
                status_code=400,
                detail="cursor does not match account or filters",
            )

        marker = conn.execute(
            """
            SELECT created_at
            FROM transactions
            WHERE account_id = ? AND id = ?
            """,
            (account_id, page["last_id"]),
        ).fetchone()

        if marker is None or marker["created_at"] != page["last_at"]:
            raise HTTPException(status_code=400, detail="invalid cursor")

        snapshot_id = page["snapshot_id"]

    else:
        # Freeze which transaction IDs belong to this sequence of pages.
        snapshot_id = conn.execute(
            """
            SELECT COALESCE(MAX(id), 0)
            FROM transactions
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()[0]

    conditions = ["account_id = ?", "id <= ?"]
    parameters = [account_id, snapshot_id]

    if from_date is not None:
        conditions.append("date(created_at) >= ?")
        parameters.append(from_date.isoformat())

    if to_date is not None:
        conditions.append("date(created_at) <= ?")
        parameters.append(to_date.isoformat())

    if transaction_type is not None:
        conditions.append("type = ?")
        parameters.append(transaction_type)

    if page is not None:
        # Continue after the last row returned on the previous page.
        conditions.append("(created_at, id) < (?, ?)")
        parameters.extend([page["last_at"], page["last_id"]])

    # Fetch one extra row to determine whether another page exists.
    rows = conn.execute(
        f"""
        SELECT id, type, amount, created_at
        FROM transactions
        WHERE {" AND ".join(conditions)}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        parameters + [limit + 1],
    ).fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]

    items = [
        {
            "id": row["id"],
            "type": row["type"],
            "amount": f"{row['amount']:.2f}",
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    next_cursor = None

    if has_more:
        last = rows[-1]
        next_cursor = encode_cursor(
            {
                "version": 1,
                **filters,
                "snapshot_id": snapshot_id,
                "last_id": last["id"],
                "last_at": last["created_at"],
            }
        )

    return {"items": items, "next_cursor": next_cursor}