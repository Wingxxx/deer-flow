# API Reference

## Collector

### `TrainingDataCollector`

```python
class TrainingDataCollector(config: dict | None = None)
```

Process-level singleton for async buffered writing of training data. All collection methods are non-blocking, exception-safe, and thread-safe. Uses `threading.Lock` to protect concurrent buffer access from multiple sessions.

**Constructor parameters:**
- `config` -- Optional config dict. Falls back to `load_config()` defaults.

---

#### `record(sample_type: str, data: dict) -> None`

General-purpose record method. All semantic methods delegate here. The record is timestamped (UTC ISO-8601), buffered, and flushed asynchronously.

- `sample_type` -- One of: `agent_input`, `model_output`, `tool_call_request`, `tool_call_result`, `agent_intermediate_state`, `final_response`.
- `data` -- Arbitrary JSON-serializable payload.

---

#### `record_agent_input(session_id, user_query, system_prompt, history_context, rag_context="", agent_config=None) -> None`

**Collection point P1**: Record agent input.

- `session_id` -- Conversation thread ID.
- `user_query` -- The user's raw input text.
- `system_prompt` -- System prompt used for this session.
- `history_context` -- Recent message history (last 4 messages).
- `rag_context` -- Retrieved RAG context text.
- `agent_config` -- Optional agent configuration dict.

---

#### `record_model_output(session_id, step_number, raw_response, response_type, finish_reason, tool_calls, token_usage, thinking_content, latency_ms) -> None`

**Collection point P2**: Record model output.

- `step_number` -- Zero-based step index within the session.
- `raw_response` -- The model's response text.
- `response_type` -- `"text"` or `"tool_calls"`.
- `finish_reason` -- LLM finish reason (e.g. `"stop"`, `"tool_calls"`).
- `tool_calls` -- List of tool call dicts with `tool_name`, `call_id`, `arguments`.
- `token_usage` -- Dict with `prompt_tokens`, `completion_tokens`, `total_tokens`.
- `thinking_content` -- Chain-of-thought or reasoning content.
- `latency_ms` -- Model inference latency in milliseconds.

---

#### `record_tool_call(session_id, step_number, tool_name, tool_params, call_id, tool_result=None, error=None, duration_ms=0.0, phase="request") -> None`

**Collection points P3+P4**: Record tool call request and result.

- `tool_name` -- Name of the invoked tool.
- `tool_params` -- Dict of tool arguments.
- `call_id` -- Unique identifier for this tool call.
- `tool_result` -- Tool return value (only in `"result"` phase).
- `error` -- Error message if tool raised (only in `"result"` phase).
- `duration_ms` -- Tool execution duration.
- `phase` -- `"request"` (P3) or `"result"` (P4).

---

#### `record_intermediate_state(session_id, step_number, total_steps, message_count, accumulated_tokens, tools_called, loop_detected=False) -> None`

**Collection point P5**: Record agent intermediate state.

- `total_steps` -- Maximum allowed steps for this agent.
- `message_count` -- Total messages in the conversation so far.
- `accumulated_tokens` -- Running token usage dict.
- `tools_called` -- List of tool names invoked in this step.
- `loop_detected` -- Whether a loop was detected.

---

#### `record_final_response(session_id, final_response, total_duration_ms, total_llm_calls, total_tool_calls, total_tokens, resolution_status) -> None`

**Collection point P6**: Record final agent response.

- `final_response` -- The agent's final answer text.
- `total_duration_ms` -- Total session duration in milliseconds.
- `total_llm_calls` -- Total LLM invocations in this session.
- `total_tool_calls` -- Total tool invocations in this session.
- `total_tokens` -- Total tokens consumed.
- `resolution_status` -- `"completed"` or `"error"`.

---

#### `async shutdown() -> None`

Gracefully shut down the collector. Cancels the periodic flush task and performs a final flush of all buffered records.

---

### `get_collector() -> TrainingDataCollector`

```python
def get_collector() -> TrainingDataCollector
```

Return the global collector singleton. Creates a new instance with default config on first access.

---

### `set_collector(collector: TrainingDataCollector) -> None`

```python
def set_collector(collector: TrainingDataCollector) -> None
```

Replace the global collector instance. Intended for testing and mock injection.

---

## Middleware

### `DataCollectionMiddleware`

```python
class DataCollectionMiddleware(AgentMiddleware)
```

DeerFlow agent middleware that hooks into the agent lifecycle at `before_model`, `abefore_model`, `after_model`, `aafter_model`, `wrap_tool_call`, `awrap_tool_call`, `after_agent`, and `aafter_agent` to drive all 6 collection points.

Inherits from `deerflow.agents.middlewares.base.AgentMiddleware`. Automatically obtains the collector singleton via `get_collector()`.

All middleware methods are fully thread-safe and support concurrent session execution. The async methods (`abefore_model`, `aafter_model`, `aafter_agent`) delegate to their sync counterparts to ensure consistent behavior.

---

## Config

### `load_config(config_path: str | None = None) -> dict[str, Any]`

```python
def load_config(config_path: str | None = None) -> dict[str, Any]
```

Load and merge configuration from available sources. Returns a dict compatible with `TrainingDataCollector.__init__`.

**Priority (highest to lowest):**
1. Standalone YAML file specified by `config_path`
2. DeerFlow `config.yaml` `data_collection` section
3. Environment variable overrides (`DATA_COLLECTION_*`)
4. `DEFAULT_CONFIG` fallback values

---

### `DEFAULT_CONFIG`

```python
DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "output_dir": "/data/deerflow/training_logs",
    "buffer_size": 500,
    "flush_interval_sec": 5.0,
    "max_file_size_mb": 100,
    "collect_agent_input": True,
    "collect_model_output": True,
    "collect_tool_calls": True,
    "collect_intermediate_state": False,
    "collect_final_response": True,
}
```

Default configuration values used when no external config source is available.

---

## Startup

### `install_data_collection(config_path: str | None = None) -> None`

```python
def install_data_collection(config_path: str | None = None) -> None
```

Monkey-patch `deerflow.agents.lead_agent.agent._build_middlewares` to inject `DataCollectionMiddleware` into every new agent middleware chain.

- Idempotent: subsequent calls are no-ops.
- Uses `try/except` internally -- if `deerflow` is not importable, the patch silently degrades.
- `config_path` is forwarded to `load_config()` to check the `enabled` flag.
- Only patches the agent module (not the client module) for minimal intrusion.

---

## Scripts

### `run_daily_pipeline(date_str: str | None = None) -> dict[str, Any]`

```python
def run_daily_pipeline(date_str: str | None = None) -> dict[str, Any]
```

Execute the full ETL pipeline for a given date. Loads raw JSONL from `daily/`, cleans, aggregates by session, and writes training data to `aggregated/YYYYMMDD/`.

- `date_str` -- Date in `YYYYMMDD` format. Defaults to current UTC date.
- **Returns** -- Dict with `raw_count`, `cleaned_count`, `train_sample_count`, `categories`.
- **Raises** -- `FileNotFoundError` if the daily JSONL file does not exist.

---

### `export_dataset(input_path, output_path, format="llamafactory_messages") -> None`

```python
def export_dataset(
    input_path: str,
    output_path: str,
    format: OutputFormat = "llamafactory_messages",
) -> None
```

Convert a messages-format JSONL dataset to another training framework format.

- `input_path` -- Path to aggregated `train_data.jsonl`.
- `output_path` -- Destination path for the converted JSONL.
- `format` -- One of `"llamafactory_messages"` (pass-through), `"sharegpt"`, `"alpaca_simple"`.
- **Raises** -- `FileNotFoundError`, `KeyError` (unknown format).

---

### `FormatValidator`

```python
class FormatValidator
```

Static validation utilities for LlamaFactory-compatible messages format.

---

#### `validate(sample: dict) -> list[str]`

Validate a single training sample against LlamaFactory format rules. Returns a list of issue descriptions (empty list = valid).

Rules checked: required roles, role validity, `tool_calls` placement, `function.arguments` JSON validity, `tool_call_id` cross-referencing.

---

#### `validate_file(file_path: str) -> dict`

Validate every line in a JSONL file. Returns a report dict:

```python
{
    "total_samples": int,
    "valid_samples": int,
    "invalid_samples": int,
    "valid_rate": float,       # 0.0 - 1.0
    "sample_errors": list[dict],  # {"line": int, "errors": [str, ...]}
}
```

On I/O errors, returns a dict with an `"error"` key instead.

---

### `generate_daily_report(date_str: str) -> dict`

```python
def generate_daily_report(date_str: str) -> dict
```

Read the `stats.json` produced by `run_daily_pipeline` and produce a quality summary with category distribution and estimated disk usage.

- `date_str` -- Date in `YYYYMMDD` format.
- **Returns** -- Dict with `date`, `total_raw`, `total_train`, `categories`, `category_distribution`, `estimated_disk_mb`.
- **Raises** -- `FileNotFoundError`, `RuntimeError`.

---

## Helper Types

### `OutputFormat`

```python
OutputFormat = Literal["llamafactory_messages", "sharegpt", "alpaca_simple"]
```

Supported export formats for `export_dataset()`.

---

### `convert_messages_to_sharegpt(sample: dict) -> dict`

```python
def convert_messages_to_sharegpt(sample: dict) -> dict
```

Convert a single messages-format sample to ShareGPT `{"conversations": [...]}` format.

---

### `convert_messages_to_alpaca_simple(sample: dict) -> dict | None`

```python
def convert_messages_to_alpaca_simple(sample: dict) -> dict | None
```

Convert a single messages-format sample to Alpaca `{"instruction", "input", "output"}` format. Returns `None` if the sample contains tool calls or lacks required fields.

WING
