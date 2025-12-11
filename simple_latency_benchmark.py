import asyncio
import json
import argparse
import time
import os
from typing import List, Dict, Any, Optional

try:
    import boto3
except ImportError:
    boto3 = None

from openai import AsyncOpenAI, AsyncAzureOpenAI
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TaskProgressColumn

# --- Data Structures ---

class ModelConfig:
    def __init__(self, name: str, api_type: str, 
                 api_key: str = None, base_url: str = None, model: str = None, 
                 api_version: str = None,
                 region_name: str = None, access_key: str = None, secret_key: str = None):
        self.name = name
        self.api_type = api_type.lower()
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.api_version = api_version
        self.region_name = region_name
        self.access_key = access_key
        self.secret_key = secret_key

class LatencyResult:
    def __init__(self, test_id: str, model_name: str, 
                 ttft: float, second_token_time: float, 
                 total_duration: float, error: str = None):
        self.test_id = test_id
        self.model_name = model_name
        self.ttft = ttft
        self.second_token_time = second_token_time
        self.diff = second_token_time - ttft if second_token_time > 0 and ttft > 0 else 0
        self.total_duration = total_duration
        self.error = error

# --- Async Execution ---

async def run_latency_test(config: ModelConfig, test_case: Dict[str, Any]) -> LatencyResult:
    start_time = time.time()
    ttft = 0.0
    second_token_time = 0.0
    
    try:
        # --- Bedrock Logic ---
        if config.api_type == 'bedrock':
            if boto3 is None:
                raise ImportError("boto3 is required for Bedrock support. Install it via `pip install boto3`.")
            
            # Construct boto3 client (sync, but operations are fast enough for setup)
            # For streaming, we use invoke_model_with_response_stream.
            # Boto3 is synchronous by default. We can use `aioboto3` or run in executor.
            # For this simple script, sticking to sync boto3 for stream iteration might block the event loop slightly,
            # but usually it's network IO bound. Ideally we run this in a thread or use an async lib.
            # But the user asked for simple script. I will assume sync boto3 in a thread for 'async' feel or just block.
            # Actually, `invoke_model_with_response_stream` returns an event stream. Iterating it is sync.
            # To avoid blocking other tasks, we should really run the heavy lifting in run_in_executor.
            
            # However, for simplicity and since we only run 2-3 models, we can wrap the whole function in run_in_executor if needed,
            # OR just accept slight blocking. Let's try to do it cleanly.
            
            # We will use asyncio.to_thread for the blocking boto3 call
            def bedrock_worker():
                nonlocal ttft, second_token_time
                bedrock = boto3.client(
                    service_name='bedrock-runtime',
                    region_name=config.region_name,
                    aws_access_key_id=config.access_key,
                    aws_secret_access_key=config.secret_key
                )
                
                # Format messages for Claude
                # System message needs to be extracted
                messages = test_case["messages"]
                system_prompt = ""
                user_messages = []
                for msg in messages:
                    if msg['role'] == 'system':
                        system_prompt += msg['content'] + "\n"
                    else:
                        # Ensure content is string
                        user_messages.append({"role": msg['role'], "content": msg['content']})
                
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 100, # We only need 2 tokens
                    "messages": user_messages
                }
                if system_prompt:
                    body["system"] = system_prompt
                
                response = bedrock.invoke_model_with_response_stream(
                    modelId=config.model,
                    body=json.dumps(body)
                )
                
                stream = response.get('body')
                chunk_count = 0
                
                for event in stream:
                    chunk = event.get('chunk')
                    if chunk:
                        chunk_json = json.loads(chunk.get('bytes').decode())
                        # Claude 3 stream structure:
                        # type: message_start, content_block_start, content_block_delta ...
                        event_type = chunk_json.get('type')
                        
                        if event_type == 'content_block_delta':
                            current_time = time.time()
                            chunk_count += 1
                            if chunk_count == 1:
                                ttft = current_time - start_time
                            elif chunk_count == 2:
                                second_token_time = current_time - start_time
                                break # Stop reading stream
                                
            await asyncio.to_thread(bedrock_worker)
            
        # --- OpenAI / Azure Logic ---
        else:
            if config.api_type == 'azure':
                client = AsyncAzureOpenAI(
                    api_key=config.api_key,
                    azure_endpoint=config.base_url,
                    api_version=config.api_version
                )
            else:
                client = AsyncOpenAI(
                    api_key=config.api_key,
                    base_url=config.base_url
                )

            stream = await client.chat.completions.create(
                model=config.model,
                messages=test_case["messages"],
                stream=True
            )
            # print(config.model, config.base_url, config.api_key)
            chunk_count = 0
            # print(config.base_url)
            async for chunk in stream:
                # if chunk.choices:
                #     print(chunk.choices[0].delta.content, flush=True, end="")
                current_time = time.time()
                # Count any chunk that comes back as activity
                chunk_count += 1
                
                if chunk_count == 1:
                    ttft = current_time - start_time
                elif chunk_count == 2:
                    second_token_time = current_time - start_time
                    # await stream.close()
                    # break
        
        total_duration = time.time() - start_time
        return LatencyResult(
            test_id=test_case.get("id", "unknown"),
            model_name=config.name,
            ttft=ttft,
            second_token_time=second_token_time,
            total_duration=total_duration
        )

    except Exception as e:
        import traceback
        print("error: ", config.base_url, traceback.format_exc())
        total_duration = time.time() - start_time
        return LatencyResult(
            test_id=test_case.get("id", "unknown"),
            model_name=config.name,
            ttft=0, second_token_time=0,
            total_duration=total_duration,
            error=str(e)
        )

async def benchmark_suite(test_cases: List[Dict], configs: List[ModelConfig]):
    console = Console()
    results: List[LatencyResult] = []
    
    table = Table(title="Latency Comparison (Seconds)")
    table.add_column("Test ID", style="cyan", no_wrap=True)
    table.add_column("Model", style="magenta")
    table.add_column("TTFT", justify="right", style="green")
    table.add_column("2nd Token", justify="right", style="yellow")
    table.add_column("Diff", justify="right", style="blue")
    table.add_column("Error", style="red")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[bold green]Running Latency Tests...", total=len(test_cases))
        
        for test in test_cases:
            tasks = [asyncio.create_task(run_latency_test(cfg, test)) for cfg in configs]
            
            case_results = await asyncio.gather(*tasks)
            
            for r in case_results:
                table.add_row(
                    str(r.test_id),
                    r.model_name,
                    f"{r.ttft:.4f}",
                    f"{r.second_token_time:.4f}",
                    f"{r.diff:.4f}",
                    r.error if r.error else ""
                )
            
            results.extend(case_results)
            progress.advance(task)
            
    console.print(table)
    
    # Calculate Averages
    summary = Table(title="Average Latency Summary")
    summary.add_column("Model", style="magenta")
    summary.add_column("Avg TTFT", justify="right", style="green")
    summary.add_column("Avg 2nd Token", justify="right", style="yellow")
    summary.add_column("Avg Diff", justify="right", style="blue")
    
    for cfg in configs:
        model_results = [r for r in results if r.model_name == cfg.name and not r.error]
        if not model_results:
            summary.add_row(cfg.name, "N/A", "N/A", "N/A")
            continue
            
        avg_ttft = sum(r.ttft for r in model_results) / len(model_results)
        avg_2nd = sum(r.second_token_time for r in model_results) / len(model_results)
        avg_diff = sum(r.diff for r in model_results) / len(model_results)
        
        summary.add_row(cfg.name, f"{avg_ttft:.4f}", f"{avg_2nd:.4f}", f"{avg_diff:.4f}")
    
    console.print(summary)


def safe_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    model_count = 4
    for i in range(1, model_count + 1):
        p = f"m{i}"
        parser.add_argument(f"--{p}-type", choices=['openai', 'azure', 'bedrock'], default=None)
        parser.add_argument(f"--{p}-name", default=f"Model {i}")
        parser.add_argument(f"--{p}-key")
        parser.add_argument(f"--{p}-base")
        parser.add_argument(f"--{p}-model")
        parser.add_argument(f"--{p}-version")
        parser.add_argument(f"--{p}-region")
        parser.add_argument(f"--{p}-access-key")
        parser.add_argument(f"--{p}-secret-key")

    args = parser.parse_args()
    
    with open(args.input, 'r', encoding='utf-8') as f:
        test_cases = json.load(f)

    configs = []
    for i in range(1, model_count + 1):
        p = f"m{i}"
        m_model = getattr(args, f"{p}_model")
        if not m_model:
            continue # Skip if no model ID provided
            
        # Defaults for type
        m_type = getattr(args, f"{p}_type")
        if not m_type: 
            m_type = 'openai' # Default
            
        cfg = ModelConfig(
            name=getattr(args, f"{p}_name"),
            api_type=m_type,
            api_key=getattr(args, f"{p}_key"),
            base_url=getattr(args, f"{p}_base"),
            model=m_model,
            api_version=getattr(args, f"{p}_version"),
            region_name=getattr(args, f"{p}_region"),
            access_key=getattr(args, f"{p}_access_key"),
            secret_key=getattr(args, f"{p}_secret_key")
        )
        configs.append(cfg)
        
    if not configs:
        print("No models configured. Provide at least --m1-model.")
        return

    print(f"Starting Latency Benchmark with {len(configs)} models...")
    asyncio.run(benchmark_suite(test_cases, configs))

if __name__ == "__main__":
    safe_main()
