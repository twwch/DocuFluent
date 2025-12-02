# Word Document Translation SDK

A Python SDK for translating Word documents (`.docx`) using a multi-model workflow (Translate -> Evaluate -> Optimize -> Select).

## Features

- **Multi-Model Workflow**: 
    - **Model A**: Initial Translation
    - **Model B**: Evaluation (Accuracy, Fluency, Consistency, Terminology, Completeness)
    - **Model C**: Optimization based on evaluation
    - **Selection**: Automatically selects the best translation based on scores.
- **Format Preservation**: Preserves paragraph styles, tables, and formulas.
- **Comprehensive Reporting**: Generates Excel and PDF reports with detailed evaluation metrics.
- **Bilingual Output**: Generates a bilingual document (Original + Translation).

## Installation

This project uses `uv` for dependency management.

```bash
# Clone the repository
git clone <repository-url>
cd translation-sdk

# Install dependencies
uv sync
```

## Usage

### Command Line Interface (CLI)

You can use the SDK directly from the command line.

```bash
# Set up your API key (if using OpenAI)
export OPENAI_API_KEY="your-api-key"

# Run translation with Azure OpenAI
uv run python -m src.translation_sdk.main input.docx \
    --output-dir output \
    --provider azure \
    --base-url https://your-resource.openai.azure.com/ \
    --api-key your-azure-key \
    --api-version 2023-05-15 \
    --model-a gpt-35-turbo-deployment \
    --model-b gpt-4-deployment \
    --model-c gpt-4-deployment \
    --source-lang auto \
    --target-lang "French"
```

**Arguments:**

- `input_file`: Path to the `.docx` file to translate.
- `--output-dir`: Directory to save the output files (default: `output`).
- `--provider`: LLM provider to use (`openai`, `azure`, or `mock`). Default is `mock`.
- `--api-key`: API key for the provider.
- `--base-url`: Base URL (OpenAI) or Azure Endpoint (Azure).
- `--api-version`: API Version (Azure only, e.g., `2023-05-15`).
- `--model-a`: Model/Deployment for translation.
- `--model-b`: Model/Deployment for evaluation.
- `--model-c`: Model/Deployment for optimization.
- `--source-lang`: Source language (default: `auto`).
- `--target-lang`: Target language (default: `Chinese`).

### Python SDK

You can also use the SDK in your Python code.

```python
from translation_sdk.main import TranslationSDK

# Initialize SDK with specific configurations for each model
# This allows using different providers/models for each step
sdk = TranslationSDK(
    config_a={
        "provider": "openai",
        "api_key": "key-for-provider-1",
        "base_url": "https://api.provider1.com/v1",
        "model": "model-name-1"
    },
    config_b={
        "provider": "openai",
        "api_key": "key-for-provider-2",
        "base_url": "https://api.provider2.com/v1",
        "model": "model-name-2"
    },
    config_c={
        "provider": "azure",
        "api_key": "azure-key",
        "base_url": "https://your-resource.openai.azure.com/",
        "api_version": "2023-05-15",
        "model": "gpt-4-deployment"
    }
)

# Translate a document
sdk.translate_document(
    "path/to/document.docx", 
    output_dir="output",
    source_lang="English",
    target_lang="Spanish"
)
```

## Output Files

The SDK generates the following files in the output directory:

1.  `{filename}_translated.docx`: The fully translated document.
2.  `{filename}_bilingual.docx`: A document with both original and translated text.
3.  `{filename}_report.xlsx`: An Excel file containing detailed scores for each segment across 5 dimensions.
4.  `{filename}_report.pdf`: A PDF summary of the translation quality.

## Evaluation Dimensions

The translation is evaluated on 5 dimensions (0-100 score):
1.  **Accuracy**: How accurately the meaning is conveyed.
2.  **Fluency**: How natural the translation sounds.
3.  **Consistency**: Consistency of terminology and style.
4.  **Terminology**: Accuracy of specific domain terms.
5.  **Completeness**: Whether all content is translated.
