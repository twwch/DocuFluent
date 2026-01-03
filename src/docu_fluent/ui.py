import gradio as gr
import os
import json
import re
from datetime import datetime
from .sdk import TranslationSDK
from .utils import parse_glossary_text

LANG_MAPPING = {
    "(自动检测)auto": "auto",
    "(中文)Chinese": "Chinese",
    "(英文)English": "English",
    "(俄语)Russian": "Russian",
    "(西班牙语)Spanish": "Spanish",
    "(法语)French": "French",
    "(德语)German": "German",
    "(日语)Japanese": "Japanese",
    "(韩语)Korean": "Korean",
    "(阿拉伯语)Arabic": "Arabic",
    "(葡萄牙语)Portuguese": "Portuguese"
}

LANG_CHOICES_SOURCE = list(LANG_MAPPING.keys())
LANG_CHOICES_TARGET = [k for k in LANG_CHOICES_SOURCE if LANG_MAPPING[k] != "auto"]

def create_interface(config_path=None):
    # Load default config for initial values
    default_config_str = "{}"
    
    # Priority: 1. config_path argument, 2. "model_config.json" in current dir
    path_to_load = config_path if config_path else "model_config.json"
    
    if path_to_load and os.path.exists(path_to_load):
        try:
            with open(path_to_load, "r") as f:
                default_config_str = f.read()
        except Exception as e:
            print(f"Warning: Failed to load config from {path_to_load}: {e}")
            default_config_str = "{}"

    def process_file(file_obj, source_lang_label, target_lang_label, glossary_text, config_json, progress=gr.Progress()):
        if not file_obj:
            return [None] * 7
            
        source_lang = LANG_MAPPING.get(source_lang_label, source_lang_label)
        target_lang = LANG_MAPPING.get(target_lang_label, target_lang_label)
        
        input_path = file_obj.name
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join("output", f"{base_name}_{timestamp}")
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        output_dir = os.path.abspath(output_dir)
            
        # Parse config from JSON editor
        try:
            model_config = json.loads(config_json)
        except Exception as e:
            raise gr.Error(f"Invalid JSON configuration: {e}")
            
        sdk = TranslationSDK(
            translation_config=model_config.get("translation_config", {}),
            evaluation_config=model_config.get("evaluation_config", {}),
            optimization_config=model_config.get("optimization_config", {}),
            concurrency_config=model_config.get("concurrency_config", {})
        )
        
        # Define progress callback adapter
        def progress_callback(p, desc):
            progress(p, desc=desc)
            
        # Run translation
        try:
            sdk.translate_document(
                input_path, 
                output_dir, 
                source_lang=source_lang, 
                target_lang=target_lang,
                progress_callback=progress_callback,
                glossary_text=glossary_text
            )
        except Exception as e:
            raise gr.Error(f"Translation failed: {e}")
            
        # Paths
        p_trans = os.path.join(output_dir, f"{base_name}_translated.docx")
        p_bi = os.path.join(output_dir, f"{base_name}_bilingual.docx")
        p_excel = os.path.join(output_dir, f"{base_name}_report.xlsx")
        p_pdf = os.path.join(output_dir, f"{base_name}_report.pdf")
        p_usage = os.path.join(output_dir, f"{base_name}_usage.json")
        p_map = os.path.join(output_dir, f"{base_name}_model_mapping.json")
        p_res = os.path.join(output_dir, f"{base_name}_results.json")
        
        return (
            p_trans, p_bi, p_excel, p_pdf, p_usage, p_map, p_res
        )

    def validate_terminology(text):
        if not text.strip():
            return "Empty terminology."
        
        parsed = parse_glossary_text(text)
        if not parsed:
            return "No valid terms found. Please use markdown table (| Source | Target |) or list (- Source: Target)."
        
        lines = parsed.split("\n")
        return f"Validated: {len(lines)} terms found.\nPreview:\n" + "\n".join(lines[:5]) + ("\n..." if len(lines) > 5 else "")

    with gr.Blocks(title="DocuFluent Translation") as demo:
        gr.Markdown("# DocuFluent Translation System")
        
        with gr.Row():
            with gr.Column(scale=1):
                file_input = gr.File(label="Upload Word Document (.docx)", file_types=[".docx"])
                source_lang = gr.Dropdown(
                    choices=LANG_CHOICES_SOURCE,
                    value="(自动检测)auto",
                    label="Source Language",
                    allow_custom_value=True
                )
                target_lang = gr.Dropdown(
                    choices=LANG_CHOICES_TARGET,
                    value="(中文)Chinese",
                    label="Target Language",
                    allow_custom_value=True
                )
                submit_btn = gr.Button("Start Translation", variant="primary")
                
            with gr.Column(scale=2):
                with gr.Tabs():
                    with gr.TabItem("Downloads"):
                        out_translated = gr.File(label="Translated Document")
                        out_bilingual = gr.File(label="Bilingual Document")
                        with gr.Row():
                            out_report_excel = gr.File(label="Report (Excel)")
                            out_report_pdf = gr.File(label="Report (PDF)")
                        with gr.Row():
                            out_usage = gr.File(label="Usage (JSON)")
                            out_model_map = gr.File(label="Mapping (JSON)")
                            out_results = gr.File(label="Results (JSON)")
                    
                    with gr.TabItem("Terminology"):
                        gr.Markdown("### Terminology Database (Markdown Format)")
                        gr.Markdown("Supports tables: `| Source | Target |` or lists: `- Source: Target`")
                        glossary_input = gr.Code(
                            label="Terminology (Markdown)", 
                            value="| Original | Translation |\n| --- | --- |\n", 
                            language="markdown", 
                            lines=15
                        )
                        validate_btn = gr.Button("Validate Format")
                        validation_output = gr.Markdown("Enter terminology and click validate.")
                        
                        validate_btn.click(
                            fn=validate_terminology,
                            inputs=[glossary_input],
                            outputs=[validation_output]
                        )

                    with gr.TabItem("Settings"):
                        gr.Markdown("### Configuration (JSON)")
                        config_input = gr.Code(label="model_config.json", value=default_config_str, language="json", lines=15)

        submit_btn.click(
            fn=process_file,
            inputs=[
                file_input, source_lang, target_lang,
                glossary_input, config_input
            ],
            outputs=[
                out_translated, out_bilingual, out_report_excel, out_report_pdf, out_usage, out_model_map, out_results
            ]
        )
        
    return demo
