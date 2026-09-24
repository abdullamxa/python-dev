# What I don't trust

I would verify simultaneous transfers and retries, including a crash
around the commit, before shipping. The current tests do not prove those
cases. SQLite REAL storage remains approximate despite Decimal
calculations; exact storage needs a separate migration. Existing databases
also need the new idempotency table applied explicitly. I would check
pagination performance on larger datasets and confirm that historical
timestamps consistently use UTC. The cursor assumes transaction records
remain unchanged while paging.

# AI use

I used ChatGPT to explain the starter code, suggest implementation changes,
draft tests, identify review issues, and draft these documents. I applied
the changes locally and ran pytest. The interaction included revising
an exact-storage approach and returning to the original REAL schema.