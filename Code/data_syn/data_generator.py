#!/usr/bin/env python3
import json

import os

import random

import numpy as np

from typing import Dict, List, Any, Tuple

from datetime import datetime, timedelta

import sys

import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from LLM_Utils import extract_json, run_llm, get_embedding, cosine_similarity

from Config import MODEL, Qwen_Embedding_MODEL

from LLM_Utils import Qwen_URL, Qwen_API_KEY


class DataGenerator:
    def __init__(self):
        self.llm_model = "deepseek-chat"
        self.embedding_model = Qwen_Embedding_MODEL
        self.embedding_base_url = Qwen_URL
        self.embedding_api_key = Qwen_API_KEY
        self.prompts_dir = "./Prompts"
        os.makedirs(self.prompts_dir, exist_ok=True)
        self.property_values_cache = {}
        self._create_prompt_templates()
        self.embedding_cache = {}

    def pre_generate_property_values(self, schema: Dict, values_per_property: int = 50):
        print("开始预生成属性值...")
        for node_type in schema["node_types"]:
            node_type_name = node_type["name"]
            domain = schema["domain"]
            for prop in node_type["properties"]:
                if (
                    prop["type"] == "string"
                    and (not prop.get("is_category", False))
                    and (not prop.get("is_id", False))
                ):
                    prop_key = f"{domain}:{node_type_name}:{prop['name']}"
                    if prop_key not in self.property_values_cache:
                        print(f"  为 {prop_key} 生成 {values_per_property} 个值...")
                        values = self._generate_llm_string_values_batch(
                            prop, domain, values_per_property
                        )
                        self.property_values_cache[prop_key] = values
        print(f"预生成完成，共缓存了 {len(self.property_values_cache)} 个属性的值")

    def _generate_llm_string_values_batch(
        self, prop: Dict, domain: str, count: int
    ) -> List[str]:
        prop_name = prop["name"]
        description = prop.get("description", "")
        try:
            prompt = f"Generate diverse and realistic values for the following property in the {domain} domain.\n\nProperty: {prop_name}\nDescription: {description}\n\nPlease generate {count} diverse, realistic values that would be appropriate for this property in the {domain} domain.\nThe values should be varied and cover different realistic scenarios. For attributes like id,email etc., they should be in the same format.\nReturn only the values, one per line, without any additional text or formatting.\n"
            (response, _) = run_llm(self.llm_model, prompt)
            if response:
                values = [
                    value.strip()
                    for value in response.strip().split("\n")
                    if value.strip()
                ]
                if values:
                    return values
        except Exception as e:
            print(f"LLM批量生成字符串值失败: {e}")
        default_values = [f"{prop_name}_{i}" for i in range(count)]
        return default_values

    def _create_prompt_templates(self):
        general_string_prompt = "Generate diverse and realistic values for the following property in the {domain} domain.\n\nProperty: {property_name}\nDescription: {description}\nCurrent values: {current_values}\n\nPlease generate {count} diverse, realistic values that would be appropriate for this property in the {domain} domain. \nThe values should be varied and cover different realistic scenarios.\nReturn only the values, one per line, without any additional text or formatting.\n\nExamples of good values:\n{examples}"
        name_prompt = "Generate diverse and realistic {name_type} names for the {domain} domain.\n\nGenerate {count} diverse names that would be appropriate for {name_type} in the {domain} domain.\nConsider different cultural backgrounds, regions, and naming conventions.\nReturn only the names, one per line, without any additional text or formatting."
        address_prompt = "Generate diverse and realistic addresses for the {domain} domain.\n\nGenerate {count} diverse addresses that would be appropriate for the {domain} domain.\nInclude street addresses, cities, and regions that make sense for this domain.\nReturn only the addresses, one per line, without any additional text or formatting."
        description_prompt = "Generate diverse and realistic descriptions for the {domain} domain.\n\nProperty: {property_name}\nContext: {context}\n\nGenerate {count} diverse, realistic descriptions that would be appropriate for this property in the {domain} domain.\nKeep descriptions concise but informative (1-2 sentences each).\nReturn only the descriptions, one per line, without any additional text or formatting."
        templates = {
            "general_string": general_string_prompt,
            "name": name_prompt,
            "address": address_prompt,
            "description": description_prompt,
        }
        for (template_name, template_content) in templates.items():
            template_path = os.path.join(
                self.prompts_dir, f"{template_name}_prompt.txt"
            )
            with open(template_path, "w", encoding="utf-8") as f:
                f.write(template_content)

    def load_schema(self, schema_path: str) -> List[Dict]:
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def generate_data_for_schema(
        self,
        schema: Dict,
        node_count: int = 1000,
        relationship_count: int = 500,
        use_ldbc: bool = True,
        use_llm_constraints: bool = True,
    ) -> Tuple[List[Dict], List[Dict]]:
        print(f"开始为 {schema['name']} 生成数据...")
        if use_llm_constraints:
            print("使用LLM约束感知生成节点数据...")
            nodes = self._generate_nodes_with_llm_constraints(schema, node_count)
        else:
            print("使用传统方法生成节点数据...")
            self.pre_generate_property_values(schema, values_per_property=node_count)
            nodes = self._generate_nodes(schema, node_count)
        relationships = self._generate_relationships(
            schema, nodes, relationship_count, use_ldbc
        )
        print(f"生成了 {len(nodes)} 个节点和 {len(relationships)} 个关系")
        return (nodes, relationships)

    def _generate_nodes(self, schema: Dict, node_count: int) -> List[Dict]:
        nodes = []
        for node_type in schema["node_types"]:
            node_type_name = node_type["name"]
            instances_per_type = max(1, node_count // len(schema["node_types"]))
            print(f"  生成 {node_type_name} 节点，目标数量: {instances_per_type}")
            for i in range(instances_per_type):
                node_data = self._generate_single_node(node_type, schema["domain"], i)
                nodes.append(node_data)
        return nodes

    def _generate_single_node(self, node_type: Dict, domain: str, index: int) -> Dict:
        node_data = {
            "id": f"{node_type['name']}_{index}",
            "type": node_type["name"],
            "properties": {},
        }
        for prop in node_type["properties"]:
            prop_name = prop["name"]
            prop_type = prop["type"]
            if prop_type == "string":
                value = self._generate_string_value(
                    prop, domain, node_type["name"], index
                )
            elif prop_type == "int":
                value = self._generate_int_value(prop)
            elif prop_type == "float":
                value = self._generate_float_value(prop)
            elif prop_type == "boolean":
                value = random.choice([True, False])
            elif prop_type == "date":
                value = self._generate_date_value(prop)
            elif prop_type == "datetime":
                value = self._generate_datetime_value(prop)
            else:
                value = f"unknown_type_{prop_type}"
            node_data["properties"][prop_name] = value
        return node_data

    def _generate_nodes_with_llm_constraints(
        self, schema: Dict, node_count: int
    ) -> List[Dict]:
        print("  使用LLM根据约束规则生成节点数据...")
        nodes = []
        for node_type in schema["node_types"]:
            node_type_name = node_type["name"]
            domain = schema["domain"]
            instances_per_type = max(1, node_count // len(schema["node_types"]))
            print(f"    为 {node_type_name} 生成 {instances_per_type} 个实例...")
            constraints_info = self._build_constraints_info(schema, node_type)
            llm_nodes = self._generate_nodes_with_llm(
                node_type, domain, instances_per_type, constraints_info
            )
            nodes.extend(llm_nodes)
        return nodes

    def _build_constraints_info(self, schema: Dict, node_type: Dict) -> str:
        constraints = []
        for prop in node_type["properties"]:
            prop_constraints = []
            if prop.get("required"):
                prop_constraints.append("required field")
            if prop.get("unique"):
                prop_constraints.append("unique value")
            if prop["type"] in ["int", "float"]:
                min_val = prop.get("min_value")
                max_val = prop.get("max_value")
                if min_val is not None or max_val is not None:
                    range_str = f"range: {(min_val if min_val is not None else 'unlimited')} - {(max_val if max_val is not None else 'unlimited')}"
                    prop_constraints.append(range_str)
            if prop.get("allowed_values"):
                prop_constraints.append(f"allowed values: {prop['allowed_values']}")
            if prop_constraints:
                constraints.append(
                    f"- {prop['name']} ({prop['type']}): {', '.join(prop_constraints)}"
                )
        if schema.get("business_constraints"):
            for constraint in schema["business_constraints"]:
                affected_entities = constraint.get("affected_entities", [])
                if node_type["name"] in affected_entities:
                    constraints.append(
                        f"- business constraint: {constraint['description']}"
                    )
        return "\n".join(constraints) if constraints else "no special constraints"

    def _generate_nodes_with_llm(
        self,
        node_type: Dict,
        domain: str,
        count: int,
        constraints_info: str,
        batch_size: int = 50,
    ) -> List[Dict]:
        prop_names = [prop["name"] for prop in node_type["properties"]]
        prop_types = {prop["name"]: prop["type"] for prop in node_type["properties"]}
        all_nodes = []
        batch_size = count
        total_batches = (count + batch_size - 1) // batch_size
        print(f"      批量生成 {count} 个实例，每批 {batch_size} 个，共 {total_batches} 批...")
        for batch_idx in range(total_batches):
            current_batch_size = min(batch_size, count - len(all_nodes))
            current_start_idx = len(all_nodes)
            print(
                f"      正在生成第 {batch_idx + 1}/{total_batches} 批（{current_batch_size} 个实例）..."
            )
            prompt = f"""Generate {current_batch_size} realistic {node_type['name']} instances for the {domain} domain.\n\nNode Type: {node_type['name']}\nProperties: {', '.join(prop_names)}\nProperty Types: {prop_types}\n\nConstraints:\n{constraints_info}\n\nPlease generate {current_batch_size} diverse, realistic instances that satisfy all constraints.\nReturn the data as a JSON array, where each object has the properties: {', '.join(prop_names)}.\n\nExample format:\n[\n  {{\n    "property1": "value1",\n    "property2": 123,\n    "property3": 45.67\n  }},\n  {{\n    "property1": "value2", \n    "property2": 456,\n    "property3": 78.90\n  }}\n]\n\nReturn only the JSON array, no additional text."""
            batch_nodes = None
            for attempt in range(3):
                try:
                    (response, _) = run_llm(self.llm_model, prompt)
                    if response:
                        llm_data_str = (
                            response.strip().replace("```json", "").replace("```", "")
                        )
                        llm_data = json.loads(llm_data_str)
                        batch_nodes = []
                        for (i, data) in enumerate(llm_data):
                            node_data = {
                                "id": f"{node_type['name']}_{current_start_idx + i}",
                                "type": node_type["name"],
                                "properties": data,
                            }
                            batch_nodes.append(node_data)
                        break
                except Exception as e:
                    if attempt < 2:
                        print(f"        LLM生成节点数据失败, 正在重试 ({attempt + 1}/3)... 错误: {e}")
                        time.sleep(5)
                    else:
                        print(f"        LLM生成节点数据失败: {e}")
            if batch_nodes:
                all_nodes.extend(batch_nodes)
                print(
                    f"        成功生成 {len(batch_nodes)} 个实例，累计 {len(all_nodes)}/{count}"
                )
                if len(all_nodes) >= count:
                    break
            else:
                print(f"        回退到原始方法生成本批节点...")
                for i in range(current_batch_size):
                    node_data = self._generate_single_node(
                        node_type, domain, current_start_idx + i
                    )
                    all_nodes.append(node_data)
        print(f"      完成！共生成 {len(all_nodes)} 个 {node_type['name']} 节点")
        return all_nodes

    def _generate_string_value(
        self, prop: Dict, domain: str, node_type: str, index: int
    ) -> str:
        prop_name = prop["name"]
        if prop.get("is_category", False) and prop.get("allowed_values"):
            return random.choice(prop["allowed_values"])
        if prop.get("is_id", False) or "id" in prop_name.lower():
            return f"{prop_name.upper()}_{index:06d}"
        prop_key = f"{domain}:{node_type}:{prop_name}"
        if prop_key in self.property_values_cache:
            return random.choice(self.property_values_cache[prop_key])
        return f"{prop_name}_{index}"

    def _generate_name_value(self, prop_name: str, domain: str, index: int) -> str:
        name_types = {
            "customer": "customer",
            "investor": "investor",
            "player": "player",
            "student": "student",
            "user": "user",
            "patient": "patient",
            "doctor": "doctor",
            "professor": "professor",
            "actor": "actor",
            "director": "director",
        }
        name_type = "person"
        for (key, value) in name_types.items():
            if key in prop_name.lower():
                name_type = value
                break
        sample_names = [
            "John Smith",
            "Maria Garcia",
            "Ahmed Hassan",
            "Li Wei",
            "Emma Johnson",
            "Carlos Rodriguez",
            "Yuki Tanaka",
            "Anna Kowalski",
            "David Kim",
            "Sophie Martin",
        ]
        try:
            prompt = f"Generate diverse and realistic {name_type} names for the {domain} domain.\n\nGenerate 10 diverse names that would be appropriate for {name_type} in the {domain} domain.\nConsider different cultural backgrounds, regions, and naming conventions.\nReturn only the names, one per line, without any additional text or formatting.\n\nExamples:\n{chr(10).join(sample_names[:5])}"
            (response, _) = run_llm(self.llm_model, prompt)
            if response:
                names = [
                    name.strip()
                    for name in response.strip().split("\n")
                    if name.strip()
                ]
                if names:
                    return random.choice(names)
        except Exception as e:
            print(f"LLM生成姓名失败: {e}")
        return random.choice(sample_names)

    def _generate_email_value(self, index: int) -> str:
        domains = [
            "gmail.com",
            "yahoo.com",
            "hotmail.com",
            "outlook.com",
            "company.com",
        ]
        names = [
            "john",
            "maria",
            "ahmed",
            "li",
            "emma",
            "carlos",
            "yuki",
            "anna",
            "david",
            "sophie",
        ]
        return f"{random.choice(names)}{index}@{random.choice(domains)}"

    def _generate_phone_value(self) -> str:
        return f"+1-{random.randint(200, 999)}-{random.randint(100, 999)}-{random.randint(1000, 9999)}"

    def _generate_address_value(self, domain: str, index: int) -> str:
        streets = ["Main St", "Oak Ave", "Pine Rd", "Cedar Ln", "Maple Dr"]
        cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"]
        return f"{random.randint(100, 9999)} {random.choice(streets)}, {random.choice(cities)}"

    def _generate_description_value(
        self, prop_name: str, domain: str, index: int
    ) -> str:
        descriptions = [
            f"Standard {prop_name} in {domain} domain",
            f"Professional {prop_name} with comprehensive details",
            f"Detailed {prop_name} covering all aspects",
            f"Comprehensive {prop_name} for {domain} context",
            f"Standard {prop_name} with relevant information",
        ]
        return random.choice(descriptions)

    def _generate_int_value(self, prop: Dict) -> int:
        if prop.get("is_category", False) and prop.get("allowed_values"):
            return random.choice(prop["allowed_values"])
        min_val = prop.get("min_value", 0)
        max_val = prop.get("max_value", 100)
        return random.randint(min_val, max_val)

    def _generate_float_value(self, prop: Dict) -> float:
        if prop.get("is_category", False) and prop.get("allowed_values"):
            return random.choice(prop["allowed_values"])
        min_val = prop.get("min_value", 0.0)
        max_val = prop.get("max_value", 100.0)
        return round(random.uniform(min_val, max_val), 2)

    def _generate_date_value(self, prop: Dict) -> str:
        start_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 12, 31)
        random_date = start_date + timedelta(
            days=random.randint(0, (end_date - start_date).days)
        )
        return random_date.strftime("%Y-%m-%d")

    def _generate_datetime_value(self, prop: Dict) -> str:
        start_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 12, 31)
        random_datetime = start_date + timedelta(
            days=random.randint(0, (end_date - start_date).days),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        return random_datetime.strftime("%Y-%m-%d %H:%M:%S")

    def _generate_relationships(
        self, schema: Dict, nodes: Dict, relationship_count: int, use_ldbc: bool
    ) -> List[Dict]:
        relationships = []
        if not use_ldbc:
            return self._generate_simple_relationships(
                schema, nodes, relationship_count
            )
        print("  使用LDBC风格生成关系...")
        similarity_matrix = self._calculate_similarity_matrix(nodes, schema)
        relationships = self._generate_ldbc_relationships(
            schema, nodes, similarity_matrix, relationship_count
        )
        return relationships

    def _generate_simple_relationships(
        self, schema: Dict, nodes: List[Dict], relationship_count: int
    ) -> List[Dict]:
        relationships = []
        for rel_type in schema["relationship_types"]:
            from_node_type = rel_type["from_node"]
            to_node_type = rel_type["to_node"]
            from_nodes = [n for n in nodes if n["type"] == from_node_type]
            to_nodes = [n for n in nodes if n["type"] == to_node_type]
            if not from_nodes or not to_nodes:
                continue
            rel_count = max(1, relationship_count // len(schema["relationship_types"]))
            for _ in range(rel_count):
                from_node = random.choice(from_nodes)
                to_node = random.choice(to_nodes)
                relationship = {
                    "id": f"{rel_type['name']}_{len(relationships)}",
                    "type": rel_type["name"],
                    "from_node": from_node["id"],
                    "to_node": to_node["id"],
                    "properties": self._generate_relationship_properties(
                        rel_type, from_node, to_node
                    ),
                }
                relationships.append(relationship)
        return relationships

    def _get_embeddings_batch(
        self, text_list: List[str], batch_size: int = 10
    ) -> Dict[str, List[float]]:
        from openai import OpenAI

        uncached_texts = [
            text for text in text_list if text not in self.embedding_cache
        ]
        if uncached_texts:
            print(
                f"        批量获取 {len(uncached_texts)} 个embedding（共 {len(text_list)} 个，{len(text_list) - len(uncached_texts)} 个已缓存）..."
            )
            client = OpenAI(
                base_url=self.embedding_base_url, api_key=self.embedding_api_key
            )
            safe_batch_size = max(1, min(10, batch_size))
            for batch_start in range(0, len(uncached_texts), safe_batch_size):
                batch_end = min(batch_start + safe_batch_size, len(uncached_texts))
                batch_texts = uncached_texts[batch_start:batch_end]
                try:
                    response = client.embeddings.create(
                        input=batch_texts, model=self.embedding_model
                    )
                    for (i, text) in enumerate(batch_texts):
                        if i < len(response.data):
                            self.embedding_cache[text] = response.data[i].embedding
                        else:
                            print(f"        警告：embedding返回数量不匹配，文本: {text[:50]}...")
                            try:
                                embedding = get_embedding(
                                    text,
                                    self.embedding_model,
                                    self.embedding_base_url,
                                    self.embedding_api_key,
                                )
                                self.embedding_cache[text] = embedding
                            except:
                                self.embedding_cache[text] = [0.0] * 1536
                    if len(uncached_texts) > batch_size:
                        print(
                            f"        已处理 {min(batch_end, len(uncached_texts))}/{len(uncached_texts)} 个embedding..."
                        )
                except Exception as e:
                    print(f"        批量获取embedding失败（批次 {batch_start}-{batch_end}）: {e}")
                    for text in batch_texts:
                        try:
                            embedding = get_embedding(
                                text,
                                self.embedding_model,
                                self.embedding_base_url,
                                self.embedding_api_key,
                            )
                            self.embedding_cache[text] = embedding
                        except Exception as e2:
                            print(f"        获取embedding失败（文本: {text[:50]}...）: {e2}")
                            self.embedding_cache[text] = [0.0] * 1536
        return {text: self.embedding_cache[text] for text in text_list}

    def _calculate_similarity_matrix(
        self, nodes: List[Dict], schema: Dict
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        print("  计算节点相似度（使用缓存和批量计算）...")
        similarity_matrix = {}
        node_types = {}
        for node in nodes:
            node_type = node["type"]
            if node_type not in node_types:
                node_types[node_type] = []
            node_types[node_type].append(node)
        for rel_type in schema["relationship_types"]:
            from_node_type = rel_type["from_node"]
            to_node_type = rel_type["to_node"]
            from_nodes = node_types.get(from_node_type, [])
            to_nodes = node_types.get(to_node_type, [])
            if not from_nodes or not to_nodes:
                continue
            rel_key = f"{rel_type['name']}:{from_node_type}->{to_node_type}"
            print(
                f"    计算关系 {rel_key} 的节点相似度（{len(from_nodes)} x {len(to_nodes)} = {len(from_nodes) * len(to_nodes)} 个节点对）..."
            )
            node_type_def = None
            for nt in schema["node_types"]:
                if nt["name"] == from_node_type:
                    node_type_def = nt
                    break
            if not node_type_def:
                continue
            all_attrs = [prop["name"] for prop in node_type_def["properties"]]
            if not all_attrs:
                continue
            all_node_strings = []
            for node_list in [from_nodes, to_nodes]:
                for node in node_list:
                    attr_string = self._build_attribute_string(node, all_attrs)
                    all_node_strings.append(attr_string)
            unique_node_strings = list(set(all_node_strings))
            embeddings_dict = self._get_embeddings_batch(unique_node_strings)
            node_embeddings = {}
            for node_list in [from_nodes, to_nodes]:
                for node in node_list:
                    attr_string = self._build_attribute_string(node, all_attrs)
                    node_embeddings[node["id"]] = embeddings_dict[attr_string]
            similarity_matrix[rel_key] = {}
            total_pairs = len(from_nodes) * len(to_nodes)
            processed_pairs = 0
            for from_node in from_nodes:
                similarity_matrix[rel_key][from_node["id"]] = {}
                from_embedding = node_embeddings[from_node["id"]]
                for to_node in to_nodes:
                    if from_node["id"] != to_node["id"]:
                        to_embedding = node_embeddings[to_node["id"]]
                        similarity = cosine_similarity(from_embedding, to_embedding)
                        similarity_matrix[rel_key][from_node["id"]][
                            to_node["id"]
                        ] = similarity
                        processed_pairs += 1
                        if processed_pairs % 1000 == 0:
                            print(
                                f"        已处理 {processed_pairs}/{total_pairs} 个节点对..."
                            )
            print(f"        完成！共计算 {processed_pairs} 个节点对的相似度")
        print(f"  Embedding缓存大小: {len(self.embedding_cache)} 个")
        return similarity_matrix

    def _calculate_node_similarity(
        self, node1: Dict, node2: Dict, schema: Dict
    ) -> float:
        node_type_def = None
        for nt in schema["node_types"]:
            if nt["name"] == node1["type"]:
                node_type_def = nt
                break
        if not node_type_def:
            return 0.0
        return self._calculate_string_similarity(node1, node2, node_type_def)

    def _calculate_string_similarity(
        self, node1: Dict, node2: Dict, node_type_def: Dict
    ) -> float:
        all_attrs = []
        for prop in node_type_def["properties"]:
            all_attrs.append(prop["name"])
        if not all_attrs:
            return 0.5
        attr_string1 = self._build_attribute_string(node1, all_attrs)
        attr_string2 = self._build_attribute_string(node2, all_attrs)
        try:
            embeddings_dict = self._get_embeddings_batch([attr_string1, attr_string2])
            embedding1 = embeddings_dict[attr_string1]
            embedding2 = embeddings_dict[attr_string2]
            similarity = cosine_similarity(embedding1, embedding2)
            return similarity
        except Exception as e:
            print(f"计算embedding相似度失败: {e}")
            return 0.5

    def _build_attribute_string(self, node: Dict, string_attrs: List[str]) -> str:
        attr_pairs = []
        for attr in string_attrs:
            if attr in node["properties"]:
                value = str(node["properties"][attr])
                attr_pairs.append(f"{attr}:{value}")
        return "{" + ",".join(attr_pairs) + "}"

    def _calculate_numeric_similarity(
        self, node1: Dict, node2: Dict, node_type_def: Dict
    ) -> float:
        numeric_attrs = []
        for prop in node_type_def["properties"]:
            if prop["type"] in ["int", "float"]:
                numeric_attrs.append(prop["name"])
        if not numeric_attrs:
            return 0.5
        distances = []
        for attr in numeric_attrs:
            if attr in node1["properties"] and attr in node2["properties"]:
                val1 = float(node1["properties"][attr])
                val2 = float(node2["properties"][attr])
                (min_val, max_val) = self._get_property_range(attr, node_type_def)
                if max_val > min_val:
                    normalized_distance = abs(val1 - val2) / (max_val - min_val)
                    distances.append(normalized_distance)
        if not distances:
            return 0.5
        avg_distance = np.mean(distances)
        similarity = 1.0 - avg_distance
        return max(0.0, min(1.0, similarity))

    def _get_property_range(
        self, attr_name: str, node_type_def: Dict
    ) -> Tuple[float, float]:
        for prop in node_type_def["properties"]:
            if prop["name"] == attr_name:
                min_val = prop.get("min_value", 0)
                max_val = prop.get("max_value", 100)
                return (float(min_val), float(max_val))
        return (0.0, 100.0)

    def _generate_ldbc_relationships(
        self,
        schema: Dict,
        nodes: List[Dict],
        similarity_matrix: Dict,
        relationship_count: int,
    ) -> List[Dict]:
        relationships = []

        def get_constraint_priority(rel_type):
            cardinality = rel_type.get("cardinality", "N:M")
            if cardinality == "1:1":
                return 0
            elif cardinality == "1:N":
                return 1
            elif cardinality == "N:1":
                return 2
            else:
                return 3

        sorted_rel_types = sorted(
            schema["relationship_types"], key=get_constraint_priority
        )
        for rel_type in sorted_rel_types:
            from_node_type = rel_type["from_node"]
            to_node_type = rel_type["to_node"]
            from_nodes = [n for n in nodes if n["type"] == from_node_type]
            to_nodes = [n for n in nodes if n["type"] == to_node_type]
            if not from_nodes or not to_nodes:
                continue
            rel_count = max(1, relationship_count // len(schema["relationship_types"]))
            for from_node in from_nodes:
                rel_key = f"{rel_type['name']}:{from_node_type}->{to_node_type}"
                if rel_key in similarity_matrix:
                    candidates = similarity_matrix[rel_key].get(from_node["id"], {})
                    if candidates:
                        sorted_candidates = sorted(
                            candidates.items(), key=lambda x: x[1], reverse=True
                        )
                        top_candidates = sorted_candidates[
                            : min(10, len(sorted_candidates))
                        ]
                        valid_candidates = self._filter_valid_candidates_with_nodes(
                            top_candidates, from_node, rel_type, relationships, to_nodes
                        )
                        p = 0.5
                        for (i, (candidate_id, similarity)) in enumerate(
                            valid_candidates
                        ):
                            geometric_prob = (1 - p) ** i * p
                            if random.random() < geometric_prob:
                                candidate_node = next(
                                    (n for n in to_nodes if n["id"] == candidate_id),
                                    None,
                                )
                                if (
                                    candidate_node
                                    and self._check_cardinality_constraint(
                                        from_node,
                                        candidate_node,
                                        rel_type,
                                        relationships,
                                    )
                                ):
                                    relationship = {
                                        "id": f"{rel_type['name']}_{len(relationships)}",
                                        "type": rel_type["name"],
                                        "from_node": from_node["id"],
                                        "to_node": candidate_node["id"],
                                        "properties": self._generate_relationship_properties(
                                            rel_type, from_node, candidate_node
                                        ),
                                    }
                                    relationships.append(relationship)
                else:
                    max_attempts = 10
                    attempts = 0
                    while attempts < max_attempts:
                        to_node = random.choice(to_nodes)
                        if self._check_cardinality_constraint(
                            from_node, to_node, rel_type, relationships
                        ):
                            relationship = {
                                "id": f"{rel_type['name']}_{len(relationships)}",
                                "type": rel_type["name"],
                                "from_node": from_node["id"],
                                "to_node": to_node["id"],
                                "properties": self._generate_relationship_properties(
                                    rel_type, from_node, to_node
                                ),
                            }
                            relationships.append(relationship)
                            break
                        attempts += 1
        return relationships

    def _generate_relationship_properties(
        self, rel_type: Dict, from_node: Dict, to_node: Dict
    ) -> Dict:
        properties = {}
        if (
            not rel_type.get("properties")
            or rel_type["properties"] is None
            or len(rel_type["properties"]) == 0
        ):
            print(f"关系类型 {rel_type['name']} 没有定义属性，返回空字典")
            return {}
        properties = self._generate_relationship_properties_with_llm(
            rel_type, from_node, to_node
        )
        return properties

    def _generate_relationship_properties_with_llm(
        self, rel_type: Dict, from_node: Dict, to_node: Dict
    ) -> Dict:
        properties = {}
        prop_info = []
        for prop in rel_type["properties"]:
            prop_type = prop.get("type", "string")
            prop_desc = f"- {prop['name']}: type={prop_type}"
            if prop.get("required"):
                prop_desc += " [required]"
            if prop.get("allowed_values"):
                prop_desc += f" [allowed values: {', '.join(prop['allowed_values'])}]"
            if prop.get("min_value") is not None:
                prop_desc += f" [min: {prop['min_value']}]"
            if prop.get("max_value") is not None:
                prop_desc += f" [max: {prop['max_value']}]"
            if prop.get("description"):
                prop_desc += f" - {prop['description']}"
            prop_info.append(prop_desc)
        prompt = f"""Generate properties for a {rel_type['name']} relationship between:\nFrom node: {from_node['type']} (ID: {from_node['id']})\nTo node: {to_node['type']} (ID: {to_node['id']})\n\nRequired properties:\n{chr(10).join(prop_info)}\n\nGenerate realistic values for these properties. Return only a JSON object with the property names as keys and their values as values.\nExample: {{"property1": "value1", "property2": 123}}"""
        try:
            (response, _) = run_llm(self.llm_model, prompt)
            if response:
                import json

                llm_properties_str = (
                    response.strip().replace("```json", "").replace("```", "")
                )
                llm_properties = json.loads(llm_properties_str)
                properties.update(llm_properties)
        except Exception as e:
            print(f"LLM生成关系属性失败: {e}")
            properties = self._generate_relationship_properties_simple(
                rel_type, from_node, to_node
            )
        return properties

    def _generate_relationship_properties_simple(
        self, rel_type: Dict, from_node: Dict, to_node: Dict
    ) -> Dict:
        properties = {}
        for prop in rel_type["properties"]:
            prop_name = prop["name"]
            prop_type = prop["type"]
            if prop_type == "string":
                if prop.get("allowed_values"):
                    properties[prop_name] = random.choice(prop["allowed_values"])
                elif prop.get("is_category"):
                    if "strength" in prop_name.lower():
                        properties[prop_name] = random.choice(["low", "medium", "high"])
                    elif "type" in prop_name.lower():
                        properties[prop_name] = random.choice(
                            ["type1", "type2", "type3"]
                        )
                    else:
                        properties[prop_name] = f"value_{random.randint(1, 100)}"
                else:
                    properties[
                        prop_name
                    ] = f"generated_{prop_name}_{random.randint(1, 1000)}"
            elif prop_type == "int":
                min_val = prop.get("min_value", 0)
                max_val = prop.get("max_value", 100)
                properties[prop_name] = random.randint(min_val, max_val)
            elif prop_type == "float":
                min_val = prop.get("min_value", 0.0)
                max_val = prop.get("max_value", 100.0)
                properties[prop_name] = round(random.uniform(min_val, max_val), 2)
            elif prop_type == "boolean":
                properties[prop_name] = random.choice([True, False])
            elif prop_type in ["date", "datetime"]:
                days_ago = random.randint(0, 30)
                if prop_type == "date":
                    properties[prop_name] = (
                        datetime.now() - timedelta(days=days_ago)
                    ).strftime("%Y-%m-%d")
                else:
                    properties[prop_name] = (
                        datetime.now() - timedelta(days=days_ago)
                    ).strftime("%Y-%m-%d %H:%M:%S")
        return properties

    def _filter_relationships_with_llm(
        self,
        schema: Dict,
        relationships: List[Dict],
        nodes: List[Dict],
        batch_size: int = 20,
    ) -> List[Dict]:
        print("  使用LLM筛选关系以满足约束...")
        filtered_relationships = []
        for i in range(0, len(relationships), batch_size):
            batch = relationships[i : i + batch_size]
            print(f"    处理第 {i // batch_size + 1} 批关系，共 {len(batch)} 条...")
            filtered_batch = self._filter_relationship_batch_with_llm(
                schema, batch, nodes
            )
            filtered_relationships.extend(filtered_batch)
        print(f"  关系筛选完成：原始 {len(relationships)} 条，筛选后 {len(filtered_relationships)} 条")
        return filtered_relationships

    def _filter_relationship_batch_with_llm(
        self, schema: Dict, relationships: List[Dict], nodes: List[Dict]
    ) -> List[Dict]:
        if not relationships:
            return []
        constraints_info = self._build_relationship_constraints_info(schema)
        relationship_data = []
        for rel in relationships:
            from_node = next((n for n in nodes if n["id"] == rel["from_node"]), None)
            to_node = next((n for n in nodes if n["id"] == rel["to_node"]), None)
            if from_node and to_node:
                relationship_data.append(
                    {
                        "relationship_type": rel["type"],
                        "from_node": {
                            "id": from_node["id"],
                            "type": from_node["type"],
                            "properties": from_node["properties"],
                        },
                        "to_node": {
                            "id": to_node["id"],
                            "type": to_node["type"],
                            "properties": to_node["properties"],
                        },
                    }
                )
        if not relationship_data:
            return []
        prompt = f"You are given a list of relationships and need to filter them based on business constraints.\n\nSchema Domain: {schema['domain']}\nSchema Name: {schema['name']}\n\nBusiness Constraints:\n{constraints_info}\n\nRelationships to evaluate:\n{json.dumps(relationship_data, indent=2, ensure_ascii=False)}\n\nPlease evaluate each relationship and determine if it satisfies all business constraints. If you cannot determine if a relationship is valid, take it as valid.\nReturn a JSON array with only the relationships that are valid (satisfy all constraints), i.e. delete all invalid relationships from the input array.\nReturn only the JSON array, no additional text.\n"
        for attempt in range(3):
            try:
                (response, _) = run_llm(self.llm_model, prompt)
                if response:
                    filtered_data_str = (
                        response.strip().replace("```json", "").replace("```", "")
                    )
                    filtered_data = json.loads(filtered_data_str)
                    filtered_relationships = []
                    for data in filtered_data:
                        relationship = {
                            "id": f"{data['relationship_type']}_{len(filtered_relationships)}",
                            "type": data["relationship_type"],
                            "from_node": data["from_node"]["id"],
                            "to_node": data["to_node"]["id"],
                            "properties": {},
                        }
                        filtered_relationships.append(relationship)
                    return filtered_relationships
            except Exception as e:
                print(f"LLM筛选关系失败, 正在重试 ({attempt + 1}/3)... 错误: {e}")
                time.sleep(5)
        print(f"LLM筛选关系失败: {e}")
        return relationships

    def _build_relationship_constraints_info(self, schema: Dict) -> str:
        constraints = []
        if schema.get("business_constraints"):
            for constraint in schema["business_constraints"]:
                constraint_type = constraint.get("constraint_type", "unknown")
                description = constraint.get("description", "")
                condition = constraint.get("condition", "")
                constraints.append(f"- {constraint_type}: {description}")
                if condition:
                    constraints.append(f"  condition: {condition}")
        return "\n".join(constraints) if constraints else "no special constraints"

    def _filter_valid_candidates_with_nodes(
        self,
        candidates: List[Tuple[str, float]],
        from_node: Dict,
        rel_type: Dict,
        existing_relationships: List[Dict],
        to_nodes: List[Dict],
    ) -> List[Tuple[str, float]]:
        valid_candidates = []
        for (candidate_id, similarity) in candidates:
            candidate_node = next(
                (n for n in to_nodes if n["id"] == candidate_id), None
            )
            if candidate_node and self._check_cardinality_constraint(
                from_node, candidate_node, rel_type, existing_relationships
            ):
                valid_candidates.append((candidate_id, similarity))
        return valid_candidates

    def _check_cardinality_constraint(
        self,
        from_node: Dict,
        to_node: Dict,
        rel_type: Dict,
        existing_relationships: List[Dict],
    ) -> bool:
        from_connections = self._count_connections(
            from_node["id"], rel_type["name"], "from", existing_relationships
        )
        if (
            rel_type.get("max_connections_per_from")
            and from_connections >= rel_type["max_connections_per_from"]
        ):
            return False
        to_connections = self._count_connections(
            to_node["id"], rel_type["name"], "to", existing_relationships
        )
        if (
            rel_type.get("max_connections_per_to")
            and to_connections >= rel_type["max_connections_per_to"]
        ):
            return False
        return True

    def _count_connections(
        self,
        node_id: str,
        rel_type_name: str,
        direction: str,
        existing_relationships: List[Dict],
    ) -> int:
        count = 0
        for rel in existing_relationships:
            if rel["type"] == rel_type_name:
                if direction == "from" and rel["from_node"] == node_id:
                    count += 1
                elif direction == "to" and rel["to_node"] == node_id:
                    count += 1
        return count

    def generate_cycle_data(
        self, schema: Dict, node_count_per_type: int = 5, existing_data: Dict = None
    ) -> Tuple[List[Dict], List[Dict]]:
        print(f"开始为 {schema['name']} 生成环数据...")
        cycle_patterns = schema.get("cycle_patterns", [])
        if not cycle_patterns:
            print(f"Schema {schema['name']} 没有预定义环模式")
            return ([], [])
        valid_cycle_patterns = [
            pattern for pattern in cycle_patterns if pattern.get("is_valid", False)
        ]
        if not valid_cycle_patterns:
            print(f"Schema {schema['name']} 没有有效的环模式")
            return ([], [])
        cycle_pattern = valid_cycle_patterns[0]
        cycle_path = cycle_pattern["cycle_path"]
        explanation = cycle_pattern["explanation"]
        print(f"使用预定义环模式: {cycle_pattern['name']}")
        print(f"环路径: {' -> '.join(cycle_path)}")
        print(f"环模式解释: {explanation}")
        (nodes, relationships) = self._generate_cycle_with_llm_from_pattern(
            schema, cycle_pattern, node_count_per_type
        )
        if nodes:
            nodes = self._resolve_unique_conflicts_post_processing(
                nodes, schema, existing_data
            )
        print(f"生成了 {len(nodes)} 个节点和 {len(relationships)} 个关系用于环")
        return (nodes, relationships)

    def _generate_cycle_with_llm_from_pattern(
        self, schema: Dict, cycle_pattern: Dict, node_count_per_type: int
    ) -> Tuple[List[Dict], List[Dict]]:
        print(f"  使用LLM生成环数据...")
        cycle_path = cycle_pattern["cycle_path"]
        example_cycle = cycle_pattern.get("example_cycle", {})
        cycle_description = self._build_cycle_description(schema, cycle_pattern)
        constraints_info = self._build_cycle_constraints_info(schema, cycle_pattern)
        prompt = f"""Generate {node_count_per_type} complete cycle instances for the {schema['domain']} domain.\n\nCycle Pattern: {cycle_pattern['name']}\nDescription: {cycle_pattern['description']}\nCycle Path: {' -> '.join(cycle_path)}\nExplanation: {cycle_pattern['explanation']}\n\n{cycle_description}\n\nConstraints:\n{constraints_info}\n\nRequirements:\n1. Generate {node_count_per_type} complete cycle instances\n2. Each cycle must be a true instance-level cycle (start and end at the same node instance)\n3. Use 'cycle_' prefix for all node and relationship IDs\n4. Ensure all unique properties are unique\n5. Follow the exact cycle path: {' -> '.join(cycle_path)}\n\nReturn the data as a JSON object with structured cycles:\n{{\n  "cycles": [\n    {{\n      "cycle_id": "cycle_1",\n      "path": [\n        {{"type": "NodeType", "id": "cycle_NodeType_0", "properties": {{...}}}},\n        {{"type": "RelType", "id": "cycle_RelType_0", "from_node": "cycle_NodeType_0", "to_node": "cycle_NodeType_1", "properties": {{...}}}},\n        {{"type": "NodeType", "id": "cycle_NodeType_1", "properties": {{...}}}},\n        {{"type": "RelType", "id": "cycle_RelType_1", "from_node": "cycle_NodeType_1", "to_node": "cycle_NodeType_2", "properties": {{...}}}},\n        ...\n        {{"type": "NodeType", "id": "cycle_NodeType_0", "properties": {{...}}}}  // return to the start node\n      ]\n    }},\n    ...\n  ]\n}}\n\nIMPORTANT: \n- Each cycle's path must follow the cycle_path pattern exactly\n- The last element in each cycle's path must be the same node instance as the first element\n- The path alternates between nodes and relationships: [node, rel, node, rel, ..., node]\n\nReturn only the JSON object, no additional text."""
        for attempt in range(3):
            try:
                (response, _) = run_llm(self.llm_model, prompt)
                if response:
                    cycle_data = json.loads(
                        response.strip().replace("```json", "").replace("```", "")
                    )
                    if "cycles" in cycle_data:
                        if self._validate_cycles_format(
                            cycle_data["cycles"], cycle_path
                        ):
                            (
                                nodes,
                                relationships,
                            ) = self._extract_nodes_and_rels_from_cycles(
                                cycle_data["cycles"]
                            )
                            return (nodes, relationships)
                        else:
                            print(f"LLM生成的环数据验证失败，正在重试 ({attempt + 1}/3)...")
                            continue
                    elif "nodes" in cycle_data and "relationships" in cycle_data:
                        nodes = cycle_data.get("nodes", [])
                        relationships = cycle_data.get("relationships", [])
                        if self._validate_cycle_data(nodes, relationships, cycle_path):
                            return (nodes, relationships)
                        else:
                            print(f"LLM生成的环数据验证失败，正在重试 ({attempt + 1}/3)...")
                            continue
                    else:
                        print(f"    未知的数据格式，无法解析")
                        continue
            except Exception as e:
                print(f"LLM生成环数据失败, 正在重试 ({attempt + 1}/3)... 错误: {e}")
                time.sleep(5)
        print(f"LLM生成环数据失败，使用备用方法")
        return ([], [])

    def _build_cycle_description(self, schema: Dict, cycle_pattern: Dict) -> str:
        cycle_path = cycle_pattern["cycle_path"]
        node_types_info = []
        for i in range(0, len(cycle_path), 2):
            if i < len(cycle_path):
                node_type_name = cycle_path[i]
                for node_type in schema["node_types"]:
                    if node_type["name"] == node_type_name:
                        prop_details = []
                        for prop in node_type["properties"]:
                            prop_desc = (
                                f"  - {prop['name']}: type={prop.get('type', 'string')}"
                            )
                            if prop.get("required"):
                                prop_desc += " [required]"
                            if prop.get("unique"):
                                prop_desc += " [unique]"
                            if prop.get("allowed_values"):
                                prop_desc += f" [allowed values: {', '.join(prop['allowed_values'])}]"
                            if prop.get("min_value") is not None:
                                prop_desc += f" [min: {prop['min_value']}]"
                            if prop.get("max_value") is not None:
                                prop_desc += f" [max: {prop['max_value']}]"
                            prop_details.append(prop_desc)
                        node_info = f"- {node_type_name}:\n" + "\n".join(prop_details)
                        node_types_info.append(node_info)
                        break
        relationship_types_info = []
        for i in range(1, len(cycle_path), 2):
            if i < len(cycle_path):
                rel_type_name = cycle_path[i]
                for rel_type in schema["relationship_types"]:
                    if rel_type["name"] == rel_type_name:
                        if rel_type.get("properties"):
                            prop_details = []
                            for prop in rel_type["properties"]:
                                prop_desc = f"  - {prop['name']}: type={prop.get('type', 'string')}"
                                if prop.get("required"):
                                    prop_desc += " [required]"
                                if prop.get("allowed_values"):
                                    prop_desc += f" [allowed values: {', '.join(prop['allowed_values'])}]"
                                if prop.get("min_value") is not None:
                                    prop_desc += f" [min: {prop['min_value']}]"
                                if prop.get("max_value") is not None:
                                    prop_desc += f" [max: {prop['max_value']}]"
                                prop_details.append(prop_desc)
                            rel_info = (
                                f"- {rel_type_name}: {rel_type['from_node']} -> {rel_type['to_node']}:\n"
                                + "\n".join(prop_details)
                            )
                        else:
                            rel_info = f"- {rel_type_name}: {rel_type['from_node']} -> {rel_type['to_node']} (no properties)"
                        relationship_types_info.append(rel_info)
                        break
        return f"Node Types Information in Cycle:\n{chr(10).join(list(set(node_types_info)))}\n\nRelationship Types Information in Cycle:\n{chr(10).join(list(set(relationship_types_info)))}\n\nIMPORTANT: Only generate properties that are defined in the schema above. Do not add any properties that are not listed.\nEnsure that string values are enclosed in double quotes, and boolean values are true/false (lowercase).\nFor date properties, use 'YYYY-MM-DD' format. For datetime properties, use 'YYYY-MM-DD HH:MM:SS' format."

    def _build_cycle_constraints_info(self, schema: Dict, cycle_pattern_or_path) -> str:
        constraints = []
        constraints.append("1. All node and relationship IDs must use 'cycle_' prefix")
        constraints.append("2. Each cycle must be a true instance-level cycle")
        constraints.append("3. All unique properties must be unique")
        if isinstance(cycle_pattern_or_path, dict):
            cycle_pattern = cycle_pattern_or_path
            node_types_involved = cycle_pattern.get("node_types_involved", [])
        else:
            cycle_path = cycle_pattern_or_path
            node_types_involved = []
            for i in range(0, len(cycle_path), 2):
                if i < len(cycle_path):
                    node_types_involved.append(cycle_path[i])
        for node_type in schema["node_types"]:
            if node_type["name"] in node_types_involved:
                node_constraints = self._build_constraints_info(schema, node_type)
                if node_constraints != "no special constraints":
                    constraints.append(f"Node Type '{node_type['name']}' Constraints:")
                    constraints.append(node_constraints)
        return "\n".join(constraints)

    def _resolve_unique_conflicts_post_processing(
        self, nodes: List[Dict], schema: Dict, existing_data: Dict = None
    ) -> List[Dict]:
        print(f"  后处理解决unique属性冲突...")
        node_type_map = {}
        for node_type in schema["node_types"]:
            node_type_map[node_type["name"]] = node_type
        for node in nodes:
            node_type = node_type_map.get(node["type"])
            if node_type:
                unique_properties = [
                    prop
                    for prop in node_type["properties"]
                    if prop.get("unique", False)
                ]
                for prop in unique_properties:
                    prop_name = prop["name"]
                    if prop_name in node.get("properties", {}):
                        current_value = node["properties"][prop_name]
                        new_value = self._generate_unique_value_simple(
                            prop, current_value, existing_data
                        )
                        node["properties"][prop_name] = new_value
        return nodes

    def _generate_unique_value_simple(
        self, prop: Dict, current_value: str, existing_data: Dict = None
    ) -> str:
        prop_name = prop["name"]
        prop_type = prop["type"]
        if prop_type == "string":
            if prop.get("is_id", False) or "id" in prop_name.lower():
                return f"cycle_{prop_name.upper()}_{random.randint(1000, 9999)}"
            else:
                return f"cycle_{current_value}_{random.randint(1000, 9999)}"
        elif prop_type == "int":
            return self._generate_unique_int_value(prop, existing_data)
        elif prop_type == "float":
            return self._generate_unique_float_value(prop, existing_data)
        else:
            return f"cycle_{current_value}_{random.randint(1000, 9999)}"

    def _generate_unique_int_value(self, prop: Dict, existing_data: Dict = None) -> int:
        min_val = prop.get("min_value", 0)
        max_val = prop.get("max_value", 100)
        used_values = set()
        if existing_data:
            for node in existing_data.get("nodes", []):
                for (prop_name, prop_value) in node.get("properties", {}).items():
                    if prop_name == prop["name"] and isinstance(prop_value, int):
                        used_values.add(prop_value)
        max_attempts = 1000
        for _ in range(max_attempts):
            candidate = random.randint(min_val, max_val)
            if candidate not in used_values:
                return candidate
        return random.randint(min_val, max_val)

    def _generate_unique_float_value(
        self, prop: Dict, existing_data: Dict = None
    ) -> float:
        min_val = prop.get("min_value", 0.0)
        max_val = prop.get("max_value", 100.0)
        used_values = set()
        if existing_data:
            for node in existing_data.get("nodes", []):
                for (prop_name, prop_value) in node.get("properties", {}).items():
                    if prop_name == prop["name"] and isinstance(
                        prop_value, (int, float)
                    ):
                        used_values.add(prop_value)
        max_attempts = 1000
        for _ in range(max_attempts):
            candidate = random.uniform(min_val, max_val)
            if prop.get("max_value", 0) <= 1000:
                candidate = round(candidate, 2)
            else:
                candidate = round(candidate, 0)
            if candidate not in used_values:
                return candidate
        return random.uniform(min_val, max_val)

    def _analyze_schema_for_cycles(self, schema: Dict) -> Tuple[bool, List[str], str]:
        print(f"  分析schema是否可能构成环...")
        node_types_info = []
        for node_type in schema["node_types"]:
            node_info = f"- {node_type['name']}: {node_type.get('description', '')}"
            node_types_info.append(node_info)
        relationship_types_info = []
        for rel_type in schema["relationship_types"]:
            rel_info = f"- {rel_type['name']}: {rel_type['from_node']} -> {rel_type['to_node']}"
            if rel_type.get("description"):
                rel_info += f" ({rel_type['description']})"
            relationship_types_info.append(rel_info)
        prompt = f"""Analyze whether the following graph schema can form a cycle.\n\nGraph Schema Information:\nDomain: {schema['domain']}\nName: {schema['name']}\n\nNode Types:\n{chr(10).join(node_types_info)}\n\nRelationship Types:\n{chr(10).join(relationship_types_info)}\n\nPlease analyze:\n1. Can this graph schema form a cycle of any length? Note: the cycle should align with business logic and common sense.\n2. If yes, provide a possible cycle path (alternating sequence of node types and relationship types)\n\nCycle definition: Starting from a specific node instance, through a series of relationship instances, eventually returning to the same node instance. This means the schema must allow for a path where:\n- A node instance of type A connects to a node instance of type B via relationship type R1\n- The node instance of type B connects to a node instance of type C via relationship type R2\n- And so on, until we return to the original node instance of type A\n\nPlease respond in JSON format:\n{{\n    "can_form_cycle": true/false,\n    "cycle_path": ["NodeType1", "RelationType1", "NodeType2", "RelationType2", "NodeType3", "RelationType3", "NodeType1"],\n    "explanation": "Explain why it can or cannot form a cycle at the instance level"\n}}\n\nReturn only JSON, no additional text."""
        for attempt in range(3):
            try:
                (response, _) = run_llm(self.llm_model, prompt)
                if response:
                    result = json.loads(
                        response.strip().replace("```json", "").replace("```", "")
                    )
                    can_form_cycle = result.get("can_form_cycle", False)
                    cycle_path = result.get("cycle_path", [])
                    explanation = result.get("explanation", "")
                    print(f"    分析结果: {explanation}")
                    self._save_cycle_pattern_to_schema(
                        schema, can_form_cycle, cycle_path, explanation
                    )
                    return (can_form_cycle, cycle_path, explanation)
            except Exception as e:
                print(f"LLM分析环可能性失败, 正在重试 ({attempt + 1}/3)... 错误: {e}")
                time.sleep(5)
        print(f"LLM分析环可能性失败: {e}")
        return (False, [], "")

    def _save_cycle_pattern_to_schema(
        self,
        schema: Dict,
        can_form_cycle: bool,
        cycle_path: List[str],
        explanation: str,
    ):
        print(f"  保存环模式到schema文件...")
        schema_file_path = f"./schemas/{schema['domain']}_schemas.json"
        try:
            with open(schema_file_path, "r", encoding="utf-8") as f:
                schemas_data = json.load(f)
        except FileNotFoundError:
            print(f"    Schema文件不存在: {schema_file_path}")
            return False
        cycle_pattern = {
            "id": f"cycle_{schema['name']}_1",
            "name": f"{schema['name']}_cycle",
            "description": f"在{schema['domain']}领域的{schema['name']}中识别的环模式",
            "cycle_path": cycle_path,
            "cycle_length": len(cycle_path),
            "explanation": explanation,
            "node_types_involved": [cycle_path[i] for i in range(0, len(cycle_path), 2)]
            if cycle_path
            else [],
            "relationship_types_involved": [
                cycle_path[i] for i in range(1, len(cycle_path), 2)
            ]
            if cycle_path
            else [],
        }
        schema_updated = False
        for (i, existing_schema) in enumerate(schemas_data):
            if existing_schema.get("name") == schema.get("name"):
                existing_schema["cycle_patterns"] = [cycle_pattern]
                schemas_data[i] = existing_schema
                schema_updated = True
                break
        if not schema_updated:
            print(f"    未找到对应的schema: {schema.get('name')}")
            return False
        try:
            with open(schema_file_path, "w", encoding="utf-8") as f:
                json.dump(schemas_data, f, ensure_ascii=False, indent=2)
            print(f"    成功保存环模式到schema文件")
            return True
        except Exception as e:
            print(f"    保存环模式到schema文件失败: {e}")
            return False

    def _validate_cycles_format(
        self, cycles: List[Dict], expected_cycle_path: List[str]
    ) -> bool:
        if not cycles:
            print(f"    cycles数组为空")
            return False
        expected_path_length = len(expected_cycle_path)
        for (cycle_idx, cycle) in enumerate(cycles):
            if "path" not in cycle:
                print(f"    cycle_{cycle_idx} 缺少path字段")
                return False
            path = cycle["path"]
            if len(path) != expected_path_length:
                print(
                    f"    cycle_{cycle_idx} path长度不匹配: 期望{expected_path_length}, 实际{len(path)}"
                )
                return False
            if "from_node" in path[0] or "from_node" in path[-1]:
                print(f"    cycle_{cycle_idx} path必须以节点开始和结束")
                return False
            first_node = path[0]
            last_node = path[-1]
            if first_node.get("id") != last_node.get("id"):
                print(
                    f"    cycle_{cycle_idx} 第一个节点({first_node.get('id')})和最后一个节点({last_node.get('id')})不是同一个实例"
                )
                return False
            for (i, item) in enumerate(path):
                expected_type = expected_cycle_path[i]
                actual_type = item.get("type")
                if actual_type != expected_type:
                    print(
                        f"    cycle_{cycle_idx} path[{i}] 类型不匹配: 期望{expected_type}, 实际{actual_type}"
                    )
                    return False
                if "from_node" in item:
                    if i % 2 == 0:
                        print(f"    cycle_{cycle_idx} path[{i}] 关系应该在奇数索引位置")
                        return False
                    if i > 0:
                        prev_node = path[i - 1]
                        if item["from_node"] != prev_node.get("id"):
                            print(
                                f"    cycle_{cycle_idx} path[{i}] from_node({item['from_node']})与上一个节点({prev_node.get('id')})不匹配"
                            )
                            return False
                    if i < len(path) - 1:
                        next_node = path[i + 1]
                        if item["to_node"] != next_node.get("id"):
                            print(
                                f"    cycle_{cycle_idx} path[{i}] to_node({item['to_node']})与下一个节点({next_node.get('id')})不匹配"
                            )
                            return False
                elif i % 2 != 0:
                    print(f"    cycle_{cycle_idx} path[{i}] 节点应该在偶数索引位置")
                    return False
            for (i, item) in enumerate(path):
                if "id" not in item or "type" not in item:
                    print(f"    cycle_{cycle_idx} path[{i}] 缺少id或type字段")
                    return False
                if "from_node" in item:
                    if "to_node" not in item:
                        print(f"    cycle_{cycle_idx} path[{i}] 关系缺少to_node字段")
                        return False
        print(f"    成功验证{len(cycles)}个环")
        return True

    def _extract_nodes_and_rels_from_cycles(
        self, cycles: List[Dict]
    ) -> Tuple[List[Dict], List[Dict]]:
        nodes = []
        relationships = []
        node_ids_seen = set()
        rel_ids_seen = set()
        for cycle in cycles:
            if "path" not in cycle:
                continue
            for item in cycle["path"]:
                if "from_node" in item:
                    rel_id = item.get("id")
                    if rel_id and rel_id not in rel_ids_seen:
                        relationships.append(
                            {
                                "id": item["id"],
                                "type": item["type"],
                                "from_node": item["from_node"],
                                "to_node": item["to_node"],
                                "properties": item.get("properties", {}),
                            }
                        )
                        rel_ids_seen.add(rel_id)
                else:
                    node_id = item.get("id")
                    if node_id and node_id not in node_ids_seen:
                        nodes.append(
                            {
                                "id": item["id"],
                                "type": item["type"],
                                "properties": item.get("properties", {}),
                            }
                        )
                        node_ids_seen.add(node_id)
        return (nodes, relationships)

    def _validate_cycle_data(
        self,
        nodes: List[Dict],
        relationships: List[Dict],
        expected_cycle_path: List[str],
    ) -> bool:
        if not nodes or not relationships:
            return False
        expected_node_types = set()
        for i in range(0, len(expected_cycle_path), 2):
            if i < len(expected_cycle_path):
                expected_node_types.add(expected_cycle_path[i])
        expected_relationship_types = set()
        for i in range(1, len(expected_cycle_path), 2):
            if i < len(expected_cycle_path):
                expected_relationship_types.add(expected_cycle_path[i])
        node_types = set((node["type"] for node in nodes))
        if not expected_node_types.issubset(node_types):
            print(f"    缺少节点类型: {expected_node_types - node_types}")
            return False
        relationship_types = set((rel["type"] for rel in relationships))
        if not expected_relationship_types.issubset(relationship_types):
            print(f"    缺少关系类型: {expected_relationship_types - relationship_types}")
            return False
        return self._validate_instance_level_cycle(
            nodes, relationships, expected_cycle_path
        )

    def _validate_instance_level_cycle(
        self, nodes: List[Dict], relationships: List[Dict], cycle_path: List[str]
    ) -> bool:
        if len(cycle_path) < 3:
            return False
        node_map = {node["id"]: node for node in nodes}
        rel_map = {rel["id"]: rel for rel in relationships}
        nodes_by_type = {}
        for node in nodes:
            node_type = node["type"]
            if node_type not in nodes_by_type:
                nodes_by_type[node_type] = []
            nodes_by_type[node_type].append(node)
        rels_by_type = {}
        for rel in relationships:
            rel_type = rel["type"]
            if rel_type not in rels_by_type:
                rels_by_type[rel_type] = []
            rels_by_type[rel_type].append(rel)
        start_node_type = cycle_path[0]
        if start_node_type not in nodes_by_type:
            print(f"    起始节点类型 {start_node_type} 没有实例")
            return False
        for start_node in nodes_by_type[start_node_type]:
            if self._can_form_cycle_from_node(
                start_node, cycle_path, nodes_by_type, rels_by_type, node_map, rel_map
            ):
                print(f"    找到实例级别的环，起始节点: {start_node['id']}")
                return True
        print(f"    无法找到实例级别的环")
        return False

    def _can_form_cycle_from_node(
        self,
        start_node: Dict,
        cycle_path: List[str],
        nodes_by_type: Dict,
        rels_by_type: Dict,
        node_map: Dict,
        rel_map: Dict,
    ) -> bool:
        current_node = start_node
        visited_nodes = {start_node["id"]}
        for i in range(1, len(cycle_path), 2):
            if i >= len(cycle_path):
                break
            rel_type = cycle_path[i]
            next_node_type = (
                cycle_path[i + 1] if i + 1 < len(cycle_path) else cycle_path[0]
            )
            found_relationship = None
            if rel_type in rels_by_type:
                for rel in rels_by_type[rel_type]:
                    if rel["from_node"] == current_node["id"]:
                        found_relationship = rel
                        break
            if not found_relationship:
                return False
            target_node_id = found_relationship["to_node"]
            if target_node_id not in node_map:
                return False
            target_node = node_map[target_node_id]
            if target_node["type"] != next_node_type:
                return False
            current_node = target_node
            if i + 1 >= len(cycle_path) - 1:
                return current_node["id"] == start_node["id"]
        return False

    def generate_data_with_cycles(
        self, schema: Dict, cycle_node_count: int = 5
    ) -> Tuple[List[Dict], List[Dict]]:
        print(f"开始为 {schema['name']} 生成环数据...")
        (cycle_nodes, cycle_relationships) = self.generate_cycle_data(
            schema, cycle_node_count
        )
        print(f"生成了 {len(cycle_nodes)} 个节点和 {len(cycle_relationships)} 个关系")
        return (cycle_nodes, cycle_relationships)

    def save_generated_data(
        self, nodes: List[Dict], relationships: List[Dict], output_file: str
    ):
        data = {
            "nodes": nodes,
            "relationships": relationships,
            "generation_time": datetime.now().isoformat(),
            "node_count": len(nodes),
            "relationship_count": len(relationships),
        }
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"数据已保存到: {output_file}")


def main():

    generator = DataGenerator()
    CYCLIC_SCHEMA_NAMES = [
        "banking_system",
        "social_network",
        "dating_system",
        "ecommerce_system",
        "entertainment_system",
    ]
    schemas_dir = "./schemas"
    if not os.path.exists(schemas_dir):
        print(f"Schemas目录不存在: {schemas_dir}")
        return
    schema_files = [f for f in os.listdir(schemas_dir) if f.endswith("_schemas.json")]
    if not schema_files:
        print(f"Schemas目录中没有找到schema文件")
        return
    print(f"找到 {len(schema_files)} 个schema文件，开始处理...")
    todo = ["social_network"]
    for schema_file in schema_files:
        schema_path = os.path.join(schemas_dir, schema_file)
        print(f"\n{'=' * 60}")
        print(f"处理schema文件: {schema_file}")
        print(f"{'=' * 60}")
        try:
            schemas = generator.load_schema(schema_path)
            for schema in schemas:
                if schema["name"] not in todo:
                    continue
                print("\n1. 使用LLM约束感知生成:")
                (
                    regular_nodes,
                    regular_relationships,
                ) = generator.generate_data_for_schema(
                    schema,
                    node_count=200,
                    relationship_count=100,
                    use_ldbc=True,
                    use_llm_constraints=True,
                )
                print("\n2. 测试环数据生成:")
                (
                    cycle_nodes,
                    cycle_relationships,
                ) = generator.generate_data_with_cycles(schema, cycle_node_count=3)
                print("\n3. 合并环数据和常规数据:")
                all_nodes = cycle_nodes + regular_nodes
                all_relationships = cycle_relationships + regular_relationships
                print(f"合并后生成了 {len(all_nodes)} 个节点和 {len(all_relationships)} 个关系")
                if cycle_nodes:
                    print(
                        f"其中包含环数据: {len(cycle_nodes)} 个节点和 {len(cycle_relationships)} 个关系"
                    )
                output_file_combined = (
                    f"./data/{schema['domain']}_{schema['name']}_with_cycles_data.json"
                )
                os.makedirs("./data", exist_ok=True)
                generator.save_generated_data(
                    all_nodes, all_relationships, output_file_combined
                )
        except Exception as e:
            print(f"处理schema文件 {schema_file} 时出错: {e}")
            continue
    print(f"\n{'=' * 60}")
    print("所有schema文件处理完成！")
    print(f"{'=' * 60}")


if __name__ == "__main__":

    main()
