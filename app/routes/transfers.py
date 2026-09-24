import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_conn
from app.models import TransferRequest, TransferResponse

router = APIRouter()


@router.post("/transfers", status_code=201, response_model=TransferResponse)
def create_transfer(req: TransferRequest, conn: sqlite3.Connection = Depends(get_conn)):
    src = conn.execute("SELECT id, balance FROM accounts WHERE id = ?", (req.from_account,)).fetchone()
    dst = conn.execute("SELECT id, balance FROM accounts WHERE id = ?", (req.to_account,)).fetchone()
    if src is None or dst is None:
        raise HTTPException(status_code=404, detail="account not found")
    if src["balance"] < req.amount:
        raise HTTPException(status_code=409, detail="insufficient funds")

    new_src = src["balance"] - req.amount
    new_dst = dst["balance"] + req.amount
    transfer_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_src, req.from_account))
    conn.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_dst, req.to_account))
    conn.execute(
        "INSERT INTO transfers (id, from_account, to_account, amount, created_at) VALUES (?, ?, ?, ?, ?)",
        (transfer_id, req.from_account, req.to_account, req.amount, now),
    )
    conn.execute(
        "INSERT INTO transactions (account_id, type, amount, created_at, transfer_id) VALUES (?, 'transfer_out', ?, ?, ?)",
        (req.from_account, req.amount, now, transfer_id),
    )
    conn.execute(
        "INSERT INTO transactions (account_id, type, amount, created_at, transfer_id) VALUES (?, 'transfer_in', ?, ?, ?)",
        (req.to_account, req.amount, now, transfer_id),
    )
    conn.commit()
    return {"transfer_id": transfer_id, "from_balance": str(new_src), "to_balance": str(new_dst)}
