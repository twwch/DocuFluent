import os
import argparse
from docx import Document
from src.docu_fluent.cli import TranslationSDK, launch_ui

def verify_output(output_dir, base_name):
    print(f"Verifying output in {output_dir}...")
    files = [
        f"{base_name}_translated.docx",
        f"{base_name}_bilingual.docx",
        f"{base_name}_report.xlsx",
        f"{base_name}_report.pdf",
        f"{base_name}_usage.json",
        f"{base_name}_model_mapping.json",
        f"{base_name}_results.json"
    ]
    
    all_exist = True
    for f in files:
        path = os.path.join(output_dir, f)
        if os.path.exists(path):
            print(f"[OK] Found {f}")
        else:
            print(f"[FAIL] Missing {f}")
            all_exist = False
            
    if all_exist:
        print("All output files generated successfully.")
    else:
        print("Some output files are missing.")

def main():
    parser = argparse.ArgumentParser(description="Run Translation SDK Test")
    parser.add_argument("--input-file", help="Path to input file")
    parser.add_argument("--output-dir", default="output", help="Output directory")
    parser.add_argument("--target-lang", default="Chinese", help="Target language (default: Chinese)")
    parser.add_argument("--gui", action="store_true", help="Launch Gradio GUI")
    parser.add_argument("--glossary", help="Path to terminology markdown file")

    
    args = parser.parse_args()
    
    if args.gui:
        launch_ui()
        return

    print(f"Running SDK on {args.input_file}...")
    
    import json
    model_config = json.load(open("model_config.json"))
    
    try:
        sdk = TranslationSDK(
            translation_config=model_config.get("translation_config", {}),
            evaluation_config=model_config.get("evaluation_config", {}),
            optimization_config=model_config.get("optimization_config", {}),
            concurrency_config=model_config.get("concurrency_config", {})
        )
        sdk.translate_document(args.input_file, args.output_dir, target_lang=args.target_lang, glossary_path=args.glossary)
        
        base_name = os.path.splitext(os.path.basename(args.input_file))[0]
        verify_output(args.output_dir, base_name)
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
