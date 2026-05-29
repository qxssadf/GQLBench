import os
from openai import OpenAI
from google import genai
import openai
import regex
import time
import numpy as np
from functools import cache
import httpx

SILICON_API_KEY = '<YOUR_SILICON_API_KEY>'
SILICON_URL = '<YOUR_SILICON_BASE_URL>'
DEEPSEEK_API_KEY = '<YOUR_DEEPSEEK_API_KEY>'
DEEPSEEK_URL = '<YOUR_DEEPSEEK_BASE_URL>'
Qwen_API_KEY = '<YOUR_QWEN_API_KEY>'
Qwen_URL = '<YOUR_QWEN_BASE_URL>'
OPENAI_API_KEY = '<YOUR_OPENAI_API_KEY>'
OPENAI_URL = '<YOUR_OPENAI_BASE_URL>'
OPENAI_PROXY = ''
GEMINI_API_KEY = '<YOUR_GEMINI_API_KEY>'
GEMINI_URL = '<YOUR_GEMINI_BASE_URL>'

GPT_API_KEY = '<YOUR_GPT_API_KEY>'
GPT_URL = '<YOUR_GPT_BASE_URL>'

BASE_URL = SILICON_URL
API_KEY = SILICON_API_KEY
BASE_URL = DEEPSEEK_URL
API_KEY = DEEPSEEK_API_KEY

def run_llm(model,prompt,temperature=0,base_url=BASE_URL,use_json_output=False):
    start_time = time.time()

    api_key = API_KEY
    http_client = None

    if model == 'gemini-3-flash-preview':
        base_url = GPT_URL
        api_key = GPT_API_KEY
    elif model.startswith('gemini-'):
        base_url = GEMINI_URL
        api_key = GEMINI_API_KEY

        if OPENAI_PROXY:

            os.environ['HTTP_PROXY'] = OPENAI_PROXY
            os.environ['HTTPS_PROXY'] = OPENAI_PROXY
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")

    elif model == 'gpt-4o-mini':
        base_url = GPT_URL
        api_key = GPT_API_KEY

    elif model=='claude-sonnet-4.5':
        base_url = GPT_URL
        api_key = GPT_API_KEY
        model = 'claude-sonnet-4-5-20250929'
    elif model == 'qwen3-max':
        base_url = Qwen_URL
        api_key = Qwen_API_KEY

    client_kwargs = {
        "base_url": base_url,
        "api_key": api_key,
        "timeout": 600.0,
    }
    if http_client:
        client_kwargs["http_client"] = http_client

    if model != 'gemini-3-flash-preview' and 'gemini' in model:

        client = genai.Client(api_key=api_key)
    else:
        client = OpenAI(**client_kwargs)

    max_tokens = 512
    if model=='deepseek-chat':
        max_tokens = 8192
    if 'gpt-oss' in model:
        max_tokens = 8192
    if model == 'gemini-3-flash-preview':
        max_tokens = 8192
    params = {
        "model": model,
        "messages":[
                {"role": "user", "content": prompt}
            ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed":42,

    }
    if use_json_output:
        params["response_format"] = {"type": "json_object"}

    if 'qwen3-32b' in model or 'gpt-oss' in model or 'qwen3-8b' in model:
        params['extra_body']={"chat_template_kwargs": {"enable_thinking": False}}
    if 'gpt-oss' in model:
        params['stream'] = False
    if 'gemini' in model:
        del params['seed']

    retry = 5
    try_time = 0
    stop_reason = None

    while try_time < retry:
        try:
            if model != 'gemini-3-flash-preview' and 'gemini' in model:
                response = client.models.generate_content(
                    model=model, contents=prompt
                )
                return response.text, time.time()-start_time
            else:
                response = client.chat.completions.create(**params)

                print("***************")
                print(response.choices[0].finish_reason)
                print(response.usage)
                print(response.choices[0].message.content)
                print("*********************")

                if response.choices[0].finish_reason != 'stop':
                    stop_reason = response.choices[0].finish_reason
                    assert response.choices[0].finish_reason == 'stop'
                if response.choices[0].finish_reason=='length':
                    print(response.choices[0].message.content)

                response = response.choices[0].message.content

                assert response.strip() != ''
                return response, time.time() - start_time

        except Exception as e:
            msg = repr(e)
            if 'maximum context length' in msg:
                print("Context too long to process")
                return "maximum context length", time.time()-start_time
            if stop_reason=='length':
                print("LLM stuck in infinite repetition")

                return "llm get stuck repeating itself", time.time()-start_time

            if 'APITimeoutError' in str(type(e).__name__) or 'timeout' in msg.lower():

                print(f'!!!LLM timeout!!! (attempt {try_time + 1}/{retry})')
                print(repr(e))
                try_time += 1

                time.sleep(30)
            else:
                print('!!!LLM error!!!')
                print(repr(e))
                try_time += 1
                time.sleep(20)

    print(f'LLM failed after {retry} retries')
    return None,time.time()-start_time

def run_llm_local(model,prompt,temperature=0):
    pass

def extract_json(content):

    pattern = r'\{(?:[^{}]|(?R))*\}'
    matches = regex.findall(pattern, content)
    if len(matches)==0:
        matches = ['{}']
    return matches[-1]

@cache
def get_embedding(content,model,base_url,api_key):
    client = OpenAI(base_url=base_url,api_key=api_key)

    response = client.embeddings.create(
        input=content,
        model=model,
    )

    embedding_vector = response.data[0].embedding

    return embedding_vector

def cosine_similarity(vec1, vec2):
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)

    if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
        return 0.0
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

if __name__ == '__main__':
    embedding1 = get_embedding('PostId',"text-embedding-v3",Qwen_URL,Qwen_API_KEY)
    embedding2 = get_embedding('Post',"text-embedding-v3",Qwen_URL,Qwen_API_KEY)
    print(cosine_similarity(embedding1,embedding2))