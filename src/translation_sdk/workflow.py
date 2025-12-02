from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, field
import logging
import json
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_fixed
from .llm import LLMBase, GenerationResult
from .document import TranslationSegment

logger = logging.getLogger(__name__)

@dataclass
class EvaluationResult:
    accuracy: int
    fluency: int
    consistency: int
    terminology: int
    completeness: int
    suggestions: str
    
    @property
    def total_score(self) -> float:
        return (self.accuracy + self.fluency + self.consistency + self.terminology + self.completeness) / 5.0

@dataclass
class WorkflowResult:
    segment_id: str
    original: str
    translation_a: str = ""
    eval_a: EvaluationResult = None
    translation_c: str = ""
    eval_c: EvaluationResult = None
    final_translation: str = ""
    final_translation: str = ""
    selected_model: str = ""
    
    # Debug Info
    translation_a_prompt: str = ""
    translation_a_raw_response: str = ""
    
    eval_a_prompt: str = ""
    eval_a_raw_response: str = ""
    
    translation_c_prompt: str = ""
    translation_c_raw_response: str = ""
    
    eval_c_prompt: str = ""
    eval_c_raw_response: str = ""

@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: 'TokenUsage'):
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens

class TranslationWorkflow:
    def __init__(self, translator: LLMBase, evaluator: LLMBase, optimizer: LLMBase):
        self.translator = translator
        self.evaluator = evaluator
        self.optimizer = optimizer
        self.total_usage = TokenUsage()
        self.stage_usage = {
            "translation": TokenUsage(),
            "evaluation_1": TokenUsage(),
            "optimization": TokenUsage(),
            "evaluation_2": TokenUsage()
        }

    def _parse_evaluation(self, text: str) -> EvaluationResult:
        """
        Parses the evaluation response. 
        Expected format: JSON with keys: accuracy, fluency, consistency, terminology, completeness, suggestions
        """
        try:
            # Try parsing as JSON first
            # Sometimes LLMs wrap JSON in markdown code blocks
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```markdownjson" in text:
                text = text.split("```markdownjson")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)
            return EvaluationResult(
                accuracy=int(data.get("accuracy", 0)),
                fluency=int(data.get("fluency", 0)),
                consistency=int(data.get("consistency", 0)),
                terminology=int(data.get("terminology", 0)),
                completeness=int(data.get("completeness", 0)),
                suggestions=data.get("suggestions", "")
            )
        except Exception as e:
            logger.warning(f"Failed to parse evaluation JSON: {text}. Error: {e}")
            return EvaluationResult(0, 0, 0, 0, 0, text)

    def _track_usage(self, stage: str, result: GenerationResult):
        usage = TokenUsage(result.prompt_tokens, result.completion_tokens, result.total_tokens)
        self.stage_usage[stage].add(usage)
        self.total_usage.add(usage)

    def _load_cache(self):
        self.cache_file = "translation_cache.json"
        self.cache = {}
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

    def _save_cache(self):
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _is_simple_segment(self, text: str) -> bool:
        """Check if segment is simple (number, symbol, placeholder) and shouldn't be processed."""
        text = text.strip()
        if not text: return True
        # Check if it's just a placeholder
        if re.match(r'^\{\{MATH_\d+\}\}$', text): return True
        # Check if it's just a number or simple symbol
        if re.match(r'^[\d\.\,\%\-\+\=\/\(\)\[\]\s]+$', text): return True
        return False

    def _get_lang_rules(self, target_lang: str) -> str:
        rules = ""
        # Russian uses comma for decimals
        if any(x in target_lang.lower() for x in ["russian", "ru", "俄语"]):
            rules += "\n7. Number Formatting: Use comma ',' for decimals (e.g. 0.008 -> 0,008). CRITICAL: Do NOT change dots '.' in serial numbers, section numbers (e.g. 1.1, 2.1.3), version numbers, or model codes."
        return rules

    def run(self, segments: List[TranslationSegment], source_lang: str = "auto", target_lang: str = "Chinese") -> Tuple[List[WorkflowResult], Dict]:
        self._load_cache()
        results_map: Dict[str, WorkflowResult] = {
            seg.id: WorkflowResult(segment_id=seg.id, original=seg.original_text) 
            for seg in segments
        }
        
        max_workers = 32
        
        # Stage 1: Translation
        print(f"\n[Stage 1/5] Translating segments (Source: {source_lang}, Target: {target_lang})...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_seg = {}
            for seg in segments:
                # 1. Skip simple segments
                if self._is_simple_segment(seg.original_text):
                    results_map[seg.id].translation_a = seg.original_text
                    results_map[seg.id].selected_model = "Skipped (Simple)"
                    continue
                
                # 2. Check Cache
                cache_key = f"{seg.original_text}_{source_lang}_{target_lang}"
                if cache_key in self.cache:
                    cached_trans = self.cache[cache_key]
                    # If cached translation is identical to original (and it's not a simple segment), 
                    # it's likely a failed translation. Do not use it.
                    if cached_trans.strip() != seg.original_text.strip():
                        results_map[seg.id].translation_a = cached_trans
                        results_map[seg.id].selected_model = "Cached"
                        continue

                future = executor.submit(self._translate_task, seg, source_lang, target_lang)
                future_to_seg[future] = seg

            for future in tqdm(as_completed(future_to_seg), total=len(future_to_seg), colour='green', desc="Translation"):
                seg = future_to_seg[future]
                try:
                    trans_text, usage, prompt, raw_response = future.result()
                    results_map[seg.id].translation_a = trans_text
                    results_map[seg.id].translation_a_prompt = prompt
                    results_map[seg.id].translation_a_raw_response = raw_response
                    self._track_usage("translation", usage)
                    
                    # Update Cache
                    # Only cache if translation is different from original
                    if trans_text.strip() != seg.original_text.strip():
                        cache_key = f"{seg.original_text}_{source_lang}_{target_lang}"
                        self.cache[cache_key] = trans_text
                except Exception as e:
                    logger.error(f"Translation failed for {seg.id}: {e}")
        
        self._save_cache()

        # Stage 1.5: Repair Failed Translations
        # Identify segments where translation == original (and not skipped/simple)
        failed_segments = []
        for seg in segments:
            res = results_map[seg.id]
            if res.selected_model == "Skipped (Simple)":
                continue
            
            # Check if translation is identical to original (ignoring whitespace)
            if res.translation_a.strip() == seg.original_text.strip():
                failed_segments.append(seg)
        
        if failed_segments:
            print(f"\n[Stage 1.5/5] Repairing {len(failed_segments)} failed translations...")
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_seg = {}
                for seg in failed_segments:
                    # Retry translation
                    future = executor.submit(self._translate_task, seg, source_lang, target_lang)
                    future_to_seg[future] = seg
                
                for future in tqdm(as_completed(future_to_seg), total=len(future_to_seg), colour='red', desc="Repair"):
                    seg = future_to_seg[future]
                    try:
                        trans_text, usage, prompt, raw_response = future.result()
                        results_map[seg.id].translation_a = trans_text
                        results_map[seg.id].translation_a_prompt = prompt
                        results_map[seg.id].translation_a_raw_response = raw_response
                        self._track_usage("translation", usage)
                        
                        # Update Cache if successful
                        if trans_text.strip() != seg.original_text.strip():
                            cache_key = f"{seg.original_text}_{source_lang}_{target_lang}"
                            self.cache[cache_key] = trans_text
                    except Exception as e:
                        logger.error(f"Repair failed for {seg.id}: {e}")
            
            self._save_cache()

        # Stage 2: Evaluation 1
        print("\n[Stage 2/5] Evaluating initial translations...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_seg = {}
            for seg in segments:
                # Skip if skipped or cached in Stage 1 (Optional: could re-eval cached, but let's save tokens)
                if results_map[seg.id].selected_model in ["Skipped (Simple)"]:
                    results_map[seg.id].eval_a = EvaluationResult(10,10,10,10,10,"Simple segment, no evaluation needed.")
                    continue
                
                future = executor.submit(self._evaluate_task, results_map[seg.id].original, results_map[seg.id].translation_a, source_lang, target_lang)
                future_to_seg[future] = seg

            for future in tqdm(as_completed(future_to_seg), total=len(future_to_seg), colour='blue', desc="Evaluation 1"):
                seg = future_to_seg[future]
                try:
                    eval_res, usage, prompt, raw_response = future.result()
                    results_map[seg.id].eval_a = eval_res
                    results_map[seg.id].eval_a_prompt = prompt
                    results_map[seg.id].eval_a_raw_response = raw_response
                    self._track_usage("evaluation_1", usage)
                except Exception as e:
                    logger.error(f"Evaluation 1 failed for {seg.id}: {e}")

        # Stage 3: Optimization
        print("\n[Stage 3/5] Optimizing translations...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_seg = {}
            for seg in segments:
                if results_map[seg.id].selected_model in ["Skipped (Simple)"]:
                    results_map[seg.id].translation_c = results_map[seg.id].translation_a
                    continue

                # If evaluation is perfect, skip optimization
                if results_map[seg.id].eval_a and results_map[seg.id].eval_a.total_score >= 9.5:
                     results_map[seg.id].translation_c = results_map[seg.id].translation_a
                     continue

                future = executor.submit(
                    self._optimize_task, 
                    results_map[seg.id].original, 
                    results_map[seg.id].translation_a, 
                    results_map[seg.id].eval_a.suggestions,
                    target_lang
                )
                future_to_seg[future] = seg

            for future in tqdm(as_completed(future_to_seg), total=len(future_to_seg), colour='yellow', desc="Optimization"):
                seg = future_to_seg[future]
                try:
                    opt_text, usage, prompt, raw_response = future.result()
                    results_map[seg.id].translation_c = opt_text
                    results_map[seg.id].translation_c_prompt = prompt
                    results_map[seg.id].translation_c_raw_response = raw_response
                    self._track_usage("optimization", usage)
                except Exception as e:
                    logger.error(f"Optimization failed for {seg.id}: {e}")

        # Stage 4: Comparative Evaluation
        print("\n[Stage 4/5] Comparative Evaluation (A vs C)...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_seg = {}
            for seg in segments:
                if results_map[seg.id].selected_model in ["Skipped (Simple)"]:
                     results_map[seg.id].eval_c = EvaluationResult(10,10,10,10,10,"Simple segment.")
                     continue
                
                # If we skipped optimization, copy eval_a to eval_c
                if results_map[seg.id].translation_c == results_map[seg.id].translation_a:
                    results_map[seg.id].eval_c = results_map[seg.id].eval_a
                    continue

                future = executor.submit(
                    self._evaluate_comparative_task, 
                    results_map[seg.id].original, 
                    results_map[seg.id].translation_a,
                    results_map[seg.id].translation_c,
                    source_lang,
                    target_lang
                )
                future_to_seg[future] = seg

            for future in tqdm(as_completed(future_to_seg), total=len(future_to_seg), colour='magenta', desc="Final Evaluation"):
                seg = future_to_seg[future]
                try:
                    eval_a, eval_c, usage, prompt, raw_response = future.result()
                    results_map[seg.id].eval_a = eval_a
                    results_map[seg.id].eval_c = eval_c
                    results_map[seg.id].eval_c_prompt = prompt
                    results_map[seg.id].eval_c_raw_response = raw_response
                    self._track_usage("evaluation_2", usage)
                except Exception as e:
                    logger.error(f"Comparative evaluation failed for {seg.id}: {e}")

        # Stage 5: Selection
        print("\n[Stage 5/5] Selecting best translations...")
        final_results = []
        for seg in segments:
            res = results_map[seg.id]
            # Handle missing data if failures occurred
            if not res.eval_a: res.eval_a = EvaluationResult(0,0,0,0,0,"Failed")
            if not res.eval_c: res.eval_c = EvaluationResult(0,0,0,0,0,"Failed")
            
            if res.selected_model == "Skipped (Simple)":
                res.final_translation = res.translation_a
            elif res.eval_c.total_score > res.eval_a.total_score:
                res.final_translation = res.translation_c
                res.selected_model = "C (Optimized)"
            else:
                res.final_translation = res.translation_a
                res.selected_model = "A (Initial)"
            final_results.append(res)

        usage_report = {
            "total": vars(self.total_usage),
            "stages": {k: vars(v) for k, v in self.stage_usage.items()}
        }
        
        return final_results, usage_report

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def _evaluate_comparative_task(self, original: str, trans_a: str, trans_c: str, source_lang: str, target_lang: str) -> Tuple[EvaluationResult, EvaluationResult, GenerationResult, str, str]:
        prompt = f"""Evaluate the following two translations from {source_lang} to {target_lang} on 5 dimensions: Accuracy, Fluency, Consistency, Terminology Accuracy, Completeness.
 
Original ({source_lang}): {original}
 
Model A Translation ({target_lang}): {trans_a}
 
Model C Translation ({target_lang}): {trans_c}
 
Provide a score (0-10) for each dimension and suggestions for improvement for BOTH models.
IMPORTANT: Provide suggestions in Chinese.

CRITICAL: Verify the translation status.
1. Check if the Translation is identical to the Original.
   - If YES, and the Original is NOT just numbers/symbols/proper nouns/codes, then it is a FAILURE (Untranslated). Score 0 for Accuracy and Completeness.
   - If YES, and the Original IS just numbers/symbols/codes/model numbers (e.g. "MTENTU-JKBG-2505"), it is acceptable and should receive a high score if correct.
2. Check if the Translation is in {target_lang}.
   - If NO, it is a FAILURE (Wrong Language). Score 0 for Accuracy and Completeness.
   - Note: The translation may contain numbers or symbols from the original, which is fine as long as the text parts are translated.
3. Check Number Formatting:{self._get_lang_rules(target_lang)}
   - If the translation violates these rules (e.g. wrong decimal separator for {target_lang}), penalize Accuracy and Fluency.

If it is NOT a failure, evaluate the quality normally.

Return JSON format: 
{{
    "model_a": {{
        "accuracy": <int>, 
        "fluency": <int>, 
        "consistency": <int>, 
        "terminology": <int>, 
        "completeness": <int>, 
        "suggestions": "<string>"
    }},
    "model_c": {{
        "accuracy": <int>, 
        "fluency": <int>, 
        "consistency": <int>, 
        "terminology": <int>, 
        "completeness": <int>, 
        "suggestions": "<string>"
    }}
}}"""
        result = self.evaluator.generate(prompt)
        
        # Parse combined result
        try:
            text = result.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```markdownjson" in text:
                text = text.split("```markdownjson")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(text)
            
            def parse_one(d):
                return EvaluationResult(
                    accuracy=int(d.get("accuracy", 0)),
                    fluency=int(d.get("fluency", 0)),
                    consistency=int(d.get("consistency", 0)),
                    terminology=int(d.get("terminology", 0)),
                    completeness=int(d.get("completeness", 0)),
                    suggestions=d.get("suggestions", "")
                )
                
            eval_a = parse_one(data.get("model_a", {}))
            eval_c = parse_one(data.get("model_c", {}))
            return eval_a, eval_c, result, prompt, result.text
            
        except Exception as e:
            logger.warning(f"Failed to parse comparative evaluation: {e}")
            empty = EvaluationResult(0,0,0,0,0,"Failed")
            return empty, empty, result, prompt, result.text

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def _translate_task(self, segment: TranslationSegment, source_lang: str, target_lang: str) -> Tuple[str, GenerationResult, str, str]:
        source_desc = f" from {source_lang}" if source_lang != "auto" else ""
        system_prompt = f"""You are a professional translator.
Task: Translate the user's text{source_desc} to {target_lang}.
Rules:
1. Maintain all formatting.
2. Keep any {{{{MATH_N}}}} placeholders unchanged. Do NOT add new ones.
3. Return ONLY the translated text. Do NOT include the original text, explanations, or notes.
4. If the text is already in {target_lang}, return it as is.
5. CRITICAL: The target language is {target_lang}. Do NOT translate to English unless {target_lang} is English.
6. Do NOT translate or transliterate alphanumeric codes, model numbers, or technical identifiers (e.g. keep "STR-1650", "RS8-500" as is).{self._get_lang_rules(target_lang)}
"""
        user_prompt = f"{segment.original_text}"
        result = self.translator.generate(user_prompt, system_prompt=system_prompt)
        text = result.text
        
        # Post-process to remove hallucinated placeholders
        # If LLM adds {{MATH_N}} that wasn't in original (not in math_elements), strip the tags
        # e.g. {{MATH_4}} -> 4
        def replace_invalid(match):
            placeholder = match.group(0)
            if placeholder not in segment.math_elements:
                # It's a hallucination. Return the number inside.
                # match.group(1) is the number N
                # But wait, the regex should capture the content?
                # Actually, usually it's {{MATH_N}}. 
                # Let's just strip {{MATH_ and }}
                return placeholder.replace("{{MATH_", "").replace("}}", "")
            return placeholder

        text = re.sub(r'\{\{MATH_(\d+)\}\}', lambda m: m.group(0) if m.group(0) in segment.math_elements else m.group(1), text)
        
        full_prompt = f"System: {system_prompt}\nUser: {user_prompt}"
        return text, result, full_prompt, result.text

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def _evaluate_task(self, original: str, translation: str, source_lang: str, target_lang: str) -> Tuple[EvaluationResult, GenerationResult, str, str]:
        prompt = f"""Evaluate the following translation from {source_lang} to {target_lang} on 5 dimensions: Accuracy, Fluency, Consistency, Terminology Accuracy, Completeness.
Original ({source_lang}): {original}
Translation ({target_lang}): {translation}

Provide a score (0-10) for each dimension and suggestions for improvement.
IMPORTANT: Provide suggestions in Chinese.

CRITICAL: Verify the translation status.
1. Check if the Translation is identical to the Original.
   - If YES, and the Original is NOT just numbers/symbols/proper nouns/codes, then it is a FAILURE (Untranslated). Score 0 for Accuracy and Completeness.
   - If YES, and the Original IS just numbers/symbols/codes/model numbers (e.g. "MTENTU-JKBG-2505"), it is acceptable and should receive a high score if correct.
2. Check if the Translation is in {target_lang}.
   - If NO, it is a FAILURE (Wrong Language). Score 0 for Accuracy and Completeness.
   - Note: The translation may contain numbers or symbols from the original, which is fine as long as the text parts are translated.
3. Check Number Formatting:{self._get_lang_rules(target_lang)}
   - If the translation violates these rules (e.g. wrong decimal separator for {target_lang}), penalize Accuracy and Fluency.

If it is NOT a failure, evaluate the quality normally.

Return JSON format: 
{{
    "accuracy": <int>, 
    "fluency": <int>, 
    "consistency": <int>, 
    "terminology": <int>, 
    "completeness": <int>, 
    "suggestions": "<string in Chinese>"
}}"""
        result = self.evaluator.generate(prompt)
        return self._parse_evaluation(result.text), result, prompt, result.text

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def _optimize_task(self, original: str, translation: str, suggestions: str, target_lang: str) -> Tuple[str, GenerationResult, str, str]:
        system_prompt = f"""You are a translation optimizer.
Task: Improve the translation based on the provided suggestions.
Target Language: {target_lang}
Rules:
1. Keep any {{{{MATH_N}}}} placeholders unchanged.
2. Return ONLY the optimized translation text. Do NOT return explanations or the original text.
3. If no changes are needed, return the Current Translation exactly.
4. CRITICAL: Ensure the result is in {target_lang}. Do NOT translate to English.
5. Do NOT translate or transliterate alphanumeric codes, model numbers, or technical identifiers.{self._get_lang_rules(target_lang)}
"""
        user_prompt = f"""Original: {original}
Current Translation: {translation}
Suggestions: {suggestions}"""
        
        result = self.optimizer.generate(user_prompt, system_prompt=system_prompt)
        full_prompt = f"System: {system_prompt}\nUser: {user_prompt}"
        return result.text, result, full_prompt, result.text
