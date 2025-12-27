from typing import List, Dict, Any, Tuple, Callable
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
    def __init__(self, translator: LLMBase, evaluator: LLMBase, optimizer: LLMBase, concurrency_config: Dict[str, int] = None, glossary: str = ""):
        self.translator = translator
        self.evaluator = evaluator
        self.optimizer = optimizer
        self.concurrency_config = concurrency_config or {}
        self.glossary = glossary
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
        """Check if segment is simple (number, symbol, placeholder, punctuation) and shouldn't be processed."""
        text = text.strip()
        if not text: return True
        # Check if it's just a placeholder
        if re.match(r'^\{\{MATH_\d+\}\}$', text): return True
        # Check if it's just numbers, symbols, OR punctuation only
        # This includes things like "-", "...", "!!!", "4.1.2", etc.
        if re.match(r'^[\d\.\,\%\-\+\=\/\(\)\[\]\s«»""\'\'!?;:¿¡*&#@^_~`|\\<>]+$', text): return True
        return False

    def _get_lang_rules(self, target_lang: str) -> str:
        rules = ""
        # Russian uses comma for decimals
        if any(x in target_lang.lower() for x in ["russian", "ru", "俄语"]):
            rules += "\n7. Number Formatting: Use comma ',' for decimals (e.g. 0.008 -> 0,008). CRITICAL: Do NOT change dots '.' in serial numbers, section numbers (e.g. 1.1, 2.1.3), version numbers, or model codes."
        return rules

    def run(self, segments: List[TranslationSegment], source_lang: str = "auto", target_lang: str = "Chinese", progress_callback: Callable[[float, str], None] = None) -> Tuple[List[WorkflowResult], Dict]:
        self._load_cache()
        results_map: Dict[str, WorkflowResult] = {
            seg.id: WorkflowResult(segment_id=seg.id, original=seg.original_text) 
            for seg in segments
        }
        
        def _update_progress(stage_start, stage_end, current, total, desc):
            if progress_callback:
                # Calculate overall progress
                # stage_start + (current / total) * (stage_end - stage_start)
                progress = stage_start + (current / total) * (stage_end - stage_start)
                progress_callback(progress, desc)
        
        
        # Get concurrency settings (default 32)
        workers_trans = self.concurrency_config.get("translation", 32)
        workers_eval1 = self.concurrency_config.get("evaluation_1", 32)
        workers_opt = self.concurrency_config.get("optimization", 32)
        workers_eval2 = self.concurrency_config.get("evaluation_2", 32)
        
        # Stage 1: Translation (0.0 - 0.3)
        print(f"\n[Stage 1/5] Translating segments (Source: {source_lang}, Target: {target_lang})...")
        _update_progress(0.0, 0.3, 0, len(segments), "Starting Translation...")
        with ThreadPoolExecutor(max_workers=workers_trans) as executor:
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

            completed = 0
            for future in tqdm(as_completed(future_to_seg), total=len(future_to_seg), colour='green', desc="Translation"):
                completed += 1
                _update_progress(0.0, 0.3, completed, len(segments), f"Translating {completed}/{len(segments)}")
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
            _update_progress(0.3, 0.35, 0, len(failed_segments), "Repairing failed translations...")
            with ThreadPoolExecutor(max_workers=workers_trans) as executor:
                future_to_seg = {}
                for seg in failed_segments:
                    # Retry translation
                    future = executor.submit(self._translate_task, seg, source_lang, target_lang)
                    future_to_seg[future] = seg
                
                completed = 0
                for future in tqdm(as_completed(future_to_seg), total=len(future_to_seg), colour='red', desc="Repair"):
                    completed += 1
                    _update_progress(0.3, 0.35, completed, len(failed_segments), f"Repairing {completed}/{len(failed_segments)}")
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

        # Stage 2: Evaluation 1 (0.35 - 0.55)
        print("\n[Stage 2/5] Evaluating initial translations...")
        _update_progress(0.35, 0.55, 0, len(segments), "Starting Evaluation 1...")
        with ThreadPoolExecutor(max_workers=workers_eval1) as executor:
            future_to_seg = {}
            for seg in segments:
                # Skip if skipped or cached in Stage 1
                if results_map[seg.id].selected_model in ["Skipped (Simple)"]:
                    results_map[seg.id].eval_a = EvaluationResult(10,10,10,10,10,"Simple segment, no evaluation needed.")
                    continue
                
                # Bypass evaluation if same language
                if source_lang.lower() == target_lang.lower() and source_lang != "auto":
                    results_map[seg.id].eval_a = EvaluationResult(10,10,10,10,10,"Source and Target languages are the same.")
                    continue

                future = executor.submit(self._evaluate_task, results_map[seg.id].original, results_map[seg.id].translation_a, source_lang, target_lang)
                future_to_seg[future] = seg

            completed = 0
            for future in tqdm(as_completed(future_to_seg), total=len(future_to_seg), colour='blue', desc="Evaluation 1"):
                completed += 1
                _update_progress(0.35, 0.55, completed, len(segments), f"Evaluating {completed}/{len(segments)}")
                seg = future_to_seg[future]
                try:
                    eval_res, usage, prompt, raw_response = future.result()
                    results_map[seg.id].eval_a = eval_res
                    results_map[seg.id].eval_a_prompt = prompt
                    results_map[seg.id].eval_a_raw_response = raw_response
                    self._track_usage("evaluation_1", usage)
                except Exception as e:
                    logger.error(f"Evaluation 1 failed for {seg.id}: {e}")

        # Stage 3: Optimization (0.55 - 0.75)
        print("\n[Stage 3/5] Optimizing translations...")
        _update_progress(0.55, 0.75, 0, len(segments), "Starting Optimization...")
        with ThreadPoolExecutor(max_workers=workers_opt) as executor:
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

            completed = 0
            for future in tqdm(as_completed(future_to_seg), total=len(future_to_seg), colour='yellow', desc="Optimization"):
                completed += 1
                _update_progress(0.55, 0.75, completed, len(segments), f"Optimizing {completed}/{len(segments)}")
                seg = future_to_seg[future]
                try:
                    opt_text, usage, prompt, raw_response = future.result()
                    results_map[seg.id].translation_c = opt_text
                    results_map[seg.id].translation_c_prompt = prompt
                    results_map[seg.id].translation_c_raw_response = raw_response
                    self._track_usage("optimization", usage)
                except Exception as e:
                    logger.error(f"Optimization failed for {seg.id}: {e}")

        # Stage 4: Comparative Evaluation (0.75 - 0.95)
        print("\n[Stage 4/5] Comparative Evaluation (A vs C)...")
        _update_progress(0.75, 0.95, 0, len(segments), "Starting Comparative Evaluation...")
        with ThreadPoolExecutor(max_workers=workers_eval2) as executor:
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

            completed = 0
            for future in tqdm(as_completed(future_to_seg), total=len(future_to_seg), colour='magenta', desc="Final Evaluation"):
                completed += 1
                _update_progress(0.75, 0.95, completed, len(segments), f"Comparing {completed}/{len(segments)}")
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

        # Stage 5: Selection (0.95 - 1.0)
        print("\n[Stage 5/5] Selecting best translations...")
        _update_progress(0.95, 1.0, 0, 1, "Finalizing...")
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
        source_detect_instr = f"Identify the source language of the 'Original' text (currently indicated as '{source_lang}')." if source_lang == "auto" else f"The source language is {source_lang}."
        
        glossary_instr = ""
        if self.glossary:
            glossary_instr = f"\nTerminology constraints (Must follow):\n{self.glossary}\n"

        prompt = f"""Evaluate the two translations provided below.
 
Context:
- {source_detect_instr}
- The target language is {target_lang}.
{glossary_instr}
 
Content to Evaluate:
Original: {original}
Model A Translation: {trans_a}
Model C Translation: {trans_c}
 
Evaluation Dimensions (0-10): Accuracy, Fluency, Consistency, Terminology Accuracy, Completeness.
 
CRITICAL RULES for 'Untranslated' or 'Same Language' scenarios:
1. If the translation is identical to the original:
   - If the source and target languages are the same (or the content is already in the target language), this is CORRECT. Score 10 for Accuracy.
   - If the content is a universal code, model number, or technical identifier (e.g., 'MTENTU-JKBG-2505'), this is CORRECT. Score 10 for Accuracy.
   - If the content SHOULD have been translated but wasn't, it is a FAILURE (Untranslated). Score 0 for Accuracy and Completeness.
2. Mixed Content: If the translation contains both translated text and original numbers/symbols, evaluate the quality of the translated parts.
3. Wrong Language: If the translation is in a language other than {target_lang}, score 0 for Accuracy.
4. Number Formatting:{self._get_lang_rules(target_lang)}
5. Terminology: If terminology is provided, model must adhere to it strictly. Failure to do so should result in a low Terminology Accuracy score.
 
Identify the source language first, then provide a score (0-10) for each dimension and suggestions for improvement (in Chinese).
 
Return JSON format: 
{{
    "detected_source_lang": "<string>",
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
        
        glossary_instr = ""
        if self.glossary:
            glossary_instr = f"\n7. Terminology: Strictly follow these terms:\n{self.glossary}\n"

        system_prompt = f"""You are a professional translator.
Task: Translate the user's text{source_desc} to {target_lang}.
Rules:
1. Maintain all formatting.
2. Keep any {{{{MATH_N}}}} placeholders unchanged. Do NOT add new ones.
3. Return ONLY the translated text. Do NOT include the original text, explanations, or notes.
4. If the text is already in {target_lang}, return it as is.
5. CRITICAL: The target language is {target_lang}. Do NOT translate to English unless {target_lang} is English.
6. Do NOT translate or transliterate alphanumeric codes, model numbers, or technical identifiers (e.g. keep "STR-1650", "RS8-500" as is).{self._get_lang_rules(target_lang)}{glossary_instr}
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
        source_detect_instr = f"Identify the source language of the 'Original' text (currently indicated as '{source_lang}')." if source_lang == "auto" else f"The source language is {source_lang}."
        
        glossary_instr = ""
        if self.glossary:
            glossary_instr = f"\nTerminology constraints (Must follow):\n{self.glossary}\n"

        prompt = f"""Evaluate the translation provided below.
 
Context:
- {source_detect_instr}
- The target language is {target_lang}.
{glossary_instr}
 
Content to Evaluate:
Original: {original}
Translation: {translation}
 
Evaluation Dimensions (0-10): Accuracy, Fluency, Consistency, Terminology Accuracy, Completeness.
 
CRITICAL RULES for 'Untranslated' or 'Same Language' scenarios:
1. If the translation is identical to the original:
   - If the source and target languages are the same (or the content is already in the target language), this is CORRECT. Score 10 for Accuracy.
   - If the content is a universal code, model number, or technical identifier (e.g., 'MTENTU-JKBG-2505'), this is CORRECT. Score 10 for Accuracy.
   - If the content SHOULD have been translated but wasn't, it is a FAILURE (Untranslated). Score 0 for Accuracy and Completeness.
2. Mixed Content: If the translation contains both translated text and original numbers/symbols, evaluate the quality of the translated parts.
3. Wrong Language: If the translation is in a language other than {target_lang}, score 0 for Accuracy.
4. Number Formatting:{self._get_lang_rules(target_lang)}
5. Terminology: If terminology is provided, model must adhere to it strictly. Failure to do so should result in a low Terminology Accuracy score.
 
Identify the source language first, then provide a score (0-10) for each dimension and suggestions for improvement (in Chinese).
 
Return JSON format: 
{{
    "detected_source_lang": "<string>",
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
        glossary_instr = ""
        if self.glossary:
            glossary_instr = f"\n6. Terminology: Strictly follow these terms:\n{self.glossary}\n"

        system_prompt = f"""You are a translation optimizer.
Task: Improve the translation based on the provided suggestions.
Target Language: {target_lang}
Rules:
1. Keep any {{{{MATH_N}}}} placeholders unchanged.
2. Return ONLY the optimized translation text. Do NOT return explanations or the original text.
3. If no changes are needed, return the Current Translation exactly.
4. CRITICAL: Ensure the result is in {target_lang}. Do NOT translate to English.
5. Do NOT translate or transliterate alphanumeric codes, model numbers, or technical identifiers.{self._get_lang_rules(target_lang)}{glossary_instr}
"""
        user_prompt = f"""Original: {original}
Current Translation: {translation}
Suggestions: {suggestions}"""
        
        result = self.optimizer.generate(user_prompt, system_prompt=system_prompt)
        full_prompt = f"System: {system_prompt}\nUser: {user_prompt}"
        return result.text, result, full_prompt, result.text
