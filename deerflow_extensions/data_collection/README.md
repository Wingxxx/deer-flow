# DeerFlow Data Collection

Zero-intrusion side-channel collection of full-chain LLM inference data from DeerFlow, providing high-quality business-grounded training data for distillation.

## Architecture Overview

The system instruments the DeerFlow agent lifecycle at 6 collection points (P1-P6):

| Point | Hook Location | Data Captured |
|-------|--------------|---------------|
| **P1** | `before_model` / `abefore_model` (middleware) | Agent input: user query, system prompt, history context, RAG context |
| **P2** | `after_model` / `aafter_model` (middleware) | Model output: raw response, token usage, finish reason, thinking content |
| **P3** | `wrap_tool_call` / `awrap_tool_call` (before) | Tool invocation: tool name, parameters, call ID |
| **P4** | `wrap_tool_call` / `awrap_tool_call` (after) | Tool result: return value, error, latency |
| **P5** | `after_model` / `aafter_model` (middleware) | Intermediate state: step count, message count, accumulated tokens |
| **P6** | `after_agent` / `aafter_agent` (middleware) | Final response: total duration, total LLM/tool calls, resolution status |

Records are buffered in memory (configurable via `buffer_size`) and flushed asynchronously to daily JSONL files. All exceptions are caught and logged at DEBUG level -- a collector failure will never crash the agent.

## Quick Installation

Add the following 3 lines to `backend/app/gateway/app.py` (already present in the standard deployment):

```python
# Data collection system (zero-injection, monkey-patch based)
try:
    from deerflow_extensions.data_collection.startup import install_data_collection
    install_data_collection()
except ImportError:
    pass
```

Place the import block near the top of `app.py`, before the lifespan handler. The `try/except ImportError` ensures DeerFlow runs normally even if the `deerflow_extensions` package is not installed.

## Configuration

### YAML file

Create a `data_collection.yaml` anywhere accessible to the process:

```yaml
data_collection:
  enabled: true
  output_dir: ./data_collection_logs
  buffer_size: 500
  flush_interval_sec: 5.0
  max_file_size_mb: 100
  collect_agent_input: true
  collect_model_output: true
  collect_tool_calls: true
  collect_intermediate_state: false
  collect_final_response: true
  role_extract_mode: auto
  collect_user_identity: true
  collect_channel_user_id: true
  pseudonymize_identity: true
  pseudonym_salt: ""          # Leave empty to auto-generate a random salt
```

Pass the path to `install_data_collection(config_path="data_collection.yaml")`.

### Complete Configuration Reference

| Config Key | Type | Default | Env Variable | Description |
|-----------|------|---------|-------------|-------------|
| `enabled` | `bool` | `true` | `DATA_COLLECTION_ENABLED` | Enable/disable data collection |
| `output_dir` | `str` | `./data_collection_logs` | `DATA_COLLECTION_OUTPUT_DIR` | Output directory (contains raw/daily/archive subdirectories) |
| `buffer_size` | `int` | `500` | `DATA_COLLECTION_BUFFER_SIZE` | In-memory buffer size (record count) |
| `flush_interval_sec` | `float` | `5.0` | `DATA_COLLECTION_FLUSH_INTERVAL` | Periodic flush interval in seconds |
| `max_file_size_mb` | `int` | `100` | `DATA_COLLECTION_MAX_FILE_SIZE_MB` | Max daily file size in MB before rotation (clamped to ≥1) |
| `collect_agent_input` | `bool` | `true` | `DATA_COLLECTION_COLLECT_AGENT_INPUT` | Collect agent input (P1) |
| `collect_model_output` | `bool` | `true` | `DATA_COLLECTION_COLLECT_MODEL_OUTPUT` | Collect model output (P2) |
| `collect_tool_calls` | `bool` | `true` | `DATA_COLLECTION_COLLECT_TOOL_CALLS` | Collect tool calls (P3+P4) |
| `collect_intermediate_state` | `bool` | `false` | `DATA_COLLECTION_COLLECT_INTERMEDIATE_STATE` | Collect intermediate state (P5) — high volume, default off |
| `collect_final_response` | `bool` | `true` | `DATA_COLLECTION_COLLECT_FINAL_RESPONSE` | Collect final response (P6) |
| `role_extract_mode` | `str` | `auto` | `DATA_COLLECTION_ROLE_EXTRACT_MODE` | Role extraction mode: `auto` / `human` / `user` |
| `collect_user_identity` | `bool` | `true` | `DATA_COLLECTION_COLLECT_USER_IDENTITY` | Record authenticated user_id (pseudonymized when enabled) |
| `collect_channel_user_id` | `bool` | `true` | `DATA_COLLECTION_COLLECT_CHANNEL_USER_ID` | Record IM platform channel_user_id |
| `pseudonymize_identity` | `bool` | `true` | `DATA_COLLECTION_PSEUDONYMIZE_IDENTITY` | HMAC-SHA256 pseudonymize before writing |
| `pseudonym_salt` | `str` | auto-generated | `DATA_COLLECTION_PSEUDONYM_SALT` | HMAC salt (auto-generated via `secrets.token_hex(32)` if empty) |

### role_extract_mode configuration

The `role_extract_mode` setting controls how user messages are identified from LangGraph message objects:

| Mode | Description |
|------|-------------|
| `auto` (default) | Recognizes both `role="user"` and `type="human"` (LangGraph HumanMessage) |
| `human` | Only recognizes `type="human"` (LangGraph HumanMessage format) |
| `user` | Only recognizes `role="user"` (traditional format) |

For most DeerFlow deployments, `auto` is recommended as it handles both LangGraph's HumanMessage and dict-style messages correctly.

### Configuration priority

1. Standalone YAML file → 2. DeerFlow `config.yaml` → 3. Environment variables → 4. `DEFAULT_CONFIG` defaults

---

## Pseudonym Salt

The pseudonymization salt controls the HMAC-SHA256 key used to hash user identities before writing to JSONL. The salt has a **three-layer priority**:

| Priority | Source | Behavior |
|----------|--------|----------|
| 1 (highest) | `DATA_COLLECTION_PSEUDONYM_SALT` env var | Explicitly set by operator — always wins |
| 2 | `{output_dir}/.pseudonym_salt` file | Persisted on first auto-generation; read on subsequent starts |
| 3 (default) | Auto-generated `secrets.token_hex(32)` | 256-bit CSPRNG random value, generated once and persisted to file |

**Key behaviors:**
- The salt is **automatically generated** when `pseudonymize_identity=true` and no salt is configured. No manual setup required for basic operation.
- The generated salt is persisted to `{output_dir}/.pseudonym_salt` and survives restarts.
- Each machine independently generates its own salt. For **cluster deployments** where cross-node identity linking is needed, inject the same salt via `DATA_COLLECTION_PSEUDONYM_SALT` env var on all nodes.
- The salt file should be kept secret. Recommended permissions: `600` (owner read/write only).
- When backing up the output directory, include `.pseudonym_salt` to preserve the ability to link identities across the backup.

---

## Plaintext Identity Gate

For safety, writing raw (non-pseudonymized) user identities to JSONL requires **explicit operator confirmation**.

When `collect_user_identity=true` and `pseudonymize_identity=false`, the system will **refuse to start** unless you set:

```bash
DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY=true
```

This gate prevents accidental plaintext identity recording — a configuration that violates OWASP "Secure by Default" principles. If the allow flag is not set, `load_config()` raises a `ValueError` with a clear diagnostic message.

When the flag IS set, a CRITICAL-level log message is emitted at startup acknowledging the risk. This mode is **not recommended for production** and should only be used for debugging/testing.

---

## Full Environment Variable List

All 16 environment variables recognized by the data collection module:

| Env Variable | Type | Default | Example |
|-------------|------|---------|---------|
| `DATA_COLLECTION_ENABLED` | `bool` | `true` | `true` |
| `DATA_COLLECTION_OUTPUT_DIR` | `str` | `./data_collection_logs` | `/data/deerflow/training_logs` |
| `DATA_COLLECTION_BUFFER_SIZE` | `int` | `500` | `1000` |
| `DATA_COLLECTION_FLUSH_INTERVAL` | `float` | `5.0` | `10.0` |
| `DATA_COLLECTION_MAX_FILE_SIZE_MB` | `int` | `100` | `200` |
| `DATA_COLLECTION_ROLE_EXTRACT_MODE` | `str` | `auto` | `human` |
| `DATA_COLLECTION_COLLECT_AGENT_INPUT` | `bool` | `true` | `false` |
| `DATA_COLLECTION_COLLECT_MODEL_OUTPUT` | `bool` | `true` | `false` |
| `DATA_COLLECTION_COLLECT_TOOL_CALLS` | `bool` | `true` | `false` |
| `DATA_COLLECTION_COLLECT_INTERMEDIATE_STATE` | `bool` | `false` | `true` |
| `DATA_COLLECTION_COLLECT_FINAL_RESPONSE` | `bool` | `true` | `false` |
| `DATA_COLLECTION_COLLECT_USER_IDENTITY` | `bool` | `true` | `false` |
| `DATA_COLLECTION_COLLECT_CHANNEL_USER_ID` | `bool` | `true` | `false` |
| `DATA_COLLECTION_PSEUDONYMIZE_IDENTITY` | `bool` | `true` | `false` |
| `DATA_COLLECTION_PSEUDONYM_SALT` | `str` | auto | `abc123...` |
| `DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY` | `bool` | `false` | `true` |

---

### Identity collection (privacy-safe)

The system records `user_id` (Web UI users) and `channel_user_id` (IM platform users) in training data by default. Identity values are HMAC-SHA256 pseudonymized when `pseudonymize_identity=True` (also the default).

**Important security notes:**
- `collect_user_identity=true + pseudonymize_identity=false` requires `DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY=true` to start (see [Plaintext Identity Gate](#plaintext-identity-gate))
- The pseudonymization salt is auto-generated via `secrets.token_hex(32)` (256-bit CSPRNG) and persisted to `{output_dir}/.pseudonym_salt`
- `channel_user_id` may contain platform PII (e.g., email addresses) — treat with extra care
- Identity flows through the `identity=` parameter on each `record_*()` method call, injected by the middleware with zero intrusion on semantic method signatures
- See [PRIVACY.md](./PRIVACY.md) for GDPR compliance details, DSAR procedures, right-to-erasure workflows, and salt lifecycle management

## Data Directory Structure

All collected data is written under the `output_dir` (default: `./data_collection_logs/`):

```
{output_dir}/
├── .pseudonym_salt          # Auto-generated HMAC salt (keep secret!)
├── raw/                    # Reserved for future raw passthrough
├── daily/
│   └── train_data_YYYYMMDD.jsonl   # Current day's buffered records
├── archive/
│   └── train_data_YYYYMMDD_HHMMSS.jsonl  # Rotated files (>max_file_size_mb)
├── aggregated/
│   └── YYYYMMDD/
│       ├── train_data.jsonl         # Cleaned & aggregated training data
│       └── stats.json               # Pipeline statistics
└── flagged/
    └── YYYYMMDD/
        └── flagged_data.jsonl       # Error & short-reply records for Bad Case analysis
```

- **daily/**: Incremental raw JSONL, one file per day. Automatically rotates to `archive/` when exceeding `max_file_size_mb`.
- **aggregated/**: Output of `clean_and_aggregate.py`. Contains clean, deduplicated, session-merged training samples in OpenAI messages format.
- **flagged/**: Tagged records (errors, short replies) routed for Bad Case analysis. Preserved in full for downstream analysis pipelines.

## Daily Pipeline

Schedule `clean_and_aggregate.py` via cron to transform daily raw logs into training-ready datasets:

```cron
# Run daily at 03:00 UTC
0 3 * * * cd /path/to/deerflow && python -m deerflow_extensions.data_collection.scripts.clean_and_aggregate
```

The pipeline performs:
1. Filter incomplete records (missing session_id / user_query / raw_response)
2. Deduplicate by (user_query + raw_response) MD5 hash
3. Tag short responses (< 5 chars) and error cases for Bad Case analysis
4. Route tagged records to `flagged/YYYYMMDD/flagged_data.jsonl`
5. Aggregate clean samples into OpenAI messages-format training samples
6. Write `train_data.jsonl` and `stats.json` (with enhanced `flagged` block) to `aggregated/YYYYMMDD/`

## Format Validation

Use `validate_format.py` to verify aggregated data is compatible with LlamaFactory and other fine-tuning frameworks:

```bash
python -m deerflow_extensions.data_collection.scripts.validate_format \
    /data/deerflow/training_logs/aggregated/20260428/train_data.jsonl
```

Validation rules:
- **Rule1**: `messages` field must be a non-empty list
- **Rule2**: Each message must have a valid role (`system`/`user`/`assistant`/`tool`)
- **Rule3**: At least one `user` and one `assistant` message required
- **Rule4**: `tool_calls` only allowed on `assistant` messages
- **Rule5**: `tool_calls` entries must have valid `function.arguments` (JSON string)
- **Rule6**: Every `tool_call_id` in `tool` messages must have a matching assistant `tool_calls` entry
- **Rule7**: Each line must be valid JSON

Export to other formats:

```bash
python -c "
from deerflow_extensions.data_collection.scripts import export_dataset
export_dataset(
    '/data/deerflow/training_logs/aggregated/20260428/train_data.jsonl',
    '/data/deerflow/training_logs/aggregated/20260428/train_data_sharegpt.jsonl',
    format='sharegpt'
)
"
```

Supported formats: `llamafactory_messages` (pass-through), `sharegpt`, `alpaca_simple`.

## Uninstallation

Delete the 3-line import block from `backend/app/gateway/app.py`:

```python
# Data collection system (zero-injection, monkey-patch based)
try:
    from deerflow_extensions.data_collection.startup import install_data_collection
    install_data_collection()
except ImportError:
    pass
```

No other files are modified. The data collection directory and accumulated logs can be removed separately.

## Caveats

- Integration testing requires a running DeerFlow environment (LangGraph agent, FastAPI gateway) to validate end-to-end data flow.
- The monkey-patch (`install_data_collection`) must be called before any agent middleware chain is built -- importing at module level in `app.py` is the safest approach.
- If the package is not installed, the `try/except ImportError` guarantees zero impact on DeerFlow operations.
- Collected data lives on local disk; set up external backup/offload for production deployments.
- The collector uses thread-safe buffering with `threading.Lock` to support concurrent writes from multiple sessions.
- Middleware methods support both sync and async execution paths for full LangGraph compatibility.
- Identity fields (`user_id`, `channel_user_id`) are written to raw JSONL — **never include raw identity values in application logs, error reports, or any external pipeline** without going through the export layer's `strip_identity` parameter.
- When exporting datasets for external fine-tuning, pass `strip_identity=True` to `export_dataset()` to strip `user_id`, `channel_user_id`, and `session_id` from the exported output — this happens before format conversion, so no converter can accidentally propagate identity fields.
- The pseudonymization salt (auto-generated at `{output_dir}/.pseudonym_salt`) must be kept secret and rotated periodically — leaking the salt allows hash-to-identity mapping. See [PRIVACY.md](./PRIVACY.md) for key rotation procedures.
- Setting `collect_user_identity=true` with `pseudonymize_identity=false` requires the explicit environment variable `DATA_COLLECTION_ALLOW_PLAINTEXT_IDENTITY=true`. Without it, the system will refuse to start (fail-closed).
- `max_file_size_mb` is clamped to a minimum of 1 MB — negative or zero values are treated as 1 to prevent infinite file rotation.
# DeerFlow Distillation Data Collection System

Zero-intrusion side-channel collection of full-chain LLM inference data from DeerFlow, providing high-quality business-grounded training data for distillation.

## Architecture Overview

The system instruments the DeerFlow agent lifecycle at 6 collection points (P1-P6):

| Point | Hook Location | Data Captured |
|-------|--------------|---------------|
| **P1** | `before_model` / `abefore_model` (middleware) | Agent input: user query, system prompt, history context, RAG context |
| **P2** | `after_model` / `aafter_model` (middleware) | Model output: raw response, token usage, finish reason, thinking content |
| **P3** | `wrap_tool_call` / `awrap_tool_call` (before) | Tool invocation: tool name, parameters, call ID |
| **P4** | `wrap_tool_call` / `awrap_tool_call` (after) | Tool result: return value, error, latency |
| **P5** | `after_model` / `aafter_model` (middleware) | Intermediate state: step count, message count, accumulated tokens |
| **P6** | `after_agent` / `aafter_agent` (middleware) | Final response: total duration, total LLM/tool calls, resolution status |

Records are buffered in memory (configurable via `buffer_size`) and flushed asynchronously to daily JSONL files. All exceptions are caught and logged at DEBUG level -- a collector failure will never crash the agent.

## Quick Installation

Add the following 3 lines to `backend/app/gateway/app.py` (already present in the standard deployment):

```python
# Data collection system (zero-injection, monkey-patch based)
try:
    from deerflow_extensions.data_collection.startup import install_data_collection
    install_data_collection()
except ImportError:
    pass
```

Place the import block near the top of `app.py`, before the lifespan handler. The `try/except ImportError` ensures DeerFlow runs normally even if the `deerflow_extensions` package is not installed.

## Configuration

### YAML file

Create a `data_collection.yaml` anywhere accessible to the process:

```yaml
data_collection:
  enabled: true
  output_dir: /data/deerflow/training_logs
  buffer_size: 500
  flush_interval_sec: 5.0
  max_file_size_mb: 100
  collect_agent_input: true
  collect_model_output: true
  collect_tool_calls: true
  collect_intermediate_state: false
  collect_final_response: true
```

Pass the path to `install_data_collection(config_path="data_collection.yaml")`.

### Environment variables

Override individual settings without a YAML file:

| Variable | Config Key | Example |
|----------|-----------|---------|
| `DATA_COLLECTION_ENABLED` | enabled | `true` |
| `DATA_COLLECTION_OUTPUT_DIR` | output_dir | `/custom/path` |
| `DATA_COLLECTION_BUFFER_SIZE` | buffer_size | `1000` |
| `DATA_COLLECTION_FLUSH_INTERVAL` | flush_interval_sec | `10.0` |
| `DATA_COLLECTION_ROLE_EXTRACT_MODE` | role_extract_mode | `auto` |

### role_extract_mode configuration

The `role_extract_mode` setting controls how user messages are identified from LangGraph message objects:

| Mode | Description |
|------|-------------|
| `auto` (default) | Recognizes both `role="user"` and `type="human"` (LangGraph HumanMessage) |
| `human` | Only recognizes `type="human"` (LangGraph HumanMessage format) |
| `user` | Only recognizes `role="user"` (traditional format) |

For most DeerFlow deployments, `auto` is recommended as it handles both LangGraph's HumanMessage and dict-style messages correctly.

### Configuration priority

1. Standalone YAML file → 2. DeerFlow `config.yaml` → 3. Environment variables → 4. `DEFAULT_CONFIG` defaults

### Identity collection (privacy-safe)

The system records `user_id` (Web UI users) and `channel_user_id` (IM platform users) in training data by default. Identity values are HMAC-SHA256 pseudonymized when `pseudonymize_identity=True` (also the default).

| Variable | Config Key | Type | Default | Description |
|----------|-----------|------|---------|-------------|
| `DATA_COLLECTION_COLLECT_USER_IDENTITY` | `collect_user_identity` | `bool` | `true` | Record authenticated user_id |
| `DATA_COLLECTION_COLLECT_CHANNEL_USER_ID` | `collect_channel_user_id` | `bool` | `true` | Record IM platform channel_user_id |
| — | `pseudonymize_identity` | `bool` | `true` | HMAC-SHA256 hash before writing |
| `DATA_COLLECTION_PSEUDONYM_SALT` | `pseudonym_salt` | `str` | `""` | Salt for HMAC (empty → WARNING) |

**Important security notes:**
- `collect_user_identity=true + pseudonymize_identity=false` writes **raw user_id in plaintext** — a WARNING is logged at startup
- `pseudonym_salt=""` when `pseudonymize_identity=true` produces a WARNING — hashes will NOT be linkable across sessions (each restart generates effectively unique hashes)
- `channel_user_id` may contain platform PII (e.g., email addresses) — treat with extra care
- Identity is **not** collected on any `record_*` method's parameter list — it flows through the `record()` uniform injection layer, zero intrusion on semantic method signatures
- See [PRIVACY.md](./PRIVACY.md) for GDPR compliance details, DSAR procedures, and the three pseudonymization modes

## Data Directory Structure

All collected data is written under the `output_dir` (default: `/data/deerflow/training_logs/`):

```
/data/deerflow/training_logs/
├── raw/                    # Reserved for future raw passthrough
├── daily/
│   └── train_data_YYYYMMDD.jsonl   # Current day's buffered records
├── archive/
│   └── train_data_YYYYMMDD_HHMMSS.jsonl  # Rotated files (>max_file_size_mb)
├── aggregated/
│   └── YYYYMMDD/
│       ├── train_data.jsonl         # Cleaned & aggregated training data
│       └── stats.json               # Pipeline statistics
└── flagged/
    └── YYYYMMDD/
        └── flagged_data.jsonl       # Error & short-reply records for Bad Case analysis
```

- **daily/**: Incremental raw JSONL, one file per day. Automatically rotates to `archive/` when exceeding `max_file_size_mb`.
- **aggregated/**: Output of `clean_and_aggregate.py`. Contains clean, deduplicated, session-merged training samples in OpenAI messages format.
- **flagged/**: Tagged records (errors, short replies) routed for Bad Case analysis. Preserved in full for downstream analysis pipelines.

## Daily Pipeline

Schedule `clean_and_aggregate.py` via cron to transform daily raw logs into training-ready datasets:

```cron
# Run daily at 03:00 UTC
0 3 * * * cd /path/to/deerflow && python -m deerflow_extensions.data_collection.scripts.clean_and_aggregate
```

The pipeline performs:
1. Filter incomplete records (missing session_id / user_query / raw_response)
2. Deduplicate by (user_query + raw_response) MD5 hash
3. Tag short responses (< 5 chars) and error cases for Bad Case analysis
4. Route tagged records to `flagged/YYYYMMDD/flagged_data.jsonl`
5. Aggregate clean samples into OpenAI messages-format training samples
6. Write `train_data.jsonl` and `stats.json` (with enhanced `flagged` block) to `aggregated/YYYYMMDD/`

## Format Validation

Use `validate_format.py` to verify aggregated data is compatible with LlamaFactory and other fine-tuning frameworks:

```bash
python -m deerflow_extensions.data_collection.scripts.validate_format \
    /data/deerflow/training_logs/aggregated/20260428/train_data.jsonl
```

Validation rules:
- **Rule1**: `messages` field must be a non-empty list
- **Rule2**: Each message must have a valid role (`system`/`user`/`assistant`/`tool`)
- **Rule3**: At least one `user` and one `assistant` message required
- **Rule4**: `tool_calls` only allowed on `assistant` messages
- **Rule5**: `tool_calls` entries must have valid `function.arguments` (JSON string)
- **Rule6**: Every `tool_call_id` in `tool` messages must have a matching assistant `tool_calls` entry
- **Rule7**: Each line must be valid JSON

Export to other formats:

```bash
python -c "
from deerflow_extensions.data_collection.scripts import export_dataset
export_dataset(
    '/data/deerflow/training_logs/aggregated/20260428/train_data.jsonl',
    '/data/deerflow/training_logs/aggregated/20260428/train_data_sharegpt.jsonl',
    format='sharegpt'
)
"
```

Supported formats: `llamafactory_messages` (pass-through), `sharegpt`, `alpaca_simple`.

## Uninstallation

Delete the 3-line import block from `backend/app/gateway/app.py`:

```python
# Data collection system (zero-injection, monkey-patch based)
try:
    from deerflow_extensions.data_collection.startup import install_data_collection
    install_data_collection()
except ImportError:
    pass
```

No other files are modified. The data collection directory and accumulated logs can be removed separately.

## Caveats

- Integration testing requires a running DeerFlow environment (LangGraph agent, FastAPI gateway) to validate end-to-end data flow.
- The monkey-patch (`install_data_collection`) must be called before any agent middleware chain is built -- importing at module level in `app.py` is the safest approach.
- If the package is not installed, the `try/except ImportError` guarantees zero impact on DeerFlow operations.
- Collected data lives on local disk; set up external backup/offload for production deployments.
- The collector uses thread-safe buffering with `threading.Lock` to support concurrent writes from multiple sessions.
- Middleware methods support both sync and async execution paths for full LangGraph compatibility.
- Identity fields (`user_id`, `channel_user_id`) are written to raw JSONL — **never include raw identity values in application logs, error reports, or any external pipeline** without going through the export layer's `strip_identity` parameter.
- When exporting datasets for external fine-tuning, pass `strip_identity=True` to `export_dataset()` to strip `user_id`, `channel_user_id`, and `session_id` from the exported output — this happens before format conversion, so no converter can accidentally propagate identity fields.
- The pseudonymization salt (`DATA_COLLECTION_PSEUDONYM_SALT`) must be kept secret and rotated periodically — leaking the salt allows hash-to-identity mapping. See PRIVACY.md for key rotation procedures.

WING
