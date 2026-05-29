#!/usr/bin/env python3
import json

import os

import re

from typing import Dict, List, Any

from concurrent.futures import ThreadPoolExecutor, as_completed

from threading import Lock

try:

    from tqdm import tqdm

except ImportError:

    tqdm = None

try:

    import openai

    LLM_API_KEY = "<YOUR_LLM_API_KEY>"
    LLM_BASE_URL = "<YOUR_LLM_BASE_URL>"
    openai.api_base = LLM_BASE_URL
    openai.api_key = LLM_API_KEY

except ImportError:

    print("警告: 未安装openai库，请运行: pip install openai")
    openai = None


class NLGeneratorSimple:

    SCHEMA_FILE_MAPPING = {
        "E_commerce_schemas.json": "E-commerce_schemas.json",
        "Real_Estate_schemas.json": "Real Estate_schemas.json",
    }

    def __init__(self, openai_api_key: str = None):
        if not openai:
            print("错误: 未安装openai库")
            return
        if openai_api_key:
            self.client = openai.OpenAI(api_key=openai_api_key)
        elif os.getenv("OPENAI_API_KEY"):
            self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        elif openai.api_key:
            self.client = openai.OpenAI(
                api_key=openai.api_key, base_url=LLM_BASE_URL
            )
        else:
            print("警告: 未设置OpenAI API密钥")
            self.client = None

    def parse_template_filename(self, filename: str) -> tuple:
        name = filename.replace(".json", "")
        name = name[10:]
        gql_type = "cypher"
        if name.startswith("nebula_"):
            gql_type = "nebula"
            name = name[7:]
        elif name.startswith("cypher_"):
            gql_type = "cypher"
            name = name[7:]
        schemas_pos = name.find("_schemas_")
        if schemas_pos == -1:
            raise ValueError(f"无法解析文件名: {filename}")
        schema_file = name[: schemas_pos + 8] + ".json"
        remaining = name[schemas_pos + 9 :]
        parts = remaining.split("_", 1)
        schema_index = int(parts[0]) - 1
        db_name = parts[1] if len(parts) > 1 else ""
        return (schema_file, schema_index, db_name, gql_type)

    def load_schema(self, schema_file: str, schema_index: int) -> Dict[str, Any]:
        with open(schema_file, "r", encoding="utf-8") as f:
            schemas = json.load(f)
        if not isinstance(schemas, list):
            schemas = [schemas]
        if schema_index >= len(schemas):
            raise ValueError(
                f"Schema索引 {schema_index} 超出范围，文件中有 {len(schemas)} 个schema"
            )
        return schemas[schema_index]

    def load_templates(self, template_file: str) -> List[Dict[str, Any]]:
        with open(template_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def build_schema_description(self, schema: Dict[str, Any]) -> str:
        desc = f"Domain: {schema.get('domain', 'Unknown')}\n"
        desc += f"System: {schema.get('name', 'Unknown')}\n"
        desc += f"Description: {schema.get('description', 'No description')}\n\n"
        desc += "Node Types:\n"
        for node_type in schema.get("node_types", []):
            desc += f"- {node_type['name']}: {node_type.get('description', 'No description')}\n"
            desc += "  Properties:\n"
            for prop in node_type.get("properties", []):
                prop_desc = f"    - {prop['name']} ({prop['type']})"
                if prop.get("description"):
                    prop_desc += f": {prop['description']}"
                desc += prop_desc + "\n"
            desc += "\n"
        desc += "Relationship Types:\n"
        for rel_type in schema.get("relationship_types", []):
            desc += f"- {rel_type['name']}: {rel_type.get('description', 'No description')}\n"
            if rel_type.get("properties"):
                desc += "  Properties:\n"
                for prop in rel_type["properties"]:
                    prop_desc = f"    - {prop['name']} ({prop['type']})"
                    if prop.get("description"):
                        prop_desc += f": {prop['description']}"
                    desc += prop_desc + "\n"
            desc += "\n"
        return desc

    def generate_nl_query(self, gql_template: str, schema: Dict[str, Any]) -> str:
        if not self.client:
            return "查询相关数据"
        schema_desc = self.build_schema_description(schema)
        prompt = f"You are a professional database query expert. Please generate a natural, fluent English query question based on the given GQL query and database schema.\n\nDatabase Schema:\n{schema_desc}\n\nGQL Query:\n{gql_template}\n\nPlease generate an English query question that:\n1. Is natural and fluent\n2. Accurately reflects the intent of the GQL query\n3. Includes specific business scenario descriptions\n\nNote:\n1. Please note the string operations in the `WHERE` clause, such as TOUPPER. You should include the string operation in the query question rather than only the value of the property.\n2. Please note the content in the `RETURN` clause. You should include all the content in the `RETURN` clause in your query question. If the `RETURN` clause contains entities or relations, you should include them in the query question.\n\n\nPlease only return the query question:"
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat", messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"生成NL查询时出错: {e}")
            return "查询相关数据"

    def process_template_file(
        self,
        template_file: str,
        schemas_dir: str = "./schemas",
        output_dir: str = "./nl_gql_pairs",
        max_queries: int = None,
        max_workers: int = 4,
    ) -> None:
        print(f"处理模板文件: {template_file}")
        try:
            (
                schema_file,
                schema_index,
                db_name,
                gql_type,
            ) = self.parse_template_filename(template_file)
            print(
                f"  Schema文件: {schema_file}, 索引: {schema_index}, 数据库: {db_name}, GQL类型: {gql_type}"
            )
            actual_schema_file = self.SCHEMA_FILE_MAPPING.get(schema_file, schema_file)
            if actual_schema_file != schema_file:
                print(f"  映射到实际文件: {actual_schema_file}")
            schema_path = os.path.join(schemas_dir, actual_schema_file)
            schema = self.load_schema(schema_path, schema_index)
            print(f"  加载schema: {schema['name']}")
            template_path = os.path.join("./templates_filter", template_file)
            templates = self.load_templates(template_path)
            if max_queries:
                templates = templates[:max_queries]
            print(f"  加载了 {len(templates)} 个模板")
            nl_queries = [None] * len(templates)

            def process_single_template(idx_template):
                (idx, template) = idx_template
                try:
                    nl_query = self.generate_nl_query(template["template"], schema)
                    return (
                        idx,
                        {
                            "gql_template": template["template"],
                            "gql_dialect": gql_type,
                            "nl_query": nl_query,
                            "template_info": template,
                            "schema_name": schema["name"],
                            "domain": schema.get("domain", "Unknown"),
                            "success": True,
                            "error_message": None,
                        },
                        None,
                    )
                except Exception as e:
                    import traceback

                    error_detail = (
                        f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                    )
                    return (idx, None, f"处理模板 {idx + 1} 时出错: {error_detail}")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(process_single_template, (i, template)): i
                    for (i, template) in enumerate(templates)
                }
                if tqdm:
                    pbar = tqdm(total=len(templates), desc="生成NL查询")
                else:
                    pbar = None
                completed = 0
                failed = 0
                failed_indices = []
                for future in as_completed(futures):
                    (idx, result, error) = future.result()
                    if error:
                        failed += 1
                        failed_indices.append(idx)
                        print(f"\n  ❌ 模板 {idx + 1} 处理失败: {error[:200]}...")
                        nl_queries[idx] = {
                            "gql_template": templates[idx]["template"],
                            "gql_dialect": gql_type,
                            "nl_query": None,
                            "template_info": templates[idx],
                            "schema_name": schema["name"],
                            "domain": schema.get("domain", "Unknown"),
                            "success": False,
                            "error_message": error,
                        }
                    else:
                        completed += 1
                        nl_queries[idx] = result
                    if pbar:
                        pbar.update(1)
                if pbar:
                    pbar.close()
                print(f"  完成: {completed} 成功, {failed} 失败")
                if failed_indices:
                    print(f"  失败的模板索引: {[i + 1 for i in failed_indices]}")
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"nl_gql_pairs_{template_file}")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(nl_queries, f, ensure_ascii=False, indent=2)
            print(f"  保存到: {output_file}")
            print("  示例查询:")
            for (i, query) in enumerate(nl_queries[:3]):
                print(f"    {i + 1}. {query['nl_query']}")
                gql_dialect = query.get("gql_dialect", "cypher")
                print(f"       {gql_dialect}: {query['gql_template']}")
        except Exception as e:
            print(f"  处理失败: {e}")
            import traceback

            traceback.print_exc()

    def process_all_templates(
        self,
        schemas_dir: str = "./schemas",
        templates_dir: str = "./templates_filter",
        output_dir: str = "./nl_gql_pairs",
        max_queries_per_file: int = 20,
        max_workers: int = 4,
    ) -> None:
        template_files = [
            f
            for f in os.listdir(templates_dir)
            if f.endswith(".json") and "cypher" in f
        ]
        template_files = [
            f
            for f in os.listdir(templates_dir)
            if f.endswith(".json") and "nebula" in f
        ]
        print(f"找到 {len(template_files)} 个模板文件")
        for template_file in template_files:
            self.process_template_file(
                template_file,
                schemas_dir,
                output_dir,
                max_queries_per_file,
                max_workers,
            )
            print()


def main():

    generator = NLGeneratorSimple()
    generator.process_all_templates(
        schemas_dir="./schemas",
        templates_dir="./templates_filter",
        output_dir="./nl_gql_pairs_new",
        max_queries_per_file=None,
        max_workers=8,
    )


if __name__ == "__main__":

    main()
