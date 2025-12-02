import argparse
import json
import os
import logging
from src.translation_sdk.document import DocumentProcessor

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

def reconstruct_bilingual(input_docx, results_json, output_path):
    logger.info(f"Loading document: {input_docx}")
    doc_processor = DocumentProcessor(input_docx)
    doc_processor.extract_segments() # Needed to initialize segments
    
    logger.info(f"Loading results from: {results_json}")
    with open(results_json, 'r', encoding='utf-8') as f:
        results_data = json.load(f)
    
    # Create translations dictionary
    # Map segment_id -> final_translation
    translations = {}
    for item in results_data:
        seg_id = item.get('segment_id')
        final_trans = item.get('final_translation')
        if seg_id and final_trans:
            translations[seg_id] = final_trans
            
    logger.info(f"Loaded {len(translations)} translations")
    
    logger.info(f"Reconstructing bilingual document to: {output_path}")
    doc_processor.save_bilingual(output_path, translations)
    logger.info("Done.")

def main():
    parser = argparse.ArgumentParser(description="Reconstruct bilingual document from JSON results")
    parser.add_argument("input_docx", help="Path to the original .docx file")
    parser.add_argument("results_json", help="Path to the results .json file")
    parser.add_argument("output_path", help="Path to save the reconstructed bilingual .docx")
    
    args = parser.parse_args()
    
    reconstruct_bilingual(args.input_docx, args.results_json, args.output_path)

if __name__ == "__main__":
    main()
