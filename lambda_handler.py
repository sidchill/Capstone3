import json
import logging

from orchestrator import build_orchestrator
from tokenomics_logger import run_traced_query


logger = logging.getLogger()
logger.setLevel(logging.INFO)

orchestrator = build_orchestrator()


def handler(event, context):
    try:
        body = event.get("body", "{}")

        if isinstance(body, str):
            body = json.loads(body)

        if not isinstance(body, dict):
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Request body must be a JSON object"}),
            }

        question = body.get("question", "")
        if not isinstance(question, str) or not question.strip():
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "question is required"}),
            }

        result = run_traced_query(orchestrator, question.strip())
        sql_result = result.get("sql_result") or {}
        sql_validation = sql_result.get("metadata", {}).get("validation")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "answer": result.get("final_answer"),
                "route": result.get("route"),
                "sql_validation": sql_validation,
                "token_usage": result.get("token_usage", {}),
            }),
        }

    except Exception:
        logger.exception("Lambda handler failed")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal processing error"}),
        }