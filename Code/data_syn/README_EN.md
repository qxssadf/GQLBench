# GQLBench Data Synthesis

Pipeline for synthesizing NL2GQL training data. Run scripts from `Code/data_syn/` in order:

```bash
python schema_generator.py
python data_generator.py
python cypher_template_generator.py
python import_data_syn_to_graphdb.py --gql_type cypher --only_convert
python import_data_syn_to_graphdb.py --gql_type cypher --only_import
python validate_gql.py --template_dir ./templates
python nl_generator_new.py
```

## LLM Configuration

| Script | Where to configure |
|--------|-------------------|
| `nl_generator_new.py` | `<YOUR_LLM_API_KEY>`, `<YOUR_LLM_BASE_URL>` (top of file, ~line 26–27) |
| `data_generator.py` | `Code/Config.py` and `Code/LLM_Utils.py` (LLM model, API key, embedding settings) |

## License

MIT License.
