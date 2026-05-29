import os
from Config import *
import subprocess
import json
from tqdm import tqdm
import numpy as np
import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
import gc
import ast
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from nebulagraph_python import NebulaClient, NebulaAsyncClient, SessionConfig, SessionPoolConfig
from nebulagraph_python.client._connection import ConnectionConfig
from nebulagraph_python.data import HostAddress
from sqlite_process import Sqlite_Process
import pandas as pd
import re

def check_memory_usage():
    """检查内存使用情况"""
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        print(f"  📊 当前内存使用: {memory_mb:.1f} MB")
        return memory_mb
    except ImportError:
        print("  📊 无法监控内存使用 (需要安装psutil)")
        return 0

class Import_Graph_Data_Nebula:
    def __init__(self, op_db, use_remote_db=True, use_async=False, schema=None):

        if NEBULA_SESSION_POOL_SIZE < max(NEBULA_THREAD_POOL_WORKERS, NEBULA_ASYNC_SEMAPHORE):
            print(f"⚠️  警告: 会话池大小 ({NEBULA_SESSION_POOL_SIZE}) 小于最大并发数 "
                  f"(线程: {NEBULA_THREAD_POOL_WORKERS}, 异步: {NEBULA_ASYNC_SEMAPHORE})")
            print(f"   这可能导致 'No session available' 错误")
            print(f"   建议: NEBULA_SESSION_POOL_SIZE >= max(NEBULA_THREAD_POOL_WORKERS, NEBULA_ASYNC_SEMAPHORE)")

        if use_remote_db:
            cmd = [
                "ssh",
                "-N",
                "-L", f"{NEBULA_PORT}:localhost:{NEBULA_PORT}",
                REMOTE_DB_HOST
            ]
            subprocess.Popen(cmd)
            print("端口转发成功")

        self.host = "127.0.0.1"
        self.port = NEBULA_PORT
        self.user = NEBULA_USERNAME
        self.password = NEBULA_PASSWORD
        self.op_db = op_db
        self.use_async = use_async
        self.schema = schema

        host_address_obj = HostAddress(host=self.host, port=self.port)

        conn_config = ConnectionConfig(
            hosts=[host_address_obj],
            request_timeout=3000.0,
            connect_timeout=10.0
        )

        self.client = NebulaClient(
            hosts=[host_address_obj],
            username=self.user,
            password=self.password,
            conn_config=conn_config,
            session_config=SessionConfig(
                schema=self.schema
            ),
            session_pool_config=SessionPoolConfig(
                size=NEBULA_SESSION_POOL_SIZE,
                wait_timeout=120.0
            )
        )

    def close(self):
        """关闭客户端连接"""
        if hasattr(self, 'client') and self.client is not None:
            try:
                self.client.close()
                print("  🔄 Nebula客户端连接已关闭")
            except Exception as e:
                print(f"  ⚠️  关闭客户端时出错: {e}")

    @staticmethod
    def schema_name(name):
        return name

    def nebula_type_mapping(self, type_str: str):
        """
        将导出schema中的SQLite类型映射为Nebula字段类型。
        与 Convert_Nebula_DB 中的映射保持一致。
        遵循 get_exported_csv 中的类型规则：
        - TEXT/BLOB/varchar/char/空类型 -> STRING
        - INTEGER/int/BIT/YEAR -> INT
        - REAL/float/double/decimal/numeric/number -> FLOAT
        - BOOL/BOOLEAN/bool -> BOOL
        - DATE/Date/date/DATETIME/datetime/timestamp -> LOCAL DATETIME
        """
        if pd.isna(type_str) or type_str is None or type_str == "":
            return "STRING"

        t = type_str.strip()
        t_upper = t.upper()
        t_lower = t.lower()

        if t_upper in ("DATE", "DATETIME") or t_lower in ("date", "datetime") or "timestamp" in t_lower:
            return "LOCAL DATETIME"

        if t_upper in ("TEXT", "BLOB") or "varchar" in t_lower or "char" in t_lower:
            return "STRING"

        if t_upper == "INTEGER" or "int" in t_lower or t_upper in ("BIT", "YEAR"):
            return "INT"

        if t_upper == "REAL" or "number" in t_lower or "float" in t_lower or "double" in t_lower or "decimal" in t_lower or "numeric" in t_lower:
            return "FLOAT"

        if t_upper in ("BOOL", "BOOLEAN") or "bool" in t_lower:
            return "BOOL"

        return "STRING"

    def get_exported_schema(self, database_file, table_name):
        """获取表名对应的导出的schema"""
        exported_schema_filepath = os.path.join(database_file, EXPORTED_SCHEMA_PATH)
        table_name = Sqlite_Process.table_name_align_with_exported_csv(database_file, table_name)
        file_path = f"{exported_schema_filepath}/{table_name}.csv"
        return pd.read_csv(file_path)

    def preprocess(self, database_path):
        print(f"=== Preprocess: {database_path} ===")

        all_tables = Sqlite_Process.get_all_tables(database_path)
        all_jointables = Sqlite_Process.get_all_jointables(database_path, "DeepSeek-R1")
        all_jointables_lower = [table.lower() for table in all_jointables]

        node_tables = [table for table in all_tables if table.lower() not in all_jointables_lower]

        prop_type_map = {}

        all_tables_to_check = node_tables + all_jointables
        for table in all_tables_to_check:
            try:
                schema_df = self.get_exported_schema(database_path, table)
                for _, row in schema_df.iterrows():
                    col_name = str(row['name']).lower()
                    col_type = str(row['type']).upper()
                    nebula_type = self.nebula_type_mapping(col_type)

                    if col_name not in prop_type_map:
                        prop_type_map[col_name] = {}
                    prop_type_map[col_name][table] = nebula_type
            except Exception as e:
                print(f"  ⚠️  读取表 {table} 的schema时出错: {e}")
                continue

        conflicts = []
        for prop_name, node_types in prop_type_map.items():

            types = set(node_types.values())
            if len(types) > 1:

                conflict_info = {
                    'property': prop_name,
                    'nodes': node_types
                }
                conflicts.append(conflict_info)
                print(f"  ❌ 属性 '{prop_name}' 在不同节点中有不同的类型:")
                for node, node_type in node_types.items():
                    print(f"      - {node}: {node_type}")

        duplicate_edges = []
        try:
            insert_querys_path = os.path.join(database_path, IMPORT_GRAPH_DATA_PATH)
            schema_file = os.path.join(insert_querys_path, 'schema_nebula_commands.txt')

            if os.path.exists(schema_file):
                with open(schema_file, 'r', encoding='utf-8') as f:
                    schema_data = json.load(f)

                create_graph_type_query = None
                for item in schema_data:
                    if 'query' in item and 'CREATE GRAPH TYPE' in item['query']:
                        create_graph_type_query = item['query']
                        break

                if create_graph_type_query:

                    edge_pattern = r'EDGE\s+`([^`]+)`'
                    edge_matches = re.findall(edge_pattern, create_graph_type_query)

                    edge_count = {}
                    for edge_name in edge_matches:
                        edge_name_lower = edge_name.lower()
                        edge_count[edge_name_lower] = edge_count.get(edge_name_lower, 0) + 1

                    for edge_name, count in edge_count.items():
                        if count > 1:
                            duplicate_edges.append({
                                'edge': edge_name,
                                'count': count
                            })
                            print(f"  ❌ 边类型 '{edge_name}' 在schema中定义了 {count} 次")
        except Exception as e:
            print(f"  ⚠️  检查同名边时出错: {e}")

        if conflicts or duplicate_edges:

            folder = os.path.dirname(database_path)
            skip_file = os.path.join(folder, 'import_nebula_skip.txt')
            database_name = os.path.basename(database_path)

            skipped = []
            if os.path.exists(skip_file):
                try:
                    with open(skip_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            skipped = ast.literal_eval(content)
                except:
                    skipped = []

            if database_name not in skipped:
                skipped.append(database_name)
                with open(skip_file, 'w', encoding='utf-8') as f:
                    f.write(str(skipped))

            if conflicts:
                print(f"  ⛔ 检测到 {len(conflicts)} 个属性类型冲突，跳过数据库: {database_name}")
            if duplicate_edges:
                print(f"  ⛔ 检测到 {len(duplicate_edges)} 个同名边，跳过数据库: {database_name}")
            print(f"  📝 已记录到: {skip_file}")
            return False

        print(f"  ✅ 预处理通过，未发现类型冲突和同名边")
        return True

    def import_graph_data(self, database_path, schema_name):
        """导入图数据到Nebula Graph"""

        if not self.preprocess(database_path):
            print(f"  ⏭️  跳过数据库导入: {os.path.basename(database_path)}")
            return

        insert_querys_path = os.path.join(database_path, IMPORT_GRAPH_DATA_PATH)

        def file_sort_key(s):
            s = s.lower()
            if 'schema' in s:
                return (0, s)
            if 'node' in s:
                return (1, s)
            elif 'jt' in s:
                return (2, s)
            elif 'fk' in s:
                return (3, s)
            else:
                return (4, s)

        node_first_files = sorted(
            os.listdir(insert_querys_path),
            key=file_sort_key
        )

        schema_files = []
        node_files = []
        other_files = []

        for item in node_first_files:
            if 'nebula' not in item:
                continue
            if 'schema' in item:
                schema_files.append(item)
            elif 'node' in item:
                node_files.append(item)
            else:
                other_files.append(item)

        if schema_files:
            print(f"=== 优先执行 {len(schema_files)} 个schema文件 ===")
            for item in schema_files:
                print(f"执行schema文件: {item}")
                self._execute_file_queries(insert_querys_path, item, schema_name)
        time.sleep(5)

        if node_files:
            print(f"=== 优先执行 {len(node_files)} 个node文件 ===")
            for item in node_files:
                print(f"执行node文件: {item}")
                self._execute_file_queries(insert_querys_path, item, schema_name)
        time.sleep(5)

        if other_files:
            print(f"=== 执行 {len(other_files)} 个其他文件 ===")
            for item in other_files:
                print(f"执行文件: {item}")
                self._execute_file_queries(insert_querys_path, item, schema_name)

    def _execute_file_queries(self, insert_querys_path, item, schema_name):
        """执行单个文件中的所有查询"""
        item_path = os.path.join(insert_querys_path, item)
        with open(item_path, 'r') as f:
            querys = json.load(f)

        is_schema_file = 'schema' in item.lower()

        batch_size = NEBULA_INSERT_BATCH_SIZE if 'NEBULA_INSERT_BATCH_SIZE' in globals() else 100
        expanded_queries = []

        for q in querys:
            if 'table_rows' in q and 'table_cols' in q:

                table_rows = q['table_rows']
                table_cols = q['table_cols']
                query_template = q['query']

                for batch_start in range(0, len(table_rows), batch_size):
                    batch_rows = table_rows[batch_start:batch_start+batch_size]

                    rows_str_list = []
                    for row_vals in batch_rows:
                        row_str = ', '.join(map(str, row_vals))
                        rows_str_list.append(f"({row_str})")
                    table_rows_str = ", \n".join(rows_str_list)

                    final_query = query_template.replace('$table_rows', table_rows_str)
                    expanded_queries.append({
                        "query": final_query,
                        "params": [],
                        "time_cols": q.get('time_cols', [])
                    })

            else:

                for d in q.get('params', []):
                    for col in q.get('time_cols', []):
                        if col in d:
                            d[col] = eval(d[col])

                expanded_queries.append(q)

        if self.op_db:
            if is_schema_file:

                self._execute_queries_serial(schema_name, expanded_queries)
            elif not self.use_async:
                self._execute_queries_parallel(schema_name, expanded_queries)
            else:
                asyncio.run(self._execute_queries_async_new(schema_name, expanded_queries))

    def _execute_queries_serial(self, schema_name, querys):
        """串行执行查询（用于schema文件）"""
        completed_count = 0
        failed_count = 0
        with tqdm(total=len(querys), desc="串行执行查询") as pbar:
            for idx, q in enumerate(querys):
                try:
                    print(f"  执行query {idx+1}/{len(querys)}: {q['query'][:50]}...")

                    result = self._execute_single_query(schema_name, q)

                    if result:
                        completed_count += 1
                        print(f"    ✅ Query {idx+1} 完成")
                    else:
                        failed_count += 1
                        print(f"    ❌ Query {idx+1} 失败")

                except Exception as e:
                    failed_count += 1
                    print(f"    ❌ Query {idx+1} 失败: {e}")

                pbar.update(1)

        print(f"  文件执行完成: 成功 {completed_count}, 失败 {failed_count}")

    def _execute_queries_parallel(self, schema_name, querys):
        """多线程并行执行查询（使用会话池）"""

        with ThreadPoolExecutor(max_workers=NEBULA_THREAD_POOL_WORKERS) as executor:
            futures = []
            for idx, q in enumerate(querys):

                future = executor.submit(self._execute_single_query_with_session_pool, schema_name, q, idx)
                futures.append((future, idx))

            completed_count = 0
            failed_count = 0
            with tqdm(total=len(querys), desc="执行查询") as pbar:
                for future, idx in futures:
                    try:
                        result = future.result()
                        if result:
                            completed_count += 1
                        else:
                            failed_count += 1
                    except Exception as e:
                        failed_count += 1
                        print(f"    ❌ Query {idx+1} 失败: {e}")
                    pbar.update(1)

            print(f"  文件执行完成: 成功 {completed_count}, 失败 {failed_count}")

    def _execute_single_query_with_session_pool(self, schema_name, query_info, idx):
        """使用会话池执行单个查询（每个线程会从池中获取独立的会话）"""
        try:

            result = self.client.execute(f'use {schema_name}\n' + query_info['query'])

            return True

        except Exception as e:
            print(f"    ❌ Query {idx+1} 执行出错: {e}")
            print(f"    查询内容: {query_info['query']}")
            return False

    def _execute_single_query(self, schema_name, query_info):
        """执行单个查询"""
        try:

            result = self.client.execute(query_info['query'])

            return True

        except Exception as e:
            print(f"执行查询时出错: {e}")
            if 'Properties with the same name must have the same type' in str(e):
                print('不同点同名属性类型不同 跳过')

            return False

    async def _execute_queries_async(self, schema_name, querys):
        """异步执行查询"""
        print(f"开始异步执行 {len(querys)} 个query")

        host_address_obj = HostAddress(host=self.host, port=self.port)

        conn_config = ConnectionConfig(
            hosts=[host_address_obj],
            request_timeout=3000.0,
            connect_timeout=10.0
        )

        semaphore = asyncio.Semaphore(NEBULA_ASYNC_SEMAPHORE)

        async def execute_with_semaphore(query_info, idx):
            """每个任务使用独立的异步客户端"""
            async with semaphore:

                async_client = await NebulaAsyncClient.connect(
                    hosts=[host_address_obj],
                    username=self.user,
                    password=self.password,
                    conn_config=conn_config,
                    session_config=SessionConfig(
                        schema=self.schema
                    )
                )

                try:

                    await async_client.execute(f'SESSION SET GRAPH {schema_name}')

                    return await self._execute_single_query_async(async_client, schema_name, query_info, idx)
                finally:

                    try:
                        await async_client.close()
                    except Exception as e:
                        print(f"  ⚠️  关闭客户端时出错: {e}")

        tasks = [execute_with_semaphore(q, idx) for idx, q in enumerate(querys)]

        completed_count = 0
        failed_count = 0
        with tqdm(total=len(querys), desc="异步执行查询") as pbar:
            for coro in asyncio.as_completed(tasks):
                try:
                    result = await coro
                    if result:
                        completed_count += 1
                    else:
                        failed_count += 1
                    pbar.update(1)
                except Exception as e:
                    failed_count += 1
                    print(f"  💥 任务异常: {e}")
                    pbar.update(1)

        print(f"所有query执行完成，成功: {completed_count}, 失败: {failed_count}")

    async def _execute_single_query_async(self, async_client, schema_name, query_info, idx):
        """异步执行单个查询"""
        try:

            result = await async_client.execute(f'USE `{schema_name}`\n' + query_info['query'])

            return True

        except Exception as e:
            result = await async_client.execute('show current_schema')
            result.print()
            result = await async_client.execute('show graphs')
            result.print()

            print(f'USE `{schema_name}`\n' + query_info['query'])

            print(f"  ❌ Query {idx+1} 执行出错: {e}")
            return False

    async def _execute_queries_async_new(self, schema_name, querys):
        """异步执行查询（使用会话池，参考 ng-python/example.py 中的 async_session_pool_example）"""
        print(f"开始异步执行 {len(querys)} 个query（使用会话池）")

        host_address_obj = HostAddress(host=self.host, port=self.port)

        conn_config = ConnectionConfig(
            hosts=[host_address_obj],
            request_timeout=3000.0,
            connect_timeout=10.0
        )

        async_client = await NebulaAsyncClient.connect(
            hosts=[host_address_obj],
            username=self.user,
            password=self.password,
            conn_config=conn_config,
            session_config=SessionConfig(
                schema=self.schema
            ),
            session_pool_config=SessionPoolConfig(
                size=NEBULA_SESSION_POOL_SIZE,
                wait_timeout=120.0
            )
        )

        try:

            semaphore = asyncio.Semaphore(NEBULA_ASYNC_SEMAPHORE)

            async def execute_one_query(query_info, idx):
                """执行单个查询的任务（使用会话池）"""

                async with semaphore:

                    import asyncio

                    max_retries = 3
                    delay = 10
                    for attempt in range(max_retries):
                        try:
                            combined_query = f'USE `{schema_name}`\n{query_info["query"]}'

                            result = await async_client.execute(combined_query)
                            return (True, idx)
                        except Exception as e:

                            if attempt < max_retries - 1 and 'No session available' in str(e):
                                print(f"    重试{attempt+1}/{max_retries}... 错误: {e}")
                                await asyncio.sleep(delay)
                            else:
                                print(f"  ❌ Query {idx+1} 重试{max_retries}次后仍失败: {e}")
                                print(f"    查询内容: {query_info['query']}")
                                breakpoint()
                                exit()
                                return (False, idx)

            tasks = [execute_one_query(q, idx) for idx, q in enumerate(querys)]

            completed_count = 0
            failed_count = 0
            with tqdm(total=len(querys), desc="异步执行查询（会话池）") as pbar:
                for coro in asyncio.as_completed(tasks):
                    try:
                        success, idx = await coro
                        if success:
                            completed_count += 1
                        else:
                            failed_count += 1
                    except Exception as e:
                        failed_count += 1
                        print(f"  💥 任务异常: {e}")
                    pbar.update(1)

            print(f"所有query执行完成，成功: {completed_count}, 失败: {failed_count}")

        finally:

            await async_client.close()

if __name__ == "__main__":

    folder = BIRD_TRAIN_folder
    schema = "/BIRD_train"

    nebula_importer = Import_Graph_Data_Nebula(op_db=True, use_remote_db=False, use_async=True, schema=schema)

    if os.path.exists(f'{folder}/import_nebula_processed.txt'):
        with open(f'{folder}/import_nebula_processed.txt','r') as f:
            exists = ast.literal_eval(f.read())
    else:
        exists = []

    for item in os.listdir(folder):
        filepath = os.path.join(folder,item)
        if os.path.isdir(filepath):

            print(filepath)
            if item in exists:
                continue

            schema_name = item
            nebula_importer.import_graph_data(filepath, schema_name)
            exists.append(item)
            with open(f'{folder}/import_nebula_processed.txt','w') as f:
                f.write(str(exists))

    nebula_importer.close()