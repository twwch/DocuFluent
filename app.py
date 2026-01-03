import sys
import os

# Monkeypatch HfFolder which was removed in huggingface_hub >= 1.0.0
# Gradio 4.x still expects it.
try:
    import huggingface_hub
    if not hasattr(huggingface_hub, "HfFolder"):
        import types
        mock_hf_folder = types.ModuleType("HfFolder")
        mock_hf_folder.get_token = lambda: None
        mock_hf_folder.save_token = lambda token: None
        mock_hf_folder.delete_token = lambda: None
        huggingface_hub.HfFolder = mock_hf_folder
        sys.modules["huggingface_hub.hf_folder"] = mock_hf_folder
except Exception:
    pass

# Add src to python path to allow imports from docu_fluent
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from docu_fluent.ui import create_interface

if __name__ == "__main__":
    demo = create_interface()
    # share=True is not needed for HF Spaces as it's handled by their infrastructure
    demo.launch(server_name="0.0.0.0", server_port=7860, show_api=False)
