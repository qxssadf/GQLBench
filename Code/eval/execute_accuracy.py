# adapted from https://github.com/megagonlabs/cypherbench/blob/main/cypherbench/metrics/execution_accuracy.py
import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Config import * 
from import_graph_data import Import_Graph_Data_neo4j
from neo4j import GraphDatabase, Query
import neo4j
from nebulagraph_python import NebulaClient, SessionConfig, SessionPoolConfig
from nebulagraph_python.client._connection import ConnectionConfig
from nebulagraph_python.data import HostAddress
import math 
from collections import Counter 
import time
import json
from collections import defaultdict
import re
from typing import Tuple, List, Set
from itertools import product
import random

def unorder_row(row: Tuple) -> Tuple:
    return tuple(sorted(row, key=lambda x: str(x) + str(type(x))))

def quick_rej(result1: List[Tuple], result2: List[Tuple], order_matters: bool) -> bool:
    s1 = [unorder_row(row) for row in result1]
    s2 = [unorder_row(row) for row in result2]
    if order_matters:
        return s1 == s2
    else:
        return set(s1) == set(s2)

def cypher_execute(db_name,cypher_statement):
    db_name = Import_Graph_Data_neo4j.db_name(db_name)
    uri = "bolt://localhost:7687"
    username = NEO4jUSERNAME
    password = NEO4jPASSWORD

    def cypher_value_to_python_value(x):
        if isinstance(x,neo4j.graph.Node) or isinstance(x,neo4j.graph.Relationship):
            return x.element_id
        elif isinstance(x, neo4j.time.DateTime):
            return datetime.datetime.fromisoformat(x.iso_format())
        elif isinstance(x,list):
            return tuple([cypher_value_to_python_value(item) for item in x])
        elif isinstance(x,dict):
            return tuple(sorted((cypher_value_to_python_value(k), cypher_value_to_python_value(v)) for k, v in x.items()))
        else:
            return x

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        start_time = time.time()
        df = driver.execute_query(
            Query(cypher_statement,timeout=1800),
            database_=db_name,
            result_transformer_=neo4j.Result.to_df,
        )
        cypher_time = time.time() - start_time
        print(f"Cypher执行时间: {cypher_time:.4f}秒")
        time.sleep(0.1)
        res = [
            tuple([cypher_value_to_python_value(cell) for cell in row])
            for row in df.itertuples(index=False)
        ]

        return res, cypher_time
    finally:
        driver.close()

def nebula_execute(db_name, nebula_statement, source):
    if source.lower()=='bird_dev':
        source = 'BIRD_dev'
    elif source.lower()=='bird_train':
        source = 'BIRD_train'
    elif source.lower()=='spider_train':
        source = 'spider_train_dev'
    elif source.lower()=='spider_test':
        source = 'spider_test'
    elif source.lower()=='datasyn':
        source = 'datasyn'
    else:
        raise ValueError(f"Invalid source: {source}")

    from import_graph_data_nebula import Import_Graph_Data_Nebula
    import datetime
    
    db_name = Import_Graph_Data_Nebula.schema_name(db_name)
    host = "127.0.0.1"
    port = NEBULA_PORT
    username = NEBULA_USERNAME
    password = NEBULA_PASSWORD
    
    def to_python_type(x):
        from nebulagraph_python.py_data_types import Node, Edge, Path
        from nebulagraph_python.value_wrapper import ValueWrapper
        
        if isinstance(x, ValueWrapper):
            x = x.cast()
        
        if isinstance(x, Node):
            return x.get_id()
        elif isinstance(x, Edge):
            return f"{x.get_src_id()}_{x.get_dst_id()}_{x.get_type()}_{x.get_rank()}"
        elif isinstance(x, Path):
            path_tuple = []
            nodes = x.get_nodes()
            edges = x.get_edges()
            values = x.get_values()
            for val in values:
                if val.is_node():
                    node = val.as_node()
                    path_tuple.append(node.get_id())
                elif val.is_edge():
                    edge = val.as_edge()
                    path_tuple.append(f"{edge.get_src_id()}_{edge.get_dst_id()}_{edge.get_type()}_{edge.get_rank()}")
            return tuple(path_tuple)
        elif isinstance(x, datetime.datetime):
            return x
        elif isinstance(x, str):
            try:
                return datetime.datetime.fromisoformat(x)
            except:
                return x
        elif isinstance(x, list):
            return tuple([to_python_type(item) for item in x])
        elif isinstance(x,dict):
            return tuple(sorted((to_python_type(k), to_python_type(v)) for k, v in x.items()))
        else:
            return x
    
    host_address = HostAddress(host=host, port=port)
    conn_config = ConnectionConfig(
        hosts=[host_address],
        request_timeout=1200.0,
        connect_timeout=100.0
    )
    client = NebulaClient(
        hosts=[host_address],
        username=username,
        password=password,
        conn_config=conn_config,
        session_config=SessionConfig(
            schema='/' + source
        )
    )
    try:
        client.execute(f'SESSION SET GRAPH `{db_name}`')
        start_time = time.time()
        result = client.execute(nebula_statement,timeout=1800)
        nebula_time = time.time() - start_time
        time.sleep(0.1)
        res = []
        for record in result.records():
            row = []
            for val in record.values():
                if val is None:
                    row.append(None)
                else:
                    cell = val.cast()
                    row.append(to_python_type(cell))
            res.append(tuple(row))
        return res, nebula_time
    except Exception as e:
        print(f"NebulaGraph 查询错误: {e}")
        return f"Nebula query Error: {str(e)}", 0.0
    finally:
        client.close()

def unorder_row(row: Tuple) -> Tuple:
    return tuple(sorted(row, key=lambda x: str(x) + str(type(x))))

def quick_rej(result1: List[Tuple], result2: List[Tuple], order_matters: bool) -> bool:
    s1 = [unorder_row(row) for row in result1]
    s2 = [unorder_row(row) for row in result2]
    if order_matters:
        return s1 == s2
    else:
        return set(tuple(s1)) == set(tuple(s2))

def get_constraint_permutation(tab1_sets_by_columns: List[Set], result2: List[Tuple]):
    num_cols = len(result2[0])
    perm_constraints = [{i for i in range(num_cols)} for _ in range(num_cols)]
    if num_cols <= 3:
        return product(*perm_constraints)

    for _ in range(20):
        random_tab2_row = random.choice(result2)

        for tab1_col in range(num_cols):
            for tab2_col in set(perm_constraints[tab1_col]):
                if random_tab2_row[tab2_col] not in tab1_sets_by_columns[tab1_col]:
                    perm_constraints[tab1_col].remove(tab2_col)
    return product(*perm_constraints)

def multiset_eq(l1: List, l2: List) -> bool:
    if len(l1) != len(l2):
        return False
    d = defaultdict(int)
    for e in l1:
        d[e] = d[e] + 1
    for e in l2:
        d[e] = d[e] - 1
        if d[e] < 0:
            return False
    return True

def permute_tuple(element: Tuple, perm: Tuple) -> Tuple:
    assert len(element) == len(perm)
    return tuple([element[i] for i in perm])

def res_eq(res1: List[Tuple], res2: List[Tuple], order_matters: bool) -> bool:
    if len(res1)==0 and len(res2)==0:
        return 1
    if len(res1)!=len(res2):
        return 0

    if len(res1[0]) != len(res2[0]):
        return 0
    num_cols = len(res1[0])
    if not quick_rej(res1,res2,order_matters):
        return 0

    tab1_sets_by_columns = [{row[i] for row in res1} for i in range(num_cols)]

    for perm in get_constraint_permutation(tab1_sets_by_columns, res2):
        if len(perm) != len(set(perm)):
            continue
        if num_cols == 1:
            res2_perm = res2
        else:
            res2_perm = [permute_tuple(element, perm) for element in res2]
        if order_matters:
            if res1 == res2_perm:
                return True
        else:
            if set(res1) == set(res2_perm) and multiset_eq(res1, res2_perm):
                return True
    return False


def execution_accuracy(pred_gql:str,target_gql:str,db_name:str,gql_dialect:str,source:str) -> float:
    if pred_gql.strip() == target_gql.strip():
        return 1, "No Error"
    
    target_res, target_time = cypher_execute(db_name,target_gql) if gql_dialect == 'cypher' else nebula_execute(db_name,target_gql,source)  

    try:
        retry=0
        while retry < 3:
            pred_res, pred_time = cypher_execute(db_name,pred_gql) if gql_dialect == 'cypher' else nebula_execute(db_name,pred_gql,source)
            if isinstance(pred_res,str) and 'Failed to connect to any of the provided hosts. Last error: Connection timeout after' in pred_res:
                retry += 1
                time.sleep(1)
                continue
            elif isinstance(pred_res,str):
                return 0.0, pred_res
            else:
                break
        if isinstance(pred_res,str):
            return 0.0, pred_res
    except Exception as e:
        return 0.0, str(e)

    if len(pred_res) != len(target_res):
        return 0.0, "Length mismatch"
    if len(pred_res) == 0 and len(target_res) == 0:
        return 1.0, "No Error: Both are empty"
    if len(pred_res[0]) != len(target_res[0]):
        return 0.0, "Column number mismatch"
    order_matters = True if "order by" in target_gql.lower() else False
    return res_eq(pred_res,target_res,order_matters=order_matters), "last res_eq"

if __name__ == "__main__":
    cypher_execute('','return 1,2')
