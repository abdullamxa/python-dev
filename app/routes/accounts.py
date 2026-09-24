import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_conn

router = APIRouter()


@router.get("/accounts/{account_id}")
def get_account(account_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute(
        "SELECT id, client_name, balance FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="account not found")
    return {"id": row["id"], "client_name": row["client_name"], "balance": str(row["balance"])}


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
