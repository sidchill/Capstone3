import json

from agents.sql_agent import validate_sql
from orchestrator import build_orchestrator
from tokenomics_logger import run_traced_query


CASES = [
    ("SQL", "How many active projects do we have?"),
    ("SQL", "What is the total budget across all projects?"),
    ("Retrieval", "What does the remote work policy say about revoking arrangements?"),
    ("Retrieval", "Describe the cloud migration approach."),
    ("Both", "How many active projects do we have, and what does the remote work policy say?"),
    ("Both", "What is the total invoice amount, and describe the cloud migration approach."),
    ("Unanswerable", "What is our current stock price?"),
]


def main():
    graph = build_orchestrator()

    for category, question in CASES:
        print(f"\n{'=' * 72}\n[{category}] {question}")
        result = run_traced_query(graph, question)

        sql_result = result.get("sql_result") or {}
        metadata = sql_result.get("metadata") or {}

        print("Route:", result.get("route"))
        print("Answer:", result.get("final_answer"))
        print("SQL validation:", metadata.get("validation", "not run"))

    unsafe_sql = "DROP TABLE projects"
    validation = validate_sql(unsafe_sql)
    print(f"\n{'=' * 72}\n[Unsafe SQL] {unsafe_sql}")
    print("Route: validator-only (not sent to the database)")
    print("Answer:", validation["reason"])
    print("SQL validation:", "BLOCKED" if not validation["valid"] else "PASSED")

    print(f"\n{'=' * 72}\nRecent token summary:")
    from tokenomics_logger import summarize_recent_queries
    print(json.dumps(summarize_recent_queries(), indent=2))


if __name__ == "__main__":
    main()