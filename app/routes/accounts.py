import sqlite3
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_conn

router = APIRouter()


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

    conditions = ["account_id = ?"]
    parameters = [account_id]

    if from_date is not None:
        conditions.append("date(created_at) >= ?")
        parameters.append(from_date.isoformat())

    if to_date is not None:
        conditions.append("date(created_at) <= ?")
        parameters.append(to_date.isoformat())

    if transaction_type is not None:
        conditions.append("type = ?")
        parameters.append(transaction_type)

    rows = conn.execute(
        f"""
        SELECT id, type, amount, created_at
        FROM transactions
        WHERE {" AND ".join(conditions)}
        ORDER BY created_at DESC, id DESC
        """,
        parameters,
    ).fetchall()

    items = [
        {
            "id": row["id"],
            "type": row["type"],
            "amount": f"{row['amount']:.2f}",
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    return {"items": items, "next_cursor": None}