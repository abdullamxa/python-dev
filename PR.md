# Fix and harden

The positions endpoint performed a separate fund lookup for each position.
I replaced those lookups with a JOIN, reducing the request to two SELECTs.

Balances were formatted inconsistently, transfer calculations used floats,
and the idempotency header was ignored. I added two-decimal formatting,
Decimal calculations, and validation for positive amounts with at most two
decimal places.

Transfers now use BEGIN IMMEDIATE before reading balances or checking
idempotency. Balance changes, transaction records, and the saved response
are committed together or rolled back on failure. Repeated keys return the
original response; conflicting reuse returns 409.

I also rejected transfers to the same account and added tests for that
defect and invalid amounts. All 11 tests pass on Python 3.11.

I retained the existing SQLite REAL columns to keep this change within the
exercise's scope. Decimal calculations do not make persisted REAL values
exact; exact money storage would require a separate schema and data migration.