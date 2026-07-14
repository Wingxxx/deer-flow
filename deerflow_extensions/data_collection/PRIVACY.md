# Privacy & Data Protection

> **Last updated:** 2026-07-14

This document describes how the DeerFlow Data Collection system handles personally identifiable information (PII) and how to operate it in compliance with GDPR, CCPA, and other data protection regulations.

## Identity collection overview

The system can optionally record two identity fields in training data:

| Field | Source | Typical Value | PII Risk |
|-------|--------|---------------|----------|
| `user_id` | `runtime.context.user_id` (Web UI) | UUID string | Low (synthetic identifier) |
| `channel_user_id` | `runtime.context.channel_user_id` (IM) | Platform user ID, **may be email** | **High** |

Both fields are **enabled by default**. However, when `pseudonymize_identity=True` (default), identity values are HMAC-SHA256 pseudonymized before writing. To disable identity collection, set `collect_user_identity: false` and `collect_channel_user_id: false`.

## Salt lifecycle management

The pseudonymization salt is the HMAC key used to hash identity values. The system uses a **three-layer priority** for salt resolution:

| Priority | Source | Behavior |
|----------|--------|----------|
| 1 (highest) | `DATA_COLLECTION_PSEUDONYM_SALT` env var | Operator-provided — always wins |
| 2 | `{output_dir}/.pseudonym_salt` file | Persisted on first auto-generation; loaded on subsequent starts |
| 3 (default) | Auto-generated `secrets.token_hex(32)` | 256-bit CSPRNG random value, written to the file above |

### Salt auto-generation (secure-by-default)

When `pseudonymize_identity=true` and no salt is configured:
1. `secrets.token_hex(32)` generates a 256-bit (64-char hex) random salt
2. The salt is persisted to `{output_dir}/.pseudonym_salt` for survival across restarts
3. An INFO-level log indicates the file location and reminds the operator that `DATA_COLLECTION_PSEUDONYM_SALT` can override

### Salt file security

The `.pseudonym_salt` file should:
- Have filesystem permissions `600` (owner read/write only)
- Be included in output directory backups (without it, historical hashes cannot be linked to identities)
- Be protected with the same level of care as any cryptographic key material

### Cluster deployments

Each node independently auto-generates its own salt. For cross-node identity correlation:
- Generate a single salt: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- Set `DATA_COLLECTION_PSEUDONYM_SALT=<generated-salt>` on all nodes
- This ensures the same user produces the same hash regardless of which node handled their request

## Dangerous configuration combinations

| Combination | Risk | Mitigation |
|-------------|------|------------|
| `collect_user_identity=true` + `pseudonymize_identity=false` | Raw user_id in plaintext on local disk | **Startup blocked** — requires `DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY=true` to proceed |
| `collect_channel_user_id=true` | Platform PII (email, phone) may be stored | Treat `channel_user_id` as sensitive; enable pseudonymization |
| `pseudonym_salt` reused across environments (dev/staging/prod) | Cross-environment user correlation | Use separate salts per environment |
| Salt rotation without migration | Old hashes unlinkable from new hashes | Plan for dual-hashing or batch re-processing on rotation |

## Fail-open and fail-closed design

The identity collection layer has a dual safety philosophy:

- **Fail-open** (runtime): If identity logic fails during a hook call (exception in middleware, missing context, corrupt session cache), the training record is **still written** — only the identity fields are absent. This ensures no data loss from identity logic failures.
- **Fail-closed** (startup): If `load_config()` itself fails (e.g., YAML parse error), identity collection is **entirely disabled** (`collect_user_identity=false`, `collect_channel_user_id=false`, `pseudonymize_identity=false`). This prevents silent plaintext leakage when the configuration is in an unknown state.

## Plaintext mode

Disabling pseudonymization (`pseudonymize_identity=false`) while keeping identity collection enabled writes raw user_id values to JSONL files. This mode is protected by an **explicit gate**:

```bash
DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY=true
```

Without this environment variable, `load_config()` raises a `ValueError` and the system refuses to start. This is a safety measure to prevent accidental plaintext identity recording.

**When plaintext mode is enabled:**
- A CRITICAL-level log message is emitted at startup acknowledging the risk
- Under GDPR, this constitutes processing of personal data — Article 35 DPIA (Data Protection Impact Assessment) is likely required
- **Only use in testing/development environments**
- Ensure the `output_dir` has strict filesystem permissions

## Right to Erasure (Article 17 GDPR)

Since identity fields are pseudonymized (not anonymized), you can fulfill DSAR erasure requests:

### Procedure

1. **Identify the data subject's raw user_id** from your authentication system
2. **Compute the hash** using the same salt and HMAC-SHA256:
   ```python
   import hmac, hashlib
   raw_id = "user-12345"  # from authentication system
   salt = "your-salt"     # from {output_dir}/.pseudonym_salt or DATA_COLLECTION_PSEUDONYM_SALT
   user_hash = hmac.new(salt.encode("utf-8"), raw_id.encode("utf-8"), hashlib.sha256).hexdigest()
   ```
3. **Search training logs** for records where `user_id == user_hash` or `channel_user_id == user_hash`:
   ```bash
   grep -r "user_id.*<user_hash>" {output_dir}/
   ```
4. **Delete or anonymize** the affected records from all `daily/`, `aggregated/`, and `flagged/` directories
5. **Re-aggregate** if records were removed from `aggregated/` to maintain data consistency
6. **Document** the deletion in your data processing register

### Salt loss contingency

If the `.pseudonym_salt` file is lost and no `DATA_COLLECTION_PSEUDONYM_SALT` backup exists:
- Historical hashes cannot be linked back to raw identities
- Erasure requests cannot be fulfilled for records written with the lost salt
- **Mitigation**: include `.pseudonym_salt` in your backup strategy alongside `output_dir`

## DSAR (Data Subject Access Request) procedure

Since identity fields are pseudonymized (not anonymized), you can fulfill DSAR requests:

1. **Identify the data subject's raw user_id** from your authentication system
2. **Compute the hash** using the same salt and HMAC-SHA256 (see procedure above)
3. **Search training logs** for records matching the hash
4. **Export** those records as required by the request

For **right to erasure**, see the dedicated section above.

## Salt rotation procedure

When rotating the pseudonymization salt:

1. **Stop data collection** or reconfigure to use the **new salt** going forward
2. **Keep the old salt** for DSAR queries on historical data
3. Optionally **re-hash** historical records with the new salt if cross-era analysis is required
4. Update `DATA_COLLECTION_PSEUDONYM_SALT` in your `.env` and restart

## Security model

- **CSPRNG**: Salt generation uses `secrets.token_hex()` — the operating system's cryptographically secure pseudo-random number generator (e.g., `/dev/urandom` on Linux)
- **HMAC-SHA256**: Pseudonymization uses Python's `hmac` module with SHA-256, providing 256-bit output (64-char hex digest)
- **File permissions**: Recommend `600` for `.pseudonym_salt` file. The `output_dir` should have restrictive permissions appropriate to your deployment's threat model.
- **Multi-node deployments**: Each node auto-generates an independent salt. For cross-node identity linking, inject a unified salt via `DATA_COLLECTION_PSEUDONYM_SALT`.
- **Pseudonymization, not anonymization**: HMAC is a keyed one-way function. Anyone with the salt can brute-force short user IDs (e.g., integer sequences). There is no "decrypt" operation, but the salt enables hash-to-identity mapping for authorized operators.

## Best practices

1. **Default-on**: identity collection is enabled by default (pseudonymized). Explicitly disable via config when identity fields are not needed
2. **Pseudonymize always**: keep `pseudonymize_identity=true` in production
3. **Separate salts**: use different salts per environment (dev/staging/prod)
4. **Audit regularly**: scan raw JSONL for unexpected plaintext identity fields
5. **Strip on export**: use `export_dataset(strip_identity=True)` when sharing data externally
6. **Log hygiene**: never log raw identity values in application logs or error reports
7. **Retention policy**: configure automated cleanup of raw JSONL after the aggregation pipeline has processed it
8. **Backup the salt**: include `.pseudonym_salt` in output directory backups to preserve erasure-request capability
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
