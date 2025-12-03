import gradio as gr
import os
import json
from datetime import datetime
from .sdk import TranslationSDK

def create_interface():
    # Load default config for initial values
    try:
        with open("model_config.json", "r") as f:
            default_config_str = f.read()
    except:
        default_config_str = "{}"

    def process_file(file_obj, source_lang, target_lang, config_json, progress=gr.Progress()):
        if not file_obj:
            return [None] * 7
            
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
                progress_callback=progress_callback
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

    with gr.Blocks(title="DocuFluent Translation") as demo:
        gr.Markdown("# DocuFluent Translation System")
        
        with gr.Row():
            with gr.Column(scale=1):
                file_input = gr.File(label="Upload Word Document (.docx)", file_types=[".docx"])
                source_lang = gr.Dropdown(
                    choices=["auto", "Chinese", "English", "Russian", "Spanish", "French", "German", "Japanese", "Korean", "Arabic", "Portuguese"],
                    value="auto",
                    label="Source Language",
                    allow_custom_value=True
                )
                target_lang = gr.Dropdown(
                    choices=["Chinese", "English", "Russian", "Spanish", "French", "German", "Japanese", "Korean", "Arabic", "Portuguese"],
                    value="Chinese",
                    label="Target Language",
                    allow_custom_value=True
                )
                submit_btn = gr.Button("Start Translation", variant="primary")
                
            with gr.Column(scale=2):
                with gr.Tabs():
                    with gr.TabItem("Downloads"):
                        out_translated = gr.File(label="Translated Document")
                        out_bilingual = gr.File(label="Bilingual Document")
                        out_report_excel = gr.File(label="Evaluation Report (Excel)")
                        out_report_pdf = gr.File(label="Evaluation Report (PDF)")
                        out_usage = gr.File(label="Token Usage (JSON)")
                        out_model_map = gr.File(label="Model Mapping (JSON)")
                        out_results = gr.File(label="Full Results (JSON)")
                    
                    with gr.TabItem("Settings"):
                        gr.Markdown("### Configuration (JSON)")
                        config_input = gr.Code(label="model_config.json", value=default_config_str, language="json", lines=20)

        submit_btn.click(
            fn=process_file,
            inputs=[
                file_input, source_lang, target_lang,
                config_input
            ],
            outputs=[
                out_translated, out_bilingual, out_report_excel, out_report_pdf, out_usage, out_model_map, out_results
            ]
        )
        
    return demo
