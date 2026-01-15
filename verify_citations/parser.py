"""
BibTeX file parsing utilities.
"""

from typing import List, Dict
import bibtexparser
from bibtexparser.bparser import BibTexParser


def parse_bibtex_file(filepath: str) -> List[Dict]:
    """
    Parse a BibTeX file and return list of entries.
    
    Args:
        filepath: Path to the BibTeX file
        
    Returns:
        List of entry dictionaries
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        parser = BibTexParser(common_strings=True)
        bib_database = bibtexparser.load(f, parser=parser)
        return bib_database.entries


def format_entry_summary(entry: Dict) -> str:
    """
    Format a BibTeX entry as a human-readable summary.
    
    Args:
        entry: BibTeX entry dictionary
        
    Returns:
        Formatted string
    """
    title = entry.get('title', 'No title').strip('{}')
    authors = entry.get('author', 'Unknown authors')
    year = entry.get('year', 'Unknown year')
    entry_id = entry.get('ID', 'Unknown')
    
    return f"[{entry_id}] {title} ({authors}, {year})"
