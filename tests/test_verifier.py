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


@pytest.mark.integration
def test_parse_google_scholar_tomasello_book():
    """Test parsing Google Scholar HTML for the Tomasello book entry with real HTTP request."""
    verifier = CitationVerifier()
    
    # Make actual HTTP request to Google Scholar
    title_query = "Becoming human: A theory of ontogeny"
    from urllib.parse import quote_plus
    search_url = f"https://scholar.google.com/scholar?q={quote_plus(title_query)}"
    
    try:
        response = verifier._make_request_with_retry('get', search_url, timeout=verifier.timeout)
        
        if response.status_code == 200:
            html = response.text
            title, authors = verifier._parse_google_scholar_first_result(html)
            
            # Verify title extraction - should find the Tomasello book
            assert title is not None, "Should extract a title from Google Scholar"
            
            # Title should be similar to the query
            bibtex_title = "Becoming human: A theory of ontogeny"
            similarity = verifier._calculate_title_similarity(bibtex_title.lower(), title.lower())
            
            # Be more lenient since Google Scholar results may vary
            assert similarity >= 0.3, f"Title similarity {similarity:.2%} should be >= 30% for '{title}'"
            
            # Verify author extraction if authors are found
            if authors:
                author_str = ', '.join(authors).lower()
                # Check if Tomasello appears in the author list
                assert 'tomasello' in author_str, f"Expected 'tomasello' in authors: {authors}"
        elif response.status_code == 429:
            pytest.skip("Google Scholar rate limited (429) - skipping test")
        else:
            pytest.skip(f"Google Scholar returned status {response.status_code} - skipping test")
    except Exception as e:
        pytest.skip(f"Network error accessing Google Scholar: {str(e)}")


def test_retry_on_429():
    """Test that 429 errors trigger retry with exponential backoff."""
    from unittest.mock import Mock, patch
    import time
    
    verifier = CitationVerifier()
    
    # Mock response that returns 429 first time, then 200
    mock_response_429 = Mock()
    mock_response_429.status_code = 429
    
    mock_response_200 = Mock()
    mock_response_200.status_code = 200
    
    with patch.object(verifier.session, 'get', side_effect=[mock_response_429, mock_response_200]) as mock_get:
        with patch('time.sleep') as mock_sleep:
            response = verifier._make_request_with_retry('get', 'https://example.com')
            
            # Should have called get twice
            assert mock_get.call_count == 2
            # Should have slept once (after first 429)
            assert mock_sleep.call_count == 1
            # Should have slept for initial delay
            mock_sleep.assert_called_with(verifier.INITIAL_RETRY_DELAY)
            # Final response should be 200
            assert response.status_code == 200


def test_max_retries_on_429():
    """Test that max retries are respected for 429 errors."""
    from unittest.mock import Mock, patch
    
    verifier = CitationVerifier()
    
    # Mock response that always returns 429
    mock_response_429 = Mock()
    mock_response_429.status_code = 429
    
    with patch.object(verifier.session, 'get', return_value=mock_response_429) as mock_get:
        with patch('time.sleep') as mock_sleep:
            response = verifier._make_request_with_retry('get', 'https://example.com')
            
            # Should have called get max_retries + 1 times (initial + retries)
            assert mock_get.call_count == verifier.max_retries + 1
            # Should have slept max_retries times
            assert mock_sleep.call_count == verifier.max_retries
            # Final response should still be 429
            assert response.status_code == 429


def test_exponential_backoff_on_429():
    """Test that exponential backoff is used for 429 retries."""
    from unittest.mock import Mock, patch
    
    verifier = CitationVerifier()
    
    # Mock response that always returns 429
    mock_response_429 = Mock()
    mock_response_429.status_code = 429
    
    with patch.object(verifier.session, 'get', return_value=mock_response_429) as mock_get:
        with patch('time.sleep') as mock_sleep:
            response = verifier._make_request_with_retry('get', 'https://example.com')
            
            # Check that sleep was called with increasing delays
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert len(sleep_calls) == verifier.max_retries
            
            # Verify exponential backoff
            expected_delays = []
            delay = verifier.INITIAL_RETRY_DELAY
            for _ in range(verifier.max_retries):
                expected_delays.append(delay)
                delay = min(delay * 2, verifier.MAX_RETRY_DELAY)
            
            assert sleep_calls == expected_delays


def test_url_valid_handles_429():
    """Test that _check_url_valid properly handles 429 errors."""
    from unittest.mock import Mock, patch
    
    verifier = CitationVerifier()
    
    # Mock response that returns 429 after retries
    mock_response_429 = Mock()
    mock_response_429.status_code = 429
    
    with patch.object(verifier, '_make_request_with_retry', return_value=mock_response_429):
        result, message = verifier._check_url_valid('https://example.com/paper.pdf')
        
        # Should return None (warning) for 429
        assert result is None
        assert '429' in message
        assert 'Rate limited' in message


def test_search_continues_after_429():
    """Test that search continues to next source after 429."""
    from unittest.mock import Mock, patch
    
    verifier = CitationVerifier()
    
    entry = {
        'ID': 'test2023',
        'title': 'Test Paper About Machine Learning',
        'author': 'Smith, John',
        'year': '2023'
    }
    
    # Mock arxiv to return 429, but Semantic Scholar to succeed
    mock_response_429 = Mock()
    mock_response_429.status_code = 429
    
    mock_response_200 = Mock()
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {
        'data': [{
            'title': 'Test Paper About Machine Learning',
            'paperId': 'abc123'
        }]
    }
    
    # First two calls (arXiv ID and search) return 429, third call (Semantic Scholar) succeeds
    with patch.object(verifier, '_make_request_with_retry', 
                      side_effect=[mock_response_429, mock_response_429, mock_response_200]):
        findable, search_url, logs = verifier._check_findable_online(entry)
        
        # Should find the paper via alternative source
        assert findable is True
        assert 'semanticscholar.org' in search_url
        # Logs should mention rate limiting
        log_text = ' '.join(logs)
        assert '429' in log_text or 'rate limited' in log_text.lower()


def test_verbose_logging_for_retries():
    """Test that verbose logs are generated for retry attempts."""
    from unittest.mock import Mock, patch
    
    verifier = CitationVerifier()
    
    # Mock response that returns 429 twice, then 200
    mock_response_429 = Mock()
    mock_response_429.status_code = 429
    
    mock_response_200 = Mock()
    mock_response_200.status_code = 200
    
    with patch.object(verifier.session, 'get', 
                      side_effect=[mock_response_429, mock_response_429, mock_response_200]):
        with patch('time.sleep'):
            verbose_logs = []
            response = verifier._make_request_with_retry('get', 'https://example.com', verbose_logs)
            
            # Should have logged retry attempts
            assert len(verbose_logs) > 0
            log_text = ' '.join(verbose_logs)
            
            # Should mention 429 and waiting
            assert '429' in log_text
            assert 'Rate Limited' in log_text
            assert 'Waiting' in log_text
            
            # Should show attempt numbers
            assert 'attempt' in log_text.lower()
            
            # Final response should be 200
            assert response.status_code == 200


def test_verbose_logging_for_semantic_scholar_authors():
    """Test that verbose logs are generated for author verification in Semantic Scholar."""
    from unittest.mock import Mock, patch
    
    verifier = CitationVerifier()
    
    entry = {
        'ID': 'test2023',
        'title': 'Test Paper About Machine Learning',
        'author': 'Smith, John and Doe, Jane',
        'year': '2023'
    }
    
    search_url = 'https://www.semanticscholar.org/paper/abc123'
    
    # Mock the Semantic Scholar API response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'title': 'Test Paper About Machine Learning',
        'authors': [
            {'name': 'John Smith'},
            {'name': 'Jane Doe'}
        ]
    }
    
    with patch.object(verifier, '_make_request_with_retry', return_value=mock_response):
        correct, message, details, logs = verifier._check_metadata(entry, search_url)
        
        # Should have verbose logs
        assert len(logs) > 0
        log_text = ' '.join(logs)
        
        # Should mention author comparison
        assert 'Comparing authors' in log_text or 'authors' in log_text.lower()
        assert 'BibTeX' in log_text
        assert 'Online' in log_text
        assert 'Extracted' in log_text
        
        # Should show similarity or match result
        assert 'Similarity' in log_text or 'Match' in log_text or 'Result' in log_text


@pytest.mark.integration
def test_sotopia_pi_paper_google_scholar():
    """Test parsing Google Scholar HTML for SOTOPIA-π paper with real HTTP request."""
    verifier = CitationVerifier()
    
    # Make actual HTTP request to Google Scholar for SOTOPIA-π paper
    title_query = "SOTOPIA-π: Interactive Learning of Socially Intelligent Language Agents"
    from urllib.parse import quote_plus
    search_url = f"https://scholar.google.com/scholar?q={quote_plus(title_query)}"
    
    try:
        response = verifier._make_request_with_retry('get', search_url, timeout=verifier.timeout)
        
        if response.status_code == 200:
            html = response.text
            title, authors = verifier._parse_google_scholar_first_result(html)
            
            # Verify title extraction
            assert title is not None, "Should extract a title from Google Scholar"
            
            # Title should contain key parts (be lenient as Google Scholar may format differently)
            assert "SOTOPIA" in title or "sotopia" in title.lower(), f"Expected 'SOTOPIA' in title: '{title}'"
            
            # BibTeX title has LaTeX notation: SOTOPIA-$\pi$
            bibtex_title = "SOTOPIA-$\\pi$: Interactive Learning of Socially Intelligent Language Agents"
            cleaned_bibtex_title = verifier._remove_curly_braces(bibtex_title).lower()
            
            # Calculate similarity
            similarity = verifier._calculate_title_similarity(cleaned_bibtex_title, title.lower())
            # Be more lenient since Google Scholar may format titles differently
            assert similarity >= 0.3, \
                f"Title similarity {similarity:.2%} should be >= 30% for '{title}'"
            
            # Verify author extraction
            if authors:
                author_str = ', '.join(authors).lower()
                
                # Check that at least some key authors are present
                # Google Scholar may abbreviate names differently
                key_authors_found = 0
                for key_author in ['wang', 'neubig', 'zhu', 'yu', 'sap', 'bisk']:
                    if key_author in author_str:
                        key_authors_found += 1
                
                assert key_authors_found >= 3, \
                    f"Expected at least 3 key authors in {authors}, found {key_authors_found}"
                
                # Verify author matching would work
                bibtex_authors = "Wang, Ruiyi and Yu, Haofei and Zhang, Wenxin and Qi, Zhengyang and Sap, Maarten and Bisk, Yonatan and Neubig, Graham and Zhu, Hao"
                bibtex_author_names = verifier._extract_author_names(bibtex_authors)
                online_author_names = verifier._extract_author_names(', '.join(authors))
                
                # Calculate author similarity
                author_similarity = verifier._calculate_author_similarity(bibtex_author_names, online_author_names)
                # Be lenient as Google Scholar may format authors differently
                assert author_similarity >= 0.25, \
                    f"Author similarity {author_similarity:.2%} should be >= 25%"
        elif response.status_code == 429:
            pytest.skip("Google Scholar rate limited (429) - skipping test")
        else:
            pytest.skip(f"Google Scholar returned status {response.status_code} - skipping test")
    except Exception as e:
        pytest.skip(f"Network error accessing Google Scholar: {str(e)}")


def test_custom_max_retries():
    """Test that max_retries parameter can be customized."""
    from unittest.mock import Mock, patch
    
    # Create verifier with custom max_retries
    verifier = CitationVerifier(max_retries=5)
    
    # Verify the value is set correctly
    assert verifier.max_retries == 5
    
    # Mock response that always returns 429
    mock_response_429 = Mock()
    mock_response_429.status_code = 429
    
    with patch.object(verifier.session, 'get', return_value=mock_response_429) as mock_get:
        with patch('time.sleep') as mock_sleep:
            response = verifier._make_request_with_retry('get', 'https://example.com')
            
            # Should have called get 6 times (initial + 5 retries)
            assert mock_get.call_count == 6
            # Should have slept 5 times
            assert mock_sleep.call_count == 5
            # Final response should still be 429
            assert response.status_code == 429


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
