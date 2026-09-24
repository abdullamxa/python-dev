from app.db import connect


def test_transactions_unknown_account(client):
    response = client.get("/accounts/ACC-9999/transactions")
    assert response.status_code == 404


def test_transactions_empty_account(client):
    response = client.get("/accounts/ACC-1001/transactions")

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


def test_transactions_order_and_account_filter(client, db_path):
    conn = connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO transactions (account_id, type, amount, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("ACC-1001", "deposit", 10, "2026-08-01T10:00:00+00:00"),
                ("ACC-1001", "withdrawal", 20, "2026-08-02T10:00:00+00:00"),
                ("ACC-1001", "deposit", 30, "2026-08-02T10:00:00+00:00"),
                ("ACC-1002", "deposit", 99, "2026-08-03T10:00:00+00:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/accounts/ACC-1001/transactions")

    assert response.status_code == 200
    body = response.json()
    items = body["items"]

    assert [item["amount"] for item in items] == ["30.00", "20.00", "10.00"]
    assert items[0]["id"] > items[1]["id"]
    assert all(
        set(item) == {"id", "type", "amount", "created_at"}
        for item in items
    )
    assert body["next_cursor"] is None

def test_transactions_date_and_type_filters(client, db_path):
    conn = connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO transactions (account_id, type, amount, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("ACC-1001", "deposit", 5, "2026-07-31T23:59:59+00:00"),
                ("ACC-1001", "deposit", 10, "2026-08-01T00:00:00+00:00"),
                ("ACC-1001", "withdrawal", 20, "2026-08-02T12:00:00+00:00"),
                ("ACC-1001", "deposit", 30, "2026-08-03T23:59:59+00:00"),
                ("ACC-1001", "deposit", 40, "2026-08-04T00:00:00+00:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get(
        "/accounts/ACC-1001/transactions",
        params={
            "from": "2026-08-01",
            "to": "2026-08-03",
            "type": "deposit",
        },
    )

    assert response.status_code == 200
    assert [item["amount"] for item in response.json()["items"]] == [
        "30.00",
        "10.00",
    ]


def test_transactions_invalid_filters(client):
    invalid_parameters = [
        {"from": "not-a-date"},
        {"to": "2026-02-30"},
        {"type": "unknown"},
        {"from": "2026-08-03", "to": "2026-08-01"},
    ]

    for parameters in invalid_parameters:
        response = client.get(
            "/accounts/ACC-1001/transactions",
            params=parameters,
        )
        assert response.status_code == 422