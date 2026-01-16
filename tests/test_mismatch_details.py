"""
Test for detailed mismatch reporting.
"""

from verify_citations.verifier import CitationVerifier


def test_format_metadata_result_with_details():
    """Test formatting metadata results with detailed mismatch information."""
    verifier = CitationVerifier()
    
    # Test case 1: Title mismatch with details
    details = {
        'entry_title': 'Original Title',
        'online_title': 'Different Title Online',
        'entry_authors': 'Smith, John',
        'online_authors': 'Smith, John',
        'source_url': 'https://example.com/paper',
        'title_match': False,
        'author_match': True
    }
    
    result, message = verifier._format_metadata_result(False, True, details)
    
    assert result is False
    assert 'Title mismatch detected' in message
    assert 'Original Title' in message
    assert 'Different Title Online' in message
    assert 'https://example.com/paper' in message
    
    # Test case 2: Author mismatch with details
    details = {
        'entry_title': 'Same Title',
        'online_title': 'Same Title',
        'entry_authors': 'Smith, John',
        'online_authors': 'Doe, Jane',
        'source_url': 'https://example.com/paper',
        'title_match': True,
        'author_match': False
    }
    
    result, message = verifier._format_metadata_result(True, False, details)
    
    assert result is False
    assert 'author list mismatch detected' in message
    assert 'Smith, John' in message
    assert 'Doe, Jane' in message
    assert 'https://example.com/paper' in message
    
    # Test case 3: Both mismatch with details
    details = {
        'entry_title': 'Wrong Title',
        'online_title': 'Correct Title',
        'entry_authors': 'Smith, John',
        'online_authors': 'Doe, Jane',
        'source_url': 'https://example.com/paper',
        'title_match': False,
        'author_match': False
    }
    
    result, message = verifier._format_metadata_result(False, False, details)
    
    assert result is False
    assert 'Both title and author mismatches detected' in message
    assert 'Wrong Title' in message
    assert 'Correct Title' in message
    assert 'Smith, John' in message
    assert 'Doe, Jane' in message
    assert 'https://example.com/paper' in message


def test_verify_citation_includes_metadata_details():
    """Test that verify_citation includes metadata_details in result."""
    verifier = CitationVerifier()
    entry = {
        'ID': 'test2023',
        'title': 'Test Paper',
        'author': 'Smith, John',
        'year': '2023'
    }
    
    result = verifier.verify_citation(entry)
    
    # Check that metadata_details field exists in result
    assert 'metadata_details' in result
    
    # When no mismatch (or no findable paper), details should be None
    # since we can't actually connect to verify
    assert result['metadata_details'] is None or isinstance(result['metadata_details'], dict)


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
