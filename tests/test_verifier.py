"""
Tests for citation verification functionality.
"""

import os
import tempfile

import pytest

from verify_citations.parser import parse_bibtex_file, format_entry_summary
from verify_citations.verifier import CitationVerifier


def test_parse_bibtex_file():
    """Test parsing a BibTeX file."""
    # Create a temporary BibTeX file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bib', delete=False) as f:
        f.write("""
@article{test2023,
  title={Test Paper},
  author={Smith, John},
  year={2023},
  journal={Test Journal}
}
""")
        temp_path = f.name
    
    try:
        entries = parse_bibtex_file(temp_path)
        assert len(entries) == 1
        assert entries[0]['ID'] == 'test2023'
        assert 'Test Paper' in entries[0]['title']
        assert entries[0]['year'] == '2023'
    finally:
        os.unlink(temp_path)


def test_format_entry_summary():
    """Test formatting a BibTeX entry."""
    entry = {
        'ID': 'smith2023',
        'title': 'A Great Paper',
        'author': 'Smith, John',
        'year': '2023'
    }
    
    summary = format_entry_summary(entry)
    assert 'smith2023' in summary
    assert 'A Great Paper' in summary
    assert 'Smith, John' in summary
    assert '2023' in summary


def test_citation_verifier_init():
    """Test CitationVerifier initialization."""
    verifier = CitationVerifier(timeout=5)
    assert verifier.timeout == 5
    assert verifier.session is not None


def test_verify_citation_basic():
    """Test basic citation verification."""
    verifier = CitationVerifier()
    entry = {
        'ID': 'test2023',
        'title': 'Test Paper',
        'author': 'Smith, John',
        'year': '2023'
    }
    
    result = verifier.verify_citation(entry)
    
    assert result['id'] == 'test2023'
    assert result['title'] == 'Test Paper'
    assert 'checks' in result
    assert 'findable_online' in result['checks']
    assert 'url_valid' in result['checks']
    assert 'metadata_correct' in result['checks']
    assert 'version_info' in result['checks']
    assert 'messages' in result
    assert 'status' in result


def test_extract_arxiv_id():
    """Test arXiv ID extraction."""
    verifier = CitationVerifier()
    
    # Test various arXiv URL formats
    assert verifier._extract_arxiv_id('https://arxiv.org/abs/1706.03762') == '1706.03762'
    assert verifier._extract_arxiv_id('https://arxiv.org/pdf/1810.04805.pdf') == '1810.04805'
    assert verifier._extract_arxiv_id('1706.03762') == '1706.03762'
    assert verifier._extract_arxiv_id('') is None
    assert verifier._extract_arxiv_id('https://example.com') is None


def test_version_info_extraction():
    """Test version information extraction."""
    verifier = CitationVerifier()
    
    # Test with arXiv
    entry = {
        'ID': 'test1',
        'eprint': '1706.03762',
        'journal': 'Nature'
    }
    version_info = verifier._check_version_info(entry)
    assert 'arXiv:1706.03762' in version_info
    assert 'Journal: Nature' in version_info
    
    # Test with conference
    entry = {
        'ID': 'test2',
        'booktitle': 'NeurIPS 2023',
        'doi': '10.1234/test'
    }
    version_info = verifier._check_version_info(entry)
    assert 'Conference: NeurIPS 2023' in version_info
    assert 'DOI: 10.1234/test' in version_info


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
