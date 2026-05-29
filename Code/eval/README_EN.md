# NL-to-GQL Evaluation

Evaluation toolkit for natural-language-to-graph-query (NL2GQL) models. It generates GQL queries from natural language using a zero-shot prompt, executes both predicted and gold queries against live graph databases, and reports **execution accuracy** — whether the two queries return equivalent results.

## Directory Structure

| File | Description |
|------|-------------|
| `evaluate.py` | Main entry point: loads benchmark data, calls the LLM, runs metrics, and writes results |
| `execute_accuracy.py` | Execution-accuracy metric for Cypher (Neo4j) and ISO GQL (NebulaGraph) |
| `eval.sh` | Example shell script that invokes `evaluate.py` with common arguments |

## Requirements

- The Nebula Python SDK can be obtained by contacting the official team.

## Quick Start

Run evaluation on the test split with an API model:

```bash
python evaluate.py \
  --model_name deepseek-chat \
  --dataset test \
  --gql_dialect nebula \
  --source_ datasyn \
  --metric execution_accuracy
```

Run with a locally served model via vLLM:

```bash
python evaluate.py \
  --model_name llama3.1-8b-instruct \
  --vllm_port 8001 \
  --gql_dialect nebula \
  --source_ datasyn \
  --metric execution_accuracy
```

Or use the provided shell wrapper:

```bash
bash eval.sh
```

## CLI Reference

| Argument | Default | Description |
|----------|---------|-------------|
| `--dataset` | `test` | Split to evaluate: `train` or `test` |
| `--gql_dialect` | `cypher` | Query language: `cypher` or `nebula` |
| `--metric` | `execution_accuracy` | Evaluation metric |
| `--model_name` | `deepseek-chat` | LLM identifier passed to the inference backend |
| `--concurrent` | enabled | Run evaluation with multi-threaded concurrency |
| `--max_workers` | `8` | Number of concurrent worker threads |
| `--source_` | — | Data source filter (required when `--gql_dialect=cypher`) |
| `--vllm_port` | — | Port of a local vLLM OpenAI-compatible server |


## How It Works

1. **`evaluate.py`** loads NL–GQL pairs and graph schemas, builds a zero-shot prompt for each example, and queries the configured LLM.
2. The predicted query is passed to **`execute_accuracy.py`**, which executes both the prediction and the gold query on the target database.
3. Results are compared row-by-row.

## Output

Results are written as JSONL files under `res_{model_name}_new/`:

```
res_{model_name}_new/{dataset}_{metric}_{baseline}_{gql_dialect}_all_new_prompt.jsonl
```

Each line contains:

```json
{
  "prompt": "...",
  "response": "...",
  "is_success": true,
  "error_message": "No Error",
  "target_gql": "...",
  "db_name": "...",
  "gql_dialect": "nebula",
  "source": "datasyn"
}
```

Failed samples are additionally logged to a companion `*_failed.jsonl` file in the same directory.

## License

See the repository root for license information.
