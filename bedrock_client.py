import boto3
import json
from tokenomics_logger import log_claude_call

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")


def get_model_id() -> str:
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    return f"arn:aws:bedrock:us-east-1:{account_id}:inference-profile/us.anthropic.claude-sonnet-4-6"


def invoke_claude(
    prompt: str,
    max_tokens: int = 500,
    component: str = "unspecified",
) -> dict:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = bedrock.invoke_model(
        modelId=get_model_id(),
        body=json.dumps(body),
    )
    result = json.loads(response["body"].read())

    input_tokens = result["usage"]["input_tokens"]
    output_tokens = result["usage"]["output_tokens"]
    log_claude_call(component, input_tokens, output_tokens)

    return {
        "text": result["content"][0]["text"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }

def invoke_claude_raw(body: dict) -> dict:
    """
    Lower-level helper for calls that need the full Messages API shape —
    system prompts, tool definitions, multi-turn conversations with
    tool_use/tool_result blocks — that invoke_claude() doesn't cover.

    Pass a body dict using the same keys you'd pass to the direct Anthropic
    SDK's client.messages.create() (max_tokens, system, tools, messages,
    etc.) — this just adds anthropic_version and sends it to Bedrock.

    Returns the parsed response as a plain dict, matching the same shape
    as the Anthropic SDK's response object, just accessed with ["..."]
    instead of attribute access: response["content"], response["stop_reason"],
    block["type"], block["input"], etc. — since Bedrock's InvokeModel API
    for Claude models returns the identical structure to the direct
    Anthropic API, confirmed against AWS's own documentation.
    """
    body = {**body}
    body.setdefault("anthropic_version", "bedrock-2023-05-31")
    response = bedrock.invoke_model(modelId=get_model_id(), body=json.dumps(body))
    return json.loads(response["body"].read())