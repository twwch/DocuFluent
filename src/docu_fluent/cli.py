import os
import argparse
from .sdk import TranslationSDK
from .utils import setup_logging

def launch_ui(config_path=None):
    """Launch the Gradio User Interface."""
    from .ui import create_interface
    demo = create_interface(config_path=config_path)
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
    parser.add_argument("--model-translation", default="gpt-3.5-turbo", help="Model for translation")
    parser.add_argument("--model-evaluation", default="gpt-4", help="Model for evaluation")
    parser.add_argument("--model-optimization", default="gpt-4", help="Model for optimization")
    parser.add_argument("--source-lang", default="auto", help="Source language (default: auto)")
    parser.add_argument("--target-lang", default="Chinese", help="Target language (default: Chinese)")
    parser.add_argument("--concurrency-trans", type=int, default=32, help="Concurrency for translation (default: 32)")
    parser.add_argument("--concurrency-eval1", type=int, default=32, help="Concurrency for evaluation 1 (default: 32)")
    parser.add_argument("--concurrency-opt", type=int, default=32, help="Concurrency for optimization (default: 32)")
    parser.add_argument("--config", help="Path to model_config.json")
    parser.add_argument("--glossary", help="Path to the terminology markdown file")
    
    args = parser.parse_args()
    
    if args.gui:
        launch_ui(config_path=args.config)
        return

    if not args.input_file:
        parser.print_help()
        print("\nError: input_file is required unless --gui is specified.")
        return
    
    setup_logging()
    
    if args.config:
        import json
        import sys
        logger.info(f"Loading configuration from {args.config}")
        try:
            with open(args.config, 'r') as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON config file: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to read config file: {e}")
            sys.exit(1)
            
        # Validate required keys
        required_keys = ["translation_config", "evaluation_config", "optimization_config"]
        missing_keys = [key for key in required_keys if key not in config_data]
        
        if missing_keys:
            logger.error(f"Invalid configuration file. Missing required keys: {', '.join(missing_keys)}")
            sys.exit(1)
            
        # Validate types
        for key in required_keys:
            if not isinstance(config_data[key], dict):
                logger.error(f"Invalid configuration file. '{key}' must be a dictionary.")
                sys.exit(1)
            
        translation_config = config_data.get("translation_config", {})
        evaluation_config = config_data.get("evaluation_config", {})
        optimization_config = config_data.get("optimization_config", {})
        concurrency_config = config_data.get("concurrency_config", {
            "translation": args.concurrency_trans,
            "evaluation_1": args.concurrency_eval1,
            "optimization": args.concurrency_opt,
            "evaluation_2": args.concurrency_eval2
        })
    else:
        # Base configuration from CLI args
        base_config = {
            "provider": args.provider,
            "api_key": args.api_key,
            "base_url": args.base_url,
            "api_version": args.api_version
        }
        
        # Create specific configs
        translation_config = base_config.copy()
        translation_config["model"] = args.model_translation
        
        evaluation_config = base_config.copy()
        evaluation_config["model"] = args.model_evaluation
        
        optimization_config = base_config.copy()
        optimization_config["model"] = args.model_optimization
        
        concurrency_config = {
            "translation": args.concurrency_trans,
            "evaluation_1": args.concurrency_eval1,
            "optimization": args.concurrency_opt,
            "evaluation_2": args.concurrency_eval2
        }
    
    sdk = TranslationSDK(translation_config, evaluation_config, optimization_config, concurrency_config)
    
    sdk.translate_document(args.input_file, args.output_dir, source_lang=args.source_lang, target_lang=args.target_lang, glossary_path=args.glossary)

if __name__ == "__main__":
    main()
