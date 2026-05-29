from neo4j import GraphDatabase,AsyncGraphDatabase
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

class Import_Graph_Data_neo4j:
    def __init__(self,op_db,use_remote_db=True,use_async=False):

        self.uri = "bolt://localhost:7687" if not use_remote_db else NEO4j_remote_uri
        self.username = NEO4jUSERNAME if not use_remote_db else NEO4jUSERNAME_remote
        self.password = NEO4jPASSWORD if not use_remote_db else NEO4jPASSWORD_remote
        self.op_db = op_db
        self.use_async = use_async

        if not use_async:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
        else:
            self.driver = AsyncGraphDatabase.driver(self.uri, auth=(self.username, self.password))

    async def close(self):
        """关闭driver连接"""
        if hasattr(self, 'driver') and self.driver is not None:
            try:
                await self.driver.close()
                print("  🔄 主Driver连接已关闭")
            except Exception as e:
                print(f"  ⚠️  关闭主driver时出错: {e}")

    def close_sync(self):
        """同步关闭driver连接（用于非协程环境）"""
        if hasattr(self, 'driver') and self.driver is not None:
            try:
                self.driver.close()
                print("  🔄 主Driver连接已关闭")
            except Exception as e:
                print(f"  ⚠️  关闭主driver时出错: {e}")

    @staticmethod
    def db_name(name):
        return name.replace("_","-")

    def create_database(self,database_path):
        database_name = database_path.split(FILEPATH_SPLIT)[-1]
        database_name = Import_Graph_Data_neo4j.db_name(database_name)
        print(database_name)
        if self.op_db:
            with GraphDatabase.driver(self.uri, auth=(self.username, self.password)).session(database="system") as session:
                session.run(f'DROP DATABASE `{database_name}` IF EXISTS')
                session.run(f"CREATE DATABASE `{database_name}` IF NOT EXISTS")
                time.sleep(5)

        return database_name

    def import_graph_data(self,database_path,database_name):

        insert_querys_path = os.path.join(database_path,IMPORT_GRAPH_DATA_PATH)
        def file_sort_key(s):
            s = s.lower()
            if 'node' in s:
                return (0, s)
            elif 'jt' in s:
                return (1, s)
            elif 'fk' in s:
                return (2, s)
            else:
                return (3, s)

        node_first_files = sorted(
            os.listdir(insert_querys_path),
            key=file_sort_key
        )

        node_files = []
        other_files = []

        for item in node_first_files:
            if 'cypher' not in item:
                continue
            if 'node' in item:
                node_files.append(item)
            else:
                other_files.append(item)

        if node_files:
            print(f"=== 优先执行 {len(node_files)} 个node文件 ===")
            for item in node_files:
                print(f"执行node文件: {item}")
                self._execute_file_queries(insert_querys_path, item, database_name)

        if other_files:
            print(f"=== 执行 {len(other_files)} 个其他文件 ===")
            for item in other_files:
                print(f"执行文件: {item}")
                self._execute_file_queries(insert_querys_path, item, database_name)

    def _execute_file_queries(self, insert_querys_path, item, database_name):
        """执行单个文件中的所有查询"""
        item_path = os.path.join(insert_querys_path, item)
        with open(item_path, 'r') as f:
            querys = json.load(f)

        for q in querys:
            for d in q['params']:
                for col in q['time_cols']:
                    if col in d:
                        d[col] = eval(d[col])

        if self.op_db:
            if not self.use_async:

                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = []
                    for idx, q in enumerate(querys):
                        print(f"  提交query {idx+1}/{len(querys)}: {q['query'][:50]}...")
                        if isinstance(q, str):
                            future = executor.submit(self._execute_simple_query, database_name, q)
                        else:
                            future = executor.submit(self.execute_one_query_batch_parallel, database_name, q, max_workers=2)
                        futures.append((future, idx, q))

                    completed_count = 0
                    failed_count = 0
                    with tqdm(total=len(querys), desc=f"执行 {item}") as pbar:
                        for future, idx, q in futures:
                            try:
                                result = future.result()
                                completed_count += 1
                                print(f"    ✅ Query {idx+1} 完成")
                            except Exception as e:
                                failed_count += 1
                                print(f"    ❌ Query {idx+1} 失败: {e}")
                            pbar.update(1)

                    print(f"  文件 {item} 执行完成: 成功 {completed_count}, 失败 {failed_count}")
            else:

                batch_size = NEO4j_INSERT_BATCH_SIZE
                single_batch_count = 0
                for q in querys:
                    params = q['params']
                    if len(params) <= batch_size:
                        single_batch_count += 1

                if single_batch_count >= len(querys) * 0.7:

                    asyncio.run(self._execute_all_queries_async(database_name, querys, max_concurrent=16))
                else:

                    async def run_serial():
                        for idx, q in enumerate(querys):
                            print(f"  提交query {idx+1}/{len(querys)}: {q['query'][:50]}...")
                            try:
                                await self.execute_one_query_batch_async(database_name, q, max_concurrent=32)
                                print(f"    ✅ Query {idx+1} 完成")
                            except Exception as e:
                                print(f"    ❌ Query {idx+1} 失败: {e}")

                    print("  所有query并行执行，每个query内部也并行")
                    async def run_parallel_queries_parallel_batches():

                        tasks = []
                        for idx, q in enumerate(querys):
                            print(f"  提交query {idx+1}/{len(querys)}: {q['query'][:50]}...")

                            async def execute_single_query(query_info, query_idx):
                                try:

                                    await self.execute_one_query_batch_async(database_name, query_info, max_concurrent=8)
                                    print(f"    ✅ Query {query_idx+1} 完成")
                                    return True
                                except Exception as e:
                                    print(f"    ❌ Query {query_idx+1} 失败: {e}")
                                    return False

                            task = execute_single_query(q, idx)
                            tasks.append(task)

                        results = await asyncio.gather(*tasks, return_exceptions=True)

                        success_count = sum(1 for r in results if r is True)
                        print(f"  所有query执行完成: 成功 {success_count}/{len(querys)}")

                    print("  所有query并行执行，每个query内部串行")
                    async def run_parallel_queries_serial_batches():

                        tasks = []
                        for idx, q in enumerate(querys):
                            print(f"  提交query {idx+1}/{len(querys)}: {q['query'][:50]}...")

                            async def execute_single_query(query_info, query_idx):
                                try:

                                    await self.execute_one_query_batch_async(database_name, query_info, max_concurrent=1)
                                    print(f"    ✅ Query {query_idx+1} 完成")
                                    return True
                                except Exception as e:
                                    print(f"    ❌ Query {query_idx+1} 失败: {e}")
                                    return False

                            task = execute_single_query(q, idx)
                            tasks.append(task)

                        results = await asyncio.gather(*tasks, return_exceptions=True)

                        success_count = sum(1 for r in results if r is True)
                        print(f"  所有query执行完成: 成功 {success_count}/{len(querys)}")

                    if 'node' in item:
                        asyncio.run(run_serial())
                    else:

                        asyncio.run(run_serial())

    def _execute_batch_parallel(self, database_name, query, params_batch):
        """并行执行批量查询，保持原有的pairs参数结构"""

        with GraphDatabase.driver(self.uri, auth=(self.username, self.password)).session(database=database_name) as session:
            try:

                result = session.run(query, {"pairs": params_batch})

                if NEO4j_TRANSACTION_DELAY > 0:
                    time.sleep(NEO4j_TRANSACTION_DELAY)

                return len(params_batch)
            except Exception as e:
                print(f"批量执行错误: {e}")

                count = 0
                for params in tqdm(params_batch, desc="回退到逐条执行", leave=False):
                    try:

                        if isinstance(params, dict):
                            result = session.run(query, {"pairs": [params]})
                        else:
                            result = session.run(query, {"pairs": [params]})

                        count += 1

                        if NEO4j_TRANSACTION_DELAY > 0:
                            time.sleep(NEO4j_TRANSACTION_DELAY * 0.5)

                    except Exception as e2:
                        print(f"单条执行错误: {e2}")
                return count

    def execute_one_query_batch_parallel(self,database_name,query_info,max_workers=8):
            query = query_info['query']
            params = query_info['params']
            batch_size = NEO4j_INSERT_BATCH_SIZE

            batches = [params[i:i+batch_size] for i in range(0, len(params), batch_size)]

            print(f"  总参数数: {len(params)}, 批次大小: {batch_size}, 总批次数: {len(batches)}")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []

                for batch in batches:
                    future = executor.submit(
                        self._execute_batch_parallel,
                        database_name,
                        query,
                        batch
                    )
                    futures.append(future)

                total_count = 0
                for future in tqdm(as_completed(futures), total=len(futures), desc="  并行处理批次"):
                    try:
                        count = future.result()
                        total_count += count
                    except Exception as e:
                        print(f"  批次执行失败: {e}")

                print(f"  成功导入: {total_count}/{len(params)} 条记录")

    def _execute_simple_query(self, database_name, query):
        """执行简单query"""
        with GraphDatabase.driver(self.uri, auth=(self.username, self.password)).session(database=database_name) as session:
            session.run(query).consume()
        return True

    async def _execute_all_queries_async(self, database_name, querys, max_concurrent=4):
        """协程并行执行所有query，修复连接泄漏问题"""
        print(f"开始协程并行执行 {len(querys)} 个query，最大并发: {max_concurrent}")

        driver = AsyncGraphDatabase.driver(self.uri, auth=(self.username, self.password))

        async def execute_single_query_async(query_info, idx):
            """执行单个query的协程"""
            try:
                if isinstance(query_info, str):

                    async with driver.session(database=database_name) as session:
                        result = await session.run(query_info)

                    print(f"  Query {idx+1} (简单) 完成")
                else:

                    await self.execute_one_query_batch_async(database_name, query_info, max_concurrent=1, driver=driver)
                    print(f"  Query {idx+1} (批量) 完成")
                return True
            except SystemExit as e:

                print(f"  🚨 Query {idx+1} 触发程序终止: {e}")
                raise e
            except Exception as e:
                print(f"  Query {idx+1} 失败: {e}")
                return False
            finally:

                pass

        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_with_semaphore(query_info, idx):
            async with semaphore:
                return await execute_single_query_async(query_info, idx)

        tasks = [execute_with_semaphore(q, idx) for idx, q in enumerate(querys)]

        completed_count = 0
        failed_count = 0
        try:

            with tqdm(total=len(querys), desc="协程执行查询") as pbar:

                for coro in asyncio.as_completed(tasks):
                    try:
                        result = await coro
                        if result:
                            completed_count += 1
                        else:
                            failed_count += 1
                        pbar.update(1)
                    except SystemExit as e:

                        print(f"  🚨 检测到程序终止信号: {e}")

                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        raise e
                    except Exception as e:
                        failed_count += 1
                        print(f"  💥 任务异常: {e}")
                        pbar.update(1)

            print(f"所有query执行完成，成功: {completed_count}, 失败: {failed_count}")

        except SystemExit as e:

            print(f"🚨 协程执行过程中检测到程序终止信号，终止所有协程")
            raise e
        finally:

            try:
                await driver.close()
                print("  🔄 Driver连接已关闭，释放连接池")
            except Exception as e:
                print(f"  ⚠️  关闭driver时出错: {e}")

    def execute_one_query_batch_parallel_improved(self, database_name, query_info, max_workers=4):
        """改进的多线程并行执行，减少死锁风险"""
        query = query_info['query']
        params = query_info['params']
        batch_size = NEO4j_INSERT_BATCH_SIZE

        batches = [params[i:i+batch_size] for i in range(0, len(params), batch_size)]

        print(f"  总参数数: {len(params)}, 批次大小: {batch_size}, 总批次数: {len(batches)}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []

            for batch in batches:
                future = executor.submit(
                    self._execute_batch_parallel_improved,
                    database_name,
                    query,
                    batch
                )
                futures.append(future)

            total_count = 0
            for future in tqdm(as_completed(futures), total=len(futures), desc="  改进并行处理批次"):
                try:
                    count = future.result()
                    total_count += count
                except Exception as e:
                    print(f"  批次执行失败: {e}")

            print(f"  成功导入: {total_count}/{len(params)} 条记录")

    def _execute_batch_parallel_improved(self, database_name, query, params_batch):
        """改进的批量执行，减少死锁风险"""
        with self.driver.session(database=database_name) as session:
            try:

                with session.begin_transaction() as tx:

                    result = tx.run(query, {"pairs": params_batch})

                    tx.commit()
                    return len(params_batch)

            except Exception as e:
                print(f"批量执行错误: {e}")

                return self._fallback_single_execution_improved(session, query, params_batch)

    def _fallback_single_execution_improved(self, session, query, params_batch):
        """改进的回退执行，减少锁竞争"""
        count = 0
        for params in tqdm(params_batch, desc="回退到逐条执行", leave=False):
            try:
                with session.begin_transaction() as tx:

                    if isinstance(params, dict):
                        result = tx.run(query, {"pairs": [params]})
                    else:
                        result = tx.run(query, {"pairs": [params]})

                    tx.commit()
                    count += 1

                    time.sleep(0.001)

            except Exception as e2:
                print(f"单条执行错误: {e2}")

                continue
        return count

    async def _execute_batch_async(self, database_name, query, params_batch, driver=None):
        """异步执行批量查询，带死锁检测和程序终止"""
        if driver is None:

            driver = AsyncGraphDatabase.driver(self.uri, auth=(self.username, self.password))
            should_close = True
        else:
            should_close = False

        try:
            async with driver.session(database=database_name) as session:
                deadlock_count = 0
                total_retries = 0

                while total_retries < NEO4j_DEADLOCK_RETRY_COUNT:
                    total_retries += 1
                    try:
                        result = await session.run(query, {"pairs": params_batch})

                        if NEO4j_TRANSACTION_DELAY > 0:
                            await asyncio.sleep(NEO4j_TRANSACTION_DELAY)

                        if len(params_batch) > 50:
                            await asyncio.sleep(NEO4j_TRANSACTION_DELAY * 2)

                        return len(params_batch)
                    except Exception as e:
                        error_msg = str(e)
                        print(f"批量执行错误 (重试 {total_retries}/{NEO4j_DEADLOCK_RETRY_COUNT}): {error_msg}")

                        if "DeadlockDetected" in error_msg:
                            deadlock_count += 1
                            print(f"  💀 检测到死锁 #{deadlock_count}")

                            if deadlock_count >= NEO4j_DEADLOCK_RETRY_COUNT:
                                print(f"  🚨 连续{deadlock_count}次死锁，终止程序执行")
                                raise SystemExit(f"死锁过多，连续{deadlock_count}次死锁，程序终止")

                        if total_retries < NEO4j_DEADLOCK_RETRY_COUNT:

                            await asyncio.sleep(10 * total_retries)
                            continue

                print(f"  ⚠️  批量执行失败，回退到逐条执行")
                raise SystemExit(f"批量执行失败，程序终止")

                try:
                    return await self._fallback_single_execution_async(session, query, params_batch)
                except Exception as fallback_error:
                    print(f"  💥 逐条执行也失败: {fallback_error}")
                    raise SystemExit(f"批量执行和逐条执行都失败，程序终止: {fallback_error}")
        finally:

            if should_close:
                try:
                    await driver.close()

                except Exception as e:
                    print(f"  ⚠️  关闭批量执行driver时出错: {e}")

    async def _fallback_single_execution_async(self, session, query, params_batch):
        """异步回退到逐条执行，避免死锁"""
        count = 0
        for params in tqdm(params_batch, desc="回退到逐条执行", leave=False):
            try:

                if isinstance(params, dict):
                    result = await session.run(query, {"pairs": [params]})
                else:
                    result = await session.run(query, {"pairs": [params]})

                count += 1

                await asyncio.sleep(0.001)
            except Exception as e2:
                print(f"单条执行错误: {e2}")

                breakpoint()
                continue
        return count

    async def execute_one_query_batch_async(self, database_name, query_info, max_concurrent=4, driver=None):
        """使用协程异步执行，避免死锁"""
        query = query_info['query']
        params = query_info['params']
        batch_size = NEO4j_INSERT_BATCH_SIZE

        batches = [params[i:i+batch_size] for i in range(0, len(params), batch_size)]

        print(f"  总参数数: {len(params)}, 批次大小: {batch_size}, 总批次数: {len(batches)}")

        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_batch_with_semaphore(batch):
            async with semaphore:
                return await self._execute_batch_async(database_name, query, batch, driver)

        total_count = 0
        with tqdm(total=len(batches), desc="  协程处理批次") as pbar:

            completed_count = 0

            async def execute_with_progress(batch):
                nonlocal completed_count
                try:

                    async with semaphore:
                        result = await self._execute_batch_async(database_name, query, batch, driver)
                    completed_count += 1
                    pbar.update(1)
                    pbar.set_postfix({'completed': f"{completed_count}/{len(batches)}", 'successful': f"{total_count}"})
                    return result
                except Exception as e:
                    completed_count += 1
                    pbar.update(1)
                    print(f"  批次执行失败: {e}")
                    return 0

            progress_tasks = [execute_with_progress(batch) for batch in batches]

            results = await asyncio.gather(*progress_tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    continue
                total_count += result

        print(f"  成功导入: {total_count}/{len(params)} 条记录")

if __name__ == "__main__":
    cypher_importer = Import_Graph_Data_neo4j(op_db=True,use_remote_db=False,use_async=True)

    folder = SPIDER_TEST_folder

    if os.path.exists(f'{folder}/import_processed.txt'):
        with open(f'{folder}/import_processed.txt','r') as f:
            exists = ast.literal_eval(f.read())
    else:
        exists = []

    for item in os.listdir(folder):
        filepath = os.path.join(folder,item)
        if os.path.isdir(filepath):

            print(filepath)
            if item in exists:
                continue

            database_name = cypher_importer.create_database(filepath)

            cypher_importer.import_graph_data(filepath,database_name)
            exists.append(item)
            with open(f'{folder}/import_processed.txt','w') as f:
                f.write(str(exists))

    cypher_importer.driver.close()
