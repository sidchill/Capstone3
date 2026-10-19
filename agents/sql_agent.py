import json
import os
import re

import psycopg2
from dotenv import load_dotenv
from bedrock_client import invoke_claude

load_dotenv()


SCHEMA_CONTEXT = """
Tables available:

- clients(id, name, industry, region, created_date)
  - One row per client organization.
  - region is one of: 'North', 'South', 'East', 'West'.

- projects(id, client_id, name, status, start_date, end_date, budget)
  - One row per consulting project.
  - client_id references clients.id.
  - status is one of: 'active', 'completed', 'on-hold'.
  - end_date may be NULL when a project is ongoing.
  - budget is in USD.

- consultants(id, name, grade, specialisation)
  - One row per consultant.
  - grade is one of: 'Analyst', 'Senior', 'Manager', 'Director'.

- project_consultants(project_id, consultant_id, billable_hours)
  - Assignment table linking consultants to projects.
  - project_id references projects.id.
  - consultant_id references consultants.id.
  - The primary key is (project_id, consultant_id).
  - billable_hours records hours for that consultant on that project.

- invoices(id, project_id, amount, status, due_date, paid_date)
  - One row per invoice.
  - project_id references projects.id.
  - status is one of: 'paid', 'pending', 'overdue'.
  - amount is in USD.
  - paid_date may be NULL when the invoice is unpaid.

All dates use YYYY-MM-DD. There is no client contract_value column.
To connect consultants to projects, join through project_consultants.
"""


def generate_sql(question: str, history: list = None) -> str:
    history = history or []
    history_text = "\n".join(
        f"Q: {item['question']}\nA: {item['answer']}" for item in history
    ) or "(no previous conversation)"

    prompt = (
        f"{SCHEMA_CONTEXT}\n"
        f"Conversation history:\n{history_text}\n\n"
        f"New question: {question}\n\n"
        "Generate one read-only PostgreSQL query using only the tables and "
        "columns in the schema. Resolve follow-up references using the history. "
        "For ambiguous questions, choose a reasonable schema-supported "
        "interpretation; the final answer should state the assumption. "
        "If the schema cannot answer the question, return a SELECT statement "
        "with one text column named message, whose value starts with "
        "'UNANSWERABLE:'. Do not invent tables or columns. "
        "Return ONLY SQL. No explanation, markdown, or code fences."
    )

    result = invoke_claude(prompt, max_tokens=512)
    sql = result["text"].strip()
    sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s*```$", "", sql)
    return sql.strip()


BLOCKED_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|"
    r"EXEC|EXECUTE|CALL|DO|COPY)\b",
    re.IGNORECASE,
)

UNSAFE_REQUEST = re.compile(
    r"^\s*(?:please\s+)?(?:delete|drop|truncate|insert|update|modify|remove|erase)\b",
    re.IGNORECASE,
)

def validate_sql(query: str) -> dict:
    sql = query.strip()

    if not sql:
        return {"valid": False, "reason": "The generated query is empty."}

    if "--" in sql or "/*" in sql or "*/" in sql:
        return {"valid": False, "reason": "SQL comments are not permitted."}

    # Permit one optional trailing semicolon, but reject stacked statements.
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()

    if ";" in sql:
        return {
            "valid": False,
            "reason": "Multiple SQL statements are not permitted.",
        }

    if not re.match(r"^(SELECT|WITH)\b", sql, re.IGNORECASE):
        return {
            "valid": False,
            "reason": "Only SELECT queries are permitted.",
        }

    # Ignore quoted string contents when looking for blocked SQL keywords.
    sql_without_strings = re.sub(r"'(?:''|[^'])*'", "''", sql)

    if BLOCKED_KEYWORDS.search(sql_without_strings):
        return {
            "valid": False,
            "reason": "A blocked SQL keyword was detected.",
        }

    if re.search(
        r"\bINTO\b|\bFOR\s+(UPDATE|SHARE)\b",
        sql_without_strings,
        re.IGNORECASE,
    ):
        return {
            "valid": False,
            "reason": "This SELECT query form is not permitted.",
        }

    return {"valid": True, "reason": "OK"}

def execute_query(sql: str) -> dict:
    validation = validate_sql(sql)

    if not validation["valid"]:
        return {
            "success": False,
            "error": validation["reason"],
            "validation": "BLOCKED",
        }

    connection = None

    try:
        connection = psycopg2.connect(
            host=os.environ["RDS_HOST"],
            port=int(os.getenv("RDS_PORT", "5432")),
            dbname=os.environ["RDS_DATABASE"],
            user=os.environ["RDS_USER"],
            password=os.environ["RDS_PASSWORD"],
            connect_timeout=10,
        )
        connection.set_session(readonly=True)

        with connection.cursor() as cursor:
            cursor.execute(sql)
            columns = [description[0] for description in cursor.description]
            rows = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        return {
            "success": True,
            "columns": columns,
            "rows": rows,
            "validation": "PASSED",
        }

    except Exception as error:
        return {
            "success": False,
            "error": str(error),
            "validation": "EXECUTION_ERROR",
        }

    finally:
        if connection is not None:
            connection.close()

def sql_agent(
    question: str,
    history: list = None,
    generated_sql: str = None,
    print_query: bool = True,
) -> str:
    sql = generated_sql or generate_sql(question, history)

    if print_query:
        print(f"Generated SQL:\n{sql}")

    result = execute_query(sql)

    if not result["success"]:
        return (
            f"I couldn't run the generated query: {result['error']} "
            f"(validation: {result['validation']})"
        )

    if result["rows"]:
        first_value = next(iter(result["rows"][0].values()))
        if isinstance(first_value, str) and first_value.startswith("UNANSWERABLE:"):
            return first_value.replace("UNANSWERABLE:", "", 1).strip()

    if not result["rows"]:
        return "No matching records were found."

    history_text = "\n".join(
        f"Q: {item['question']}\nA: {item['answer']}"
        for item in (history or [])
    )

    answer_prompt = (
        f"Conversation history:\n{history_text or '(none)'}\n\n"
        f"User question: {question}\n"
        f"SQL used: {sql}\n"
        f"Columns: {result['columns']}\n"
        f"Data: {json.dumps(result['rows'][:20], default=str)}\n\n"
        "Give a concise natural-language answer supported by the data. "
        "Do not invent facts. If the question was ambiguous, state the "
        "assumption used."
    )

    answer_result = invoke_claude(answer_prompt, max_tokens=500)
    return answer_result["text"].strip()


def sql_agent_with_memory(question: str, history: list) -> tuple:
    sql = generate_sql(question, history)
    print(f"Generated SQL:\n{sql}")

    answer = sql_agent(
        question,
        history=history,
        generated_sql=sql,
        print_query=False,
    )
    history.append({"question": question, "answer": answer})
    return answer, history

def run_sql_agent(question: str) -> dict:
    if UNSAFE_REQUEST.search(question):
        return {
            "success": False,
            "answer": "Unsafe data-modification request blocked; no SQL was executed.",
            "sources": [],
            "metadata": {
                "sql": None,
                "validation": "BLOCKED",
                "token_usage": {"input": 0, "output": 0},
            },
        }
    prompt = (
        f"{SCHEMA_CONTEXT}\n\n"
        f"Generate one read-only PostgreSQL query to answer: {question}\n"
        "Use only the listed tables and columns. Return ONLY SQL, "
        "without explanation, markdown, or code fences."
    )
    generation = invoke_claude(prompt, max_tokens=512, component="sql_generation")
    sql = generation["text"].strip()
    sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s*```$", "", sql).strip()

    result = execute_query(sql)
    usage = {
        "input": generation["input_tokens"],
        "output": generation["output_tokens"],
    }

    if not result["success"]:
        return {
            "success": False,
            "answer": f"Query blocked or failed: {result['error']}",
            "sources": [f"SQL: {sql}"],
            "metadata": {
                "sql": sql,
                "validation": result["validation"],
                "token_usage": usage,
            },
        }

    if not result["rows"]:
        answer = "No matching records were found."
    else:
        first_value = next(iter(result["rows"][0].values()))
        if isinstance(first_value, str) and first_value.startswith("UNANSWERABLE:"):
            answer = first_value.replace("UNANSWERABLE:", "", 1).strip()
        else:
            answer_prompt = (
                f"Question: {question}\n"
                f"SQL: {sql}\n"
                f"Columns: {result['columns']}\n"
                f"Data: {json.dumps(result['rows'][:20], default=str)}\n\n"
                "Answer concisely using only the data. Do not invent facts."
            )
            interpretation = invoke_claude(answer_prompt, max_tokens=500, component="sql_interpretation")
            answer = interpretation["text"].strip()
            usage["input"] += interpretation["input_tokens"]
            usage["output"] += interpretation["output_tokens"]

    return {
        "success": True,
        "answer": answer,
        "sources": [f"SQL: {sql}"],
        "metadata": {
            "sql": sql,
            "validation": result["validation"],
            "token_usage": usage,
        },
    }

if __name__ == "__main__":
    test_questions = [
        "How many clients do we have?",
        "What is the budget and status of the project named 'Data Migration'?",
        "Which client owns the project 'Fraud Detection System'?",
        "What is the total budget across all projects?",
        "Show invoice amounts and due dates for invoices with status 'overdue'.",
        "What is the average billable hours per project, grouped by project name?",
        "Who are our best clients?",
        "What is our current stock price?",
    ]

    # Generate and display every query before executing any of them.
    generated_tests = [
        (question, generate_sql(question))
        for question in test_questions
    ]

    print("=" * 70)
    print("GENERATED SQL — ALL QUERIES SHOWN BEFORE EXECUTION")
    print("=" * 70)

    for index, (question, sql) in enumerate(generated_tests, start=1):
        print(f"\nTest {index}: {question}\n{sql}")

    print("\n" + "=" * 70)
    print("AGENT TEST RESULTS")
    print("=" * 70)

    for question, sql in generated_tests:
        print(f"\nQ: {question}")
        print(
            f"A: {sql_agent(question, generated_sql=sql, print_query=False)}"
        )

    print("\n" + "=" * 70)
    print("CONVERSATION MEMORY TEST")
    print("=" * 70)

    history = []
    question_1 = "How many projects does Acme Corp have?"
    answer_1, history = sql_agent_with_memory(question_1, history)
    print(f"\nQ1: {question_1}\nA1: {answer_1}")

    question_2 = "What's their total budget?"
    answer_2, history = sql_agent_with_memory(question_2, history)
    print(f"\nQ2: {question_2}\nA2: {answer_2}")
