from decimal import Decimal

from pydantic import BaseModel, Field


class TransferRequest(BaseModel):
    from_account: str
    to_account: str
    amount: Decimal = Field(gt=0, decimal_places=2)


class TransferResponse(BaseModel):
    transfer_id: str
    from_balance: str
    to_balance: str