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


def test_pagination_stays_stable_when_transactions_arrive(client, db_path):
    conn = connect(db_path)
    try:
        # All five transactions deliberately share the same timestamp.
        conn.executemany(
            """
            INSERT INTO transactions (account_id, type, amount, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("ACC-1001", "deposit", amount, "2026-08-01T12:00:00+00:00")
                for amount in (10, 20, 30, 40, 50)
            ],
        )
        conn.commit()
    finally:
        conn.close()

    first = client.get(
        "/accounts/ACC-1001/transactions",
        params={"limit": 2},
    )

    assert first.status_code == 200
    first_page = first.json()
    assert len(first_page["items"]) == 2
    assert first_page["next_cursor"] is not None

    # Insert a newer transaction and a backdated one after page one.
    conn = connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO transactions (account_id, type, amount, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("ACC-1001", "deposit", 99, "2026-08-02T12:00:00+00:00"),
                ("ACC-1001", "deposit", 88, "2026-07-01T12:00:00+00:00"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    second = client.get(
        "/accounts/ACC-1001/transactions",
        params={"limit": 2, "cursor": first_page["next_cursor"]},
    )

    assert second.status_code == 200
    second_page = second.json()
    assert len(second_page["items"]) == 2
    assert second_page["next_cursor"] is not None

    third = client.get(
        "/accounts/ACC-1001/transactions",
        params={"limit": 2, "cursor": second_page["next_cursor"]},
    )

    assert third.status_code == 200
    third_page = third.json()
    assert len(third_page["items"]) == 1
    assert third_page["next_cursor"] is None

    items = (
        first_page["items"]
        + second_page["items"]
        + third_page["items"]
    )

    assert [item["amount"] for item in items] == [
        "50.00", "40.00", "30.00", "20.00", "10.00",
    ]
    assert len({item["id"] for item in items}) == 5


def test_transactions_invalid_cursor_and_limits(client):
    for cursor in ("not-a-cursor!", "e30=", "W10="):
        response = client.get(
            "/accounts/ACC-1001/transactions",
            params={"cursor": cursor},
        )
        assert response.status_code == 400

    for limit in (0, -1, 101, "abc"):
        response = client.get(
            "/accounts/ACC-1001/transactions",
            params={"limit": limit},
        )
        assert response.status_code == 422

def test_transactions_default_and_maximum_limit(client, db_path):
    conn = connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO transactions (account_id, type, amount, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("ACC-1001", "deposit", 10, "2026-08-01T12:00:00+00:00")
                for _ in range(101)
            ],
        )
        conn.commit()
    finally:
        conn.close()

    default_response = client.get("/accounts/ACC-1001/transactions")
    assert default_response.status_code == 200
    assert len(default_response.json()["items"]) == 50
    assert default_response.json()["next_cursor"] is not None

    maximum_response = client.get(
        "/accounts/ACC-1001/transactions",
        params={"limit": 100},
    )
    assert maximum_response.status_code == 200
    assert len(maximum_response.json()["items"]) == 100

    cursor = maximum_response.json()["next_cursor"]
    assert cursor is not None

    last_response = client.get(
        "/accounts/ACC-1001/transactions",
        params={"limit": 100, "cursor": cursor},
    )
    assert last_response.status_code == 200
    assert len(last_response.json()["items"]) == 1
    assert last_response.json()["next_cursor"] is None