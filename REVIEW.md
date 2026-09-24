# Review of PR #17

Line numbers below refer to the proposed files in the supplied diff.

## 1. SQL injection in client search

- File and line: `app/routes/search.py:14`.
- Severity: blocker.
- Problem: User-supplied `name` is interpolated directly into SQL.
  Malicious input can change the query, and ordinary names containing
  apostrophes can break it.
- Suggested fix: Use `LIKE ?` with a bound parameter.
  Add tests for apostrophes and malicious input.

## 2. Retried requests can duplicate ledger transfers

- File and line: `app/services/ledger_client.py:12–20, 25–33`.
- Severity: blocker.
- Problem: The ledger may process a transfer before the response times
  out. Retrying the POST without a stable identifier can process the
  same transfer again.
- Suggested fix: Send the original transfer ID as an idempotency key
  and confirm that the ledger enforces it. Reuse it across retries.
  Test a timeout after the ledger has accepted the request.

## 3. Local commit and ledger delivery can become inconsistent

- File and line: `app/routes/transfers.py:42–45`.
- Severity: blocker.
- Problem: The local transfer commits before the ledger call. If the
  call fails, the client receives an error even though local balances
  changed. A crash after the commit can also leave the transfer
  permanently absent from the ledger.
- Suggested fix: Save an outbox event in the same database transaction
  as the transfer. Deliver it through a retrying worker using a stable
  idempotency key and persist its delivery status. Test failures and
  recovery around the commit and delivery boundaries.

## 4. Retry policy includes permanent failures

- File and line: `app/services/ledger_client.py:17–20, 34`.
- Severity: should-fix.
- Problem: Catching every `httpx.HTTPError` retries HTTP status failures
  such as invalid requests and authorization failures. These generally
  will not succeed merely by repeating the request.
- Suggested fix: Retry only suitable transient failures under the
  ledger's documented contract. Handle rate limits and Retry-After
  where applicable. Keep retries bounded and test permanent failures.

## 5. Full account numbers are written to logs

- File and line: `app/services/ledger_client.py:37`.
- Severity: should-fix.
- Problem: Failure logs expose both full account numbers.
- Suggested fix: Log the transfer ID and a safe error category.
  Mask account numbers if they are necessary for troubleshooting,
  and verify the log output in a test.

## 6. Submitted timestamp has no timezone

- File and line: `app/services/ledger_client.py:30`.
- Severity: should-fix.
- Problem: `datetime.now().isoformat()` produces a local timestamp
  without a UTC offset, contrary to the repository's UTC convention.
- Suggested fix: Use `datetime.now(timezone.utc).isoformat()`.
  Create the submission timestamp once so retries preserve it.

## 7. Search failures are hidden as successful empty results

- File and line: `app/routes/search.py:17–18`.
- Severity: should-fix.
- Problem: Catching every exception and returning an empty list makes
  a database failure indistinguishable from a search with no matches.
- Suggested fix: Let unexpected failures reach normal error handling,
  return an appropriate server error, and log safe diagnostic details.
  Add a test for an injected database failure.

## 8. Search results are unbounded

- File and line: `app/routes/search.py:11–16`.
- Severity: should-fix.
- Problem: An empty or broad search can load and return every account.
- Suggested fix: Validate the search input and add a bounded result
  limit or pagination. Define whether `%` and `_` should be treated
  as literal characters or search wildcards, and test that behavior.

## Decision

Request changes. SQL injection, duplicate ledger transfers, and
inconsistent local and external state must be addressed before approval.