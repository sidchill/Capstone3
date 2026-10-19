import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def _log_path() -> Path:
    default = "/tmp/tokenomics.jsonl" if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else "tokenomics.jsonl"
    return Path(os.getenv("TOKENOMICS_LOG_PATH", default))


def _append(record: dict) -> None:
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, default=str) + "\n")


def _cost_usd(input_tokens: int, output_tokens: int):
    input_rate = os.getenv("BEDROCK_INPUT_COST_PER_1M")
    output_rate = os.getenv("BEDROCK_OUTPUT_COST_PER_1M")
    if input_rate is None or output_rate is None:
        return None
    return (
        input_tokens * float(input_rate)
        + output_tokens * float(output_rate)
    ) / 1_000_000

def log_claude_call(component: str, input_tokens: int, output_tokens: int) -> None:
    _append({
        "type": "claude_call",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": component,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": _cost_usd(input_tokens, output_tokens),
    })

def log_decision(stage: str, question: str, details: dict) -> None:
    _append({
        "type": "decision",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "question": question,
        "details": details,
    })


def _usage_from_result(result: dict | None) -> dict:
    if not result:
        return {"input": 0, "output": 0}

    usage = result.get("metadata", {}).get("token_usage", {})
    return {
        "input": int(usage.get("input", usage.get("input_tokens", 0))),
        "output": int(usage.get("output", usage.get("output_tokens", 0))),
    }


def run_traced_query(orchestrator, question: str) -> dict:
    trace_id = str(uuid.uuid4())
    log_decision("query_start", question, {"trace_id": trace_id})

    initial_state = {
        "question": question,
        "route": None,
        "sql_result": None,
        "retrieval_result": None,
        "final_answer": None,
        "token_usage": None,
    }

    try:
        result = orchestrator.invoke(initial_state)
    except Exception as error:
        log_decision("query_error", question, {
            "trace_id": trace_id,
            "error": str(error),
        })
        raise

    sql_usage = _usage_from_result(result.get("sql_result"))
    retrieval_usage = _usage_from_result(result.get("retrieval_result"))
    synthesis_usage = result.get("token_usage") or {}
    synthesis_usage = {
        "input": int(synthesis_usage.get("input", 0)),
        "output": int(synthesis_usage.get("output", 0)),
    }

    stages = {
        "sql_agent": sql_usage,
        "retrieval_agent": retrieval_usage,
        "synthesis": synthesis_usage,
    }
    total_input = sum(item["input"] for item in stages.values())
    total_output = sum(item["output"] for item in stages.values())

    summary = {
        "input": total_input,
        "output": total_output,
        "cost_usd": _cost_usd(total_input, total_output),
    }

    log_decision("query_complete", question, {
        "trace_id": trace_id,
        "route": result.get("route"),
        "sql_validation": (
            result.get("sql_result", {}).get("metadata", {}).get("validation")
            if result.get("sql_result") else None
        ),
        "retrieval_chunk_count": (
            result.get("retrieval_result", {}).get("metadata", {}).get("chunk_count")
            if result.get("retrieval_result") else None
        ),
        "stage_token_usage": stages,
        "total_token_usage": summary,
    })

    _append({
        "type": "query",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "question": question,
        "route": result.get("route"),
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cost_usd": summary["cost_usd"],
    })

    result["token_usage"] = summary
    return result


def summarize_recent_queries(limit: int = 10) -> dict:
    path = _log_path()
    if not path.exists():
        return {
            "query_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": None,
        }

    with path.open(encoding="utf-8") as file:
        queries = [
            json.loads(line)
            for line in file
            if json.loads(line).get("type") == "query"
        ]

    recent = queries[-limit:]
    costs = [item["cost_usd"] for item in recent if item["cost_usd"] is not None]

    return {
        "query_count": len(recent),
        "input_tokens": sum(item["input_tokens"] for item in recent),
        "output_tokens": sum(item["output_tokens"] for item in recent),
        "cost_usd": round(sum(costs), 8) if len(costs) == len(recent) else None,
    }