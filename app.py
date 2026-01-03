import sys
import os

# Add src to python path to allow imports from docu_fluent
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from docu_fluent.ui import create_interface

if __name__ == "__main__":
    demo = create_interface()
    # share=True is not needed for HF Spaces as it's handled by their infrastructure
    demo.launch(server_name="0.0.0.0", server_port=7860, show_api=False)
