import asyncio
import json
import argparse
import time
import os
from typing import List, Dict, Any
from openai import AsyncOpenAI
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

# --- Data Structures ---

class ModelConfig:
    def __init__(self, name: str, api_key: str, base_url: str, model: str):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

class BenchmarkResult:
    def __init__(self, test_id: str, model_name: str, iteration: int, duration: float, 
                 prompt_tokens: int, completion_tokens: int, cached_tokens: int,
                 content: str, error: str = None):
        self.test_id = test_id
        self.model_name = model_name
        self.iteration = iteration
        self.duration = duration
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cached_tokens = cached_tokens
        self.total_tokens = prompt_tokens + completion_tokens
        self.content = content
        self.error = error

# --- Async Execution ---

async def run_single_test(client: AsyncOpenAI, config: ModelConfig, test_case: Dict[str, Any], iteration: int) -> BenchmarkResult:
    start_time = time.time()
    try:
        response = await client.chat.completions.create(
            model=config.model,
            messages=test_case["messages"]
        )
        duration = time.time() - start_time
        
        usage = response.usage
        # Handle potential missing cache details
        cached = 0
        if hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
             if hasattr(usage.prompt_tokens_details, 'cached_tokens'):
                 cached = usage.prompt_tokens_details.cached_tokens
        
        return BenchmarkResult(
            test_id=test_case.get("id", "unknown"),
            model_name=config.name,
            iteration=iteration,
            duration=duration,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cached_tokens=cached,
            content=response.choices[0].message.content
        )
    except Exception as e:
        duration = time.time() - start_time
        return BenchmarkResult(
            test_id=test_case.get("id", "unknown"),
            model_name=config.name,
            iteration=iteration,
            duration=duration,
            prompt_tokens=0, completion_tokens=0, cached_tokens=0,
            content="",
            error=str(e)
        )

async def run_benchmark(test_cases: List[Dict], config1: ModelConfig, config2: ModelConfig):
    client1 = AsyncOpenAI(api_key=config1.api_key, base_url=config1.base_url)
    client2 = AsyncOpenAI(api_key=config2.api_key, base_url=config2.base_url)
    
    results = []
    total_requests = len(test_cases) * 2 * 2
    
    print(f"Running {len(test_cases)} tests x 2 iterations on 2 models ({total_requests} total requests)...")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task1 = progress.add_task("[cyan]Run 1 (Cache Warmup)...", total=len(test_cases) * 2)
        task2 = progress.add_task("[magenta]Run 2 (Cache Test)...", total=len(test_cases) * 2)
        
        # --- Iteration 1 ---
        tasks_1 = []
        for test in test_cases:
            tasks_1.append(asyncio.create_task(run_single_test(client1, config1, test, 1)))
            tasks_1.append(asyncio.create_task(run_single_test(client2, config2, test, 1)))
            
        for coro in asyncio.as_completed(tasks_1):
            result = await coro
            results.append(result)
            progress.advance(task1)
            
        # --- Iteration 2 ---
        # Wait a brief moment to ensure backend state settles if needed
        tasks_2 = []
        for test in test_cases:
            tasks_2.append(asyncio.create_task(run_single_test(client1, config1, test, 2)))
            tasks_2.append(asyncio.create_task(run_single_test(client2, config2, test, 2)))
            
        for coro in asyncio.as_completed(tasks_2):
            result = await coro
            results.append(result)
            progress.advance(task2)
            
    return results

# --- PDF Reporting ---

import html

def register_chinese_font():
    """Registers a Chinese font for ReportLab."""
    try:
        # Try common macOS Chinese font paths
        font_path = "/System/Library/Fonts/STHeiti Medium.ttc"
        if not os.path.exists(font_path):
             font_path = "/System/Library/Fonts/PingFang.ttc"
        
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
            return 'ChineseFont'
        else:
            print("Warning: Chinese font not found. PDF may have encoding issues.")
            return 'Helvetica'
    except Exception as e:
        print(f"Warning: Failed to register Chinese font: {e}")
        return 'Helvetica'

def clean_text(text: str) -> str:
    """Escapes HTML characters and replaces newlines with <br/> for ReportLab."""
    if not text:
        return ""
    # Escape HTML special characters (<, >, &, etc.)
    escaped = html.escape(text)
    # Replace newlines with <br/> tag that ReportLab understands
    return escaped.replace("\n", "<br/>")

def generate_pdf_report(results: List[BenchmarkResult], test_cases: List[Dict], output_path: str, config1: ModelConfig, config2: ModelConfig):
    font_name = register_chinese_font()
    
    doc = SimpleDocTemplate(output_path, pagesize=landscape(A4), topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Define Colors
    primary_color = colors.HexColor("#2c3e50") # Dark Blue
    accent_color = colors.HexColor("#3498db")  # Bright Blue
    light_bg = colors.HexColor("#ecf0f1")      # Light Grey
    header_text = colors.white
    
    # Custom Styles
    title_style = styles['Title']
    title_style.fontName = font_name
    title_style.textColor = primary_color
    
    h2_style = styles['Heading2']
    h2_style.fontName = font_name
    h2_style.textColor = primary_color
    h2_style.spaceBefore = 12
    h2_style.spaceAfter = 6
    
    h3_style = styles['Heading3']
    h3_style.fontName = font_name
    h3_style.textColor = accent_color
    
    normal_style = styles['Normal']
    normal_style.fontName = font_name
    normal_style.leading = 14
    
    # Title
    elements.append(Paragraph("LLM Benchmark Report (Dual Run)", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Config Summary
    elements.append(Paragraph("Configuration", h2_style))
    config_data = [
        ["Model Name", "API Base URL", "Model ID"],
        [config1.name, config1.base_url, config1.model],
        [config2.name, config2.base_url, config2.model]
    ]
    t_config = Table(config_data, colWidths=[2*inch, 4*inch, 3*inch])
    t_config.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), header_text),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
    ]))
    elements.append(t_config)
    elements.append(Spacer(1, 0.3*inch))
    
    # Aggregate Stats
    elements.append(Paragraph("Aggregate Statistics", h2_style))
    
    # Initialize stats structure
    stats = {
        config1.name: {1: {"input": 0, "output": 0, "cache": 0, "time": 0}, 2: {"input": 0, "output": 0, "cache": 0, "time": 0}, "errors": 0},
        config2.name: {1: {"input": 0, "output": 0, "cache": 0, "time": 0}, 2: {"input": 0, "output": 0, "cache": 0, "time": 0}, "errors": 0}
    }
    
    for r in results:
        s = stats[r.model_name]
        if r.error:
            s["errors"] += 1
        
        run_stats = s[r.iteration]
        run_stats["input"] += r.prompt_tokens
        run_stats["output"] += r.completion_tokens
        run_stats["cache"] += r.cached_tokens
        run_stats["time"] += r.duration

    agg_data = [
        ["Metric", config1.name, config2.name],
        ["Total Prompt Tokens (Run 1)", f"{stats[config1.name][1]['input']:,}", f"{stats[config2.name][1]['input']:,}"],
        ["Total Prompt Tokens (Run 2)", f"{stats[config1.name][2]['input']:,}", f"{stats[config2.name][2]['input']:,}"],
        ["Total Cached Tokens (Run 1)", f"{stats[config1.name][1]['cache']:,}", f"{stats[config2.name][1]['cache']:,}"],
        ["Total Cached Tokens (Run 2)", f"{stats[config1.name][2]['cache']:,}", f"{stats[config2.name][2]['cache']:,}"],
        ["Total Duration (Run 1) (s)", f"{stats[config1.name][1]['time']:.2f}", f"{stats[config2.name][1]['time']:.2f}"],
        ["Total Duration (Run 2) (s)", f"{stats[config1.name][2]['time']:.2f}", f"{stats[config2.name][2]['time']:.2f}"],
        ["Total Errors", str(stats[config1.name]['errors']), str(stats[config2.name]['errors'])]
    ]
    
    t_agg = Table(agg_data, colWidths=[3*inch, 3*inch, 3*inch])
    t_agg.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('BACKGROUND', (0, 0), (-1, 0), accent_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), header_text),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('ROWBACKGROUNDS', (1, 1), (-1, -1), [colors.white, light_bg]),
    ]))
    elements.append(t_agg)
    elements.append(Spacer(1, 0.3*inch))
    elements.append(PageBreak())

    # Detailed Results
    elements.append(Paragraph("Detailed Results", h2_style))
    
    # Map test cases by ID
    test_case_map = {t["id"]: t for t in test_cases}
    
    # Group results by test_id
    grouped_results = {}
    for r in results:
        if r.test_id not in grouped_results:
            grouped_results[r.test_id] = {config1.name: {}, config2.name: {}}
        grouped_results[r.test_id][r.model_name][r.iteration] = r
        
    # Custom style for code/content
    code_style = ParagraphStyle('Code', parent=normal_style, fontName=font_name, fontSize=9, leading=11)
    msg_style = ParagraphStyle('Msg', parent=normal_style, fontName=font_name, fontSize=9, leading=11, textColor=colors.black)
    
    for test_id, models_res in grouped_results.items():
        elements.append(Paragraph(f"Test Case: {test_id}", h3_style))
        
        # Display Original Messages
        if test_id in test_case_map:
            elements.append(Paragraph("<b>Input Messages:</b>", normal_style))
            elements.append(Spacer(1, 0.1*inch))
            for msg in test_case_map[test_id]["messages"]:
                role = msg["role"].upper()
                content = msg["content"]
                
                # Use Paragraphs instead of Table to allow splitting across pages
                elements.append(Paragraph(f"<b>[{role}]</b>", msg_style))
                elements.append(Paragraph(clean_text(content), msg_style))
                elements.append(Spacer(1, 0.1*inch))
            
            elements.append(Spacer(1, 0.1*inch))
        
        # Header
        # Columns: Metric | Model A (Run 1) | Model A (Run 2) | Model B (Run 1) | Model B (Run 2)
        header_data = [
            ["Metric", f"{config1.name}\n(Run 1)", f"{config1.name}\n(Run 2)", f"{config2.name}\n(Run 1)", f"{config2.name}\n(Run 2)"],
            
            ["Prompt", 
             models_res[config1.name][1].prompt_tokens, models_res[config1.name][2].prompt_tokens,
             models_res[config2.name][1].prompt_tokens, models_res[config2.name][2].prompt_tokens],
             
            ["Completion", 
             models_res[config1.name][1].completion_tokens, models_res[config1.name][2].completion_tokens,
             models_res[config2.name][1].completion_tokens, models_res[config2.name][2].completion_tokens],
             
            ["Cached", 
             models_res[config1.name][1].cached_tokens, models_res[config1.name][2].cached_tokens,
             models_res[config2.name][1].cached_tokens, models_res[config2.name][2].cached_tokens],
             
            ["Time (s)", 
             f"{models_res[config1.name][1].duration:.2f}", f"{models_res[config1.name][2].duration:.2f}",
             f"{models_res[config2.name][1].duration:.2f}", f"{models_res[config2.name][2].duration:.2f}"]
        ]
        
        t_detail = Table(header_data, colWidths=[1.5*inch, 1.8*inch, 1.8*inch, 1.8*inch, 1.8*inch])
        t_detail.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('BACKGROUND', (0, 0), (-1, 0), accent_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), header_text),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ]))
        elements.append(t_detail)
        elements.append(Spacer(1, 0.2*inch))
        
        # Content Comparison
        c1_r1_content = models_res[config1.name][1].error if models_res[config1.name][1].error else models_res[config1.name][1].content
        c2_r1_content = models_res[config2.name][1].error if models_res[config2.name][1].error else models_res[config2.name][1].content
        
        c1_r2_content = models_res[config1.name][2].error if models_res[config1.name][2].error else models_res[config1.name][2].content
        c2_r2_content = models_res[config2.name][2].error if models_res[config2.name][2].error else models_res[config2.name][2].content
        
        # Use Paragraphs for content comparison as well to avoid table row limits
        # Run 1
        elements.append(Paragraph(f"<b>{config1.name} Output (Run 1):</b>", normal_style))
        elements.append(Paragraph(clean_text(c1_r1_content), code_style))
        elements.append(Spacer(1, 0.1*inch))
        
        elements.append(Paragraph(f"<b>{config2.name} Output (Run 1):</b>", normal_style))
        elements.append(Paragraph(clean_text(c2_r1_content), code_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Run 2
        elements.append(Paragraph(f"<b>{config1.name} Output (Run 2):</b>", normal_style))
        elements.append(Paragraph(clean_text(c1_r2_content), code_style))
        elements.append(Spacer(1, 0.1*inch))
        
        elements.append(Paragraph(f"<b>{config2.name} Output (Run 2):</b>", normal_style))
        elements.append(Paragraph(clean_text(c2_r2_content), code_style))
        
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph("-" * 100, normal_style))
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph("-" * 100, normal_style))
        elements.append(Spacer(1, 0.2*inch))

    doc.build(elements)
    print(f"PDF Report generated at: {output_path}")

# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Benchmark two OpenAI-compatible models.")
    parser.add_argument("--input", required=True, help="Path to JSON input file containing test cases.")
    parser.add_argument("--output", default="benchmark_report.pdf", help="Path to output PDF report.")
    
    # Model 1 Config
    parser.add_argument("--m1-name", default="Model A", help="Name for Model 1")
    parser.add_argument("--m1-key", required=True, help="API Key for Model 1")
    parser.add_argument("--m1-base", required=True, help="Base URL for Model 1")
    parser.add_argument("--m1-model", required=True, help="Model ID for Model 1")
    
    # Model 2 Config
    parser.add_argument("--m2-name", default="Model B", help="Name for Model 2")
    parser.add_argument("--m2-key", required=True, help="API Key for Model 2")
    parser.add_argument("--m2-base", required=True, help="Base URL for Model 2")
    parser.add_argument("--m2-model", required=True, help="Model ID for Model 2")
    
    args = parser.parse_args()
    
    # Load Input
    with open(args.input, 'r', encoding='utf-8') as f:
        test_cases = json.load(f)
        
    config1 = ModelConfig(args.m1_name, args.m1_key, args.m1_base, args.m1_model)
    config2 = ModelConfig(args.m2_name, args.m2_key, args.m2_base, args.m2_model)
    
    # Run Benchmark
    results = asyncio.run(run_benchmark(test_cases, config1, config2))
    
    # Generate Report
    generate_pdf_report(results, test_cases, args.output, config1, config2)

if __name__ == "__main__":
    main()
