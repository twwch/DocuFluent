import argparse
import pandas as pd
import os
import sys
from src.docu_fluent.document import DocumentProcessor, TranslationSegment

def regenerate_documents(input_docx: str, input_excel: str, output_dir: str):
    print(f"Loading original document: {input_docx}")
    processor = DocumentProcessor(input_docx)
    
    print(f"Loading Excel report: {input_excel}")
    try:
        df = pd.read_excel(input_excel)
    except Exception as e:
        print(f"Error loading Excel file: {e}")
        sys.exit(1)
        
    # Check required columns
    required_cols = ['segment_id']
    for col in required_cols:
        if col not in df.columns:
            print(f"Error: Excel file missing required column: {col}")
            sys.exit(1)
            
    # Create a mapping of segment_id -> final_translation
    translation_map = {}
    
    print("Processing Excel data...")
    for index, row in df.iterrows():
        seg_id = str(row['segment_id'])
        
        # Determine final translation
        final_trans = ""
        
        # 1. If 'final_translation' column exists (user might have added it), use it
        if 'final_translation' in df.columns and pd.notna(row['final_translation']):
            final_trans = str(row['final_translation'])
        
        # 2. Else derive from selected_model
        elif 'selected_model' in df.columns:
            selected = str(row['selected_model'])
            if "C" in selected and 'translation_c' in df.columns and pd.notna(row['translation_c']):
                final_trans = str(row['translation_c'])
            elif 'translation_a' in df.columns and pd.notna(row['translation_a']):
                final_trans = str(row['translation_a'])
        
        # 3. Fallback to translation_c then translation_a
        else:
            if 'translation_c' in df.columns and pd.notna(row['translation_c']):
                final_trans = str(row['translation_c'])
            elif 'translation_a' in df.columns and pd.notna(row['translation_a']):
                final_trans = str(row['translation_a'])
                
        if final_trans:
            translation_map[seg_id] = final_trans

    # Update segments in processor and apply translations
    print(f"Updating {len(translation_map)} segments...")
    processor.apply_translations(translation_map)
            
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(input_docx))[0]
    
    # Save Translated Document
    trans_path = os.path.join(output_dir, f"{base_name}_regenerated_translated.docx")
    print(f"Saving translated document to: {trans_path}")
    processor.save(trans_path)
    
    # Save Bilingual Document
    # Note: save_bilingual requires 'score' for color coding. 
    # We can try to fetch score from Excel if available, otherwise default to 10 (no color).
    
    # We need to inject scores into segments if we want color coding
    # DocumentProcessor.save_bilingual uses seg.translation and we might need to pass a score map or similar?
    # Actually save_bilingual takes a 'results' list or similar?
    # Let's check DocumentProcessor.save_bilingual signature.
    # It seems it iterates over self.segments. 
    # Wait, save_bilingual in document.py:
    # def save_bilingual(self, output_path: str, results_map: Dict[str, Any] = None):
    
    # So we need to reconstruct results_map
    results_map = {}
    for index, row in df.iterrows():
        seg_id = str(row['segment_id'])
        
        # Get final translation (already calculated in translation_map)
        final_trans = translation_map.get(seg_id, "")
        if not final_trans:
            continue

        selected = str(row.get('selected_model', 'A'))
        score_a = float(row.get('score_a_total', 0))
        score_c = float(row.get('score_c_total', 0))
        
        # Determine score
        score = score_a
        if "C" in selected:
            score = score_c
            
        results_map[seg_id] = {
            "text": final_trans,
            "score": score
        }

    bilingual_path = os.path.join(output_dir, f"{base_name}_regenerated_bilingual.docx")
    print(f"Saving bilingual document to: {bilingual_path}")
    processor.save_bilingual(bilingual_path, results_map)
    
    print("Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenerate documents from Excel report.")
    parser.add_argument("--input-docx", required=True, help="Path to original .docx file")
    parser.add_argument("--input-excel", required=True, help="Path to Excel report file")
    parser.add_argument("--output-dir", default="output", help="Output directory")
    
    args = parser.parse_args()
    
    regenerate_documents(args.input_docx, args.input_excel, args.output_dir)
