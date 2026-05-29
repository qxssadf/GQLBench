import pandas as pd
import numpy as np
import os
import json
import ast
import sqlite3
from Config import *
import datetime
from sqlite_process import *
from pandas.api.types import is_datetime64_any_dtype as is_datetime

class Convert_DB:

    def __init__(self):
        self.anal_only = None
        self.llm_model = MODEL
        self.llm_model_name = 'DeepSeek-R1'

    @cache
    def get_exported_csv(self, database_file, table_name):
        exported_csv_filepath = os.path.join(database_file, EXPORTED_CSV_PATH)
        file_path = f'{exported_csv_filepath}/{table_name}.csv'
        schema_df = self.get_exported_schema(database_file, table_name)

        def mapping_type(type_str: str):
            if type_str == 'TEXT':
                return 'string'
        col_types_dict = {row['name']: mapping_type(row['type']) for (_, row) in schema_df.iterrows() if row['type'] == 'TEXT'}
        dateType_col = schema_df.query('type == "DATE" or type == "Date" or type=="date" or type=="DATETIME" or type=="datetime" or type.str.lower().str.contains("timestamp") or type.str.lower().str.contains("datetime")')['name'].str.lower().tolist()
        str_col = schema_df.query('type=="TEXT" or type=="BLOB" or type.str.lower().str.contains("varchar") or type.str.lower().str.contains("char")')['name'].str.lower().tolist()
        int_col = schema_df.query('type=="INTEGER" or type.str.lower().str.contains("int") or type=="BIT" or type=="YEAR"')['name'].str.lower().tolist()
        float_col = schema_df.query('type=="REAL" or type.str.lower().str.contains("number") or type.str.lower().str.contains("float") or type.str.lower().str.contains("double") or type.str.lower().str.contains("decimal") or type.str.lower().str.contains("numeric")')['name'].str.lower().tolist()
        bool_col = schema_df.query('type=="BOOL" or type=="BOOLEAN" or type.str.lower().str.contains("bool")')['name'].str.lower().tolist()
        str_col += schema_df[schema_df['type'].isna()]['name'].str.lower().tolist()
        item = database_file.split(FILEPATH_SPLIT)[-1]
        conn = sqlite3.connect(database_file + f'/{item}.sqlite')
        conn.text_factory = decode_text
        csv_df = pd.read_sql_query(f'SELECT * FROM `{table_name}`', conn)
        conn.close()
        if len(csv_df) == 0:
            return csv_df
        for coll in csv_df.columns:
            if coll.lower() in dateType_col:
                csv_df[coll] = pd.to_datetime(csv_df[coll], errors='coerce')
            elif coll.lower() in str_col:
                csv_df[coll] = csv_df[coll].astype('string')
            elif coll.lower() in bool_col:
                csv_df[coll] = csv_df[coll].astype(bool)
            elif coll.lower() in int_col:
                csv_df[coll] = csv_df[coll].replace('', np.nan).replace('NULL', np.nan)
                if csv_df[coll].isna().sum() == 0 and isinstance(csv_df[coll].iloc[0], int):
                    csv_df[coll] = csv_df[coll].astype(int)
                else:
                    csv_df[coll] = csv_df[coll].astype(float)
            elif coll.lower() in float_col:
                csv_df[coll] = csv_df[coll].replace('', np.nan).replace('NULL', np.nan)
                csv_df[coll] = csv_df[coll].astype(float)
            else:
                print(table_name, coll)
                raise TypeError('only can be datetime,str,int,float,bool')
        return csv_df

    def get_exported_schema(self, database_file, table_name):
        exported_schema_filepath = os.path.join(database_file, EXPORTED_SCHEMA_PATH)
        table_name = Sqlite_Process.table_name_align_with_exported_csv(database_file, table_name)
        file_path = f'{exported_schema_filepath}/{table_name}.csv'
        return pd.read_csv(file_path)

    @staticmethod
    def get_all_edges(database_file, llm_model_name, gql_type='cypher'):
        if gql_type == 'cypher':
            all_edges_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH, f'all_edges_{llm_model_name}_jt_align.jsonl')
        elif gql_type == 'nebula':
            all_edges_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH, f'all_edges_{llm_model_name}_jt_align_nebula.jsonl')
        with open(all_edges_filepath, 'r') as f:
            all_edges = json.load(f)
            all_edges['fk'] = {ast.literal_eval(k): v for (k, v) in all_edges['fk'].items()}
            all_edges['jt'] = {ast.literal_eval(k): v for (k, v) in all_edges['jt'].items()}
        return all_edges

    def get_time_cols(self, df: pd.DataFrame, cols):
        time_cols = []
        for col in cols:
            if is_datetime(df[col]):
                time_cols.append(col)
        return time_cols

class Convert_neo4j_DB(Convert_DB):

    def __init__(self, gql_type, anal_only):
        super().__init__()
        self.gql_type = gql_type
        self.anal_only = anal_only

    def val_mapping(self, val):
        if pd.isna(val) or pd.isnull(val):
            return val
        if isinstance(val, (int, float, complex, np.integer, np.floating)):
            return val
        elif isinstance(val, (bool, np.bool_)):
            return val
        elif isinstance(val, str):
            return f'{val}'
        elif isinstance(val, (datetime.datetime, datetime.date)):
            return f"datetime.datetime.fromisoformat('{val.isoformat()}')"
        else:
            raise TypeError(f'Unsupported type: {type(val)}')

    def col_mapping(self, col):
        pass

    def create_node_with_gql(self, database_file):
        all_jointables = Sqlite_Process.get_all_jointables(database_file, self.llm_model_name)
        all_tables = Sqlite_Process.get_all_tables(database_file)
        all_jointables_lower = [table.lower() for table in all_jointables]
        tables = [table for table in all_tables if table.lower() not in all_jointables_lower]
        print(tables)
        table_dfs = [self.get_exported_csv(database_file, table) for table in tables]
        import_graph_data_path = os.path.join(database_file, IMPORT_GRAPH_DATA_PATH)
        if not os.path.exists(import_graph_data_path):
            os.mkdir(import_graph_data_path)
        for (table_idx, table_name) in enumerate(tables):
            df = table_dfs[table_idx]
            querys = []
            pairs = json.loads(df.applymap(lambda x: self.val_mapping(x)).to_json(orient='records'))
            pairs = [{k: v for (k, v) in pair.items() if not pd.isna(v)} for pair in pairs]
            prop_unwind_query = ', '.join([f'`{col.lower()}`:pair.`{col}`' for col in df.columns])
            time_cols = self.get_time_cols(df, df.columns)
            query = f'UNWIND $pairs AS pair CREATE (:`{table_name.lower()}` {{{prop_unwind_query}}});'
            querys.append({'query': query, 'params': pairs, 'time_cols': time_cols})
            filepath = os.path.join(import_graph_data_path, f'node_{table_name}_{self.gql_type}_commands.txt')
            if not self.anal_only:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(querys, f, ensure_ascii=False, indent=2)

    def create_fk_edge_with_gql_from_edge_dict(self, database_file, fk_dict):
        querys = []
        for (src_and_tgt, edges) in fk_dict.items():
            src = src_and_tgt[0]
            tgt = src_and_tgt[1]
            for edge in edges:
                edge_label = edge['edge_label']
                src_filter_cols = edge['source_filter_columns']
                tgt_filter_cols = edge['target_filter_columns']
                (src_csv, tgt_csv) = (self.get_exported_csv(database_file, src), self.get_exported_csv(database_file, tgt))
                src_filter_cols_vals = set(src_csv[src_filter_cols].dropna().apply(tuple, axis=1))
                tgt_filter_cols_vals = set(tgt_csv[tgt_filter_cols].dropna().apply(tuple, axis=1))
                common_vals = list(src_filter_cols_vals & tgt_filter_cols_vals)
                src_filter_unwind_query = ', '.join([f'`{src_col.lower()}`:pair.`src_{src_col}`' for src_col in src_filter_cols])
                tgt_filter_unwind_query = ', '.join([f'`{tgt_col.lower()}`:pair.`tgt_{tgt_col}`' for tgt_col in tgt_filter_cols])
                time_cols = [f'src_{tmp}' for tmp in self.get_time_cols(src_csv, src_filter_cols)] + [f'tgt_{tmp}' for tmp in self.get_time_cols(tgt_csv, tgt_filter_cols)]
                unwind_query = f'UNWIND $pairs AS pair MATCH (from:`{src.lower()}` {{{src_filter_unwind_query}}}), (to:`{tgt.lower()}` {{{tgt_filter_unwind_query}}}) MERGE (from)-[r:`{edge_label.lower()}`]->(to);'
                unwind_query = f'UNWIND $pairs AS pair WITH DISTINCT pair MATCH (from:`{src.lower()}` {{{src_filter_unwind_query}}}), (to:`{tgt.lower()}` {{{tgt_filter_unwind_query}}}) CREATE (from)-[r:`{edge_label.lower()}`]->(to);'
                unwind_query = f'UNWIND $pairs AS pair WITH DISTINCT pair CALL(*) {{MATCH (from:`{src.lower()}` {{{src_filter_unwind_query}}}) WITH from LIMIT 1 MATCH (to:`{tgt.lower()}` {{{tgt_filter_unwind_query}}}) RETURN from, to LIMIT 1 }} CREATE (from)-[r:`{edge_label.lower()}`]->(to);'
                src_pairs = [{f'src_{src_col}': self.val_mapping(val) for (val, src_col) in zip(common_val, src_filter_cols)} for common_val in common_vals]
                tgt_pairs = [{f'tgt_{tgt_col}': self.val_mapping(val) for (val, tgt_col) in zip(common_val, tgt_filter_cols)} for common_val in common_vals]
                pairs = [{**src_pair, **tgt_pair} for (src_pair, tgt_pair) in zip(src_pairs, tgt_pairs)]
                querys.append({'query': unwind_query, 'params': pairs, 'time_cols': time_cols})
        import_graph_data_path = os.path.join(database_file, IMPORT_GRAPH_DATA_PATH)
        filepath = os.path.join(import_graph_data_path, f'edges_fk_{self.gql_type}_commands.txt')
        if not self.anal_only:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(querys, f, ensure_ascii=False, indent=2)

    def create_jt_edge_with_gql_from_edge_dict(self, database_file, jt_dict):
        querys = []
        for (src_and_tgt, edges) in jt_dict.items():
            src = src_and_tgt[0]
            tgt = src_and_tgt[1]
            for edge in edges:
                edge_label = edge['edge_label']
                related_jt = edge['related_jt']
                src_filter_cols = edge['source_filter_columns']
                tgt_filter_cols = edge['target_filter_columns']
                src_filter_cols_align = edge['source_filter_columns_align']
                tgt_filter_cols_align = edge['target_filter_columns_align']
                exported_jt = self.get_exported_csv(database_file, related_jt).dropna(subset=src_filter_cols + tgt_filter_cols)
                prop_cols = exported_jt.columns.to_list()
                src_filter_unwind_query = ', '.join([f'`{src_col_align.lower()}`:pair.`{src_col}`' for (src_col_align, src_col) in zip(src_filter_cols_align, src_filter_cols)])
                tgt_filter_unwind_query = ', '.join([f'`{tgt_col_align.lower()}`:pair.`{tgt_col}`' for (tgt_col_align, tgt_col) in zip(tgt_filter_cols_align, tgt_filter_cols)])
                pairs = json.loads(exported_jt.applymap(lambda x: self.val_mapping(x)).to_json(orient='records'))
                pairs = [{k: v for (k, v) in pair.items() if not pd.isna(v)} for pair in pairs]
                pairs_set = {}
                for one_pair in pairs:
                    pairs_set.setdefault(tuple(sorted(one_pair.keys())), []).append(one_pair)
                for (prop_cols_comb, one_pairs_list) in pairs_set.items():
                    prop_filter_unwind_query = ', '.join([f'`{prop_col.lower()}`:pair.`{prop_col}`' for prop_col in prop_cols_comb])
                    time_cols = self.get_time_cols(exported_jt, prop_cols_comb)
                    unwind_query = f'UNWIND $pairs AS pair MATCH (from:`{src.lower()}` {{{src_filter_unwind_query}}}), (to:`{tgt.lower()}` {{{tgt_filter_unwind_query}}}) MERGE (from)-[r:`{edge_label.lower()}` {{{prop_filter_unwind_query}}}]->(to);'
                    unwind_query = f'UNWIND $pairs AS pair WITH DISTINCT pair MATCH (from:`{src.lower()}` {{{src_filter_unwind_query}}}), (to:`{tgt.lower()}` {{{tgt_filter_unwind_query}}}) CREATE (from)-[r:`{edge_label.lower()}` {{{prop_filter_unwind_query}}}]->(to);'
                    unwind_query = f'UNWIND $pairs AS pair WITH DISTINCT pair CALL(*) {{MATCH (from:`{src.lower()}` {{{src_filter_unwind_query}}}) WITH from LIMIT 1 MATCH (to:`{tgt.lower()}` {{{tgt_filter_unwind_query}}}) RETURN from, to LIMIT 1 }} CREATE (from)-[r:`{edge_label.lower()}` {{{prop_filter_unwind_query}}}]->(to);'
                    print(unwind_query)
                    querys.append({'query': unwind_query, 'params': one_pairs_list, 'time_cols': time_cols})
        import_graph_data_path = os.path.join(database_file, IMPORT_GRAPH_DATA_PATH)
        filepath = os.path.join(import_graph_data_path, f'edges_jt_{self.gql_type}_commands.txt')
        if not self.anal_only:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(querys, f, ensure_ascii=False, indent=2)

    def create_edge_with_gql(self, database_file):
        all_edges = Convert_DB.get_all_edges(database_file=database_file, llm_model_name=self.llm_model_name)
        self.create_jt_edge_with_gql_from_edge_dict(database_file, all_edges['jt'])
        self.create_fk_edge_with_gql_from_edge_dict(database_file, all_edges['fk'])

def validate_and_convert_value(col_name, value, expected_type):
    if pd.isna(value) or value is None:
        return None
    if pd.isna(expected_type) or expected_type is None or expected_type == '':
        if isinstance(value, str):
            if value.startswith("'") and value.endswith("'"):
                return value[1:-1]
            elif value.startswith('"') and value.endswith('"'):
                return value[1:-1]
            return value
        else:
            return str(value)
    expected_type_upper = expected_type.strip().upper()
    expected_type_lower = expected_type_upper.lower()
    if expected_type_upper in ('DATE', 'DATETIME') or expected_type_lower in ('date', 'datetime') or 'timestamp' in expected_type_lower or ('datetime' in expected_type_lower):
        if isinstance(value, str) and (value.startswith('date(') or value.startswith('local_datetime(')):
            return value
        try:
            if isinstance(value, str):
                if value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
            dt = pd.to_datetime(value, errors='coerce')
            if pd.notna(dt):
                if expected_type_upper == 'DATE' or expected_type_lower == 'date':
                    return f'date("{dt.date().isoformat()}")'
                else:
                    if hasattr(dt, 'to_pydatetime'):
                        dt = dt.to_pydatetime()
                    iso = dt.replace(microsecond=0).strftime('%Y-%m-%dT%H:%M:%S')
                    return f'local_datetime("{iso}", "%Y-%m-%dT%H:%M:%S")'
        except:
            pass
        return value
    elif expected_type_upper in ('TEXT', 'BLOB', 'STRING') or 'varchar' in expected_type_lower or 'char' in expected_type_lower:
        if isinstance(value, str):
            if value.startswith("'") and value.endswith("'"):
                return value[1:-1]
            elif value.startswith('"') and value.endswith('"'):
                return value[1:-1]
            return value
        else:
            return str(value)
    elif expected_type_upper in ('INTEGER', 'INT', 'BIT', 'YEAR') or 'int' in expected_type_lower:
        try:
            if isinstance(value, str):
                if value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                return int(float(value))
            return int(float(value))
        except (ValueError, TypeError):
            print(f'Warning: column `{col_name}` expects {expected_type}, but value {value} cannot be converted to int')
            return value
    elif expected_type_upper in ('REAL', 'FLOAT', 'DOUBLE') or 'number' in expected_type_lower or 'float' in expected_type_lower or ('double' in expected_type_lower) or ('decimal' in expected_type_lower) or ('numeric' in expected_type_lower):
        try:
            if isinstance(value, str):
                if value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                return float(value)
            return float(value)
        except (ValueError, TypeError):
            print(f'Warning: column `{col_name}` expects {expected_type}, but value {value} cannot be converted to float')
            return value
    elif expected_type_upper in ('BOOL', 'BOOLEAN') or 'bool' in expected_type_lower:
        if isinstance(value, bool):
            return value
        elif isinstance(value, (int, np.integer)):
            return bool(value)
        elif isinstance(value, str):
            val_lower = value.lower().strip()
            if val_lower in ('true', '1', 'yes', 't'):
                return True
            elif val_lower in ('false', '0', 'no', 'f', ''):
                return False
            else:
                try:
                    return bool(float(value))
                except:
                    print(f'Warning: column `{col_name}` expects {expected_type}, but value {value} cannot be converted to bool')
                    return value
        else:
            try:
                return bool(value)
            except:
                print(f'Warning: column `{col_name}` expects {expected_type}, but value {value} cannot be converted to bool')
                return value
    return value

class Convert_Nebula_DB(Convert_DB):

    def __init__(self, gql_type, anal_only):
        super().__init__()
        self.gql_type = gql_type
        self.anal_only = anal_only

    def val_mapping(self, val):
        if pd.isna(val) or pd.isnull(val):
            return None
        if isinstance(val, (int, float, complex, np.integer, np.floating)):
            return val
        elif isinstance(val, (bool, np.bool_)):
            return val
        elif isinstance(val, str):
            val = val.replace('\\', '\\\\')
            val = val.replace("'", "\\'")
            val = val.replace('"', '\\"')
            return f"'{val}'"
        elif isinstance(val, datetime.date) or isinstance(val, datetime.datetime):
            if hasattr(val, 'to_pydatetime'):
                val = val.to_pydatetime()
            iso = val.replace(microsecond=0).strftime('%Y-%m-%dT%H:%M:%S')
            return f'local_datetime("{iso}","%Y-%m-%dT%H:%M:%S")'
        else:
            raise TypeError(f'Unsupported type: {type(val)}')

    def col_mapping(self, col):
        return col

    def nebula_type_mapping(self, type_str: str):
        if pd.isna(type_str) or type_str is None or type_str == '':
            return 'STRING'
        t = type_str.strip()
        t_upper = t.upper()
        t_lower = t.lower()
        if t_upper in ('DATE', 'DATETIME') or t_lower in ('date', 'datetime') or 'timestamp' in t_lower or ('datetime' in t_lower):
            return 'LOCAL DATETIME'
        if t_upper in ('TEXT', 'BLOB') or 'varchar' in t_lower or 'char' in t_lower:
            return 'STRING'
        if t_upper == 'INTEGER' or 'int' in t_lower or t_upper in ('BIT', 'YEAR'):
            return 'INT'
        if t_upper == 'REAL' or 'number' in t_lower or 'float' in t_lower or ('double' in t_lower) or ('decimal' in t_lower) or ('numeric' in t_lower):
            return 'FLOAT'
        if t_upper in ('BOOL', 'BOOLEAN') or 'bool' in t_lower:
            return 'BOOL'
        return 'STRING'

    def _batch(self, arr, batch_size: int):
        for i in range(0, len(arr), batch_size):
            yield arr[i:i + batch_size]

    def create_schema_with_gql(self, database_file):
        all_jointables = Sqlite_Process.get_all_jointables(database_file, self.llm_model_name)
        all_tables = Sqlite_Process.get_all_tables(database_file)
        all_jointables_lower = [table.lower() for table in all_jointables]
        node_tables = [table for table in all_tables if table.lower() not in all_jointables_lower]
        import_graph_data_path = os.path.join(database_file, IMPORT_GRAPH_DATA_PATH)
        if not os.path.exists(import_graph_data_path):
            os.mkdir(import_graph_data_path)

        def infer_pk(table_name: str, schema_df: pd.DataFrame):
            return 'id_for_nebula'
        node_lines = []
        for table in node_tables:
            schema_df = self.get_exported_schema(database_file, table)
            props = []
            props.append('`id_for_nebula` INT')
            for (_, row) in schema_df.iterrows():
                col_name = self.col_mapping(str(row['name']))
                col_type = self.nebula_type_mapping(str(row['type']))
                props.append(f'`{col_name.lower()}` {col_type}')
            pk_col = 'id_for_nebula'
            label_name = self.col_mapping(table)
            node_name = self.col_mapping(table)
            if props:
                node_lines.append(f"NODE `{node_name.lower()}` (LABEL `{label_name.lower()}` {{{', '.join(props)}, PRIMARY KEY (`{pk_col}`)}})")
        all_edges = Convert_DB.get_all_edges(database_file=database_file, llm_model_name=self.llm_model_name, gql_type='nebula')
        edge_lines = []
        for ((src, tgt), edges) in all_edges['fk'].items():
            for e in edges:
                edge_type = self.col_mapping(e['edge_label'])
                src_node = self.col_mapping(src)
                tgt_node = self.col_mapping(tgt)
                edge_lines.append(f'EDGE `{edge_type.lower()}` (`{src_node.lower()}`)-[:`{edge_type.lower()}` {{`id_for_nebula` INT, MULTIEDGE KEY(`id_for_nebula`)}}]->(`{tgt_node.lower()}`)')
        for ((src, tgt), edges) in all_edges['jt'].items():
            for e in edges:
                edge_type = self.col_mapping(e['edge_label'])
                related_jt = e['related_jt']
                schema_df = self.get_exported_schema(database_file, related_jt)
                props = []
                for (_, row) in schema_df.iterrows():
                    col_name = self.col_mapping(str(row['name']))
                    col_type = self.nebula_type_mapping(str(row['type']))
                    props.append(f'`{col_name.lower()}` {col_type}')
                src_node = self.col_mapping(src)
                tgt_node = self.col_mapping(tgt)
                if props:
                    edge_lines.append(f"EDGE `{edge_type.lower()}` (`{src_node.lower()}`)-[:`{edge_type.lower()}` {{{', '.join(props) + ', `id_for_nebula` INT,MULTIEDGE KEY(`id_for_nebula`)'}}} ]->(`{tgt_node.lower()}`)")
                else:
                    edge_lines.append(f'EDGE `{edge_type.lower()}` (`{src_node.lower()}`)-[:`{edge_type.lower()}`, {{`id_for_nebula` INT,MULTIEDGE KEY(`id_for_nebula`)}}]->(`{tgt_node.lower()}`)')
        base = self.col_mapping(database_file.split(FILEPATH_SPLIT)[-1])
        graph_type_name = f'{base}_type'
        graph_name = f'{base}'
        body = ', \n'.join(node_lines + edge_lines)
        drop_graph_stmt = f'DROP GRAPH IF EXISTS {graph_name}'
        drop_graph_type_stmt = f'DROP GRAPH TYPE IF EXISTS {graph_type_name}'
        graph_type_stmt = f'CREATE GRAPH TYPE IF NOT EXISTS {graph_type_name} AS {{ \n{body} \n}}'
        create_graph_stmt = f'CREATE GRAPH IF NOT EXISTS {graph_name} TYPED {graph_type_name}'
        use_session_stmt = f'SESSION SET GRAPH {graph_name}'
        querys = [{'query': drop_graph_stmt, 'params': [], 'time_cols': []}, {'query': drop_graph_type_stmt, 'params': [], 'time_cols': []}, {'query': graph_type_stmt, 'params': [], 'time_cols': []}, {'query': create_graph_stmt, 'params': [], 'time_cols': []}, {'query': use_session_stmt, 'params': [], 'time_cols': []}]
        filepath = os.path.join(import_graph_data_path, f'schema_{self.gql_type}_commands.txt')
        if not self.anal_only:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(querys, f, ensure_ascii=False, indent=2)

    def create_node_with_gql(self, database_file):
        all_jointables = Sqlite_Process.get_all_jointables(database_file, self.llm_model_name)
        all_tables = Sqlite_Process.get_all_tables(database_file)
        all_jointables_lower = [table.lower() for table in all_jointables]
        tables = [table for table in all_tables if table.lower() not in all_jointables_lower]
        print(tables)
        table_dfs = [self.get_exported_csv(database_file, table) for table in tables]
        import_graph_data_path = os.path.join(database_file, IMPORT_GRAPH_DATA_PATH)
        if not os.path.exists(import_graph_data_path):
            os.mkdir(import_graph_data_path)
        for (table_idx, table_name) in enumerate(tables):
            df = table_dfs[table_idx]
            querys = []
            tag_name = self.col_mapping(table_name.lower())
            mapped_cols = [self.col_mapping(col) for col in df.columns]
            mapped_cols_with_pk = ['id_for_nebula'] + mapped_cols
            schema_df = self.get_exported_schema(database_file, table_name)
            col_type_map = {}
            for (_, row) in schema_df.iterrows():
                col_name = str(row['name'])
                col_type = str(row['type']).upper()
                col_type_map[col_name] = col_type
            pairs = json.loads(df.applymap(lambda x: self.val_mapping(x)).to_json(orient='records'))
            time_cols = self.get_time_cols(df, df.columns)
            validated_pairs = []
            for pair in pairs:
                validated_pair = {}
                for (col_name, value) in pair.items():
                    expected_type = col_type_map.get(col_name, 'TEXT')
                    validated_value = validate_and_convert_value(col_name, value, expected_type)
                    validated_pair[col_name] = validated_value
                validated_pairs.append(validated_pair)
            insert_statements = []
            for (idx, pair) in enumerate(validated_pairs):
                kv_parts = []
                kv_parts.append(f'`id_for_nebula`:{idx}')
                for col in df.columns:
                    mapped_col = self.col_mapping(col)
                    if col in pair:
                        val = pair[col]
                        if val is None or pd.isna(val):
                            continue
                        if isinstance(val, str):
                            if val.startswith('date(') or val.startswith('local_datetime('):
                                kv_parts.append(f'`{mapped_col.lower()}`:{val}')
                            elif val.startswith("'") and val.endswith("'"):
                                inner = val[1:-1].replace('"', '\\"')
                                kv_parts.append(f'`{mapped_col.lower()}`:"{inner}"')
                            else:
                                esc = val.replace('\\', '\\\\').replace('"', '\\"')
                                kv_parts.append(f'`{mapped_col.lower()}`:"{esc}"')
                        else:
                            kv_parts.append(f'`{mapped_col.lower()}`:{val}')
                prop_str = ', '.join(kv_parts)
                insert_statements.append(f'INSERT (@`{tag_name.lower()}`{{{prop_str}}})')
            for stmt in insert_statements:
                querys.append({'query': stmt, 'time_cols': time_cols})
            filepath = os.path.join(import_graph_data_path, f'node_{table_name}_{self.gql_type}_commands.txt')
            if not self.anal_only:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(querys, f, ensure_ascii=False, indent=2)

    def create_fk_edge_with_gql_from_edge_dict(self, database_file, fk_dict):
        querys = []
        for (src_and_tgt, edges) in fk_dict.items():
            src = src_and_tgt[0]
            tgt = src_and_tgt[1]
            for edge in edges:
                edge_label = edge['edge_label']
                src_filter_cols = edge['source_filter_columns']
                tgt_filter_cols = edge['target_filter_columns']
                (src_csv, tgt_csv) = (self.get_exported_csv(database_file, src), self.get_exported_csv(database_file, tgt))
                src_filter_cols_vals = set(src_csv[src_filter_cols].dropna().apply(tuple, axis=1))
                tgt_filter_cols_vals = set(tgt_csv[tgt_filter_cols].dropna().apply(tuple, axis=1))
                common_vals = list(src_filter_cols_vals & tgt_filter_cols_vals)
                common_vals = list(set(common_vals))
                src_schema_df = self.get_exported_schema(database_file, src)
                tgt_schema_df = self.get_exported_schema(database_file, tgt)
                src_col_type_map = {}
                for (_, row) in src_schema_df.iterrows():
                    col_name = str(row['name'])
                    col_type = str(row['type']).upper()
                    src_col_type_map[col_name] = col_type
                tgt_col_type_map = {}
                for (_, row) in tgt_schema_df.iterrows():
                    col_name = str(row['name'])
                    col_type = str(row['type']).upper()
                    tgt_col_type_map[col_name] = col_type
                for (idx, vals) in enumerate(common_vals):
                    src_kv_parts = []
                    for (col, val) in zip(src_filter_cols, vals):
                        mapped_col = self.col_mapping(col).lower()
                        expected_type = src_col_type_map.get(col, None)
                        if expected_type is None:
                            for (k, v) in src_col_type_map.items():
                                if k.lower() == col.lower():
                                    expected_type = v
                                    break
                            if expected_type is None:
                                expected_type = 'TEXT'
                        mapped_val = self.val_mapping(val)
                        validated_val = validate_and_convert_value(col, mapped_val, expected_type)
                        if validated_val is None or pd.isna(validated_val):
                            continue
                        if isinstance(validated_val, str):
                            if validated_val.startswith('date(') or validated_val.startswith('local_datetime('):
                                src_kv_parts.append(f'`{mapped_col}`:{validated_val}')
                            elif validated_val.startswith("'") and validated_val.endswith("'"):
                                inner = validated_val[1:-1].replace('"', '\\"')
                                src_kv_parts.append(f'`{mapped_col}`:"{inner}"')
                            else:
                                esc = validated_val.replace('\\', '\\\\').replace('"', '\\"')
                                src_kv_parts.append(f'`{mapped_col}`:"{esc}"')
                        else:
                            src_kv_parts.append(f'`{mapped_col}`:{validated_val}')
                    tgt_kv_parts = []
                    for (col, val) in zip(tgt_filter_cols, vals):
                        mapped_col = self.col_mapping(col).lower()
                        expected_type = tgt_col_type_map.get(col, None)
                        if expected_type is None:
                            for (k, v) in tgt_col_type_map.items():
                                if k.lower() == col.lower():
                                    expected_type = v
                                    break
                            if expected_type is None:
                                expected_type = 'TEXT'
                        mapped_val = self.val_mapping(val)
                        validated_val = validate_and_convert_value(col, mapped_val, expected_type)
                        if validated_val is None or pd.isna(validated_val):
                            continue
                        if isinstance(validated_val, str):
                            if validated_val.startswith('date(') or validated_val.startswith('local_datetime('):
                                tgt_kv_parts.append(f'`{mapped_col}`:{validated_val}')
                            elif validated_val.startswith("'") and validated_val.endswith("'"):
                                inner = validated_val[1:-1].replace('"', '\\"')
                                tgt_kv_parts.append(f'`{mapped_col}`:"{inner}"')
                            else:
                                esc = validated_val.replace('\\', '\\\\').replace('"', '\\"')
                                tgt_kv_parts.append(f'`{mapped_col}`:"{esc}"')
                        else:
                            tgt_kv_parts.append(f'`{mapped_col}`:{validated_val}')
                    src_match_str = ', '.join(src_kv_parts)
                    tgt_match_str = ', '.join(tgt_kv_parts)
                    src_tag = self.col_mapping(src).lower()
                    tgt_tag = self.col_mapping(tgt).lower()
                    query = f'MATCH (n1:`{src_tag}` {{{src_match_str}}}) LIMIT 1 MATCH (n2:`{tgt_tag}` {{{tgt_match_str}}}) LIMIT 1 INSERT (n1)-[@`{edge_label.lower()}` {{`id_for_nebula`:{idx}}}]->(n2)'
                    querys.append({'query': query, 'time_cols': []})
        import_graph_data_path = os.path.join(database_file, IMPORT_GRAPH_DATA_PATH)
        filepath = os.path.join(import_graph_data_path, f'edges_fk_{self.gql_type}_commands.txt')
        if not self.anal_only:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(querys, f, ensure_ascii=False, indent=2)

    def create_jt_edge_with_gql_from_edge_dict(self, database_file, jt_dict):
        querys = []
        for (src_and_tgt, edges) in jt_dict.items():
            src = src_and_tgt[0]
            tgt = src_and_tgt[1]
            for edge in edges:
                edge_label = edge['edge_label']
                related_jt = edge['related_jt']
                src_filter_cols = edge['source_filter_columns']
                tgt_filter_cols = edge['target_filter_columns']
                src_filter_cols_align = edge['source_filter_columns_align']
                tgt_filter_cols_align = edge['target_filter_columns_align']
                exported_jt = self.get_exported_csv(database_file, related_jt).dropna(subset=src_filter_cols + tgt_filter_cols)
                prop_cols = [c for c in exported_jt.columns if c not in src_filter_cols and c not in tgt_filter_cols]
                if prop_cols:
                    exported_jt = exported_jt.drop_duplicates(subset=src_filter_cols + tgt_filter_cols + prop_cols)
                else:
                    exported_jt = exported_jt.drop_duplicates(subset=src_filter_cols + tgt_filter_cols)
                src_schema_df = self.get_exported_schema(database_file, src)
                tgt_schema_df = self.get_exported_schema(database_file, tgt)
                jt_schema_df = self.get_exported_schema(database_file, related_jt)
                src_col_type_map = {}
                for (_, row) in src_schema_df.iterrows():
                    col_name = str(row['name']).lower()
                    col_type = str(row['type']).upper()
                    src_col_type_map[col_name] = col_type
                tgt_col_type_map = {}
                for (_, row) in tgt_schema_df.iterrows():
                    col_name = str(row['name']).lower()
                    col_type = str(row['type']).upper()
                    tgt_col_type_map[col_name] = col_type
                jt_col_type_map = {}
                for (_, row) in jt_schema_df.iterrows():
                    col_name = str(row['name']).lower()
                    col_type = str(row['type']).upper()
                    jt_col_type_map[col_name] = col_type
                for (idx, (_, row)) in enumerate(exported_jt.iterrows()):
                    src_kv_parts = []
                    for (align_col, orig_col) in zip(src_filter_cols_align, src_filter_cols):
                        mapped_col = self.col_mapping(align_col).lower()
                        val = row[orig_col]
                        expected_type = src_col_type_map.get(align_col, None)
                        if expected_type is None:
                            for (k, v) in src_col_type_map.items():
                                if k.lower() == align_col.lower():
                                    expected_type = v
                                    break
                            if expected_type is None:
                                expected_type = 'TEXT'
                        mapped_val = self.val_mapping(val)
                        validated_val = validate_and_convert_value(align_col, mapped_val, expected_type)
                        if validated_val is None or pd.isna(validated_val):
                            continue
                        if isinstance(validated_val, str):
                            if validated_val.startswith('date(') or validated_val.startswith('local_datetime('):
                                src_kv_parts.append(f'`{mapped_col}`:{validated_val}')
                            elif validated_val.startswith("'") and validated_val.endswith("'"):
                                inner = validated_val[1:-1].replace('"', '\\"')
                                src_kv_parts.append(f'`{mapped_col}`:"{inner}"')
                            else:
                                esc = validated_val.replace('\\', '\\\\').replace('"', '\\"')
                                src_kv_parts.append(f'`{mapped_col}`:"{esc}"')
                        else:
                            src_kv_parts.append(f'`{mapped_col}`:{validated_val}')
                    tgt_kv_parts = []
                    for (align_col, orig_col) in zip(tgt_filter_cols_align, tgt_filter_cols):
                        mapped_col = self.col_mapping(align_col).lower()
                        val = row[orig_col]
                        expected_type = tgt_col_type_map.get(align_col, None)
                        if expected_type is None:
                            for (k, v) in tgt_col_type_map.items():
                                if k.lower() == align_col.lower():
                                    expected_type = v
                                    break
                            if expected_type is None:
                                expected_type = 'TEXT'
                        mapped_val = self.val_mapping(val)
                        validated_val = validate_and_convert_value(align_col, mapped_val, expected_type)
                        if validated_val is None or pd.isna(validated_val):
                            continue
                        if isinstance(validated_val, str):
                            if validated_val.startswith('date(') or validated_val.startswith('local_datetime('):
                                tgt_kv_parts.append(f'`{mapped_col}`:{validated_val}')
                            elif validated_val.startswith("'") and validated_val.endswith("'"):
                                inner = validated_val[1:-1].replace('"', '\\"')
                                tgt_kv_parts.append(f'`{mapped_col}`:"{inner}"')
                            else:
                                esc = validated_val.replace('\\', '\\\\').replace('"', '\\"')
                                tgt_kv_parts.append(f'`{mapped_col}`:"{esc}"')
                        else:
                            tgt_kv_parts.append(f'`{mapped_col}`:{validated_val}')
                    edge_props_parts = []
                    if prop_cols:
                        for prop_col in prop_cols:
                            mapped_col = self.col_mapping(prop_col).lower()
                            val = row[prop_col]
                            expected_type = jt_col_type_map.get(prop_col, None)
                            if expected_type is None:
                                for (k, v) in jt_col_type_map.items():
                                    if k.lower() == prop_col.lower():
                                        expected_type = v
                                        break
                                if expected_type is None:
                                    expected_type = 'TEXT'
                            mapped_val = self.val_mapping(val)
                            validated_val = validate_and_convert_value(prop_col, mapped_val, expected_type)
                            if validated_val is None or pd.isna(validated_val):
                                continue
                            if isinstance(validated_val, str):
                                if validated_val.startswith('date(') or validated_val.startswith('local_datetime('):
                                    edge_props_parts.append(f'`{mapped_col}`:{validated_val}')
                                elif validated_val.startswith("'") and validated_val.endswith("'"):
                                    inner = validated_val[1:-1].replace('"', '\\"')
                                    edge_props_parts.append(f'`{mapped_col}`:"{inner}"')
                                else:
                                    esc = validated_val.replace('\\', '\\\\').replace('"', '\\"')
                                    edge_props_parts.append(f'`{mapped_col}`:"{esc}"')
                            else:
                                edge_props_parts.append(f'`{mapped_col}`:{validated_val}')
                    src_match_str = ', '.join(src_kv_parts)
                    tgt_match_str = ', '.join(tgt_kv_parts)
                    src_tag = self.col_mapping(src).lower()
                    tgt_tag = self.col_mapping(tgt).lower()
                    if edge_props_parts:
                        edge_props_str = ', '.join(edge_props_parts)
                        edge_props_str += f', `id_for_nebula`:{idx}'
                        query = f'MATCH (n1:`{src_tag}` {{{src_match_str}}}) LIMIT 1 MATCH (n2:`{tgt_tag}` {{{tgt_match_str}}}) LIMIT 1 INSERT (n1)-[@`{edge_label.lower()}` {{{edge_props_str}}}]->(n2)'
                    else:
                        query = f'MATCH (n1:`{src_tag}` {{{src_match_str}}}) LIMIT 1 MATCH (n2:`{tgt_tag}` {{{tgt_match_str}}}) LIMIT 1 INSERT (n1)-[@`{edge_label.lower()}` {{`id_for_nebula`:{idx}}}]->(n2)'
                    querys.append({'query': query, 'time_cols': []})
        import_graph_data_path = os.path.join(database_file, IMPORT_GRAPH_DATA_PATH)
        filepath = os.path.join(import_graph_data_path, f'edges_jt_{self.gql_type}_commands.txt')
        if not self.anal_only:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(querys, f, ensure_ascii=False, indent=2)

    def create_edge_with_gql(self, database_file):
        all_edges = Convert_DB.get_all_edges(database_file=database_file, llm_model_name=self.llm_model_name, gql_type='nebula')
        self.create_jt_edge_with_gql_from_edge_dict(database_file, all_edges['jt'])
        self.create_fk_edge_with_gql_from_edge_dict(database_file, all_edges['fk'])
if __name__ == '__main__':
    gql_type = 'cypher'
    folder = SPIDER_TEST_folder
    convert_db = Convert_neo4j_DB(gql_type=gql_type, anal_only=False) if gql_type == 'cypher' else Convert_Nebula_DB(gql_type=gql_type, anal_only=False)
    if gql_type == 'nebula' and os.path.exists(f'{folder}/nebula_convert_processed.txt'):
        with open(f'{folder}/nebula_convert_processed.txt', 'r') as f:
            exists = ast.literal_eval(f.read())
    elif gql_type == 'cypher' and os.path.exists(f'{folder}/convert_processed.txt'):
        with open(f'{folder}/convert_processed.txt', 'r') as f:
            exists = ast.literal_eval(f.read())
    else:
        exists = []
    todo = []
    for item in os.listdir(folder):
        filepath = os.path.join(folder, item)
        if os.path.isdir(filepath):
            print(filepath)
            if item in exists and item not in todo:
                continue

            if gql_type == 'nebula':
                convert_db.create_schema_with_gql(filepath)
            convert_db.create_node_with_gql(filepath)
            convert_db.create_edge_with_gql(filepath)
            exists.append(item)
            if gql_type == 'nebula':
                with open(f'{folder}/nebula_convert_processed.txt', 'w') as f:
                    f.write(str(exists))
            elif gql_type == 'cypher':
                with open(f'{folder}/convert_processed.txt', 'w') as f:
                    f.write(str(exists))
    print(exists)