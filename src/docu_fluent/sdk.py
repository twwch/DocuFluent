import os
from .document import DocumentProcessor
from .llm import LLMFactory
from .workflow import TranslationWorkflow
from .report import ReportGenerator
from .utils import parse_glossary, parse_glossary_text
from loguru import logger

class TranslationSDK:
    def __init__(self, 
                 translation_config: dict,
                 evaluation_config: dict,
                 optimization_config: dict,
                 concurrency_config: dict = None,
                 glossary: str = ""):
        
        self.translator = LLMFactory.create(**translation_config)
        self.evaluator = LLMFactory.create(**evaluation_config)
        self.optimizer = LLMFactory.create(**optimization_config)
        
        self.workflow = TranslationWorkflow(self.translator, self.evaluator, self.optimizer, concurrency_config, glossary=glossary)

    def translate_document(self, input_path: str, output_dir: str, source_lang: str = "auto", target_lang: str = "Chinese", progress_callback=None, glossary_path: str = None, glossary_text: str = None):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        if glossary_text:
            logger.info("Using terminology from text input")
            terms = parse_glossary_text(glossary_text)
            self.workflow.glossary = "\n".join([f"{src} -> {tgt}" for src, tgt in terms])
        elif glossary_path:
            logger.info(f"Loading glossary from {glossary_path}")
            self.workflow.glossary = parse_glossary(glossary_path)
            
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
