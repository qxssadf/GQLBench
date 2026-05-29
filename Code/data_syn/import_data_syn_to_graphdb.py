#!/usr/bin/env python3
import os

import json

import sys

from typing import Dict, List, Any, Optional

from datetime import datetime

from tqdm import tqdm

import time

import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:

    from Config import *
    from import_graph_data import Import_Graph_Data_neo4j
    from import_graph_data_nebula import Import_Graph_Data_Nebula

except ImportError as e:

    print(f"警告: 无法导入Config或import_graph_data模块: {e}")
    print("将使用默认配置")
    NEO4j_INSERT_BATCH_SIZE = 1000
    NEBULA_INSERT_BATCH_SIZE = 1000
    NEO4j_TRANSACTION_DELAY = 0.01
    NEO4j_DEADLOCK_RETRY_COUNT = 3
    NEBULA_SESSION_POOL_SIZE = 10
    NEBULA_THREAD_POOL_WORKERS = 4
    NEBULA_ASYNC_SEMAPHORE = 8


class DataSynConverter:
    def __init__(self, gql_type="cypher", output_dir="./import_commands"):
        self.gql_type = gql_type
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.schema_prop_types = {}

    def infer_property_type(self, values: List[Any]) -> str:
        if not values:
            return "STRING"
        non_null_values = [v for v in values if v is not None]
        if not non_null_values:
            return "STRING"
        types = set()
        for val in non_null_values:
            if isinstance(val, bool):
                types.add("bool")
            elif isinstance(val, int):
                types.add("int")
            elif isinstance(val, float):
                types.add("float")
            elif isinstance(val, str):
                try:
                    datetime.fromisoformat(val.replace("Z", "+00:00"))
                    types.add("datetime")
                except:
                    types.add("str")
            elif isinstance(val, datetime):
                types.add("datetime")
            else:
                types.add("str")
        if "datetime" in types:
            return "LOCAL DATETIME"
        elif "bool" in types:
            return "BOOL"
        elif "int" in types and "float" not in types:
            return "INT"
        elif "float" in types:
            return "FLOAT"
        else:
            return "STRING"

    def nebula_type_mapping(
        self, type_str: str = None, inferred_type: str = None
    ) -> str:
        if inferred_type:
            return inferred_type
        if not type_str or type_str == "":
            return "STRING"
        t = type_str.strip()
        t_upper = t.upper()
        t_lower = t.lower()
        if (
            t_upper in ("DATE", "DATETIME")
            or t_lower in ("date", "datetime")
            or "timestamp" in t_lower
            or ("datetime" in t_lower)
        ):
            return "LOCAL DATETIME"
        if (
            t_upper in ("TEXT", "BLOB", "STRING")
            or "varchar" in t_lower
            or "char" in t_lower
        ):
            return "STRING"
        if t_upper == "INTEGER" or "int" in t_lower or t_upper in ("BIT", "YEAR"):
            return "INT"
        if (
            t_upper == "REAL"
            or "number" in t_lower
            or "float" in t_lower
            or ("double" in t_lower)
            or ("decimal" in t_lower)
            or ("numeric" in t_lower)
        ):
            return "FLOAT"
        if t_upper in ("BOOL", "BOOLEAN") or "bool" in t_lower:
            return "BOOL"
        return "STRING"

    def val_mapping(self, val, for_query=False, node_type=None, prop_name=None):
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return val
        elif isinstance(val, bool):
            return val
        elif isinstance(val, str):
            if val == "":
                if node_type and prop_name and (node_type in self.schema_prop_types):
                    if prop_name in self.schema_prop_types[node_type]:
                        schema_type = self.schema_prop_types[node_type][prop_name]
                        if schema_type.upper() in (
                            "LOCAL DATETIME",
                            "LOCALDATETIME",
                            "DATETIME",
                            "DATE",
                            "TIME",
                        ):
                            return None
            if node_type and prop_name and (node_type in self.schema_prop_types):
                if prop_name in self.schema_prop_types[node_type]:
                    schema_type = self.schema_prop_types[node_type][prop_name]
                    if schema_type.lower() in ("string", "text", "varchar", "char"):
                        if for_query:
                            if self.gql_type == "cypher":
                                val_escaped = val.replace("\\", "\\\\").replace(
                                    '"', '\\"'
                                )
                                return f'"{val_escaped}"'
                            else:
                                val_escaped = val.replace("\\", "\\\\").replace(
                                    "'", "\\'"
                                )
                                return f"'{val_escaped}'"
                        else:
                            return val
            try:
                val_clean = val.replace("Z", "+00:00") if val.endswith("Z") else val
                dt = datetime.fromisoformat(val_clean)
                if self.gql_type == "cypher":
                    if for_query:
                        return f'datetime("{val}")'
                    else:
                        return val
                elif for_query:
                    val_for_format = val.replace("Z", "") if val.endswith("Z") else val
                    if "T" in val_for_format:
                        time_part = (
                            val_for_format.split("T")[1]
                            if "T" in val_for_format
                            else ""
                        )
                        if ":" in time_part:
                            if "." in time_part:
                                return f'local_datetime("{val_for_format}", "%Y-%m-%dT%H:%M:%S.%f")'
                            else:
                                return f'local_datetime("{val_for_format}", "%Y-%m-%dT%H:%M:%S")'
                        else:
                            return f'local_datetime("{val_for_format}", "%Y-%m-%d")'
                    elif " " in val_for_format and ":" in val_for_format:
                        return (
                            f'local_datetime("{val_for_format}", "%Y-%m-%d %H:%M:%S")'
                        )
                    else:
                        return f'local_datetime("{val_for_format}", "%Y-%m-%d")'
                else:
                    return val
            except:
                if val == "" and for_query:
                    if (
                        node_type
                        and prop_name
                        and (node_type in self.schema_prop_types)
                    ):
                        if prop_name in self.schema_prop_types[node_type]:
                            schema_type = self.schema_prop_types[node_type][prop_name]
                            if schema_type.upper() in (
                                "LOCAL DATETIME",
                                "LOCALDATETIME",
                                "DATETIME",
                                "DATE",
                                "TIME",
                            ):
                                return None
                if for_query:
                    if self.gql_type == "cypher":
                        val_escaped = val.replace("\\", "\\\\").replace('"', '\\"')
                        return f'"{val_escaped}"'
                    else:
                        val_escaped = val.replace("\\", "\\\\").replace("'", "\\'")
                        return f"'{val_escaped}'"
                else:
                    return val
        elif isinstance(val, datetime):
            iso = val.isoformat()
            if self.gql_type == "cypher":
                if for_query:
                    return f'datetime("{iso}")'
                else:
                    return iso
            elif for_query:
                return f'local_datetime("{iso}", "%Y-%m-%dT%H:%M:%S")'
            else:
                return iso
        else:
            return str(val)

    def load_data_file(self, file_path: str) -> Dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def generate_node_commands(self, nodes: List[Dict], node_type: str) -> List[Dict]:
        commands = []
        batch_size = (
            NEO4j_INSERT_BATCH_SIZE
            if self.gql_type == "cypher"
            else NEBULA_INSERT_BATCH_SIZE
        )
        node_type_groups = {}
        for node in nodes:
            node_type_name = node.get("type", node_type)
            if node_type_name not in node_type_groups:
                node_type_groups[node_type_name] = []
            node_type_groups[node_type_name].append(node)
        for (node_type_name, type_nodes) in node_type_groups.items():
            for batch_start in range(0, len(type_nodes), batch_size):
                batch_nodes = type_nodes[batch_start : batch_start + batch_size]
                if self.gql_type == "cypher":
                    pairs = []
                    for node in batch_nodes:
                        props = {"id": node["id"]}
                        node_type_name = node.get("type", node_type)
                        for (key, value) in node.get("properties", {}).items():
                            mapped_val = self.val_mapping(
                                value,
                                for_query=False,
                                node_type=node_type_name,
                                prop_name=key,
                            )
                            if mapped_val is not None:
                                props[key] = mapped_val
                        pairs.append(props)
                    if not pairs:
                        continue
                    prop_parts = []
                    for key in pairs[0].keys():
                        if key == "id":
                            prop_parts.append(f"`id`:pair.`id`")
                        else:
                            prop_parts.append(f"`{key}`:pair.`{key}`")
                    if prop_parts:
                        query = f"UNWIND $pairs AS pair CREATE (:`{node_type_name}` {{{', '.join(prop_parts)}}})"
                    else:
                        query = f"UNWIND $pairs AS pair CREATE (:`{node_type_name}`)"
                    query += ";"
                    commands.append({"query": query, "params": pairs, "time_cols": []})
                else:
                    for (idx, node) in enumerate(batch_nodes):
                        kv_parts = []
                        kv_parts.append(f"`id_for_nebula`:{batch_start + idx}")
                        kv_parts.append(f'''`id`:"{node['id']}"''')
                        node_type_name = node.get("type", node_type)
                        for (key, value) in node.get("properties", {}).items():
                            mapped_val = self.val_mapping(
                                value,
                                for_query=True,
                                node_type=node_type_name,
                                prop_name=key,
                            )
                            if mapped_val is not None:
                                if isinstance(mapped_val, str) and (
                                    mapped_val.startswith("date(")
                                    or mapped_val.startswith("local_datetime(")
                                ):
                                    kv_parts.append(f"`{key}`:{mapped_val}")
                                elif (
                                    isinstance(mapped_val, str)
                                    and mapped_val.startswith("'")
                                    and mapped_val.endswith("'")
                                ):
                                    mapped_val = mapped_val[1:-1].replace('"', '\\"')
                                    kv_parts.append(f'`{key}`:"{mapped_val}"')
                                else:
                                    kv_parts.append(f"`{key}`:{mapped_val}")
                        prop_str = ", ".join(kv_parts)
                        query = f"INSERT (@`{node_type_name}`{{{prop_str}}})"
                        commands.append({"query": query, "params": [], "time_cols": []})
        return commands

    def generate_relationship_commands(
        self, relationships: List[Dict], nodes: List[Dict]
    ) -> List[Dict]:
        commands = []
        batch_size = (
            NEO4j_INSERT_BATCH_SIZE
            if self.gql_type == "cypher"
            else NEBULA_INSERT_BATCH_SIZE
        )
        node_map = {node["id"]: node for node in nodes}
        rel_type_groups = {}
        for rel in relationships:
            rel_type = rel.get("type", "RELATED_TO")
            if rel_type not in rel_type_groups:
                rel_type_groups[rel_type] = []
            rel_type_groups[rel_type].append(rel)
        for (rel_type, type_rels) in rel_type_groups.items():
            for batch_start in range(0, len(type_rels), batch_size):
                batch_rels = type_rels[batch_start : batch_start + batch_size]
                if self.gql_type == "cypher":
                    pairs = []
                    for rel in batch_rels:
                        from_id = rel.get("from_node")
                        to_id = rel.get("to_node")
                        if from_id not in node_map or to_id not in node_map:
                            continue
                        from_node = node_map[from_id]
                        to_node = node_map[to_id]
                        from_type = from_node.get("type")
                        to_type = to_node.get("type")
                        pair = {"from_id": from_id, "to_id": to_id}
                        for (key, value) in rel.get("properties", {}).items():
                            mapped_val = self.val_mapping(value, for_query=False)
                            if mapped_val is not None:
                                pair[key] = mapped_val
                        pairs.append(pair)
                    if not pairs:
                        continue
                    query = f"UNWIND $pairs AS pair "
                    query += f"MATCH (from), (to) "
                    query += f"WHERE from.`id` = pair.from_id AND to.`id` = pair.to_id "
                    prop_parts = []
                    for key in pairs[0].keys():
                        if key not in ["from_id", "to_id"]:
                            prop_parts.append(f"`{key}`:pair.`{key}`")
                    if prop_parts:
                        query += f"CREATE (from)-[:`{rel_type}` {{{', '.join(prop_parts)}}}]->(to);"
                    else:
                        query += f"CREATE (from)-[:`{rel_type}`]->(to);"
                    commands.append({"query": query, "params": pairs, "time_cols": []})
                else:
                    for (idx, rel) in enumerate(batch_rels):
                        from_id = rel.get("from_node")
                        to_id = rel.get("to_node")
                        if from_id not in node_map or to_id not in node_map:
                            continue
                        from_node = node_map[from_id]
                        to_node = node_map[to_id]
                        from_type = from_node.get("type")
                        to_type = to_node.get("type")
                        from_match = f'`id`:"{from_id}"'
                        to_match = f'`id`:"{to_id}"'
                        edge_props = [f"`id_for_nebula`:{batch_start + idx}"]
                        for (key, value) in rel.get("properties", {}).items():
                            mapped_val = self.val_mapping(value, for_query=True)
                            if mapped_val is not None:
                                if isinstance(mapped_val, str) and (
                                    mapped_val.startswith("date(")
                                    or mapped_val.startswith("local_datetime(")
                                ):
                                    edge_props.append(f"`{key}`:{mapped_val}")
                                elif (
                                    isinstance(mapped_val, str)
                                    and mapped_val.startswith("'")
                                    and mapped_val.endswith("'")
                                ):
                                    mapped_val = mapped_val[1:-1].replace('"', '\\"')
                                    edge_props.append(f'`{key}`:"{mapped_val}"')
                                else:
                                    edge_props.append(f"`{key}`:{mapped_val}")
                        edge_props_str = ", ".join(edge_props)
                        query = f"MATCH (n1:`{from_type}` {{{from_match}}}) LIMIT 1 "
                        query += f"MATCH (n2:`{to_type}` {{{to_match}}}) LIMIT 1 "
                        query += (
                            f"INSERT (n1)-[@`{rel_type}` {{{edge_props_str}}}]->(n2)"
                        )
                        commands.append({"query": query, "params": [], "time_cols": []})
        return commands

    def generate_nebula_schema(
        self,
        nodes: List[Dict],
        relationships: List[Dict],
        graph_name: str,
        schema_data: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        if self.gql_type != "nebula":
            return []
        node_type_prop_types = {}
        if schema_data:
            for schema in schema_data:
                for node_type_def in schema.get("node_types", []):
                    node_type = node_type_def.get("name", "")
                    if node_type not in node_type_prop_types:
                        node_type_prop_types[node_type] = {}
                    for prop_def in node_type_def.get("properties", []):
                        prop_name = prop_def.get("name", "")
                        prop_type = prop_def.get("type", "string")
                        node_type_prop_types[node_type][prop_name] = prop_type
            print(f"  从schema加载了 {len(node_type_prop_types)} 个节点类型的属性定义")
        node_type_props = {}
        for node in nodes:
            node_type = node.get("type", "Node")
            if node_type not in node_type_props:
                node_type_props[node_type] = {}
            for (prop_name, prop_value) in node.get("properties", {}).items():
                if prop_name not in node_type_props[node_type]:
                    node_type_props[node_type][prop_name] = []
                node_type_props[node_type][prop_name].append(prop_value)
        rel_type_props = {}
        rel_type_nodes = {}
        for rel in relationships:
            rel_type = rel.get("type", "RELATED_TO")
            if rel_type not in rel_type_props:
                rel_type_props[rel_type] = {}
                rel_type_nodes[rel_type] = []
            from_id = rel.get("from_node")
            to_id = rel.get("to_node")
            from_type = None
            to_type = None
            for node in nodes:
                if node["id"] == from_id:
                    from_type = node.get("type", "Node")
                if node["id"] == to_id:
                    to_type = node.get("type", "Node")
                if from_type and to_type:
                    break
            if from_type and to_type:
                if (from_type, to_type) not in rel_type_nodes[rel_type]:
                    rel_type_nodes[rel_type].append((from_type, to_type))
            for (prop_name, prop_value) in rel.get("properties", {}).items():
                if prop_name not in rel_type_props[rel_type]:
                    rel_type_props[rel_type][prop_name] = []
                rel_type_props[rel_type][prop_name].append(prop_value)
        node_lines = []
        for (node_type, props) in node_type_props.items():
            prop_defs = []
            prop_defs.append("`id_for_nebula` INT")
            prop_defs.append("`id` STRING")
            for (prop_name, values) in props.items():
                if (
                    node_type in node_type_prop_types
                    and prop_name in node_type_prop_types[node_type]
                ):
                    schema_type = node_type_prop_types[node_type][prop_name]
                    nebula_type = self.nebula_type_mapping(type_str=schema_type)
                    if prop_name == "contact_info" and node_type == "Owner":
                        print(
                            f"    [调试] {node_type}.{prop_name}: schema类型={schema_type} -> nebula类型={nebula_type}"
                        )
                else:
                    inferred_type = self.infer_property_type(values)
                    nebula_type = self.nebula_type_mapping(inferred_type=inferred_type)
                    if prop_name == "contact_info" and node_type == "Owner":
                        print(
                            f"    [调试] {node_type}.{prop_name}: 未找到schema定义，推断类型={inferred_type} -> nebula类型={nebula_type}"
                        )
                prop_defs.append(f"`{prop_name}` {nebula_type}")
            node_lines.append(
                f"NODE `{node_type}` (LABEL `{node_type}` {{{', '.join(prop_defs)}, PRIMARY KEY (`id_for_nebula`)}})"
            )
        edge_lines = []
        for (rel_type, node_pairs) in rel_type_nodes.items():
            rel_props = rel_type_props.get(rel_type, {})
            for (from_type, to_type) in node_pairs:
                prop_defs = []
                prop_defs.append("`id_for_nebula` INT")
                for (prop_name, values) in rel_props.items():
                    inferred_type = self.infer_property_type(values)
                    nebula_type = self.nebula_type_mapping(inferred_type=inferred_type)
                    prop_defs.append(f"`{prop_name}` {nebula_type}")
                if prop_defs:
                    edge_lines.append(
                        f"EDGE `{rel_type}` (`{from_type}`)-[:`{rel_type}` {{{', '.join(prop_defs)}, MULTIEDGE KEY(`id_for_nebula`)}}]->(`{to_type}`)"
                    )
                else:
                    edge_lines.append(
                        f"EDGE `{rel_type}` (`{from_type}`)-[:`{rel_type}` {{`id_for_nebula` INT, MULTIEDGE KEY(`id_for_nebula`)}}]->(`{to_type}`)"
                    )
        graph_type_name = f"{graph_name}_type"
        body = ", \n".join(node_lines + edge_lines)
        drop_graph_stmt = f"DROP GRAPH IF EXISTS {graph_name}"
        drop_graph_type_stmt = f"DROP GRAPH TYPE IF EXISTS {graph_type_name}"
        graph_type_stmt = (
            f"CREATE GRAPH TYPE IF NOT EXISTS {graph_type_name} AS {{ \n{body} \n}}"
        )
        create_graph_stmt = (
            f"CREATE GRAPH IF NOT EXISTS {graph_name} TYPED {graph_type_name}"
        )
        use_session_stmt = f"SESSION SET GRAPH {graph_name}"
        querys = [
            {"query": drop_graph_stmt, "params": [], "time_cols": []},
            {"query": drop_graph_type_stmt, "params": [], "time_cols": []},
            {"query": graph_type_stmt, "params": [], "time_cols": []},
            {"query": create_graph_stmt, "params": [], "time_cols": []},
            {"query": use_session_stmt, "params": [], "time_cols": []},
        ]
        return querys

    def convert_data_file(self, data_file_path: str, output_file_prefix: str):
        print(f"处理文件: {data_file_path}")
        data_filename = os.path.basename(data_file_path)
        name_without_ext = os.path.splitext(data_filename)[0]
        if name_without_ext.endswith("_with_cycles_data"):
            name_without_suffix = name_without_ext[: -len("_with_cycles_data")]
        else:
            name_without_suffix = name_without_ext
        if "_" in name_without_suffix:
            parts = name_without_suffix.split("_", 1)
            if len(parts) == 2:
                db_name = parts[1]
            else:
                db_name = name_without_suffix
        else:
            db_name = name_without_suffix
        db_output_dir = os.path.join(self.output_dir, db_name)
        os.makedirs(db_output_dir, exist_ok=True)
        data = self.load_data_file(data_file_path)
        nodes = data.get("nodes", [])
        relationships = data.get("relationships", [])
        print(f"  节点数: {len(nodes)}, 关系数: {len(relationships)}")
        schema_data = None
        if self.gql_type == "nebula":
            data_filename = os.path.basename(data_file_path)
            if "_" in data_filename:
                domain = data_filename.split("_")[0]
                name_without_ext = os.path.splitext(data_filename)[0]
                if name_without_ext.endswith("_with_cycles_data"):
                    name_without_suffix = name_without_ext[: -len("_with_cycles_data")]
                else:
                    name_without_suffix = name_without_ext
                if "_" in name_without_suffix:
                    parts = name_without_suffix.split("_", 1)
                    if len(parts) == 2:
                        target_schema_name = parts[1]
                    else:
                        target_schema_name = None
                else:
                    target_schema_name = None
                schema_file = os.path.join(
                    os.path.dirname(os.path.dirname(data_file_path)),
                    "schemas",
                    f"{domain}_schemas.json",
                )
                if os.path.exists(schema_file):
                    try:
                        with open(schema_file, "r", encoding="utf-8") as f:
                            all_schemas = json.load(f)
                        if isinstance(all_schemas, list) and target_schema_name:
                            for schema in all_schemas:
                                if schema.get("name") == target_schema_name:
                                    schema_data = [schema]
                                    print(
                                        f"  已加载schema文件: {schema_file}, 匹配到schema: {target_schema_name}"
                                    )
                                    break
                            if not schema_data:
                                print(
                                    f"  警告: 在schema文件中未找到匹配的schema: {target_schema_name}"
                                )
                                schema_data = all_schemas
                        else:
                            schema_data = all_schemas
                            print(f"  已加载schema文件: {schema_file}")
                        if schema_data:
                            self.schema_prop_types = {}
                            for schema in schema_data:
                                for node_type_def in schema.get("node_types", []):
                                    node_type = node_type_def.get("name", "")
                                    if node_type not in self.schema_prop_types:
                                        self.schema_prop_types[node_type] = {}
                                    for prop_def in node_type_def.get("properties", []):
                                        prop_name = prop_def.get("name", "")
                                        prop_type = prop_def.get("type", "string")
                                        self.schema_prop_types[node_type][
                                            prop_name
                                        ] = prop_type
                            print(f"  已保存 {len(self.schema_prop_types)} 个节点类型的属性类型映射")
                    except Exception as e:
                        print(f"  警告: 无法加载schema文件 {schema_file}: {e}")
        node_commands = self.generate_node_commands(nodes, "Node")
        print(f"  生成节点命令: {len(node_commands)} 个批次")
        rel_commands = self.generate_relationship_commands(relationships, nodes)
        print(f"  生成关系命令: {len(rel_commands)} 个批次")
        schema_commands = []
        if self.gql_type == "nebula":
            graph_name = db_name
            schema_commands = self.generate_nebula_schema(
                nodes, relationships, graph_name, schema_data
            )
            print(f"  生成schema命令: {len(schema_commands)} 条")
        if schema_commands:
            schema_file = os.path.join(
                db_output_dir, f"schema_{self.gql_type}_commands.txt"
            )
            with open(schema_file, "w", encoding="utf-8") as f:
                json.dump(schema_commands, f, ensure_ascii=False, indent=2)
            print(f"  保存schema命令到: {schema_file}")
        if node_commands:
            node_file = os.path.join(
                db_output_dir, f"node_{self.gql_type}_commands.txt"
            )
            with open(node_file, "w", encoding="utf-8") as f:
                json.dump(node_commands, f, ensure_ascii=False, indent=2)
            print(f"  保存节点命令到: {node_file}")
        if rel_commands:
            rel_file = os.path.join(db_output_dir, f"rel_{self.gql_type}_commands.txt")
            with open(rel_file, "w", encoding="utf-8") as f:
                json.dump(rel_commands, f, ensure_ascii=False, indent=2)
            print(f"  保存关系命令到: {rel_file}")
        return (node_commands, rel_commands, schema_commands)


class DataSynImporter:
    def __init__(self, gql_type="cypher", use_remote_db=False, use_async=True):
        self.gql_type = gql_type
        self.use_remote_db = use_remote_db
        self.use_async = use_async
        if gql_type == "cypher":
            self.importer = Import_Graph_Data_neo4j(
                op_db=True, use_remote_db=use_remote_db, use_async=use_async
            )
        else:
            self.importer = Import_Graph_Data_Nebula(
                op_db=True,
                use_remote_db=use_remote_db,
                use_async=use_async,
                schema="/datasyn",
            )

    def import_from_commands_dir(self, commands_dir: str, database_name: str):
        import tempfile
        import shutil

        try:
            from Config import IMPORT_GRAPH_DATA_PATH

            temp_db_dir = tempfile.mkdtemp()
            target_dir = os.path.join(temp_db_dir, IMPORT_GRAPH_DATA_PATH)
            os.makedirs(target_dir, exist_ok=True)
            for file in os.listdir(commands_dir):
                if file.endswith("_commands.txt"):
                    shutil.copy(
                        os.path.join(commands_dir, file), os.path.join(target_dir, file)
                    )
            if self.gql_type == "cypher":
                db_name = self.importer.create_database(temp_db_dir)
                self.importer.import_graph_data(temp_db_dir, db_name)
            else:
                self.importer.import_graph_data(temp_db_dir, database_name)
            shutil.rmtree(temp_db_dir)
        except ImportError:
            if self.gql_type == "cypher":
                db_name = self.importer.create_database(commands_dir)
                self._import_neo4j_direct(commands_dir, db_name)
            else:
                self._import_nebula_direct(commands_dir, database_name)

    def _import_neo4j_direct(self, commands_dir: str, database_name: str):
        files = sorted(
            [
                f
                for f in os.listdir(commands_dir)
                if f.endswith("_commands.txt") and "cypher" in f
            ]
        )
        node_files = [f for f in files if "node" in f]
        rel_files = [f for f in files if "rel" in f]
        for file in node_files:
            print(f"执行节点文件: {file}")
            self.importer._execute_file_queries(commands_dir, file, database_name)
        for file in rel_files:
            print(f"执行关系文件: {file}")
            self.importer._execute_file_queries(commands_dir, file, database_name)

    def import_from_db_folder(self, db_folder: str, database_name: str):
        if self.gql_type == "cypher":
            db_name = self.importer.create_database(db_folder)
            self._import_neo4j_direct(db_folder, db_name)
        else:
            self._import_nebula_direct(db_folder, database_name)

    def _import_nebula_direct(self, commands_dir: str, schema_name: str):
        files = sorted(
            [
                f
                for f in os.listdir(commands_dir)
                if f.endswith("_commands.txt") and "nebula" in f
            ]
        )
        schema_files = [f for f in files if "schema" in f]
        node_files = [f for f in files if "node" in f]
        rel_files = [f for f in files if "rel" in f]
        if schema_files:
            print(f"=== 优先执行 {len(schema_files)} 个schema文件 ===")
            for file in schema_files:
                print(f"执行schema文件: {file}")
                self.importer._execute_file_queries(commands_dir, file, schema_name)
            time.sleep(5)
        if node_files:
            print(f"=== 执行 {len(node_files)} 个节点文件 ===")
            for file in node_files:
                print(f"执行节点文件: {file}")
                self.importer._execute_file_queries(commands_dir, file, schema_name)
            time.sleep(5)
        if rel_files:
            print(f"=== 执行 {len(rel_files)} 个关系文件 ===")
            for file in rel_files:
                print(f"执行关系文件: {file}")
                self.importer._execute_file_queries(commands_dir, file, schema_name)

    def close(self):
        if hasattr(self.importer, "close"):
            if self.use_async:
                self.importer.close()
            else:
                self.importer.close_sync() if hasattr(
                    self.importer, "close_sync"
                ) else self.importer.close()


def main():

    import argparse

    parser = argparse.ArgumentParser(description="将data_syn数据导入到Neo4j或Nebula")
    parser.add_argument(
        "--gql_type",
        choices=["cypher", "nebula"],
        default="cypher",
        help="图数据库类型: cypher (Neo4j) 或 nebula",
    )
    parser.add_argument("--data_dir", default="./data", help="数据文件目录")
    parser.add_argument("--output_dir", default="./import_commands", help="输出命令文件目录")
    parser.add_argument("--only_convert", action="store_true", help="仅生成命令文件，不执行导入")
    parser.add_argument("--only_import", action="store_true", help="仅执行导入，不生成命令文件")
    parser.add_argument("--use_remote_db", action="store_true", help="使用远程数据库")
    parser.add_argument("--use_async", action="store_true", default=True, help="使用异步模式")
    parser.add_argument("--data_file", default=None, help="指定单个数据文件（可选）")
    args = parser.parse_args()
    data_dir = os.path.abspath(args.data_dir)
    if not os.path.exists(data_dir):
        print(f"错误: 数据目录不存在: {data_dir}")
        return
    if not args.only_import:
        converter = DataSynConverter(gql_type=args.gql_type, output_dir=args.output_dir)
        if args.data_file:
            data_files = [os.path.join(data_dir, args.data_file)]
        else:
            data_files = [f for f in os.listdir(data_dir) if f.endswith(".json")]
        print(f"找到 {len(data_files)} 个数据文件")
        for data_file in data_files:
            data_file_path = os.path.join(data_dir, data_file)
            output_prefix = os.path.splitext(data_file)[0]
            converter.convert_data_file(data_file_path, output_prefix)
        print("转换完成！")
    if not args.only_convert:
        importer = DataSynImporter(
            gql_type=args.gql_type,
            use_remote_db=args.use_remote_db,
            use_async=args.use_async,
        )
        try:
            output_dir = os.path.abspath(args.output_dir)
            if args.data_file:
                db_name = os.path.splitext(args.data_file)[0]
                db_folders = [os.path.join(output_dir, db_name)]
            else:
                db_folders = []
                for item in os.listdir(output_dir):
                    item_path = os.path.join(output_dir, item)
                    if os.path.isdir(item_path):
                        files = [
                            f
                            for f in os.listdir(item_path)
                            if f.endswith("_commands.txt")
                        ]
                        if files:
                            db_folders.append(item_path)
            print(f"找到 {len(db_folders)} 个数据库文件夹")
            for db_folder in db_folders:
                db_name = os.path.basename(db_folder)
                print(f"\n{'=' * 60}")
                print(f"导入数据库: {db_name}")
                print(f"{'=' * 60}")
                try:
                    importer.import_from_db_folder(db_folder, db_name)
                    print(f"✅ 数据库 {db_name} 导入完成")
                except Exception as e:
                    print(f"❌ 数据库 {db_name} 导入失败: {e}")
                    import traceback

                    traceback.print_exc()
            importer.close()
        except Exception as e:
            print(f"导入出错: {e}")
            import traceback

            traceback.print_exc()
            importer.close()
            raise


if __name__ == "__main__":

    main()
