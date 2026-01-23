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


def test_extract_author_names():
    """Test author name extraction."""
    verifier = CitationVerifier()
    
    # Test "Last, First and Last, First" format
    authors = "Smith, John and Doe, Jane"
    names = verifier._extract_author_names(authors)
    assert 'smith' in names
    assert 'doe' in names
    
    # Test "First Last" format
    authors = "John Smith and Jane Doe"
    names = verifier._extract_author_names(authors)
    assert 'smith' in names
    assert 'doe' in names
    
    # Test mixed format
    authors = "Smith, John and Jane Doe and Brown, Alice"
    names = verifier._extract_author_names(authors)
    assert 'smith' in names
    assert 'doe' in names
    assert 'brown' in names
    
    # Test with "and others"
    authors = "Smith, John and Doe, Jane and others"
    names = verifier._extract_author_names(authors)
    assert 'smith' in names
    assert 'doe' in names
    assert 'others' not in names
    
    # Test LaTeX special characters
    authors = r"Kaiser, {\L}ukasz"
    names = verifier._extract_author_names(authors)
    assert 'kaiser' in names


def test_fuzzy_author_matching():
    """Test fuzzy matching for author names."""
    verifier = CitationVerifier()
    
    # Test exact match
    assert verifier._fuzzy_match('smith', 'smith') is True
    
    # Test small typo (1 character difference)
    assert verifier._fuzzy_match('smith', 'smoth') is True
    
    # Test 2 character difference
    assert verifier._fuzzy_match('johnson', 'jonson') is True
    
    # Test too different
    assert verifier._fuzzy_match('smith', 'jones') is False
    
    # Test length difference
    assert verifier._fuzzy_match('ab', 'abcde') is False


def test_author_similarity_with_format_differences():
    """Test that author similarity handles name format differences."""
    verifier = CitationVerifier()
    
    # Same authors, different format
    # BibTeX: "Last, First" format
    bibtex_authors = "Vaswani, Ashish and Shazeer, Noam"
    # Online: "First Last" format  
    online_authors = "Ashish Vaswani and Noam Shazeer"
    
    bibtex_names = verifier._extract_author_names(bibtex_authors)
    online_names = verifier._extract_author_names(online_authors)
    
    similarity = verifier._calculate_author_similarity(bibtex_names, online_names)
    
    # Should match since it's the same authors
    assert similarity >= 0.5, f"Similarity {similarity} should be >= 0.5 for same authors"


def test_author_extraction_comma_separated():
    """Test author extraction with comma-separated format."""
    verifier = CitationVerifier()
    
    # Online format: comma-separated "First Last, First Last"
    online_authors = "Jacob Devlin, Ming-Wei Chang, Kenton Lee, Kristina Toutanova"
    online_names = verifier._extract_author_names(online_authors)
    
    assert 'devlin' in online_names
    assert 'chang' in online_names
    assert 'lee' in online_names
    assert 'toutanova' in online_names
    assert len(online_names) == 4
    
    # BibTeX format: "Last, First and Last, First"
    bibtex_authors = "Devlin, Jacob and Chang, Ming-Wei and Lee, Kenton and Toutanova, Kristina"
    bibtex_names = verifier._extract_author_names(bibtex_authors)
    
    assert bibtex_names == online_names, "Should extract same names from both formats"


def test_remove_curly_braces():
    """Test removal of curly braces from titles."""
    verifier = CitationVerifier()
    
    # Test with curly braces in the middle
    assert verifier._remove_curly_braces("Monitoring Human Dependence On {AI} Systems") == "Monitoring Human Dependence On AI Systems"
    
    # Test with multiple curly braces
    assert verifier._remove_curly_braces("{Deep} Learning with {GPU}s") == "Deep Learning with GPUs"
    
    # Test with nested curly braces
    assert verifier._remove_curly_braces("Title with {{nested}} braces") == "Title with nested braces"
    
    # Test with no curly braces
    assert verifier._remove_curly_braces("Normal Title") == "Normal Title"
    
    # Test empty string
    assert verifier._remove_curly_braces("") == ""


def test_title_similarity_with_curly_braces():
    """Test that title similarity handles curly braces correctly."""
    verifier = CitationVerifier()
    
    # Titles should be identical after removing curly braces
    title1 = "Monitoring Human Dependence On {AI} Systems With Reliance Drills"
    title2 = "Monitoring Human Dependence On AI Systems With Reliance Drills"
    
    similarity = verifier._calculate_title_similarity(title1, title2)
    
    # Should be 100% match after removing curly braces
    assert similarity == 1.0, f"Similarity should be 1.0 but got {similarity}"


def test_title_similarity_case_insensitive():
    """Test that title similarity is case insensitive."""
    verifier = CitationVerifier()
    
    # Same titles with different cases
    title1 = "Deep Learning for Natural Language Processing"
    title2 = "DEEP LEARNING FOR NATURAL LANGUAGE PROCESSING"
    
    similarity = verifier._calculate_title_similarity(title1, title2)
    
    # Should be 100% match
    assert similarity == 1.0, f"Similarity should be 1.0 but got {similarity}"


def test_title_similarity_with_difflib():
    """Test that title similarity uses difflib for partial matches."""
    verifier = CitationVerifier()
    
    # Similar but not identical titles
    title1 = "Deep Learning for NLP"
    title2 = "Deep Learning for Natural Language Processing"
    
    similarity = verifier._calculate_title_similarity(title1, title2)
    
    # Should have some similarity (not 0, not 1)
    assert 0 < similarity < 1, f"Similarity should be between 0 and 1 but got {similarity}"


def test_exact_issue_scenario():
    """Test the exact scenario from the GitHub issue."""
    verifier = CitationVerifier()
    
    # Exact titles from the issue
    bibtex_title = "Monitoring Human Dependence On {AI} Systems With Reliance Drills"
    online_title = "Monitoring Human Dependence On AI Systems With Reliance Drills"
    
    similarity = verifier._calculate_title_similarity(bibtex_title, online_title)
    
    # After curly brace removal and lowercase, they should be 100% match
    assert similarity == 1.0, f"Expected 100% similarity but got {similarity:.2%}"
    
    # Also verify that the threshold check passes
    assert verifier._titles_similar(bibtex_title, online_title), "Titles should be considered similar"


def test_parse_google_scholar_first_result_basic():
    """Test parsing Google Scholar HTML with basic structure."""
    verifier = CitationVerifier()
    
    # Minimal Google Scholar HTML with first result
    html = """
    <div id="gs_res_ccl_mid">
        <div class="gs_r gs_or">
            <h3 class="gs_rt">
                <a href="https://example.com/paper.pdf">Attention is All You Need</a>
            </h3>
            <div class="gs_a">
                A Vaswani, N Shazeer, N Parmar - Conference, 2017 - arxiv.org
            </div>
        </div>
    </div>
    """
    
    title, authors = verifier._parse_google_scholar_first_result(html)
    
    assert title == "Attention is All You Need"
    assert authors is not None
    assert len(authors) == 3
    assert "A Vaswani" in authors
    assert "N Shazeer" in authors
    assert "N Parmar" in authors


def test_parse_google_scholar_first_result_with_prefix():
    """Test parsing Google Scholar HTML with [PDF] or [HTML] prefix."""
    verifier = CitationVerifier()
    
    # Google Scholar HTML with [PDF] prefix
    html = """
    <div id="gs_res_ccl_mid">
        <div class="gs_r gs_or">
            <h3 class="gs_rt">
                <a href="https://example.com/paper.pdf">[PDF] Attention is All You Need</a>
            </h3>
            <div class="gs_a">
                A Vaswani, N Shazeer - Conference, 2017 - arxiv.org
            </div>
        </div>
    </div>
    """
    
    title, authors = verifier._parse_google_scholar_first_result(html)
    
    # Title should have [PDF] prefix removed
    assert title == "Attention is All You Need"
    assert authors is not None
    assert len(authors) == 2


def test_parse_google_scholar_first_result_with_ellipsis():
    """Test parsing Google Scholar HTML with ellipsis in authors."""
    verifier = CitationVerifier()
    
    # Google Scholar HTML with ellipsis (indicating more authors)
    html = """
    <div id="gs_res_ccl_mid">
        <div class="gs_r gs_or">
            <h3 class="gs_rt">
                <a href="https://example.com/paper.pdf">BERT: Pre-training of Deep Bidirectional Transformers</a>
            </h3>
            <div class="gs_a">
                J Devlin, MW Chang, K Lee, K Toutanova… - arXiv preprint, 2018 - arxiv.org
            </div>
        </div>
    </div>
    """
    
    title, authors = verifier._parse_google_scholar_first_result(html)
    
    assert title == "BERT: Pre-training of Deep Bidirectional Transformers"
    assert authors is not None
    # Ellipsis should be removed
    assert len(authors) == 4
    assert "K Toutanova" in authors
    # Ellipsis character should not be in last author name
    assert not any('…' in author for author in authors)


def test_parse_google_scholar_first_result_with_ascii_ellipsis():
    """Test parsing Google Scholar HTML with ASCII ellipsis (...) in authors."""
    verifier = CitationVerifier()
    
    # Google Scholar HTML with ASCII ellipsis
    html = """
    <div id="gs_res_ccl_mid">
        <div class="gs_r gs_or">
            <h3 class="gs_rt">
                <a href="https://example.com/paper.pdf">Test Paper</a>
            </h3>
            <div class="gs_a">
                J Smith, A Johnson, B Williams... - Conference, 2021 - example.com
            </div>
        </div>
    </div>
    """
    
    title, authors = verifier._parse_google_scholar_first_result(html)
    
    assert title == "Test Paper"
    assert authors is not None
    # ASCII ellipsis should be removed
    assert len(authors) == 3
    assert "B Williams" in authors
    # ASCII ellipsis should not be in last author name
    assert not any('...' in author for author in authors)
    assert not any('.' in authors[-1] for char in '.')  # No trailing periods


def test_parse_google_scholar_first_result_no_anchor():
    """Test parsing Google Scholar HTML when title has no anchor tag."""
    verifier = CitationVerifier()
    
    # Some results may not have clickable links
    html = """
    <div id="gs_res_ccl_mid">
        <div class="gs_r gs_or">
            <h3 class="gs_rt">
                [CITATION] Some Non-Clickable Paper
            </h3>
            <div class="gs_a">
                J Smith, A Jones - Journal, 2020 - publisher.com
            </div>
        </div>
    </div>
    """
    
    title, authors = verifier._parse_google_scholar_first_result(html)
    
    # Should still extract title even without anchor, and remove [CITATION] prefix
    assert title == "Some Non-Clickable Paper"
    assert authors is not None
    assert len(authors) == 2


def test_parse_google_scholar_first_result_fallback_to_gs_r():
    """Test parsing Google Scholar HTML with fallback to gs_r class."""
    verifier = CitationVerifier()
    
    # Use gs_r instead of gs_r gs_or
    html = """
    <div id="gs_res_ccl_mid">
        <div class="gs_r">
            <h3 class="gs_rt">
                <a href="https://example.com/paper.pdf">Test Paper Title</a>
            </h3>
            <div class="gs_a">
                A Author, B Writer - Conference, 2021 - example.com
            </div>
        </div>
    </div>
    """
    
    title, authors = verifier._parse_google_scholar_first_result(html)
    
    assert title == "Test Paper Title"
    assert authors is not None
    assert len(authors) == 2


def test_parse_google_scholar_first_result_no_container():
    """Test parsing Google Scholar HTML when container is missing."""
    verifier = CitationVerifier()
    
    # Missing gs_res_ccl_mid container
    html = """
    <div>
        <div class="gs_r gs_or">
            <h3 class="gs_rt">
                <a href="https://example.com/paper.pdf">Test Paper</a>
            </h3>
        </div>
    </div>
    """
    
    title, authors = verifier._parse_google_scholar_first_result(html)
    
    # Should return None when container is missing
    assert title is None
    assert authors is None


def test_parse_google_scholar_first_result_no_result():
    """Test parsing Google Scholar HTML when no results are present."""
    verifier = CitationVerifier()
    
    # Container exists but no results
    html = """
    <div id="gs_res_ccl_mid">
        <div class="gs_no_results">No results found</div>
    </div>
    """
    
    title, authors = verifier._parse_google_scholar_first_result(html)
    
    # Should return None when no results found
    assert title is None
    assert authors is None


def test_parse_google_scholar_first_result_malformed_html():
    """Test parsing Google Scholar HTML when HTML is malformed."""
    verifier = CitationVerifier()
    
    # Malformed or incomplete HTML
    html = """
    <div id="gs_res_ccl_mid">
        <div class="gs_r gs_or">
            <h3 class="gs_rt">
    """
    
    title, authors = verifier._parse_google_scholar_first_result(html)
    
    # Should handle gracefully and return None or empty string
    assert title is None or title == ""
    assert authors is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
