# GQLBench: A Large-Scale Cross-Domain, Cross-Dialect Benchmark for NL2GQL

This repository is for **GQLBench: A Large-Scale Cross-Domain, Cross-Dialect Benchmark for NL2GQL**, which was accepted to **ACL 2026 Main Conference**.

GQLBench is a large-scale benchmark for natural language to graph query language (NL2GQL) generation, covering multiple domains and GQL dialects.

## Data


| Component            | Location                                                                           | Description                                            |
| -------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Query benchmark data | `benchmark_data_new/`                                       | NL–GQL query pairs and schemas (included in this repo) |
| Graph database files | [Hugging Face: qxssadf/GQLBench](https://huggingface.co/datasets/qxssadf/GQLBench) | Neo4j and Nebula graph data (~9 GB)                    |


### Download graph data

```bash
# Download the archive (~9 GB)
hf download qxssadf/GQLBench --repo-type dataset --local-dir xxx

```

## Repository structure

```
GQLBench/
├── benchmark_data_new/   # Query benchmark data
├── Code/                 # Data synthesis, conversion, evaluation
├── Translator_unified_gql/
└── GraphDB/              # Graph data (download separately; not tracked in git)
    ├── neo4j/
    └── nebula/
```

## Citation

If you use GQLBench in your research, please cite our ACL 2026 paper (bibtex to be added).