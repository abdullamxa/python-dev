import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from app.db import get_conn
from app.models import TransferRequest, TransferResponse

router = APIRouter()


@router.post("/transfers", status_code=201, response_model=TransferResponse)
def create_transfer(
    req: TransferRequest,
    conn: sqlite3.Connection = Depends(get_conn),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    amount = req.amount.quantize(Decimal("0.01"))

    # Lock before checking the key or reading balances.
    if req.from_account == req.to_account:
        raise HTTPException(
            status_code=422,
            detail="source and destination accounts must differ",
        )
    conn.execute("BEGIN IMMEDIATE")

    try:
        if idempotency_key is not None:
            prior = conn.execute(
                "SELECT * FROM transfer_idempotency WHERE key = ?",
                (idempotency_key,),
            ).fetchone()

            if prior is not None:
                if (
                    prior["from_account"] != req.from_account
                    or prior["to_account"] != req.to_account
                    or prior["amount"] != str(amount)
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="idempotency key used for a different transfer",
                    )

                conn.rollback()
                return {
                    "transfer_id": prior["transfer_id"],
                    "from_balance": prior["from_balance"],
                    "to_balance": prior["to_balance"],
                }

        src = conn.execute(
            "SELECT id, balance FROM accounts WHERE id = ?", (req.from_account,)
        ).fetchone()
        dst = conn.execute(
            "SELECT id, balance FROM accounts WHERE id = ?", (req.to_account,)
        ).fetchone()

        if src is None or dst is None:
            raise HTTPException(status_code=404, detail="account not found")

        src_balance = Decimal(str(src["balance"])).quantize(Decimal("0.01"))
        dst_balance = Decimal(str(dst["balance"])).quantize(Decimal("0.01"))

        if src_balance < amount:
            raise HTTPException(status_code=409, detail="insufficient funds")

        new_src = src_balance - amount
        new_dst = dst_balance + amount
        transfer_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # SQLite REAL columns accept floats, not Python Decimal objects.
        conn.execute(
            "UPDATE accounts SET balance = ? WHERE id = ?",
            (float(new_src), req.from_account),
        )
        conn.execute(
            "UPDATE accounts SET balance = ? WHERE id = ?",
            (float(new_dst), req.to_account),
        )
        conn.execute(
            "INSERT INTO transfers (id, from_account, to_account, amount, created_at) VALUES (?, ?, ?, ?, ?)",
            (transfer_id, req.from_account, req.to_account, float(amount), now),
        )
        conn.execute(
            "INSERT INTO transactions (account_id, type, amount, created_at, transfer_id) VALUES (?, 'transfer_out', ?, ?, ?)",
            (req.from_account, float(amount), now, transfer_id),
        )
        conn.execute(
            "INSERT INTO transactions (account_id, type, amount, created_at, transfer_id) VALUES (?, 'transfer_in', ?, ?, ?)",
            (req.to_account, float(amount), now, transfer_id),
        )

        response = {
            "transfer_id": transfer_id,
            "from_balance": f"{new_src:.2f}",
            "to_balance": f"{new_dst:.2f}",
        }

        if idempotency_key is not None:
            conn.execute(
                """
                INSERT INTO transfer_idempotency
                    (key, from_account, to_account, amount,
                     transfer_id, from_balance, to_balance)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    idempotency_key,
                    req.from_account,
                    req.to_account,
                    str(amount),
                    transfer_id,
                    response["from_balance"],
                    response["to_balance"],
                ),
            )

        conn.commit()
        return response

    except Exception:
        conn.rollback()
        raise