# Mavis-Eval Assertion DSL

Executable assertions are deterministic gates or quality signals. They run before any judge model is asked to score semantic quality.

## Common Fields

Every assertion has:

- `id`: stable identifier within the case.
- `type`: assertion operator.

## Supported Types

| Type | Purpose | Required fields |
|---|---|---|
| `file_exists` | Required artifact exists in the run directory | `path` |
| `file_not_exists` | Forbidden artifact was not created | `path` |
| `directory_exists` | Required directory exists | `path` |
| `json_valid` | File parses as JSON | `path` |
| `json_field_equals` | JSON dot path equals an expected value | `path`, `json_path`, `equals` |
| `state_json_equals` | Alias for checking JSON state snapshots | `path`, `json_path`, `equals` |
| `mock_state_equals` | Alias for `state_json_equals` | `path`, `json_path`, `equals` |
| `csv_columns_present` | CSV has required headers | `path`, `columns` |
| `csv_row_count_min` | CSV has at least N data rows | `path`, `min` |
| `contains_text` | Text artifact contains all required strings | `path`, `text` or `all_of`, optional `ignore_case` |
| `regex_file` | Text artifact has at least N regex matches | `path`, `pattern`, optional `min_count` |
| `word_count_max` | Text artifact stays under a word cap | `path`, `max` |
| `tool_called` | Trajectory contains a tool call | `tool`, optional `min_count` |
| `tool_not_called` | Trajectory does not contain a tool call | `tool` |
| `no_forbidden_tool` | Trajectory avoids case `forbidden_tools` or assertion `tools` | optional `tools` |
| `no_forbidden_url` | Trajectory URLs stay within `environment.frozen_urls` or assertion `allowed_urls` | optional `allowed_urls` |
| `no_forbidden_action` | Trajectory does not contain blocked action patterns | `patterns` |

Assertion paths are relative to the run directory. Absolute paths and path traversal are rejected.

## Run Directory Contract

The MVP harness expects:

```text
runs/<case_id>/
  trajectory.jsonl
  output/
  state/
```

`trajectory.jsonl` is captured by the external harness. It should contain only tool calls, arguments, observations, state diffs, latency, and cost. It must not contain hidden model reasoning.
