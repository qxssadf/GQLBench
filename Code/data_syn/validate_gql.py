#!/usr/bin/env python3
import os

import json

import sys

import argparse

from typing import List, Dict, Any, Tuple

import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:

    from Config import *
    from neo4j import GraphDatabase
    import neo4j
    from nebulagraph_python import NebulaClient, SessionConfig
    from nebulagraph_python.client._connection import ConnectionConfig
    from nebulagraph_python.data import HostAddress

except ImportError as e:

    print(f"警告: 无法导入必要的模块: {e}")
    print("请确保已安装 neo4j 和 nebulagraph-python")


def cypher_execute(db_name: str, cypher_statement: str) -> Tuple[Any, float]:

    from import_graph_data import Import_Graph_Data_neo4j
    import datetime

    db_name = Import_Graph_Data_neo4j.db_name(db_name)
    uri = "bolt://localhost:7687"
    username = NEO4jUSERNAME
    password = NEO4jPASSWORD

    def to_python_type(x):
        if isinstance(x, neo4j.time.DateTime):
            return datetime.datetime.fromisoformat(x.iso_format())
        else:
            return x

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        start_time = time.time()
        df = driver.execute_query(
            cypher_statement, database_=db_name, result_transformer_=neo4j.Result.to_df
        )
        cypher_time = time.time() - start_time
        res = [
            [to_python_type(cell) for cell in row] for row in df.itertuples(index=False)
        ]
        return (res, cypher_time)
    except Exception as e:
        print(f"Cypher 查询错误: {e}")
        return ([], 0.0)
    finally:
        driver.close()


def nebula_execute(db_name: str, nebula_statement: str) -> Tuple[Any, float]:

    from import_graph_data_nebula import Import_Graph_Data_Nebula
    import datetime

    db_name = Import_Graph_Data_Nebula.schema_name(db_name)
    host = "127.0.0.1"
    port = NEBULA_PORT
    username = NEBULA_USERNAME
    password = NEBULA_PASSWORD

    def to_python_type(x):
        if isinstance(x, datetime.datetime):
            return x
        elif isinstance(x, str):
            try:
                return datetime.datetime.fromisoformat(x)
            except:
                return x
        else:
            return x

    host_address = HostAddress(host=host, port=port)
    conn_config = ConnectionConfig(
        hosts=[host_address], request_timeout=300.0, connect_timeout=10.0
    )
    client = NebulaClient(
        hosts=[host_address],
        username=username,
        password=password,
        conn_config=conn_config,
        session_config=SessionConfig(schema="/datasyn"),
    )
    try:
        client.execute(f"SESSION SET GRAPH `{db_name}`")
        query = nebula_statement
        start_time = time.time()
        result = client.execute(query)
        nebula_time = time.time() - start_time
        df = result.as_pandas_df()
        res = [
            [to_python_type(cell) for cell in row] for row in df.itertuples(index=False)
        ]
        return (res, nebula_time)
    except Exception as e:
        print(f"NebulaGraph 查询错误: {e}")
        return ([], 0.0)
    finally:
        client.close()


def validate_gql_statement(
    gql_statement: str, gql_type: str, db_name: str
) -> Dict[str, Any]:

    result = {
        "statement": gql_statement,
        "valid": False,
        "error": None,
        "execution_time": 0.0,
        "result_count": 0,
    }
    try:
        if gql_type == "cypher":
            (res, exec_time) = cypher_execute(db_name, gql_statement)
            result["valid"] = True
            result["execution_time"] = exec_time
            result["result_count"] = len(res) if res else 0
        elif gql_type == "nebula":
            (res, exec_time) = nebula_execute(db_name, gql_statement)
            result["valid"] = True
            result["execution_time"] = exec_time
            result["result_count"] = len(res) if res else 0
        else:
            result["error"] = f"不支持的 GQL 类型: {gql_type}"
    except Exception as e:
        result["valid"] = False
        result["error"] = str(e)
    return result


def validate_template_file(
    template_file: str, gql_type: str, db_name: str, max_validate: int = None
) -> Dict[str, Any]:

    print(f"\n验证文件: {template_file}")
    print(f"GQL 类型: {gql_type}, 数据库: {db_name}")
    with open(template_file, "r", encoding="utf-8") as f:
        templates = json.load(f)
    if not isinstance(templates, list):
        print(f"错误: 模板文件格式不正确，应该是列表格式")
        return None
    total = len(templates)
    if max_validate:
        templates = templates[:max_validate]
        print(f"验证前 {len(templates)} 个模板（共 {total} 个）")
    else:
        print(f"验证所有 {total} 个模板")
    valid_count = 0
    invalid_count = 0
    zero_result_count = 0
    total_time = 0.0
    errors = []
    filtered_templates = []
    for (i, template) in enumerate(templates, 1):
        gql_statement = template.get("template", "").strip()
        if not gql_statement:
            continue
        print(f"\n[{i}/{len(templates)}] 验证模板...")
        print(
            f"  语句: {gql_statement}"
            if len(gql_statement) > 100
            else f"  语句: {gql_statement}"
        )
        result = validate_gql_statement(gql_statement, gql_type, db_name)
        if result["valid"]:
            valid_count += 1
            total_time += result["execution_time"]
            result_count = result["result_count"]
            template["result_count"] = result_count
            if result_count == 0:
                zero_result_count += 1
            else:
                filtered_templates.append(template)
            print(
                f"  ✓ 验证通过 (执行时间: {result['execution_time']:.4f}s, 结果数: {result_count})"
            )
        else:
            invalid_count += 1
            error_msg = result["error"]
            errors.append({"index": i, "statement": gql_statement, "error": error_msg})
            print(f"  ✗ 验证失败: {error_msg}")
    stats = {
        "total": len(templates),
        "valid": valid_count,
        "invalid": invalid_count,
        "zero_result": zero_result_count,
        "valid_rate": valid_count / len(templates) if templates else 0,
        "zero_result_rate": zero_result_count / valid_count if valid_count > 0 else 0,
        "total_execution_time": total_time,
        "avg_execution_time": total_time / valid_count if valid_count > 0 else 0,
        "errors": errors,
    }
    print(f"\n{'=' * 60}")
    print(f"验证完成!")
    print(f"  总数: {stats['total']}")
    print(f"  通过: {stats['valid']}")
    print(f"  失败: {stats['invalid']}")
    print(f"  通过率: {stats['valid_rate'] * 100:.2f}%")
    print(
        f"  返回0结果数: {stats['zero_result']} (占通过查询的 {stats['zero_result_rate'] * 100:.2f}%)"
    )
    print(f"  总执行时间: {stats['total_execution_time']:.2f}s")
    print(f"  平均执行时间: {stats['avg_execution_time']:.4f}s")
    if filtered_templates:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(base_dir, "templates_filter")
        os.makedirs(output_dir, exist_ok=True)
        input_basename = os.path.basename(template_file)
        output_filename = input_basename
        output_file = os.path.join(output_dir, output_filename)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(filtered_templates, f, ensure_ascii=False, indent=2)
        print(f"\n过滤后的文件已保存到: {output_file}")
        print(f"  保留 {len(filtered_templates)} 条查询（删除了 {zero_result_count} 条返回0结果的查询）")
    return stats


def extract_db_name_from_filename(template_file: str) -> str:

    import re

    basename = os.path.basename(template_file)
    basename = basename.replace(".json", "")
    parts = basename.split("_")
    if len(parts) >= 2 and parts[0] == "templates":
        for i in range(len(parts) - 1, -1, -1):
            if parts[i].isdigit():
                if i + 1 < len(parts):
                    return "_".join(parts[i + 1 :])
        return parts[-1]
    return None


def validate_directory(
    template_dir: str, gql_type_filter: str = None, max_validate: int = None
) -> Dict[str, Any]:

    if not os.path.isdir(template_dir):
        print(f"错误: 目录不存在: {template_dir}")
        return None
    template_files = [
        f
        for f in os.listdir(template_dir)
        if f.endswith(".json") and f.startswith("templates_")
    ]
    if not template_files:
        print(f"警告: 目录中没有找到模板文件: {template_dir}")
        return None
    if gql_type_filter:
        template_files = [f for f in template_files if gql_type_filter in f]

    def sort_key(filename):
        if "nebula" in filename:
            return (0, filename)
        elif "cypher" in filename:
            return (1, filename)
        else:
            return (2, filename)

    template_files.sort(key=sort_key)
    print(f"\n{'=' * 60}")
    print(f"找到 {len(template_files)} 个模板文件")
    print(f"{'=' * 60}\n")
    all_results = {}
    total_valid = 0
    total_invalid = 0
    total_zero_result = 0
    total_templates = 0
    total_time = 0.0
    for (i, filename) in enumerate(template_files, 1):
        template_file = os.path.join(template_dir, filename)
        print(f"\n{'=' * 60}")
        print(f"[{i}/{len(template_files)}] 处理文件: {filename}")
        print(f"{'=' * 60}")
        basename = os.path.basename(template_file)
        gql_type = None
        if "nebula" in basename:
            gql_type = "nebula"
        elif "cypher" in basename:
            gql_type = "cypher"
        else:
            print(f"警告: 无法从文件名推断 GQL 类型，跳过文件: {filename}")
            continue
        db_name = extract_db_name_from_filename(template_file)
        if not db_name:
            print(f"警告: 无法从文件名推断数据库名称，跳过文件: {filename}")
            continue
        stats = validate_template_file(template_file, gql_type, db_name, max_validate)
        if stats:
            all_results[filename] = stats
            total_valid += stats["valid"]
            total_invalid += stats["invalid"]
            total_zero_result += stats.get("zero_result", 0)
            total_templates += stats["total"]
            total_time += stats["total_execution_time"]
    summary = {
        "total_files": len(template_files),
        "processed_files": len(all_results),
        "total_templates": total_templates,
        "total_valid": total_valid,
        "total_invalid": total_invalid,
        "total_zero_result": total_zero_result,
        "overall_valid_rate": total_valid / total_templates
        if total_templates > 0
        else 0,
        "zero_result_rate": total_zero_result / total_valid if total_valid > 0 else 0,
        "total_execution_time": total_time,
        "avg_execution_time": total_time / total_valid if total_valid > 0 else 0,
        "file_results": all_results,
    }
    print(f"\n{'=' * 60}")
    print(f"批量验证完成!")
    print(f"{'=' * 60}")
    print(f"  处理文件数: {summary['processed_files']}/{summary['total_files']}")
    print(f"  总模板数: {summary['total_templates']}")
    print(f"  总通过: {summary['total_valid']}")
    print(f"  总失败: {summary['total_invalid']}")
    print(f"  总体通过率: {summary['overall_valid_rate'] * 100:.2f}%")
    print(
        f"  返回0结果数: {summary['total_zero_result']} (占通过查询的 {summary['zero_result_rate'] * 100:.2f}%)"
    )
    print(f"  总执行时间: {summary['total_execution_time']:.2f}s")
    print(f"  平均执行时间: {summary['avg_execution_time']:.4f}s")
    return summary


def main():

    parser = argparse.ArgumentParser(description="验证生成的 GQL 语句是否可以正常执行")
    parser.add_argument(
        "--template_dir",
        type=str,
        required=False,
        default="./templates",
        help="模板文件目录（将验证目录下所有模板文件，默认为 ./templates）",
    )
    parser.add_argument(
        "--gql_type_filter",
        type=str,
        choices=["cypher", "nebula"],
        required=False,
        help="只验证指定类型的文件（cypher 或 nebula）",
    )
    parser.add_argument(
        "--max_validate", type=int, default=None, help="每个文件最多验证的语句数量（默认全部验证）"
    )
    parser.add_argument("--output", type=str, default=None, help="输出验证结果到文件（JSON格式）")
    args = parser.parse_args()
    if not os.path.exists(args.template_dir):
        print(f"错误: 路径不存在: {args.template_dir}")
        return
    if os.path.isfile(args.template_dir):
        template_dir = os.path.dirname(args.template_dir)
        single_file = os.path.basename(args.template_dir)
        if not single_file.startswith("templates_") or not single_file.endswith(
            ".json"
        ):
            print(f"错误: 文件格式不正确，应该是 templates_*.json 格式: {single_file}")
            return
        original_listdir = os.listdir

        def filtered_listdir(path):
            if path == template_dir:
                return [single_file]
            return original_listdir(path)

        os.listdir = filtered_listdir
        try:
            summary = validate_directory(
                template_dir, args.gql_type_filter, args.max_validate
            )
        finally:
            os.listdir = original_listdir
    else:
        summary = validate_directory(
            args.template_dir, args.gql_type_filter, args.max_validate
        )
    if args.output and summary:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"\n验证结果已保存到: {args.output}")


if __name__ == "__main__":

    main()
