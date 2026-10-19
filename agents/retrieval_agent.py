import os
import re

import boto3
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

from bedrock_client import invoke_claude
from onnx_embed import get_embedding

load_dotenv()

HOST = os.environ["OPENSEARCH_ENDPOINT"]
REGION = os.getenv("AWS_REGION", "us-east-1")


SEARCH_DOCUMENTS_TOOL = {
    "name": "search_documents",
    "description": (
        "Search indexed documents for content relevant to a question. "
        "Returns excerpts with source names."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"}
        },
        "required": ["query"],
    },
}


def get_opensearch_client():
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise RuntimeError("AWS credentials were not found.")

    frozen = credentials.get_frozen_credentials()
    auth = AWS4Auth(
        frozen.access_key,
        frozen.secret_key,
        REGION,
        "es",
        session_token=frozen.token,
    )

    host = HOST.removeprefix("https://").removeprefix("http://").rstrip("/")
    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )


def retrieve(question: str, top_k: int = 5) -> list[dict]:
    query_vector = get_embedding(question)
    client = get_opensearch_client()
    response = client.search(
        index="documents",
        body={
            "size": top_k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": query_vector,
                        "k": top_k,
                    }
                }
            },
        },
    )

    return [
        {
            "content": hit["_source"]["content"],
            "source": hit["_source"].get("source", "Unknown source"),
            "score": hit.get("_score"),
        }
        for hit in response["hits"]["hits"]
    ]


def search_documents_tool(query: str) -> str:
    """Format retrieved chunks as a document-search tool result."""
    chunks = retrieve(query)
    if not chunks:
        return "No relevant documents found."

    return "\n\n".join(
        f"[Source: {chunk['source']}]\n{chunk['content']}"
        for chunk in chunks
    )


def generate_cited_answer(
    question: str, chunks: list[dict]
) -> tuple[str, dict]:
    context = "\n\n".join(
        f"[Source {i + 1}: {chunk['source']}]\n{chunk['content']}"
        for i, chunk in enumerate(chunks)
    )
    prompt = (
        "Answer the question using ONLY the context provided below. "
        "If the answer is not in the context, say 'I cannot find this "
        "information in the provided documents.' Always cite the source "
        "number(s) you used.\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {question}\n\nANSWER:"
    )

    result = invoke_claude(prompt, max_tokens=500, component="retrieval_answer")
    usage = {
        "input": result["input_tokens"],
        "output": result["output_tokens"],
    }
    return result["text"], usage


# def check_grounding(answer: str, chunks: list[dict]) -> bool:
#     cited_sources = re.findall(r"Source (\d+)", answer)
#     if not cited_sources:
#         return "cannot find" in answer.lower()

#     return all(1 <= int(source) <= len(chunks) for source in cited_sources)
def check_grounding(answer: str, chunks: list[dict]) -> bool:
    citation_groups = re.findall(
        r"\[\s*Sources?\s+([0-9]+(?:\s*(?:,|&|and)\s*[0-9]+)*)",
        answer,
        flags=re.IGNORECASE,
    )
    cited_numbers = [
        int(number)
        for group in citation_groups
        for number in re.findall(r"\d+", group)
    ]

    if not cited_numbers:
        return "cannot find" in answer.lower()

    return all(1 <= number <= len(chunks) for number in cited_numbers)

def retrieval_agent(question: str) -> dict:
    chunks = retrieve(question)
    if not chunks:
        return {
            "answer": "No relevant documents found.",
            "sources": [],
            "chunks": [],
            "grounded": False,
            "token_usage": {"input": 0, "output": 0},
        }

    answer, usage = generate_cited_answer(question, chunks)
    return {
        "answer": answer,
        "sources": [chunk["source"] for chunk in chunks],
        "chunks": chunks,
        "grounded": check_grounding(answer, chunks),
        "token_usage": usage,
    }


def run_retrieval_agent(question: str) -> dict:
    """Match the standard interface used by the orchestrator."""
    result = retrieval_agent(question)
    return {
        "success": bool(result["chunks"]),
        "answer": result["answer"],
        "sources": result["sources"],
        "metadata": {
            "chunk_count": len(result["chunks"]),
            "grounded": result["grounded"],
            "token_usage": result["token_usage"],
        },
    }
