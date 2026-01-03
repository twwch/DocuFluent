import sys
import os
import re
from loguru import logger

def setup_logging(level="INFO"):
    logger.remove()
    logger.add(sys.stderr, level=level)

from typing import List, Tuple

def parse_glossary_text(content: str) -> List[Tuple[str, str]]:
    """
    Parses a markdown glossary string and returns a list of (Source, Target) tuples.
    Supports markdown tables and simple bullet points.
    """
    if not content:
        return []
    
    terms = []
    lines = content.split("\n")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 1. Try parsing markdown table row
        # Format: | Source | Target | ... |
        if line.startswith("|") and line.endswith("|"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                src, tgt = parts[0], parts[1]
                # Exclude headers and separators
                if src.lower() not in ["source", "original", "原文"] and not re.match(r'^[:\-|\s]+$', src):
                    terms.append((src, tgt))
            continue

        # 2. Try parsing bullet points or lines
        # Format: - Source: Target OR - Source -> Target
        list_match = re.match(r'^(?:[-*+]\s+)?([^:\-\n]+?)\s*(?:->|[:\-])\s*(.+)$', line)
        if list_match:
            src, tgt = list_match.groups()
            src = src.strip()
            tgt = tgt.strip()
            if src and tgt and not re.match(r'^[:\-|\s]+$', tgt):
                terms.append((src, tgt))
                
    # Deduplicate while preserving order
    seen = set()
    unique_terms = []
    for src, tgt in terms:
        if (src, tgt) not in seen:
            unique_terms.append((src, tgt))
            seen.add((src, tgt))
    
    return unique_terms

def parse_glossary(file_path: str) -> str:
    """
    Parses a markdown glossary file and returns a formatted string of terminology for LLM.
    """
    if not file_path or not os.path.exists(file_path):
        return ""
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        terms = parse_glossary_text(content)
        return "\n".join([f"{src} -> {tgt}" for src, tgt in terms])
    except Exception as e:
        logger.error(f"Failed to parse glossary {file_path}: {e}")
        return ""
