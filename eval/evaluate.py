from fileinput import filename
import time
import execute_accuracy
import argparse
import json
import yaml
from typing import Dict, List, Tuple, Optional
from tqdm import tqdm
import sys 
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import requests
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from LLM_Utils import run_llm
from execute_accuracy import execution_accuracy

_model_cache = {}
_model_lock = Lock()

CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCHMARK_DATA_DIR = os.path.join(CODE_DIR, 'benchmark_data_new')
NL_GQL_DIR = os.path.join(BENCHMARK_DATA_DIR, 'nl_gql')
SCHEMAS_DIR = os.path.join(BENCHMARK_DATA_DIR, 'schemas')

_schema_cache_cypher = {}
_schema_cache_nebula = {}
_lora_config = None

def load_lora_config():
    global _lora_config
    if _lora_config is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lora', 'config.yaml')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                _lora_config = yaml.safe_load(f)
        else:
            _lora_config = {}
    return _lora_config

def run_llm_with_peft(model_name: str, prompt: str, temperature: float = 0):
    global _model_cache
    
    config = load_lora_config()
    model_config = config['models'][model_name]
    base_model_path = model_config.get('base_model_path')
    lora_path = model_config.get('lora_path')
    
    cache_key = f"{base_model_path}:{lora_path}"
    if cache_key in _model_cache:
        model, tokenizer = _model_cache[cache_key]
    else:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
        import torch
        
        tokenizer = AutoTokenizer.from_pretrained(lora_path, trust_remote_code=True)
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_path,
            device_map="auto",
            trust_remote_code=True,
            torch_dtype=torch.bfloat16
        )
        model = PeftModel.from_pretrained(base_model, lora_path)
        model.eval()
        
        with _model_lock:
            _model_cache[cache_key] = (model, tokenizer)
    
    import torch
    
    if 'gpt-oss' in model_name:
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        input_length = inputs['input_ids'].shape[1]
    else:
        messages = [{"role": "user", "content": prompt}]
        if hasattr(tokenizer, 'apply_chat_template'):
            formatted = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            inputs = tokenizer(formatted, return_tensors="pt").to(model.device)
        else:
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        input_length = inputs['input_ids'].shape[1]
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=2048,
            temperature=temperature if temperature > 0 else None,
            do_sample=temperature > 0,
            pad_token_id=tokenizer.eos_token_id if tokenizer.pad_token_id is None else tokenizer.pad_token_id
        )
    
    response = tokenizer.decode(outputs[0][input_length:], skip_special_tokens=True)
    return response.strip()


def get_schema(db_name: str, source: str,dataset:str,gql_dialect:str) -> Optional[Dict]:
    cache_key = f"{source}_{db_name}"
    if gql_dialect=='cypher' and cache_key in _schema_cache_cypher:
        return _schema_cache_cypher[cache_key]
    elif gql_dialect=='nebula' and cache_key in _schema_cache_nebula:
        return _schema_cache_nebula[cache_key]
    
    schema_file = os.path.join(SCHEMAS_DIR, dataset, f'all_schemas_{gql_dialect}.json')
    
    with open(schema_file, 'r', encoding='utf-8') as f:
        schemas = json.load(f)
    schemas = [schema for schema in schemas if schema.get('source') == source]
    for schema in schemas:
        if schema.get('name') == db_name:
            if gql_dialect=='cypher':
                _schema_cache_cypher[cache_key] = {k:v for k,v in schema.items() if k != 'source'}
                return _schema_cache_cypher[cache_key]
            elif gql_dialect=='nebula':
                _schema_cache_nebula[cache_key] = {k:v for k,v in schema.items() if k != 'source'}
                return _schema_cache_nebula[cache_key]

    breakpoint()
    return None


def load_train_data() -> List[Tuple[str, str, str, str, str, str]]:
    train_file = os.path.join(NL_GQL_DIR, 'train.json')
    
    with open(train_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    result = []
    for item in data:
        nl_query = item.get('nl_query', '').strip()
        target_gql = item.get('gql_statement', '').strip()
        db_name = item.get('db_id', '')
        gql_dialect = item.get('gql_dialect', 'cypher')
        source = item.get('source', '')
        evidence = item.get('evidence', '')
        result.append((nl_query, target_gql, db_name, gql_dialect,source,evidence))
    
    return result


def load_test_data() -> List[Tuple[str, str, str, str, str, str]]:
    test_file = os.path.join(NL_GQL_DIR, 'test.json')
    
    with open(test_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    result = []
    for item in data:
        nl_query = item.get('nl_query', '').strip()
        target_gql = item.get('gql_statement', '').strip()
        db_name = item.get('db_id', '')
        gql_dialect = item.get('gql_dialect', 'cypher')
        source = item.get('source','')
        evidence = item.get('evidence', '')
        result.append((nl_query, target_gql, db_name, gql_dialect,source,evidence))
    
    return result 


def load_data(dataset:str):
    if dataset == 'train':
        return load_train_data()
    elif dataset == 'test':
        return load_test_data()
    else:
        raise ValueError(f"Invalid dataset: {dataset}")
        
def zero_shot_prompt(nl_query:str,schema:Dict,gql_dialect:str,evidence:str)->str:
    if gql_dialect == 'nebula':
        gql_dialect_str = "an ISO GQL graph database query for NebulaGraph 5.x"
    elif gql_dialect == 'cypher':
        gql_dialect_str = 'a cypher graph database query'
    else:
        raise ValueError("gql_dialect should be nebula or cypher")

    return f""" You are a graph database expert. I will show you a natural language query and a graph database schema. Your task is to generate {gql_dialect_str} that is semantically equivalent to the natural language query.
Natural Language Query: {nl_query}
Graph Database Schema: {schema}
Please only return the query in plain text format but not code block format, do not include any other content.
""" + (f"Evidence: {evidence}" if evidence else "")


def eval(nl_query:str,target_gql:str,db_name:str,gql_dialect:str,metric:str,baseline:str,source:str,dataset:str,evidence:str,model_name:str,vllm_port:str):
    schema = get_schema(db_name,source,dataset,gql_dialect)
    if baseline == 'zero_shot':
        prompt = zero_shot_prompt(nl_query=nl_query,schema=schema,gql_dialect=gql_dialect,evidence=evidence)
        if model_name in ['deepseek-chat','qwen3-max','gpt-4o-mini','claude-sonnet-4.5','gemini-3-flash-preview']:
            response, _ = run_llm(model=model_name, prompt=prompt)
            response = response.strip()
        else:
            config = load_lora_config()
            if model_name in config.get('models', {}):
                model_config = config['models'][model_name]
                
                if model_name == 'gpt-oss-20b_lora':
                    try:
                        with open("./lora/saves/GPT-OSS-20B-Thinking/lora/eval_2025-12-23-10-03-52_lora/generated_predictions.jsonl",'r') as f:
                            predict_data = [json.loads(line) for line in f]
                        response_list = [item['predict'] for item in predict_data if nl_query in item['prompt'] and gql_dialect in item['prompt'].lower()]
                        assert len(response_list) == 1
                        response = response_list[0]
                        
                    except Exception as e:
                        print(f"PEFT 推理失败: {e}")
                        response = ""
                else:
                    vllm_base_url = f"http://localhost:{vllm_port}/v1"
                    response, _ = run_llm(model=model_name, prompt=prompt, base_url=vllm_base_url)
                    if response:
                        response = response.strip()
                    else:
                        response = ""
            else:
                response, _ = run_llm(model=model_name, prompt=prompt)
                if response:
                    response = response.strip()
                else:
                    response = ""

    if metric == 'execution_accuracy':
        is_success, error_message = execution_accuracy(response,target_gql,db_name,gql_dialect,source)
        return prompt, response, is_success, error_message,target_gql,db_name,gql_dialect,source
    else:
        raise ValueError(f"Invalid metric: {metric}")

def prepare_train_data():
    train_data = load_train_data()
    result = []
    
    for nl_query,target_gql,db_name,gql_dialect,source,evidence in train_data:
        schema = get_schema(db_name,source,dataset='train',gql_dialect=gql_dialect)
        prompt = zero_shot_prompt(nl_query=nl_query,schema=schema,gql_dialect=gql_dialect,evidence=evidence)
        
        result.append({
            'instruction': "",
            'input': prompt,
            'output': target_gql
        })
    
    os.makedirs('lora',exist_ok=True)
    with open('lora/llamafactory_train_data.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

def prepare_test_data():
    test_data = load_test_data()
    result = []
    
    for nl_query,target_gql,db_name,gql_dialect,source,evidence in test_data:
        schema = get_schema(db_name,source,dataset='test',gql_dialect=gql_dialect)
        prompt = zero_shot_prompt(nl_query=nl_query,schema=schema,gql_dialect=gql_dialect,evidence=evidence)
        
        result.append({
            'instruction': "",
            'input': prompt,
            'output': target_gql
        })
    
    os.makedirs('lora',exist_ok=True)
    with open('lora/llamafactory_test_data.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

def main(dataset:str,metric:str,baseline:str,model_name:str):
    data = load_data(dataset)
    res_directory = f'res_{model_name}'
    os.makedirs(res_directory,exist_ok=True)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    res_filaname = f'{res_directory}/{dataset}_{metric}_{baseline}_{timestamp}.jsonl'

    import random
    data = [tmp for tmp in data if tmp[-3] == 'nebula']

    for nl_query,target_gql,db_name,gql_dialect,source,evidence in tqdm(data):
        prompt, response, is_success, error_message,target_gql,db_name,gql_dialect,source = eval(nl_query,target_gql,db_name,gql_dialect,metric,baseline,source,dataset,evidence,model_name)
        result = {
            'prompt': prompt,
            'response': response,
            'is_success': is_success,
            'error_message': error_message,
            'target_gql': target_gql,
            'db_name': db_name,
            'gql_dialect': gql_dialect,
            'source': source
        }
        with open(res_filaname,'a',encoding='utf-8') as f:
            f.write(json.dumps(result,ensure_ascii=False) + '\n')


def main_concurrent(dataset:str,metric:str,baseline:str,gql_dialect:str,vllm_port:str, source_:str=None,max_workers:int=4,model_name:str='deepseek-chat'):
    data = load_data(dataset)

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    res_directory = f'res_{model_name}_new'
    os.makedirs(res_directory,exist_ok=True)
    res_filename = f'{res_directory}/{dataset}_{metric}_{baseline}_{timestamp}.jsonl'
    res_filename = f'{res_directory}/{dataset}_{metric}_{baseline}_cypher_all.jsonl'
    res_filename = f'{res_directory}/{dataset}_{metric}_{baseline}_{gql_dialect}_all_new_prompt_{timestamp}.jsonl'
    res_filename = f'{res_directory}/{dataset}_{metric}_{baseline}_{gql_dialect}_all_new_prompt.jsonl'

    if os.path.exists(res_filename):
        with open(res_filename,'r') as f:
            res_hist = [json.loads(line) for line in f]
            prompt_hist = [single_hist['prompt'] for single_hist in res_hist]
    else:
        res_hist = []
        prompt_hist = []
    import random
    if gql_dialect == 'nebula' and source_ is None:
        data = [tmp for tmp in data if tmp[-3] == gql_dialect ]
    elif gql_dialect == 'nebula' and source_ is not None:
        data = [tmp for tmp in data if tmp[-3] == gql_dialect and tmp[-2] == source_]
    elif gql_dialect=='cypher':
        data = [tmp for tmp in data if tmp[-3] == 'cypher' and tmp[-2] == source_]

    data = [item for item in data if not any([item[0] in single_prompt and item[3] in single_prompt.lower() for single_prompt in prompt_hist]) ]

    print("len(data):",len(data))
    file_lock = Lock()
    
    def process_item(item):
        response = None
        nl_query, target_gql, db_name, gql_dialect, source, evidence = item
        try:
            prompt, response, is_success, error_message, target_gql, db_name, gql_dialect, source = eval(
                nl_query, target_gql, db_name, gql_dialect, metric, baseline, source, dataset, evidence, model_name,vllm_port=vllm_port
            )
            if response == "maximum context length":
                error_message = "maximum context length"
            elif response == "llm get stuck repeating itself":
                error_message = response
            elif "query timeout" in response or ("TransactionTimedOutClientConfiguration" in response and gql_dialect=='cypher') or ("RPC error: Deadline Exceeded" in response and gql_dialect=='nebula'):
                error_message = response
            result = {
                'prompt': prompt,
                'response': response,
                'is_success': is_success,
                'error_message': error_message,
                'target_gql': target_gql,
                'db_name': db_name,
                'gql_dialect': gql_dialect,
                'source': source
            }
            with file_lock:
                with open(res_filename, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(result, ensure_ascii=False) + '\n')
            return True, None, response
        except KeyError as e:
            return False, f"KeyError: {str(e)}, item={item}", response
        except AttributeError as e:
            return False, f"AttributeError: {str(e)}, item={item}", response
        except Exception as e:
            import traceback
            error_detail = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            return False, f"Error processing {db_name}: {error_detail}", response
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_item, item): item for item in data}
        
        completed = 0
        failed = 0
        with tqdm(total=len(data), desc="处理中") as pbar:
            for future in as_completed(futures):
                success, error, response = future.result()
                if success:
                    completed += 1
                else:
                    failed += 1
                    failed_item = futures[future]
                    nl_query, target_gql, db_name, gql_dialect, source, evidence = failed_item
                    
                    if error:
                        print(f"\n处理失败 [db_name={db_name}]: {error}")
                    
                    fail_filename = res_filename.replace('.jsonl','_failed.jsonl')
                    fail_info = {
                        'nl_query': nl_query,
                        'target_gql': target_gql,
                        'db_name': db_name,
                        'gql_dialect': gql_dialect,
                        'source': source,
                        'evidence': evidence,
                        'error': error if error else "Unknown error",
                        'response': response
                    }
                    with open(fail_filename,'a', encoding='utf-8') as f:
                        f.write(json.dumps(fail_info, ensure_ascii=False) + '\n')
                pbar.update(1)
        
        print(f"\n完成: {completed} 成功, {failed} 失败")



if __name__ == "__main__":
    args = argparse.ArgumentParser()
    
    args.add_argument("--dataset", type=str, default='test')
    args.add_argument("--gql_dialect", type=str, default='cypher')
    args.add_argument("--metric", type=str, default='execution_accuracy')
    args.add_argument("--baseline", type=str, default='zero_shot')
    args.add_argument("--concurrent", action='store_true', help='使用并发版本',default=True)
    args.add_argument("--max_workers", type=int, default=8, help='并发线程数（仅并发模式）')
    args.add_argument("--model_name", type=str, default='deepseek-chat', help='模型名称')
    args.add_argument("--prepare_train_data", action='store_true', help='准备训练数据')
    args.add_argument("--source_", type=str)
    args.add_argument('--vllm_port',type=str)
    args = args.parse_args()

    if args.prepare_train_data:
        prepare_train_data()
        prepare_test_data()
        exit()

    if args.gql_dialect=='cypher' and args.source_ is None:
        args.error("--source_ is required when --gql_dialect=cypher")
        
    if args.concurrent:
        main_concurrent(dataset=args.dataset, metric=args.metric, baseline=args.baseline, gql_dialect=args.gql_dialect,vllm_port=args.vllm_port,source_=args.source_, max_workers=args.max_workers, model_name=args.model_name)
    else:
        main(args.dataset, args.metric, args.baseline)
