import os
import argparse
from typing import Optional
from .document import DocumentProcessor
from .llm import LLMFactory
from .workflow import TranslationWorkflow
from .report import ReportGenerator
from .utils import setup_logging
from loguru import logger

class TranslationSDK:
    def __init__(self, 
                 translation_config: dict,
                 evaluation_config: dict,
                 optimization_config: dict,
                 concurrency_config: dict = None):
        
        self.translator = LLMFactory.create(**translation_config)
        self.evaluator = LLMFactory.create(**evaluation_config)
        self.optimizer = LLMFactory.create(**optimization_config)
        
        self.workflow = TranslationWorkflow(self.translator, self.evaluator, self.optimizer, concurrency_config)

    def translate_document(self, input_path: str, output_dir: str, source_lang: str = "auto", target_lang: str = "Chinese", progress_callback=None):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        # 1. Load Document
        logger.info(f"Loading document: {input_path}")
        doc_processor = DocumentProcessor(input_path)
        segments = doc_processor.extract_segments()
        
        # 2. Run Workflow
        logger.info(f"Starting translation workflow (Source: {source_lang}, Target: {target_lang})...")
        results, usage_report = self.workflow.run(segments, source_lang=source_lang, target_lang=target_lang, progress_callback=progress_callback)
        
        # 3. Apply Translations
        final_translations = {r.segment_id: r.final_translation for r in results}
        
        # Prepare translations with scores for bilingual doc
        bilingual_translations = {}
        for r in results:
            score = 0
            if r.selected_model == "C (Optimized)" and r.eval_c:
                score = r.eval_c.total_score
            elif r.eval_a:
                score = r.eval_a.total_score
            
            bilingual_translations[r.segment_id] = {
                "text": r.final_translation,
                "score": score
            }

        # Output paths
        trans_path = os.path.join(output_dir, f"{base_name}_translated.docx")
        bilingual_path = os.path.join(output_dir, f"{base_name}_bilingual.docx")
        report_excel = os.path.join(output_dir, f"{base_name}_report.xlsx")
        report_pdf = os.path.join(output_dir, f"{base_name}_report.pdf")
        usage_path = os.path.join(output_dir, f"{base_name}_usage.json")
        
        logger.info(f"Saving translated document to {trans_path}")
        doc_processor.apply_translations(final_translations)
        doc_processor.save(trans_path)
        
        logger.info(f"Saving bilingual document to {bilingual_path}")
        doc_processor.save_bilingual(bilingual_path, bilingual_translations)
        
        # Save usage report
        import json
        with open(usage_path, "w") as f:
            json.dump(usage_report, f, indent=2)
        print("\nToken Usage Report:")
        print(json.dumps(usage_report, indent=2))
        
        # Save model mapping (Anonymization)
        model_mapping = {
            "Model A": getattr(self.translator, "model", "Unknown"),
            "Model B": getattr(self.evaluator, "model", "Unknown"),
            "Model C": getattr(self.optimizer, "model", "Unknown")
        }
        mapping_path = os.path.join(output_dir, f"{base_name}_model_mapping.json")
        with open(mapping_path, "w") as f:
            json.dump(model_mapping, f, indent=2)
        logger.info(f"Saved model mapping to {mapping_path}")

        # Save full workflow results
        results_path = os.path.join(output_dir, f"{base_name}_results.json")
        
        # Helper to convert dataclasses to dict
        from dataclasses import asdict
        results_data = [asdict(r) for r in results]
        
        with open(results_path, "w", encoding='utf-8') as f:
            json.dump(results_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved full results to {results_path}")
        
        # 4. Generate Reports
        logger.info("Generating reports...")
        reporter = ReportGenerator(results)
        reporter.generate_excel(report_excel)
        
        metadata = {
            "filename": os.path.basename(input_path),
            "source_lang": source_lang,
            "target_lang": target_lang,
            "task_id": "161" # Placeholder or generate random
        }
        reporter.generate_pdf(report_pdf, metadata=metadata)
        
        logger.info("Translation completed successfully.")

def launch_ui():
    """Launch the Gradio User Interface."""
    from .ui import create_interface
    demo = create_interface()
    demo.launch()

def main():
    parser = argparse.ArgumentParser(description="Word Document Translation SDK")
    parser.add_argument("input_file", nargs='?', help="Path to the input .docx file")
    parser.add_argument("--output-dir", default="output", help="Directory to save outputs")
    parser.add_argument("--gui", action="store_true", help="Launch Gradio GUI")
    parser.add_argument("--provider", default="mock", help="Default LLM provider (openai, mock)")
    parser.add_argument("--api-key", help="Default API Key")
    parser.add_argument("--base-url", help="Default Base URL (or Azure Endpoint)")
    parser.add_argument("--api-version", help="Azure API Version (e.g., 2023-05-15)")
    parser.add_argument("--model-a", default="gpt-3.5-turbo", help="Model for translation")
    parser.add_argument("--model-b", default="gpt-4", help="Model for evaluation")
    parser.add_argument("--model-c", default="gpt-4", help="Model for optimization")
    parser.add_argument("--source-lang", default="auto", help="Source language (default: auto)")
    parser.add_argument("--target-lang", default="Chinese", help="Target language (default: Chinese)")
    parser.add_argument("--concurrency-trans", type=int, default=32, help="Concurrency for translation (default: 32)")
    parser.add_argument("--concurrency-eval1", type=int, default=32, help="Concurrency for evaluation 1 (default: 32)")
    parser.add_argument("--concurrency-opt", type=int, default=32, help="Concurrency for optimization (default: 32)")
    parser.add_argument("--concurrency-eval2", type=int, default=32, help="Concurrency for evaluation 2 (default: 32)")
    
    args = parser.parse_args()
    
    if args.gui:
        launch_ui()
        return

    if not args.input_file:
        parser.print_help()
        print("\nError: input_file is required unless --gui is specified.")
        return
    
    setup_logging()
    
    # Base configuration from CLI args
    base_config = {
        "provider": args.provider,
        "api_key": args.api_key,
        "base_url": args.base_url,
        "api_version": args.api_version
    }
    
    # Create specific configs
    translation_config = base_config.copy()
    translation_config["model"] = args.model_a
    
    evaluation_config = base_config.copy()
    evaluation_config["model"] = args.model_b
    
    optimization_config = base_config.copy()
    optimization_config["model"] = args.model_c
    
    optimization_config = base_config.copy()
    optimization_config["model"] = args.model_c
    
    concurrency_config = {
        "translation": args.concurrency_trans,
        "evaluation_1": args.concurrency_eval1,
        "optimization": args.concurrency_opt,
        "evaluation_2": args.concurrency_eval2
    }
    
    sdk = TranslationSDK(translation_config, evaluation_config, optimization_config, concurrency_config)
    
    sdk.translate_document(args.input_file, args.output_dir, source_lang=args.source_lang, target_lang=args.target_lang)

if __name__ == "__main__":
    main()
