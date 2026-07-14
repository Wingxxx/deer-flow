# Privacy & GDPR Compliance

> **Last updated:** 2026-07-13

This document describes how the DeerFlow Data Collection system handles personally identifiable information (PII) and how to operate it in compliance with GDPR, CCPA, and other data protection regulations.

## Identity collection overview

The system can optionally record two identity fields in training data:

| Field | Source | Typical Value | PII Risk |
|-------|--------|---------------|----------|
| `user_id` | `runtime.context.user_id` (Web UI) | UUID string | Low (synthetic identifier) |
| `channel_user_id` | `runtime.context.channel_user_id` (IM) | Platform user ID, **may be email** | **High** |

Both fields are **enabled by default**. However, when `pseudonymize_identity=True` (default), identity values are HMAC-SHA256 pseudonymized before writing. To disable identity collection, set `collect_user_identity: false` and `collect_channel_user_id: false`.

## Three pseudonymization modes

The combination of `pseudonymize_identity` and `pseudonym_salt` produces three distinct modes:

| Mode | `pseudonymize_identity` | `pseudonym_salt` | Behavior | Linkable across sessions | Use case |
|------|------------------------|-----------------|----------|-------------------------|----------|
| **1. Plaintext (not recommended)** | `false` | ignored | Raw value written as-is | Yes | Debugging / audit only |
| **2. Ephemeral hash** | `true` | `""` (empty) | HMAC-SHA256 with empty salt | No (salt resets per process start) | Testing / low-trust environments |
| **3. Stable pseudonym** | `true` | set to secret | HMAC-SHA256 with persistent salt | Yes (with same salt) | Production per-user analytics |

### Mode 3 — Stable pseudonym (recommended for production)

Set `DATA_COLLECTION_PSEUDONYM_SALT` to a long, random, secret string:

```bash
# Generate a 64-character hex salt
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Store the salt in your `.env` file:

```
DATA_COLLECTION_PSEUDONYM_SALT=abcdef0123456789...
```

### Important caveats about pseudonymization

- Pseudonymization is **reversible** by anyone who knows the salt. Treat the salt as a secret.
- The same input always produces the same hash with the same salt — this enables per-user analytics but also means **anyone with the salt can tell if two records belong to the same user**.
- HMAC-SHA256 is not encryption. It is a one-way function with a key. There is no "decrypt" operation, but an attacker with the salt can brute-force short user IDs (e.g., integer sequences).

## Dangerous configuration combinations

| Combination | Risk | Mitigation |
|-------------|------|------------|
| `collect_user_identity=true` + `pseudonymize_identity=false` | Raw user_id in plaintext on local disk | Startup WARNING + `_plaintext_identity: True` audit marker in each record |
| `collect_channel_user_id=true` | Platform PII (email, phone) may be stored | Treat `channel_user_id` as sensitive; enable pseudonymization |
| `pseudonym_salt` reused across environments (dev/staging/prod) | Cross-environment user correlation | Use separate salts per environment |
| Salt rotation without migration | Old hashes unlinkable from new hashes | Plan for dual-hashing or batch re-processing on rotation |

## Fail-open and data minimization

By design, the identity collection layer follows a **fail-open** principle: if identity logic fails (exception in middleware, missing context, corrupt session cache), the training record is still written — only the identity fields are absent. This ensures:

- No data loss from identity logic failures
- No crash propagation from identity errors
- Natural data minimization (identity is only present when the full chain succeeds)

## DSAR (Data Subject Access Request) procedure

Since identity fields are pseudonymized (not anonymized), you can fulfill DSAR requests:

1. **Identify the data subject's raw user_id** from your authentication system
2. **Compute the hash** using the same salt and HMAC-SHA256:
   ```python
   import hmac
   raw_id = "user-12345"  # from authentication system
   salt = "your-salt"     # from DATA_COLLECTION_PSEUDONYM_SALT
   user_hash = hmac.new(salt.encode("utf-8"), raw_id.encode("utf-8"), "sha256").hexdigest()
   ```
3. **Search training logs** for records where `user_id == user_hash` or `channel_user_id == user_hash`
4. **Export or delete** those records as required by the request

For **right to erasure** (Article 17 GDPR):
- Delete the affected records from all `daily/`, `aggregated/`, and `flagged/` directories
- Document the deletion in your data processing register
- Note that records without identity fields (anonymous sessions) cannot be attributed to any data subject and are not subject to erasure requests

## Salt rotation procedure

When rotating the pseudonymization salt:

1. **Stop data collection** or reconfigure to use the **new salt** going forward
2. **Keep the old salt** for DSAR queries on historical data
3. Optionally **re-hash** historical records with the new salt if cross-era analysis is required
4. Update `DATA_COLLECTION_PSEUDONYM_SALT` in your `.env` and restart

## Best practices

1. **Default-on**: identity collection is enabled by default (pseudonymized). Explicitly disable via config when identity fields are not needed
2. **Pseudonymize always**: keep `pseudonymize_identity=true` in production
3. **Separate salts**: use different salts per environment (dev/staging/prod)
4. **Audit regularly**: scan raw JSONL for unexpected plaintext identity fields
5. **Strip on export**: use `export_dataset(strip_identity=True)` when sharing data externally
6. **Log hygiene**: never log raw identity values in application logs or error reports
7. **Retention policy**: configure automated cleanup of raw JSONL after the aggregation pipeline has processed it

WING
