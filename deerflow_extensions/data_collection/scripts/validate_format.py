import json
import sys


class FormatValidator:
    REQUIRED_ROLES = {"system", "user", "assistant"}

    @staticmethod
    def validate(sample):
        issues = []

        if not isinstance(sample, dict) or "messages" not in sample:
            issues.append("Sample must be a dict with a 'messages' field")
            return issues

        messages = sample["messages"]

        if not isinstance(messages, list) or len(messages) == 0:
            issues.append("Rule1: messages field must be a non-empty list")
            return issues

        roles_seen = set()
        assistant_tool_calls_ids = set()
        tool_call_ids_in_messages = []

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                issues.append(f"Rule2: messages[{i}] is not a dict")
                continue

            role = msg.get("role")
            if role not in {"system", "user", "assistant", "tool"}:
                issues.append(
                    f"Rule2: messages[{i}] has invalid role '{role}'; "
                    f"must be one of system/user/assistant/tool"
                )
                continue

            roles_seen.add(role)

            if "tool_calls" in msg and role != "assistant":
                issues.append(
                    f"Rule4: messages[{i}] has tool_calls but role is '{role}', "
                    f"not 'assistant'"
                )

            if role == "assistant" and "tool_calls" in msg:
                tool_calls = msg["tool_calls"]
                if not isinstance(tool_calls, list):
                    issues.append(
                        f"Rule4: messages[{i}].tool_calls must be a list"
                    )
                else:
                    for j, tc in enumerate(tool_calls):
                        if not isinstance(tc, dict):
                            issues.append(
                                f"Rule5: messages[{i}].tool_calls[{j}] is not a dict"
                            )
                            continue
                        tc_id = tc.get("id")
                        if tc_id:
                            assistant_tool_calls_ids.add(tc_id)
                        function = tc.get("function")
                        if not isinstance(function, dict):
                            issues.append(
                                f"Rule5: messages[{i}].tool_calls[{j}].function "
                                f"must be a dict"
                            )
                        else:
                            arguments = function.get("arguments")
                            if not isinstance(arguments, str):
                                issues.append(
                                    f"Rule5: messages[{i}].tool_calls[{j}]."
                                    f"function.arguments must be a JSON string, "
                                    f"got {type(arguments).__name__}"
                                )
                            else:
                                try:
                                    json.loads(arguments)
                                except json.JSONDecodeError:
                                    issues.append(
                                        f"Rule5: messages[{i}].tool_calls[{j}]."
                                        f"function.arguments is not valid JSON: "
                                        f"{arguments[:200]}"
                                    )

            if role == "tool":
                tcid = msg.get("tool_call_id")
                if tcid:
                    tool_call_ids_in_messages.append((i, tcid))

        if "user" not in roles_seen:
            issues.append("Rule3: sample must contain at least one 'user' message")

        if "assistant" not in roles_seen:
            issues.append(
                "Rule3: sample must contain at least one 'assistant' message"
            )

        for idx, tcid in tool_call_ids_in_messages:
            if tcid not in assistant_tool_calls_ids:
                issues.append(
                    f"Rule6: messages[{idx}].tool_call_id '{tcid}' has no "
                    f"corresponding entry in any assistant's tool_calls"
                )

        return issues

    @staticmethod
    def validate_file(file_path):
        total_samples = 0
        valid_samples = 0
        invalid_samples = 0
        sample_errors = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        total_samples += 1
                        invalid_samples += 1
                        sample_errors.append(
                            {
                                "line": line_no,
                                "errors": ["Rule7: empty line is not valid JSON"],
                            }
                        )
                        continue

                    try:
                        sample = json.loads(line)
                    except json.JSONDecodeError as e:
                        total_samples += 1
                        invalid_samples += 1
                        error_msg = f"Rule7: line cannot be parsed by json.loads: {e}"
                        sample_errors.append(
                            {"line": line_no, "errors": [error_msg]}
                        )
                        continue

                    total_samples += 1
                    issues = FormatValidator.validate(sample)
                    if issues:
                        invalid_samples += 1
                        sample_errors.append(
                            {"line": line_no, "errors": issues}
                        )
                    else:
                        valid_samples += 1

        except FileNotFoundError:
            return {
                "error": f"File not found: {file_path}",
                "total_samples": 0,
                "valid_samples": 0,
                "invalid_samples": 0,
                "valid_rate": 0.0,
                "sample_errors": [],
            }
        except Exception as e:
            return {
                "error": f"Unexpected error reading file: {e}",
                "total_samples": total_samples,
                "valid_samples": valid_samples,
                "invalid_samples": invalid_samples,
                "valid_rate": (
                    round(valid_samples / total_samples, 4) if total_samples > 0 else 0.0
                ),
                "sample_errors": sample_errors,
            }

        valid_rate = (
            round(valid_samples / total_samples, 4) if total_samples > 0 else 0.0
        )

        return {
            "total_samples": total_samples,
            "valid_samples": valid_samples,
            "invalid_samples": invalid_samples,
            "valid_rate": valid_rate,
            "sample_errors": sample_errors,
        }


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_format.py <jsonl_file_path>", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    report = FormatValidator.validate_file(file_path)

    if "error" in report:
        print(f"ERROR: {report['error']}", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("  Format Validation Report")
    print("=" * 60)
    print(f"  File        : {file_path}")
    print(f"  Total       : {report['total_samples']}")
    print(f"  Valid       : {report['valid_samples']}")
    print(f"  Invalid     : {report['invalid_samples']}")
    print(f"  Valid Rate  : {report['valid_rate']:.2%}")
    print("=" * 60)

    if report["sample_errors"]:
        print("\n  Top 10 Sample Errors:")
        print("-" * 60)
        for entry in report["sample_errors"][:10]:
            print(f"  Line {entry['line']}:")
            for err in entry["errors"]:
                print(f"    - {err}")
            print()
    else:
        print("\n  All samples are fully compliant.")

    if report["invalid_samples"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
