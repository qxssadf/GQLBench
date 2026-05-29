#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
过滤 nl_gql_pairs 文件夹中的查询，删除返回0结果数的语句
"""

import os
import json
import sys
import time
from typing import List, Dict, Any, Tuple

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from Config import *
    from neo4j import GraphDatabase
    import neo4j
    from nebulagraph_python import NebulaClient, SessionConfig
    from nebulagraph_python.client._connection import ConnectionConfig
    from nebulagraph_python.data import HostAddress
    from import_graph_data import Import_Graph_Data_neo4j
    from import_graph_data_nebula import Import_Graph_Data_Nebula
except ImportError as e:
    print(f"错误: 无法导入必要的模块: {e}")
    sys.exit(1)


def cypher_execute(db_name: str, cypher_statement: str) -> Tuple[Any, float]:
    """
    执行 Cypher 查询
    Args:
        db_name: 数据库名称（schema_name）
        cypher_statement: Cypher 查询语句
    Returns:
        (查询结果列表, 执行时间)
    """
    import datetime
    
    db_name = Import_Graph_Data_neo4j.db_name(db_name)
    uri = "bolt://localhost:7687"
    username = NEO4jUSERNAME
    password = NEO4jPASSWORD

    def to_python_type(x):
        """将 Neo4j 特有类型转换为 Python 类型"""
        if isinstance(x, neo4j.time.DateTime):
            return datetime.datetime.fromisoformat(x.iso_format())
        else:
            return x

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        start_time = time.time()
        df = driver.execute_query(
            cypher_statement,
            database_=db_name,
            result_transformer_=neo4j.Result.to_df
        )
        cypher_time = time.time() - start_time
        
        res = [
            [to_python_type(cell) for cell in row]
            for row in df.itertuples(index=False)
        ]
        return res, cypher_time
    except Exception as e:
        print(f"  Cypher 查询错误: {e}")
        return [], 0.0
    finally:
        driver.close()


def nebula_execute(db_name: str, nebula_statement: str) -> Tuple[Any, float]:
    """
    执行 NebulaGraph 查询
    Args:
        db_name: 数据库名称（schema_name）
        nebula_statement: nGQL 查询语句
    Returns:
        (查询结果列表, 执行时间)
    """
    import datetime
    
    db_name = Import_Graph_Data_Nebula.schema_name(db_name)
    host = "127.0.0.1"
    port = NEBULA_PORT
    username = NEBULA_USERNAME
    password = NEBULA_PASSWORD

    def to_python_type(x):
        """将 NebulaGraph 特有类型转换为 Python 类型"""
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
        hosts=[host_address],
        request_timeout=1200.0,  # 1200秒超时
        connect_timeout=10.0
    )
    client = NebulaClient(
        hosts=[host_address],
        username=username,
        password=password,
        conn_config=conn_config,
        session_config=SessionConfig(
            schema="/datasyn"
        )
    )
    try:
        client.execute(f'SESSION SET GRAPH `{db_name}`')
        query = nebula_statement
        start_time = time.time()
        result = client.execute(query)
        nebula_time = time.time() - start_time
        
        df = result.as_pandas_df()
        res = [
            [to_python_type(cell) for cell in row]
            for row in df.itertuples(index=False)
        ]
        return res, nebula_time
    except Exception as e:
        print(f"  NebulaGraph 查询错误: {e}")
        return [], 0.0
    finally:
        client.close()


def extract_schema_name_from_filename(filename: str) -> str:
    """
    从文件名中提取schema_name
    文件名格式: nl_gql_pairs_templates_{gql_type}_{domain}_schemas_{i}_{schema_name}.json
    例如: nl_gql_pairs_templates_cypher_电商_schemas_1_ecommerce_system.json
    返回: ecommerce_system
    """
    basename = os.path.basename(filename)
    # 移除扩展名
    basename = basename.replace('.json', '')
    # 移除前缀
    if basename.startswith('nl_gql_pairs_templates_'):
        basename = basename[len('nl_gql_pairs_templates_'):]
    
    # 匹配格式: {gql_type}_{domain}_schemas_{i}_{schema_name}
    parts = basename.split('_')
    if 'schemas' in parts:
        schemas_idx = parts.index('schemas')
        # schemas后面应该有一个数字，然后是schema_name
        if schemas_idx + 2 < len(parts):
            # 跳过数字，取后面的部分
            return '_'.join(parts[schemas_idx + 2:])
    return None


def filter_file(input_file: str, output_file: str, gql_type: str) -> Dict[str, Any]:
    """
    过滤单个文件，删除返回0结果的查询
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        gql_type: 'cypher' 或 'nebula'
    Returns:
        统计信息
    """
    print(f"\n处理文件: {os.path.basename(input_file)}")
    print(f"GQL 类型: {gql_type}")
    
    # 加载文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        print(f"  错误: 文件格式不正确，应该是列表格式")
        return None
    
    # 尝试从第一个条目获取schema_name，如果没有则从文件名提取
    file_schema_name = None
    if data and len(data) > 0:
        file_schema_name = data[0].get('schema_name', '')
    
    if not file_schema_name:
        # 从文件名提取作为备用
        file_schema_name = extract_schema_name_from_filename(input_file)
        if file_schema_name:
            print(f"  从文件名提取schema_name: {file_schema_name}")
        else:
            print(f"  警告: 无法从文件或文件名中获取schema_name")
    
    total_count = len(data)
    filtered_data = []
    zero_result_count = 0
    error_count = 0
    
    print(f"  总查询数: {total_count}")
    if file_schema_name:
        print(f"  使用schema_name: {file_schema_name}")
    
    for i, item in enumerate(data, 1):
        # 获取查询语句和schema_name
        if gql_type == 'cypher':
            query = item.get('cypher_template', '').strip()
        else:  # nebula
            query = item.get('cypher_template', '').strip()  # nebula文件中也用这个字段名
        
        # 优先使用条目中的schema_name，如果没有则使用文件级别的
        schema_name = item.get('schema_name', '') or file_schema_name or ''
        
        if not query:
            # 如果没有查询，保留该项
            filtered_data.append(item)
            continue
        
        if not schema_name:
            # 如果没有schema_name，保留该项并警告
            print(f"  [{i}/{total_count}] 警告: 缺少schema_name，保留该项")
            filtered_data.append(item)
            continue
        
        # 执行查询
        try:
            if gql_type == 'cypher':
                result, exec_time = cypher_execute(schema_name, query)
            else:  # nebula
                result, exec_time = nebula_execute(schema_name, query)
            
            result_count = len(result) if result else 0
            
            # 只保留结果数大于0的查询
            if result_count > 0:
                filtered_data.append(item)
                if (i % 10 == 0) or (i == total_count):
                    print(f"  [{i}/{total_count}] 保留 (结果数: {result_count}, 时间: {exec_time:.4f}s)")
            else:
                zero_result_count += 1
                if (i % 10 == 0) or (i == total_count):
                    print(f"  [{i}/{total_count}] 删除 (结果数为0)")
        except Exception as e:
            error_count += 1
            print(f"  [{i}/{total_count}] 执行出错: {e}")
            # 出错时也保留该项，避免误删
            filtered_data.append(item)
    
    # 保存过滤后的数据
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, ensure_ascii=False, indent=2)
    
    stats = {
        "total": total_count,
        "filtered": len(filtered_data),
        "removed": zero_result_count,
        "errors": error_count,
        "removal_rate": zero_result_count / total_count if total_count > 0 else 0
    }
    
    print(f"  完成: 原始 {total_count} 条, 保留 {len(filtered_data)} 条, 删除 {zero_result_count} 条 (错误 {error_count} 条)")
    
    return stats


def main():
    """主函数"""
    # 设置路径
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(base_dir, 'nl_gql_pairs')
    output_dir = os.path.join(base_dir, 'nl_gql_pairs_filter')
    
    if not os.path.exists(input_dir):
        print(f"错误: 输入目录不存在: {input_dir}")
        return
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取所有JSON文件
    json_files = [f for f in os.listdir(input_dir) if f.endswith('.json')]
    
    if not json_files:
        print(f"警告: 在 {input_dir} 中没有找到JSON文件")
        return
    
    print(f"找到 {len(json_files)} 个文件")
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    
    all_stats = []
    total_original = 0
    total_filtered = 0
    total_removed = 0
    total_errors = 0
    processed_files = []
    import ast
    if os.path.exists(f'{output_dir}/processed_cypher_files.txt'):
        with open(f'{output_dir}/processed_cypher_files.txt','r') as f:
            processed_files.extend(ast.literal_eval(f.read()))
    if os.path.exists(f'{output_dir}/processed_nebula_files.txt'):
        with open(f'{output_dir}/processed_nebula_files.txt','r') as f:
            processed_files.extend(ast.literal_eval(f.read()))
    # 处理每个文件
    for i, filename in enumerate(json_files, 1):
        if filename in processed_files:
            continue
        if 'nebula' in filename: # 先不做nebula
            continue
        input_file = os.path.join(input_dir, filename)
        output_file = os.path.join(output_dir, filename)
        
        # 判断GQL类型
        if 'cypher' in filename:
            gql_type = 'cypher'
        elif 'nebula' in filename:
            gql_type = 'nebula'
        else:
            print(f"\n[{i}/{len(json_files)}] 跳过文件 {filename} (无法判断GQL类型)")
            continue
        
        print(f"\n{'='*60}")
        print(f"[{i}/{len(json_files)}] 处理文件: {filename}")
        print(f"{'='*60}")
        
        stats = filter_file(input_file, output_file, gql_type)
        
        if stats:
            all_stats.append({
                "file": filename,
                "stats": stats
            })
            total_original += stats['total']
            total_filtered += stats['filtered']
            total_removed += stats['removed']
            total_errors += stats['errors']
        processed_files.append(filename)
        with open(f'{output_dir}/processed_{gql_type}_files.txt','w') as f:
            f.write(str(processed_files))
    # 打印汇总
    print(f"\n{'='*60}")
    print(f"过滤完成!")
    print(f"{'='*60}")
    print(f"  处理文件数: {len(all_stats)}")
    print(f"  原始查询总数: {total_original}")
    print(f"  保留查询数: {total_filtered}")
    print(f"  删除查询数: {total_removed} (返回0结果)")
    print(f"  错误数: {total_errors}")
    print(f"  删除率: {total_removed/total_original*100:.2f}%" if total_original > 0 else "  删除率: 0%")
    print(f"\n过滤后的文件已保存到: {output_dir}")


if __name__ == "__main__":
    main()

