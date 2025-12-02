from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import os
from openai import OpenAI, AzureOpenAI
import logging

logger = logging.getLogger(__name__)

from dataclasses import dataclass

@dataclass
class GenerationResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class LLMBase(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> GenerationResult:
        pass

class MockLLM(LLMBase):
    def __init__(self):
        self.model = "mock"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> GenerationResult:
        logger.info(f"MockLLM generating for prompt: {prompt[:50]}...")
        text = "Mock Response"
        if "Translate" in prompt:
            text = "Mock Translation"
        elif "Evaluate" in prompt:
            if "Model A" in prompt and "Model C" in prompt:
                # Comparative evaluation
                text = json.dumps({
                    "model_a": {
                        "accuracy": 8, "fluency": 8, "consistency": 8, "terminology": 8, "completeness": 8, 
                        "suggestions": "Model A suggestion"
                    },
                    "model_c": {
                        "accuracy": 9, "fluency": 9, "consistency": 9, "terminology": 9, "completeness": 9, 
                        "suggestions": "Model C suggestion"
                    }
                })
            else:
                # Single evaluation
                text = '{"accuracy": 8, "fluency": 9, "consistency": 8, "terminology": 8, "completeness": 9, "suggestions": "不错，但可以更流畅。"}'
        elif "Optimize" in prompt:
            text = "Optimized Mock Translation"
        
        return GenerationResult(text=text, prompt_tokens=10, completion_tokens=10, total_tokens=20)

class OpenAILLM(LLMBase):
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "gpt-3.5-turbo"):
        self.client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=base_url or os.getenv("OPENAI_BASE_URL")
        )
        self.model = model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> GenerationResult:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            usage = response.usage
            return GenerationResult(
                text=response.choices[0].message.content.strip(),
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens
            )
        except Exception as e:
            logger.error(f"Error calling OpenAI: {e}")
            raise

class AzureOpenAILLM(LLMBase):
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, api_version: Optional[str] = None, model: str = "gpt-35-turbo"):
        # AzureOpenAI uses 'azure_endpoint' which corresponds to base_url
        self.client = AzureOpenAI(
            api_key=api_key or os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=base_url or os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
        )
        self.model = model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> GenerationResult:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            usage = response.usage
            return GenerationResult(
                text=response.choices[0].message.content.strip(),
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens
            )
        except Exception as e:
            logger.error(f"Error calling Azure OpenAI: {e}")
            raise

class LLMFactory:
    @staticmethod
    def create(provider: str, **kwargs) -> LLMBase:
        if provider == "openai":
            return OpenAILLM(**kwargs)
        elif provider == "azure":
            return AzureOpenAILLM(**kwargs)
        elif provider == "mock":
            return MockLLM()
        else:
            raise ValueError(f"Unknown provider: {provider}")
