import sys
import os
import re
from loguru import logger

def setup_logging(level="INFO"):
    logger.remove()
    logger.add(sys.stderr, level=level)

def parse_glossary(file_path: str) -> str:
    """
    Parses a markdown glossary file and returns a formatted string of terminology.
    Supports markdown tables and simple bullet points.
    """
    if not file_path or not os.path.exists(file_path):
        return ""
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        terms = []
        
        # 1. Try parsing markdown table
        # Format: | Source | Target |
        table_matches = re.findall(r'\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|', content)
        for src, tgt in table_matches:
            src = src.strip()
            tgt = tgt.strip()
            # Exclude headers and separators
            if src and tgt and src.lower() not in ["source", "original"] and not re.match(r'^-+$', src) and not re.match(r'^[:\-|\s]+$', src):
                terms.append(f"{src} -> {tgt}")
        
        # 2. Try parsing bullet points
        # Format: - Source: Target OR - Source -> Target
        # Only match if the target is NOT a table-like separator
        list_matches = re.findall(r'[-*+]\s+([^:\->\n]+?)\s*[:\->]\s*(.+)', content)
        for src, tgt in list_matches:
            src = src.strip()
            tgt = tgt.strip()
            if src and tgt and not re.match(r'^[:\-|\s]+$', tgt):
                terms.append(f"{src} -> {tgt}")
                
        if not terms:
            # If no structured matches, just return the whole content but stripped
            return content.strip()
            
        # Deduplicate and return
        seen = set()
        unique_terms = []
        for t in terms:
            if t not in seen:
                unique_terms.append(t)
                seen.add(t)
        
        return "\n".join(unique_terms)
    except Exception as e:
        logger.error(f"Failed to parse glossary {file_path}: {e}")
        return ""
