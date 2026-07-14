# Changelog

All notable changes to the Data Collection module.

## [Unreleased]

### Added
- `_load_or_create_salt()` function for automatic pseudonym salt generation via `secrets.token_hex(32)` (256-bit CSPRNG)
- Salt file persistence to `{output_dir}/.pseudonym_salt` for cross-restart salt survival
- Plaintext identity gate: `DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY=true` required to disable pseudonymization while keeping identity collection enabled
- 16 environment variables for all configuration keys (7 new: `COLLECT_AGENT_INPUT`, `COLLECT_MODEL_OUTPUT`, `COLLECT_TOOL_CALLS`, `COLLECT_INTERMEDIATE_STATE`, `COLLECT_FINAL_RESPONSE`, `MAX_FILE_SIZE_MB`, `PSEUDONYMIZE_IDENTITY`)
- `identity` parameter on all `TrainingDataCollector.record_*()` methods for explicit identity injection
- Identity key conflict detection in `record()` with WARNING log
- `test_pseudonymize.py`: 10 unit tests for HMAC-SHA256 pseudonymization correctness
- `test_concurrent_identity_isolation`: concurrent identity isolation test
- Per-hook identity passing verification tests (6 hooks × 1 test each)
- `config.example.yaml` with full 15-key configuration template

### Changed
- **BREAKING**: `pseudonym_salt` default changed from empty string to auto-generated random salt (`secrets.token_hex(32)`)
- **BREAKING**: `TrainingDataCollector._current_identity` shared mutable attribute removed — identity now passes via `identity=` parameter
- **BREAKING**: `DataCollectionMiddleware._prepare_identity_for_collector()` now returns `dict | None` instead of setting `collector._current_identity`
- **BREAKING**: `DataCollectionMiddleware._restore_identity_for_collector()` now returns `dict | None` (defensive copy) instead of setting `collector._current_identity`
- **Potential**: `DEFAULT_CONFIG["output_dir"]` changed from `/data/deerflow/training_logs` to `./data_collection_logs`
- `max_file_size_mb` negative values clamped to 1 MB (prevented infinite file rotation)
- `record()` method signature updated: `record(sample_type, data, identity=None)`
- All 6 semantic `record_*()` methods now accept `identity: dict | None = None` tail parameter
- `record_*()` semantic methods: identity now flows through `identity=` kwarg, not through shared mutable state
- README.md: configuration table expanded from 8 to 15 rows; added Pseudonym Salt, Plaintext Identity Gate, and Full Environment Variable List sections
- PRIVACY.md: salt management restructured as lifecycle management; added Right to Erasure and Plaintext Mode sections; updated security model
- API.md: all method signatures updated with `identity=` parameter; added `_load_or_create_salt()` documentation
- `_ENV_VAR_MAP` expanded from 8 to 15 entries for full containerized deployment coverage

### Fixed
- **Critical**: `load_config()` exception in middleware `__init__` no longer silently enables pseudonymization with empty salt (fail-closed: all identity collection disabled on config failure)
- **High**: `max_file_size_mb=-1` caused infinite file rotation on every record — now clamped to minimum 1 MB
- **Medium**: `collector._current_identity` shared mutable state race condition eliminated — identity now flows through parameter passing
- **Medium**: Plaintext identity recording (`collect_user_identity=true + pseudonymize_identity=false`) now blocked at startup (was WARNING-only)

### Security
- Salt generation uses `secrets.token_hex()` (OS CSPRNG, e.g., `/dev/urandom`) — 256-bit entropy meeting NIST SP 800-131A requirements
- Plaintext identity gate requires explicit `DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY=true` to bypass, preventing accidental PII exposure
- Fail-closed startup: config load failure now disables all identity collection instead of falling back to plaintext
- Salt file permissions recommendation: `600` (owner read/write only)
