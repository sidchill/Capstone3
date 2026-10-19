from agents.retrieval_agent import run_retrieval_agent
from agents.sql_agent import run_sql_agent


TOOL_DEFINITIONS = {
    "query_database": {
        "description": (
            "Query structured client, project, consultant, and invoice data "
            "for counts, totals, statuses, and comparisons. Not for policies "
            "or procedures."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
    "search_documents": {
        "description": (
            "Search indexed documents for policies, procedures, and guidance. "
            "Not for authoritative database counts or totals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}


def call_tool(name: str, arguments: dict) -> dict:
    if name == "query_database":
        return run_sql_agent(arguments["question"])
    if name == "search_documents":
        return run_retrieval_agent(arguments["query"])
    raise ValueError(f"Unknown tool: {name}")