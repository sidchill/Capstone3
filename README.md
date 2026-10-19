Reflection:
The question about the total budget which asked: "What is the total budget across projects", was the one that posed the largest issue to me during this capstone.  This is because the expected agent that question was meant to be routed to was the SQL agent.  However, the question was routed to both agent and this was due to the usage of keywords such as "what is" in the retrieval agent.  This is what is known as a routing failure, it is not a SQL validation or synthesis failure, and by removing that usage of the keyword I was able to correct the routing to just the SQL agent.  This specific error taught me the most about the fragility of multi-agent systems vs systems that use just one agent.  Specifically, multi-agent systems are fragile when routing rules overgeneralize and create unnecessary avenues that that a well-scoped single agent system would be able to bypass

Cost Analysis Table:
Component totals below cover the latest 80 log records (44 Claude calls).

| Component | Calls | Input tokens | Output tokens | Estimated cost (USD) |
|---|---:|---:|---:|---:|
| Retrieval answer | 10 | 21,366 | 2,511 | $0.111939 |
| SQL generation | 8 | 3,624 | 160 | $0.014599 |
| SQL interpretation | 8 | 652 | 288 | $0.006904 |
| Synthesis | 14 | 4,460 | 4,213 | $0.084233 |
| Unspecified | 4 | 3,578 | 768 | $0.024479 |
| **Total** | **44** | **33,680** | **7,940** | **$0.242154** |

The files in `evidence/` document the project checks and deployment results:

| Evidence | What it demonstrates |
|---|---|
| `rds-table-counts.txt` | This shows the actual data or the schema for the rds table. |
| `opensearch-check.txt` | This shows that we are actually accessing documents in opensearch. |
| `agent-interface-keys.txt` | Here we can see that both of the agents returned these fields: `success`, `answer`, `sources`, and `metadata`. |
| `orchestrator-evaluation.txt` | This shows how all of the questions we used for evaluation were routed and answered through the orchestrator. |
| `sql-validator-tests.txt` | These are the results of the SQL safety tests. |
| `claude-call-records.jsonl` | Individual Claude-call records with component, input/output tokens, and estimated cost. |
| `unsafe-request-through-orchestrator.txt` | This takes care of the unsafe natural language request via the orchestrator. |
| `lambda-response.json` | This shows that the lambda response was deployed succesfully. |
| `lambda-cloudwatch.log` | CloudWatch logs that show us the Lambda invocation. |

The other files outside of this folder are actual implementation and the env.example file mimics what my actual env file looks like without showing confidential data to the public.
