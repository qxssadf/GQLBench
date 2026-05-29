import pandas as pd
import numpy as np
import sqlite3
import os
import json
from jinja2 import Template
import chardet
from LLM_Utils import *
from Config import *
import ast

def decode_text(bs):
    if isinstance(bs, bytes):
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                return bs.decode(encoding)
            except (UnicodeDecodeError, AttributeError):
                continue
        return bs.decode('utf-8', errors='replace')
    return bs

class Sqlite_Process:

    def __init__(self, anal_only=True):
        self.anal_only = anal_only
        self.llm_model = MODEL
        self.llm_model_name = 'DeepSeek-R1'

    def export_to_csv_with_pandas(self, database_file, csv_filepath):
        conn = sqlite3.connect(database_file)
        conn.text_factory = decode_text
        tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)['name'].tolist()
        print(tables)
        print(f'Found {len(tables)} tables')
        csv_filepath = os.path.join(csv_filepath, 'exported_csv_tables')
        if not os.path.exists(csv_filepath):
            os.mkdir(csv_filepath)
        for table_name in tables:
            df = pd.read_sql_query(f"SELECT * FROM '{table_name}';", conn)
            print(os.path.join(csv_filepath, f'{table_name}.csv'))
            if not self.anal_only:
                df.to_csv(os.path.join(csv_filepath, f'{table_name}.csv'), index=False, encoding='utf-8')
            print(f'Table {table_name} exported to {csv_filepath}')
        conn.close()

    def export_to_csv_schema(self, database_file, filepath):
        conn = sqlite3.connect(database_file)
        conn.text_factory = decode_text
        tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)['name'].tolist()
        csv_filepath = os.path.join(filepath, EXPORTED_SCHEMA_PATH)
        if not os.path.exists(csv_filepath):
            os.mkdir(csv_filepath)
        for table_name in tables:
            df = pd.read_sql_query(f"PRAGMA table_info('{table_name}');", conn)
            print(os.path.join(csv_filepath, f'{table_name}.csv'))
            if not self.anal_only:
                df.to_csv(os.path.join(csv_filepath, f'{table_name}.csv'), index=False, encoding='utf-8')
        conn.close()

    def get_foreign_and_primary_keys(self, database_file, relation_filepath):
        conn = sqlite3.connect(database_file)
        conn.text_factory = decode_text
        database_name = database_file.split(FILEPATH_SPLIT)[-1].split('.')[0]
        fk_relation_filepath = os.path.join(relation_filepath, 'fk_relation_files')
        if not os.path.exists(fk_relation_filepath):
            os.mkdir(fk_relation_filepath)
        tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)['name'].tolist()
        to_edge_fks = {}
        JoinTables = []
        notJoinTables = []
        for table_name in tables:
            print('Table', table_name)
            fk_df_result = []
            fk_df = pd.read_sql_query(f"PRAGMA foreign_key_list('{table_name}')", conn).dropna(subset=['id', 'table', 'from', 'to'])
            for i in range(len(fk_df)):
                if fk_df.iloc[i]['table'] not in tables:
                    for table_align in tables:
                        if fk_df.iloc[i]['table'].lower() == table_align.lower():
                            fk_df.loc[fk_df.index[i], 'table'] = table_align
            for (_, group) in fk_df.groupby('id'):
                from_cols = group['from'].tolist()
                to_cols = group['to'].tolist()
                to_table = group['table'].iloc[0]
                fk_df_result.append({'from_table': table_name, 'to_table': to_table, 'from_column': from_cols, 'to_column': to_cols})
            fk_df = pd.DataFrame(fk_df_result)
            print(fk_df)
            if len(fk_df) > 0:
                table_columns_cache = {}

                def get_table_columns(table_name):
                    if table_name not in table_columns_cache:
                        if table_name in tables:
                            df = pd.read_sql_query(f'SELECT * FROM `{table_name}` LIMIT 1', conn)
                            table_columns_cache[table_name] = df.columns.tolist()
                        else:
                            table_columns_cache[table_name] = []
                    return table_columns_cache[table_name]

                def align_column_name(requested_col, actual_cols):
                    actual_cols_lower = {col.lower(): col for col in actual_cols}
                    req_col_lower = requested_col.lower()
                    if req_col_lower in actual_cols_lower:
                        return actual_cols_lower[req_col_lower]
                    return None
                rows_to_drop = []
                for (idx, row) in fk_df.iterrows():
                    from_table = row['from_table']
                    to_table = row['to_table']
                    from_cols_orig = row['from_column']
                    to_cols_orig = row['to_column']
                    from_cols = from_cols_orig if isinstance(from_cols_orig, list) else [from_cols_orig]
                    to_cols = to_cols_orig if isinstance(to_cols_orig, list) else [to_cols_orig]
                    from_table_cols = get_table_columns(from_table)
                    to_table_cols = get_table_columns(to_table)
                    aligned_from_cols = []
                    for col in from_cols:
                        aligned_col = align_column_name(col, from_table_cols)
                        if aligned_col is None:
                            print(f'Warning: column {col} not found in table {from_table}; dropping FK relation')
                            rows_to_drop.append(idx)
                            break
                        aligned_from_cols.append(aligned_col)
                    if idx in rows_to_drop:
                        continue
                    aligned_to_cols = []
                    for col in to_cols:
                        aligned_col = align_column_name(col, to_table_cols)
                        if aligned_col is None:
                            print(f'Warning: column {col} not found in table {to_table}; dropping FK relation')
                            rows_to_drop.append(idx)
                            break
                        aligned_to_cols.append(aligned_col)
                    if aligned_from_cols != from_cols or aligned_to_cols != to_cols:
                        if isinstance(from_cols_orig, list):
                            fk_df.at[idx, 'from_column'] = aligned_from_cols
                        else:
                            fk_df.at[idx, 'from_column'] = aligned_from_cols[0] if len(aligned_from_cols) == 1 else aligned_from_cols
                        if isinstance(to_cols_orig, list):
                            fk_df.at[idx, 'to_column'] = aligned_to_cols
                        else:
                            fk_df.at[idx, 'to_column'] = aligned_to_cols[0] if len(aligned_to_cols) == 1 else aligned_to_cols
                if rows_to_drop:
                    fk_df = fk_df.drop(index=rows_to_drop).reset_index(drop=True)
                    print(f'Removed {len(rows_to_drop)} invalid FK relation row(s)')
            print(fk_df)
            cur_table_nxt = np.unique(fk_df['to_table']) if len(fk_df) > 0 else []
            cur_table_fk = np.unique(fk_df['from_column']) if len(fk_df) > 0 else []
            if len(cur_table_fk) != len(fk_df):
                print('lipu')
            if not self.anal_only:
                fk_df.to_csv(fk_relation_filepath + '/' + table_name + '_fk_relation.csv', index=False)
            pk_df = pd.read_sql_query(f"PRAGMA table_info('{table_name}')", conn)
            cur_table_pk = pk_df.query('pk>0')['name'].to_list()
            if len(fk_df) <= 1:
                self.save_as_FK(table_name, fk_df, to_edge_fks)
                self.save_as_notJoinTable(table_name, notJoinTables)
            elif len([pk for pk in cur_table_pk if pk in sum(cur_table_fk, [])]) == len(cur_table_pk):
                fk_num = 0
                for cur_fk in cur_table_fk:
                    flag = 1
                    for fk in cur_fk:
                        if fk not in cur_table_pk:
                            flag = 0
                            break
                    fk_num += flag
                if fk_num <= 1:
                    self.save_as_FK(table_name, fk_df, to_edge_fks)
                else:
                    self.save_as_JoinTable(table_name, JoinTables)
                    self.save_as_FK(table_name, fk_df, to_edge_fks)
            else:
                self.save_as_FK(table_name, fk_df, to_edge_fks)
        edge_schema_filepath = os.path.join(relation_filepath, EDGE_SCHEMA_PATH)
        if not os.path.exists(edge_schema_filepath):
            os.mkdir(edge_schema_filepath)
        if not self.anal_only:
            with open(f'{edge_schema_filepath}/{database_name}.jsonl', 'w') as f:
                json.dump(to_edge_fks, f)
            with open(f'{edge_schema_filepath}/jointable.txt', 'w') as f:
                f.write(str(JoinTables))
            with open(f'{edge_schema_filepath}/notjointable.txt', 'w') as f:
                f.write(str(notJoinTables))
        conn.close()

    def fk2unique_table(self, database_file):
        database_name = database_file.split(FILEPATH_SPLIT)[-1]
        fk_json_path = os.path.join(database_file, EDGE_SCHEMA_PATH, f'{database_name}.jsonl')
        with open(fk_json_path, 'r') as f:
            fk_json = json.load(f)
        fk_t2t = {}
        for (from_table, relations) in fk_json.items():
            if from_table.lower() == 'sqlite_sequence':
                continue
            fk_t2t[from_table] = []
            if not relations:
                continue
            unique_to_tables = list(set([rel['to_table'] for rel in relations]))
            for to_table_name in unique_to_tables:
                tmp_dict = {}
                tmp_dict['to_table'] = to_table_name
                tmp_dict['from_to_columns'] = []
                tmp_dict['label'] = None
                for rel in relations:
                    if rel['to_table'] != to_table_name:
                        continue
                    tmp_dict['from_to_columns'].append((rel['from_column'], rel['to_column']))
                fk_t2t[from_table].append(tmp_dict)
        edge_schema_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH)
        if not self.anal_only:
            with open(f'{edge_schema_filepath}/{database_name}_t2t.jsonl', 'w') as f:
                json.dump(fk_t2t, f)

    def get_database_name(self, database_file):
        database_name = database_file.split(FILEPATH_SPLIT)[-1]
        return database_name

    def get_encoding(self, file):
        with open(file, 'rb') as f:
            raw_data = f.read()
        return chardet.detect(raw_data)['encoding']

    def get_database_table_schema_SPIDER(self, database_file):
        schemas = []
        exported_schema_path = os.path.join(database_file, EXPORTED_SCHEMA_PATH)
        exported_csv_path = os.path.join(database_file, EXPORTED_CSV_PATH)
        if os.path.exists(exported_schema_path) and len(os.listdir(exported_schema_path)) > 0:
            for item in os.listdir(exported_schema_path):
                if not item.endswith('.csv'):
                    continue
                table_name = item.split('.csv')[0]
                filepath = os.path.join(exported_schema_path, item)
                df = pd.read_csv(filepath, encoding=self.get_encoding(filepath))
                if {'name', 'type'}.issubset(set([c.lower() for c in df.columns])):
                    col_name = [c for c in df.columns if c.lower() == 'name'][0]
                    col_type = [c for c in df.columns if c.lower() == 'type'][0]
                    rows = [f'- {n} ({t})' for (n, t) in zip(df[col_name].astype(str), df[col_type].astype(str))]
                    table_description = 'Columns:\n' + '\n'.join(rows)
                else:
                    table_description = df.to_string(max_cols=None, max_rows=None)
                schemas.append((table_name, table_description))
        elif os.path.exists(exported_csv_path):
            for item in os.listdir(exported_csv_path):
                if not item.endswith('.csv') or item == 'sqlite_sequence.csv':
                    continue
                table_name = item.split('.csv')[0]
                filepath = os.path.join(exported_csv_path, item)
                df = pd.read_csv(filepath, nrows=0, encoding=self.get_encoding(filepath))
                cols = list(df.columns)
                table_description = 'Columns:\n' + '\n'.join([f'- {c}' for c in cols])
                schemas.append((table_name, table_description))
        return schemas

    def get_database_table_schema_BIRD(self, database_file):
        database_schema_path = os.path.join(database_file, EVERY_TABLE_DESC_PATH)
        schemas = []
        for item in os.listdir(database_schema_path):
            filepath = os.path.join(database_schema_path, item)
            with open(filepath, 'r', encoding=self.get_encoding(filepath)) as f:
                table_description = f.read()
            schemas.append((item.split('.csv')[0], table_description))
        return schemas

    def get_database_table_schema(self, database_file):
        database_schema_path = os.path.join(database_file, EVERY_TABLE_DESC_PATH)
        if os.path.exists(database_schema_path) and len(os.listdir(database_schema_path)) > 0:
            return self.get_database_table_schema_BIRD(database_file)
        return self.get_database_table_schema_SPIDER(database_file)

    def get_single_table_schema_BIRD(self, database_file, table_name):
        database_schema_path = os.path.join(database_file, EVERY_TABLE_DESC_PATH)
        table_name = Sqlite_Process.table_name_align_with_exported_schema(database_file, table_name)
        filepath = os.path.join(database_schema_path, f'{table_name}.csv')
        with open(filepath, 'r', encoding=self.get_encoding(filepath)) as f:
            table_description = f.read()
        return (table_name, table_description)

    def get_single_table_schema_SPIDER(self, database_file, table_name):
        exported_schema_path = os.path.join(database_file, EXPORTED_SCHEMA_PATH)
        exported_csv_path = os.path.join(database_file, EXPORTED_CSV_PATH)
        table_name = Sqlite_Process.table_name_align_with_exported_csv(database_file, table_name)
        schema_csv = os.path.join(exported_schema_path, f'{table_name}.csv')
        if os.path.exists(schema_csv):
            df = pd.read_csv(schema_csv, encoding=self.get_encoding(schema_csv))
            if {'name', 'type'}.issubset(set([c.lower() for c in df.columns])):
                col_name = [c for c in df.columns if c.lower() == 'name'][0]
                col_type = [c for c in df.columns if c.lower() == 'type'][0]
                rows = [f'- {n} ({t})' for (n, t) in zip(df[col_name].astype(str), df[col_type].astype(str))]
                desc = 'Columns:\n' + '\n'.join(rows)
            else:
                desc = df.to_string(max_cols=None, max_rows=None)
            return (table_name, desc)
        data_csv = os.path.join(exported_csv_path, f'{table_name}.csv')
        if os.path.exists(data_csv):
            df = pd.read_csv(data_csv, nrows=0, encoding=self.get_encoding(data_csv))
            cols = list(df.columns)
            desc = 'Columns:\n' + '\n'.join([f'- {c}' for c in cols])
            return (table_name, desc)
        return (table_name, '')

    def get_single_table_schema(self, database_file, table_name):
        database_schema_path = os.path.join(database_file, EVERY_TABLE_DESC_PATH)
        if os.path.exists(database_schema_path) and len(os.listdir(database_schema_path)) > 0:
            return self.get_single_table_schema_BIRD(database_file, table_name)
        return self.get_single_table_schema_SPIDER(database_file, table_name)

    def get_database_overview_schema_BIRD(self, database_overview_file, database_name):
        with open(database_overview_file, 'r') as f:
            overview = json.load(f)
        overview = [database for database in overview if database['db_id'] == database_name]
        assert len(overview) == 1
        return overview[0]

    def save_as_FK(self, table_name, fk_df, to_edge_fks):
        if table_name not in to_edge_fks:
            to_edge_fks[table_name] = []
        for row_idx in range(len(fk_df)):
            row = fk_df.iloc[row_idx]
            tmp_dict = {}
            tmp_dict['to_table'] = row['to_table']
            tmp_dict['from_column'] = row['from_column']
            tmp_dict['to_column'] = row['to_column']
            tmp_dict['label'] = None
            to_edge_fks[table_name].append(tmp_dict)

    def save_as_JoinTable(self, table_name, JoinTables):
        JoinTables.append(table_name)

    def save_as_notJoinTable(self, table_name, notJoinTables):
        notJoinTables.append(table_name)

    def llm_label_fk_edge(self, database_file, database_overview_file):
        database_name = self.get_database_name(database_file)
        overview_schema = self.get_database_overview_schema_BIRD(database_overview_file, database_name)
        table_description = self.get_database_table_schema(database_file)
        with open('Prompts/fk_edge.txt') as f:
            prompt = Template(f.read())
        edge_schema_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH)
        with open(f'{edge_schema_filepath}/{database_name}_t2t.jsonl', 'r') as f:
            fk_edge_info = f.read()
            fk_edge_info = json.loads(fk_edge_info)
        all_jointables = Sqlite_Process.get_all_jointables(database_file, self.llm_model_name)
        fk_edge_info = {k: [vv for vv in v if vv['to_table'] not in all_jointables] for (k, v) in fk_edge_info.items() if k not in all_jointables}
        prompt = prompt.render(database_name=database_name, database_overview_json=overview_schema, tables=table_description, fk_info=fk_edge_info)
        with open('tmp', 'w', encoding='utf-8') as f:
            f.write(prompt)
        for retry in range(5):
            try:
                (content, time) = run_llm(self.llm_model, prompt)
                content = extract_json(content)
                llm_labeled_fk_edge = json.loads(content)
                break
            except Exception as e:
                if retry < 5:
                    print(f'Attempt {retry + 1} failed: {e}, retrying...')
                else:
                    raise ValueError(e)
        print('llm_label:\n', llm_labeled_fk_edge)
        for (table_name, fk_edges) in fk_edge_info.items():
            llm_labeled_to_table_list = llm_labeled_fk_edge.get(table_name, [])
            for to_table_dict in fk_edge_info[table_name]:
                to_table_dict['label'] = [tmp_dict['label'] for tmp_dict in llm_labeled_to_table_list if tmp_dict['to_table'] == to_table_dict['to_table']][0]
                to_table_dict['label'] = [[edge_name, None] for edge_name in to_table_dict['label']]
        print('final fk_edge:')
        print(fk_edge_info)
        with open('Prompts/fk_edge_direction.txt', 'r') as f:
            prompt_template = Template(f.read())
        dirs = []
        for (table_name, fk_edges) in fk_edge_info.items():
            llm_labeled_to_table_list = llm_labeled_fk_edge.get(table_name, [])
            for to_table_dict in fk_edge_info[table_name]:
                for (edge_name, direction) in to_table_dict['label']:
                    dir1 = f"({table_name})-[:{edge_name}]->({to_table_dict['to_table']})"
                    dir2 = f"({to_table_dict['to_table']})-[:{edge_name}]->({table_name})"
                    dirs.append([dir1, dir2])
        llm_labeled_fk_edge_direction = []
        for (dir1, dir2) in dirs:
            prompt = prompt_template.render(database_name=database_name, database_overview_json=overview_schema, tables=table_description, dir1=dir1, dir2=dir2)
            with open('tmpp', 'w', encoding='utf-8') as f:
                f.write(prompt)
            content = run_llm(self.llm_model, prompt)
            if '1' in content[0]:
                llm_labeled_fk_edge_direction.append(1)
            elif '0' in content[0]:
                llm_labeled_fk_edge_direction.append(0)
            else:
                assert 1 == 0
        print(llm_labeled_fk_edge_direction)
        idx = 0
        for (table_name, fk_edges) in fk_edge_info.items():
            llm_labeled_to_table_list = llm_labeled_fk_edge.get(table_name, [])
            for to_table_dict in fk_edge_info[table_name]:
                for (label_idx, (edge_name, direction)) in enumerate(to_table_dict['label']):
                    to_table_dict['label'][label_idx] = [edge_name, llm_labeled_fk_edge_direction[idx]]
                    idx += 1
        print(fk_edge_info)
        if not self.anal_only:
            with open(f'{edge_schema_filepath}/{database_name}_t2t_{self.llm_model_name}_label.jsonl', 'w') as f:
                json.dump(fk_edge_info, f)

    def llm_classify_jointable(self, database_file, database_overview_file):
        edge_schema_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH)
        database_name = self.get_database_name(database_file)
        overview_schema = self.get_database_overview_schema_BIRD(database_overview_file, database_name)
        table_description = self.get_database_table_schema(database_file)
        with open(f'{edge_schema_filepath}/{database_name}_t2t.jsonl', 'r') as f:
            fk_edge_info = f.read()
        with open('Prompts/Jointable_classify.txt', 'r') as f:
            prompt_template = Template(f.read())
        with open(f'{edge_schema_filepath}/jointable.txt', 'r') as f:
            identified_jointables = ast.literal_eval(f.read())
        with open(f'{edge_schema_filepath}/notjointable.txt', 'r') as f:
            identified_notjointables = ast.literal_eval(f.read())
        all_tables = Sqlite_Process.get_all_tables(database_file)
        identified_jointables = [table.lower() for table in identified_jointables]
        identified_notjointables = [table.lower() for table in identified_notjointables]
        remaining_tables = [table for table in all_tables if table.lower() not in identified_jointables and table.lower() not in identified_notjointables]
        jointables_llm_label = []
        for remaining_table in remaining_tables:
            print(remaining_table)
            prompt = prompt_template.render(database_name=database_name, database_overview_json=overview_schema, tables=table_description, fk_info=fk_edge_info, table_to_pred=remaining_table)
            (content, time) = run_llm(prompt=prompt, model=self.llm_model)
            print(content.strip())
            if '1' in content:
                jointables_llm_label.append(remaining_table)
        if not self.anal_only:
            with open(f'{edge_schema_filepath}/jointable_{self.llm_model_name}_label.txt', 'w') as f:
                f.write(str(jointables_llm_label))

    def llm_jointable2edge(self, database_file, database_overview_file):
        edge_schema_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH)
        database_name = self.get_database_name(database_file)
        overview_schema = self.get_database_overview_schema_BIRD(database_overview_file, database_name)
        table_description = self.get_database_table_schema(database_file)
        with open(f'{edge_schema_filepath}/{database_name}_t2t.jsonl', 'r') as f:
            fk_edge_info = f.read()
        with open('Prompts/Jointable_edge.txt', 'r') as f:
            prompt_template = Template(f.read())
        with open(f'{edge_schema_filepath}/jointable.txt', 'r') as f:
            identified_jointables = ast.literal_eval(f.read())
        with open(f'{edge_schema_filepath}/jointable_{self.llm_model_name}_label.txt', 'r') as f:
            identified_jointables.extend(ast.literal_eval(f.read()))
        if len(identified_jointables) > 0:
            prompt = prompt_template.render(database_name=database_name, database_overview_json=overview_schema, tables=table_description, fk_info=fk_edge_info, jointables=identified_jointables)
            with open('tmpppp', 'w', encoding='utf-8') as f:
                f.write(prompt)
            (content, time) = run_llm(prompt=prompt, model=self.llm_model)
            content = extract_json(content)
            jointable_edge = json.loads(content)
            print(content.strip())
        else:
            jointable_edge = {}
        if not self.anal_only:
            with open(f'{edge_schema_filepath}/{database_name}_jointable_edge_{self.llm_model_name}.jsonl', 'w') as f:
                json.dump(jointable_edge, f)

    def embedding_align_column_and_tables_names_with_schema(self, database_file):
        edge_schema_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH)
        table_desc_filepath = os.path.join(database_file, EVERY_TABLE_DESC_PATH)
        exported_csv_filepath = os.path.join(database_file, EXPORTED_CSV_PATH)
        database_name = self.get_database_name(database_file)
        with open(f'{edge_schema_filepath}/{database_name}_jointable_edge_{self.llm_model_name}.jsonl', 'r') as f:
            jointable_edge_llm_json = json.load(f)

        def align_cols(cols, gt_cols, gt_cols_embeddings):
            res = []
            for col in cols:
                if col in gt_cols:
                    res.append(col)
                else:
                    col_embedding = get_embedding(col, model=Qwen_Embedding_MODEL, api_key=Qwen_API_KEY, base_url=Qwen_URL)
                    sims = [cosine_similarity(col_embedding, emb) for emb in gt_cols_embeddings]
                    print(col, 'change to', gt_cols[np.argmax(sims)])
                    res.append(gt_cols[np.argmax(sims)])
            return res

        def align_tables(table, gt_tables):
            if table in gt_tables:
                return table
            elif (table_lower := table.lower()) in (gt_tables_lower := [gt_table.lower() for gt_table in gt_tables]):
                return gt_tables[gt_tables_lower.index(table_lower)]
            else:
                table_embedding = get_embedding(table, model=Qwen_Embedding_MODEL, api_key=Qwen_API_KEY, base_url=Qwen_URL)
                gt_tables_embeddings = [get_embedding(gt_table, model=Qwen_Embedding_MODEL, api_key=Qwen_API_KEY, base_url=Qwen_URL) for gt_table in gt_tables]
                sims = [cosine_similarity(table_embedding, emb) for emb in gt_tables_embeddings]
                return gt_tables[np.argmax(sims)]
        tables = Sqlite_Process.get_all_tables(database_file)
        for (jointable_name, edges) in jointable_edge_llm_json.items():
            jointable_name = Sqlite_Process.table_name_align_with_exported_csv(database_file, jointable_name)
            gt_path = f'{exported_csv_filepath}/{jointable_name}.csv'
            gt = pd.read_csv(gt_path, encoding=self.get_encoding(gt_path))
            gt_cols = gt.columns.to_list()
            print(gt_cols)
            gt_cols_embeddings = [get_embedding(col, model=Qwen_Embedding_MODEL, api_key=Qwen_API_KEY, base_url=Qwen_URL) for col in gt_cols]
            for (edge_label, edge) in edges.items():
                for e in edge:
                    e['source']['filter_columns'] = align_cols(e['source']['filter_columns'], gt_cols, gt_cols_embeddings)
                    e['target']['filter_columns'] = align_cols(e['target']['filter_columns'], gt_cols, gt_cols_embeddings)
                    e['source']['Entity_type'] = align_tables(e['source']['Entity_type'], tables)
                    e['target']['Entity_type'] = align_tables(e['target']['Entity_type'], tables)
            jointable_col_llm = []
            for (edge_label, edge) in edges.items():
                for e in edge:
                    jointable_col_llm.extend(e['source']['filter_columns'])
                    jointable_col_llm.extend(e['target']['filter_columns'])
            jointable_col_llm = sorted(list(set(jointable_col_llm)))
            jointable_col_gt = sorted(gt_cols)
            assert len([a for a in jointable_col_llm if a not in jointable_col_gt]) == 0
        print(jointable_edge_llm_json)
        if not self.anal_only:
            with open(f'{edge_schema_filepath}/{database_name}_jointable_edge_{self.llm_model_name}_col_align.jsonl', 'w') as f:
                json.dump(jointable_edge_llm_json, f)

    def edge_canonicalization(self, database_file):
        edge_schema_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH)
        table_desc_filepath = os.path.join(database_file, EVERY_TABLE_DESC_PATH)
        exported_csv_filepath = os.path.join(database_file, EXPORTED_CSV_PATH)
        database_name = self.get_database_name(database_file)
        with open(f'{edge_schema_filepath}/{database_name}_jointable_edge_{self.llm_model_name}_col_align.jsonl', 'r') as f:
            jointable_edge_llm_json = json.load(f)
        with open(f'{edge_schema_filepath}/{database_name}_t2t_{self.llm_model_name}_label.jsonl', 'r') as f:
            fk_edge_llm_json = json.load(f)
        all_jointables = list(jointable_edge_llm_json.keys())
        fk_edge_llm_json = {k: v for (k, v) in fk_edge_llm_json.items() if k not in all_jointables}
        all_jt_edges = {}
        all_fk_edges = {}
        related_table = {}
        for (jointable_name, edges) in jointable_edge_llm_json.items():
            for (edge_label, edge) in edges.items():
                for e in edge:
                    source_node = e['source']['Entity_type']
                    source_filter_cols = e['source']['filter_columns']
                    target_node = e['target']['Entity_type']
                    target_filter_cols = e['target']['filter_columns']
                    tmp_dict = {'edge_label': edge_label, 'related_jt': jointable_name, 'source_filter_columns': source_filter_cols, 'target_filter_columns': target_filter_cols}
                    if (source_node, target_node) not in all_jt_edges:
                        all_jt_edges[source_node, target_node] = [tmp_dict]
                    elif tmp_dict not in all_jt_edges[source_node, target_node]:
                        all_jt_edges[source_node, target_node].append(tmp_dict)
                    related_table.setdefault((source_node, target_node), [])
                    if jointable_name not in related_table[source_node, target_node]:
                        related_table[source_node, target_node].append(jointable_name)
        for (from_table, to_tables) in fk_edge_llm_json.items():
            for table2 in to_tables:
                tot_edge_num = len(table2['label'])
                for i in range(tot_edge_num):
                    to_table = table2['to_table']
                    dir = table2['label'][i][1]
                    edge_label = table2['label'][i][0]
                    if dir == 1:
                        source_node = from_table
                        target_node = to_table
                        source_filter_cols = table2['from_to_columns'][i][0]
                        target_filter_cols = table2['from_to_columns'][i][1]
                    elif dir == 0:
                        source_node = to_table
                        target_node = from_table
                        source_filter_cols = table2['from_to_columns'][i][1]
                        target_filter_cols = table2['from_to_columns'][i][0]
                    tmp_dict = {'edge_label': edge_label, 'source_filter_columns': source_filter_cols, 'target_filter_columns': target_filter_cols}
                    if (source_node, target_node) not in all_fk_edges:
                        all_fk_edges[source_node, target_node] = [tmp_dict]
                    elif tmp_dict not in all_fk_edges[source_node, target_node]:
                        all_fk_edges[source_node, target_node].append(tmp_dict)
        with open('Prompts/merge_redundant_edges.txt', 'r') as f:
            prompt_template = Template(f.read())
        all_src_and_dst = list(set(list(all_fk_edges.keys()) + list(all_jt_edges.keys())))
        for src_and_dst in all_src_and_dst:
            src = src_and_dst[0]
            dst = src_and_dst[1]
            jt_edges = all_jt_edges.get(src_and_dst, [])
            fk_edges = all_fk_edges.get(src_and_dst, [])
            jt_edges = [{'edge_label': tmp_dict['edge_label']} for tmp_dict in jt_edges]
            fk_edges = [{'edge_label': tmp_dict['edge_label']} for tmp_dict in fk_edges]
            jt_edges = [dict(t) for t in {frozenset(d.items()) for d in jt_edges}]
            fk_edges = [dict(t) for t in {frozenset(d.items()) for d in fk_edges}]
            if len(jt_edges) + len(fk_edges) <= 1:
                continue
            if len(jt_edges) > 0 and len(fk_edges) > 0:
                print('asdffdas')
            src_desc = self.get_single_table_schema(database_file, src)[1]
            tgt_desc = self.get_single_table_schema(database_file, dst)[1]
            if (related_tables := related_table.get(src_and_dst, None)) is not None:
                related_desc = [self.get_single_table_schema(database_file, table) for table in related_tables]
            else:
                related_desc = []
            prompt = prompt_template.render(source=src, target=dst, jt_edges=jt_edges if len(jt_edges) > 0 else None, fk_edges=fk_edges if len(fk_edges) > 0 else None, source_desc=src_desc, target_desc=tgt_desc, other_nodes_desc=related_desc)
            (response, _) = run_llm(model=self.llm_model, prompt=prompt)
            print(src_and_dst)
            print(response)
            replace_json = json.loads(extract_json(response))
            new_jt_edges = all_jt_edges.get(src_and_dst, [])
            new_fk_edges = all_fk_edges.get(src_and_dst, [])
            for i in range(len(new_jt_edges)):
                tmp_edge = new_jt_edges[i]
                if tmp_edge['edge_label'] in replace_json:
                    tmp_edge['edge_label'] = replace_json[tmp_edge['edge_label']]
                    all_jt_edges[src_and_dst][i] = tmp_edge
            if len(new_jt_edges) > 0:
                all_jt_edges[src_and_dst] = list({json.dumps(d, sort_keys=True): d for d in all_jt_edges[src_and_dst]}.values())
            for i in range(len(new_fk_edges)):
                tmp_edge = new_fk_edges[i]
                if tmp_edge['edge_label'] in replace_json:
                    tmp_edge['edge_label'] = replace_json[tmp_edge['edge_label']]
                    all_fk_edges[src_and_dst][i] = tmp_edge
            if len(new_fk_edges) > 0:
                all_fk_edges[src_and_dst] = list({json.dumps(d, sort_keys=True): d for d in all_fk_edges[src_and_dst]}.values())
        final_edges = {'fk': all_fk_edges, 'jt': all_jt_edges}
        final_edges['fk'] = {str(k): v for (k, v) in final_edges['fk'].items()}
        final_edges['jt'] = {str(k): v for (k, v) in final_edges['jt'].items()}
        print(final_edges)
        if not self.anal_only:
            with open(f'{edge_schema_filepath}/all_edges_{self.llm_model_name}.jsonl', 'w') as f:
                json.dump(final_edges, f)

    def jointable_filter_cols_align_with_src_and_dst(self, database_file):
        all_edges_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH, f'all_edges_{self.llm_model_name}.jsonl')
        fk_relation_filepath = os.path.join(database_file, FK_RELATION_PATH)
        exported_csv_filepath = os.path.join(database_file, EXPORTED_CSV_PATH)
        edge_schema_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH)
        with open(all_edges_filepath, 'r') as f:
            all_edges = json.load(f)
            all_edges['fk'] = {ast.literal_eval(k): v for (k, v) in all_edges['fk'].items()}
            all_edges['jt'] = {ast.literal_eval(k): v for (k, v) in all_edges['jt'].items()}

        def align_with_fk_and_embedding(related_jt, fk_csv, gt_table, jt_filter_cols):
            fk_jt_gt = fk_csv[(fk_csv['from_table'] == related_jt) & (fk_csv['to_table'] == gt_table) & fk_csv['from_column'].apply(lambda x: x == jt_filter_cols)]
            if len(fk_jt_gt) == 1:
                return fk_jt_gt['to_column'].iloc[0]
            else:
                jt_cols_embeddings = [get_embedding(col, model=Qwen_Embedding_MODEL, api_key=Qwen_API_KEY, base_url=Qwen_URL) for col in jt_filter_cols]
                gt_table = Sqlite_Process.table_name_align_with_exported_csv(database_file, gt_table)
                gt_csv_path = f'{exported_csv_filepath}/{gt_table}.csv'
                gt_csv = pd.read_csv(gt_csv_path, encoding=self.get_encoding(gt_csv_path))
                gt_cols = gt_csv.columns.to_numpy()
                gt_cols_embeddings = [get_embedding(col, model=Qwen_Embedding_MODEL, api_key=Qwen_API_KEY, base_url=Qwen_URL) for col in gt_cols]
                sims = [[cosine_similarity(jt_col_embedding, gt_col_embdding) for gt_col_embdding in gt_cols_embeddings] for jt_col_embedding in jt_cols_embeddings]
                return gt_cols[np.argmax(sims, axis=1)].tolist()
        for ((src, tgt), edges) in all_edges['jt'].items():
            for edge in edges:
                related_jt = edge['related_jt']
                src_filter_cols = edge['source_filter_columns']
                tgt_filter_cols = edge['target_filter_columns']
                related_jt = Sqlite_Process.table_name_align_with_exported_csv(database_file, related_jt)
                fk_csv = pd.read_csv(os.path.join(fk_relation_filepath, f'{related_jt}_fk_relation.csv'))
                fk_csv['from_column'] = fk_csv['from_column'].apply(ast.literal_eval)
                fk_csv['to_column'] = fk_csv['to_column'].apply(ast.literal_eval)
                edge['source_filter_columns_align'] = align_with_fk_and_embedding(related_jt, fk_csv, src, src_filter_cols)
                edge['target_filter_columns_align'] = align_with_fk_and_embedding(related_jt, fk_csv, tgt, tgt_filter_cols)
        if not self.anal_only:
            all_edges['fk'] = {str(k): v for (k, v) in all_edges['fk'].items()}
            all_edges['jt'] = {str(k): v for (k, v) in all_edges['jt'].items()}
            with open(f'{edge_schema_filepath}/all_edges_{self.llm_model_name}_jt_align.jsonl', 'w') as f:
                json.dump(all_edges, f)

    def read_all_edge_file(self, database_file):
        edge_schema_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH)
        with open(f'{edge_schema_filepath}/all_edges_{self.llm_model_name}.jsonl', 'r') as f:
            data = json.load(f)
        print(data)

    def llm_jointable_missing_col_check(self, database_file, database_overview_file):
        edge_schema_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH)
        table_desc_filepath = os.path.join(database_file, EVERY_TABLE_DESC_PATH)
        database_name = self.get_database_name(database_file)
        with open(f'{edge_schema_filepath}/{database_name}_jointable_edge_{self.llm_model_name}.jsonl', 'r') as f:
            jointable_edge_llm_json = json.load(f)
        for (jointable_name, edges) in jointable_edge_llm_json.items():
            gt_path = f'{table_desc_filepath}/{jointable_name}.csv'
            gt = pd.read_csv(gt_path, encoding=self.get_encoding(gt_path))
            gt['column_name'] = gt['column_name'].fillna(gt['original_column_name'])
            jointable_col_llm = []
            for (edge_label, edge) in edges.items():
                for e in edge:
                    jointable_col_llm.extend(e['source']['filter_columns'])
                    jointable_col_llm.extend(e['target']['filter_columns'])
                    jointable_col_llm.extend(e['property_columns'])
            jointable_col_llm = sorted(list(set(jointable_col_llm)))
            jointable_col_gt = sorted(gt['column_name'].to_list())
            print([a for a in jointable_col_gt if a not in jointable_col_llm])
            assert jointable_col_llm == jointable_col_gt

    def number_edges_with_same_name_for_nebula(self, database_file):
        edge_schema_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH)
        all_edges_filepath = os.path.join(edge_schema_filepath, f'all_edges_{self.llm_model_name}_jt_align.jsonl')
        all_edges = {}
        with open(all_edges_filepath, 'r') as f:
            all_edges = json.load(f)
            all_edges['fk'] = {ast.literal_eval(k): v for (k, v) in all_edges['fk'].items()}
            all_edges['jt'] = {ast.literal_eval(k): v for (k, v) in all_edges['jt'].items()}
        from collections import defaultdict
        edge_label_counter = defaultdict(int)
        for edict in [all_edges['fk'], all_edges['jt']]:
            for edges in edict.values():
                for edge in edges:
                    label = edge['edge_label']
                    edge_label_counter[label] += 1
        label_seen = defaultdict(int)

        def rename_edges_with_indices(edges_dict):
            for edges in edges_dict.values():
                for edge in edges:
                    label = edge['edge_label']
                    if edge_label_counter[label] > 1:
                        label_seen[label] += 1
                        edge['edge_label'] = f'{label}_{label_seen[label]}'
        rename_edges_with_indices(all_edges['fk'])
        rename_edges_with_indices(all_edges['jt'])
        if not self.anal_only:
            all_edges['fk'] = {str(k): v for (k, v) in all_edges['fk'].items()}
            all_edges['jt'] = {str(k): v for (k, v) in all_edges['jt'].items()}
            with open(f'{edge_schema_filepath}/all_edges_{self.llm_model_name}_jt_align_nebula.jsonl', 'w') as f:
                json.dump(all_edges, f)

    @staticmethod
    def get_all_jointables(database_file, llm_model_name):
        database_jointable_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH, 'jointable.txt')
        database_jointable_llm_filepath = os.path.join(database_file, EDGE_SCHEMA_PATH, f'jointable_{llm_model_name}_label.txt')
        with open(database_jointable_filepath, 'r') as f:
            all_join_tables = f.read()
            all_join_tables = ast.literal_eval(all_join_tables)
        with open(database_jointable_llm_filepath, 'r') as f:
            tmp = f.read()
            all_join_tables.extend(ast.literal_eval(tmp))
        return all_join_tables

    @staticmethod
    def get_all_tables(database_file):
        exported_csv_filepath = os.path.join(database_file, EXPORTED_CSV_PATH)
        all_tables = []
        for item in os.listdir(f'{exported_csv_filepath}'):
            if item.endswith('.csv') and item != 'sqlite_sequence.csv':
                all_tables.append(item.split('.')[0])
        return all_tables

    @staticmethod
    def table_name_align_with_exported_csv(database_file, gt_table):
        exported_csv_filepath = os.path.join(database_file, EXPORTED_CSV_PATH)
        for item in os.listdir(f'{exported_csv_filepath}'):
            if gt_table.lower() == item.split('.csv')[0].lower():
                return item.split('.csv')[0]
        return gt_table

    @staticmethod
    def table_name_align_with_exported_schema(database_file, gt_table):
        exported_schema_filepath = os.path.join(database_file, EVERY_TABLE_DESC_PATH)
        for item in os.listdir(f'{exported_schema_filepath}'):
            if gt_table.lower() == item.split('.csv')[0].lower():
                return item.split('.csv')[0]
        return gt_table
if __name__ == '__main__':
    folder = SPIDER_TEST_folder
    database_overview_file = os.path.join(SPIDER_TEST_SQL_folder, 'test_tables.json')
    proc = Sqlite_Process(anal_only=False)
    if os.path.exists(f'{folder}/processed.txt'):
        with open(f'{folder}/processed.txt', 'r') as f:
            exists = ast.literal_eval(f.read())
    else:
        exists = []
    todo = ['cre_Drama_Workshop_Groups']
    todo = ['hospital_1', 'student_transcripts_tracking']
    for item in os.listdir(folder):
        filepath = os.path.join(folder, item)
        if os.path.isdir(filepath):
            print(filepath)
            if item in exists and item not in todo:
                continue
            database_file = os.path.join(filepath, item + '.sqlite')
            for _ in range(3):
                try:
                    proc.export_to_csv_with_pandas(database_file, filepath)
                    proc.export_to_csv_schema(database_file, filepath)
                    proc.get_foreign_and_primary_keys(database_file, filepath)
                    proc.fk2unique_table(filepath)
                    proc.llm_classify_jointable(filepath, database_overview_file)
                    proc.llm_label_fk_edge(filepath, database_overview_file)
                    proc.llm_jointable2edge(filepath, database_overview_file)
                    proc.embedding_align_column_and_tables_names_with_schema(filepath)
                    proc.edge_canonicalization(filepath)
                    proc.jointable_filter_cols_align_with_src_and_dst(filepath)
                    proc.number_edges_with_same_name_for_nebula(filepath)
                    break
                except Exception as e:
                    print(f'Error processing {item}: {e}')
                    import traceback
                    traceback.print_exc()
                    if _ == 2:
                        print(f'{item} failed after 3 retries; aborting.')
                        breakpoint()
            exists.append(item)
            with open(f'{folder}/processed.txt', 'w') as f:
                f.write(str(exists))
    print(exists)