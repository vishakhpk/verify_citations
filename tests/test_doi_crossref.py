"""
Tests for DOI verification via CrossRef API.
"""

from unittest.mock import Mock, patch

import pytest
import requests

from verify_citations.verifier import CitationVerifier


def _make_crossref_response(status_code=200, message=None):
    """Helper to create a mock CrossRef API response."""
    resp = Mock()
    resp.status_code = status_code
    if message is not None:
        resp.json.return_value = {'message': message}
    return resp


def _make_entry(**overrides):
    """Helper to create a BibTeX entry dict."""
    entry = {
        'ID': 'test2024',
        'title': 'Implicit-Explicit numerical schemes for jump-diffusion processes',
        'author': 'Briani, M. and Natalini, R. and Russo, G.',
        'year': '2007',
        'journal': 'Calcolo',
        'volume': '44',
        'doi': '10.1007/s10092-007-0128-x',
    }
    entry.update(overrides)
    return entry


class TestCheckDoiCrossref:
    """Tests for _check_doi_crossref method."""

    def test_doi_verified_all_fields_match(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'published': {'date-parts': [[2007]]},
            'volume': '44',
            'container-title': ['Calcolo'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is True
        assert 'verified' in msg.lower()
        assert details is None

    def test_doi_title_mismatch(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['A completely different paper about topology'],
            'published': {'date-parts': [[2007]]},
            'volume': '44',
            'container-title': ['Calcolo'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is False
        assert 'mismatch' in msg.lower()
        assert details is not None
        assert details['title_match'] is False
        assert any(field == 'title' for field, _, _ in details['mismatches'])

    def test_doi_year_mismatch(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'published': {'date-parts': [[2010]]},
            'volume': '44',
            'container-title': ['Calcolo'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is False
        assert 'year' in msg.lower()
        assert details is not None
        assert any(field == 'year' for field, _, _ in details['mismatches'])

    def test_doi_volume_mismatch(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'published': {'date-parts': [[2007]]},
            'volume': '99',
            'container-title': ['Calcolo'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is False
        assert 'volume' in msg.lower()

    def test_doi_journal_mismatch(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'published': {'date-parts': [[2007]]},
            'volume': '44',
            'container-title': ['Journal of Computational Physics'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is False
        assert 'journal' in msg.lower()

    def test_doi_multiple_mismatches(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['Something entirely different'],
            'published': {'date-parts': [[2020]]},
            'volume': '1',
            'container-title': ['Nature'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is False
        assert details is not None
        mismatch_fields = [field for field, _, _ in details['mismatches']]
        assert 'title' in mismatch_fields
        assert 'year' in mismatch_fields

    def test_doi_not_found_404(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        mock_resp = _make_crossref_response(404)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is False
        assert 'not found' in msg.lower()

    def test_doi_rate_limited_429(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        mock_resp = _make_crossref_response(429)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is None
        assert 'rate limited' in msg.lower()

    def test_doi_server_error(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        mock_resp = _make_crossref_response(500)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is None
        assert '500' in msg

    def test_doi_network_error(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        with patch.object(verifier, '_make_request_with_retry',
                          side_effect=requests.exceptions.ConnectionError("connection failed")):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is None
        assert 'could not verify' in msg.lower()

    def test_doi_no_title_from_crossref(self):
        """DOI resolves but CrossRef returns no title — comparison should be skipped."""
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': [],
            'published': {'date-parts': [[2007]]},
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        # No title to compare — should return None (skipped)
        assert correct is None
        assert 'skipped' in msg.lower()

    def test_crossref_mailto_appended_to_url(self):
        """Verify that crossref_mailto is included in the request URL."""
        verifier = CitationVerifier(crossref_mailto='test@university.edu')
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'published': {'date-parts': [[2007]]},
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp) as mock_req:
            verifier._check_doi_crossref(entry)

        called_url = mock_req.call_args[0][1]
        assert 'mailto=test@university.edu' in called_url

    def test_crossref_mailto_not_appended_when_empty(self):
        verifier = CitationVerifier(crossref_mailto='')
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp) as mock_req:
            verifier._check_doi_crossref(entry)

        called_url = mock_req.call_args[0][1]
        assert 'mailto' not in called_url

    def test_doi_uses_published_print_fallback(self):
        """Year extraction should fall back to published-print if published is absent."""
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'published-print': {'date-parts': [[2007]]},
            'volume': '44',
            'container-title': ['Calcolo'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is True

    def test_doi_uses_issued_fallback(self):
        """Year extraction should fall back to issued if published and published-print are absent."""
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'issued': {'date-parts': [[2007]]},
            'volume': '44',
            'container-title': ['Calcolo'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is True

    def test_doi_booktitle_used_when_no_journal(self):
        """Should compare booktitle against container-title when journal is absent."""
        verifier = CitationVerifier()
        entry = _make_entry(journal='', booktitle='NeurIPS 2023')

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'published': {'date-parts': [[2007]]},
            'container-title': ['NeurIPS 2023'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is True

    def test_doi_curly_braces_stripped(self):
        """Curly braces in BibTeX fields should not affect comparison."""
        verifier = CitationVerifier()
        entry = _make_entry(title='{Implicit}-{Explicit} numerical schemes')

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes'],
            'published': {'date-parts': [[2007]]},
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is True


class TestBogusDoiDetection:
    """Tests for bogus/malformed DOI detection."""

    @pytest.mark.parametrize('bogus_doi', [
        'mimeo', 'N/A', 'none', 'na', 'TBD', 'forthcoming', 'unpublished',
        'MIMEO', 'None', 'Forthcoming',
    ])
    def test_bogus_doi_values_detected(self, bogus_doi):
        verifier = CitationVerifier()
        entry = _make_entry(doi=bogus_doi)

        correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is None
        assert 'does not look like a valid DOI' in msg

    @pytest.mark.parametrize('malformed_doi', [
        'not-a-doi', '12345', 'https://example.com',
    ])
    def test_malformed_doi_values_detected(self, malformed_doi):
        verifier = CitationVerifier()
        entry = _make_entry(doi=malformed_doi)

        correct, msg, details, logs = verifier._check_doi_crossref(entry)

        assert correct is None
        assert 'does not look like a valid DOI' in msg

    def test_valid_doi_not_flagged_as_bogus(self):
        """A properly formatted DOI should pass the bogus check and reach the API."""
        verifier = CitationVerifier()
        entry = _make_entry(doi='10.1007/s10092-007-0128-x')

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_doi_crossref(entry)

        # Should NOT be flagged as bogus — should reach the API
        assert 'does not look like a valid DOI' not in msg


class TestCrossrefDoiSearch:
    """Tests for CrossRef DOI search in _check_findable_online."""

    def test_doi_search_prioritized_first(self):
        """CrossRef DOI search should be tried before arXiv and other sources."""
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp) as mock_req:
            findable, url, logs = verifier._check_findable_online(entry)

        assert findable is True
        assert url == f"https://doi.org/{entry['doi']}"
        # Should have only made one request (CrossRef), not fallen through to arXiv
        assert mock_req.call_count == 1
        called_url = mock_req.call_args[0][1]
        assert 'api.crossref.org/works/' in called_url

    def test_doi_search_returns_doi_org_url(self):
        """Search URL should be a doi.org link when found via CrossRef."""
        verifier = CitationVerifier()
        entry = _make_entry(doi='10.2307/2951600')

        cr_message = {'title': ['Stochastic differential utility']}
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            findable, url, logs = verifier._check_findable_online(entry)

        assert findable is True
        assert url == 'https://doi.org/10.2307/2951600'

    def test_doi_search_falls_through_on_404(self):
        """If DOI not found in CrossRef, should fall through to other sources."""
        verifier = CitationVerifier()
        entry = _make_entry()  # no eprint/url, so arXiv-by-ID is skipped

        mock_404 = _make_crossref_response(404)
        mock_200_semantic = Mock()
        mock_200_semantic.status_code = 200
        mock_200_semantic.json.return_value = {
            'data': [{'title': 'Implicit-Explicit numerical schemes for jump-diffusion processes',
                       'paperId': 'abc123'}]
        }

        # CrossRef 404 → arXiv title search 404 → ACL 404 → Semantic Scholar 200
        with patch.object(verifier, '_make_request_with_retry',
                          side_effect=[mock_404, mock_404, mock_404, mock_200_semantic]):
            findable, url, logs = verifier._check_findable_online(entry)

        assert findable is True
        assert 'semanticscholar.org' in url

    def test_doi_search_falls_through_on_429(self):
        """If CrossRef rate limits, should fall through to other sources."""
        verifier = CitationVerifier()
        entry = _make_entry()  # no eprint/url, so arXiv-by-ID is skipped

        mock_429 = _make_crossref_response(429)
        mock_404 = _make_crossref_response(404)
        mock_200_semantic = Mock()
        mock_200_semantic.status_code = 200
        mock_200_semantic.json.return_value = {
            'data': [{'title': 'Implicit-Explicit numerical schemes for jump-diffusion processes',
                       'paperId': 'abc123'}]
        }

        # CrossRef 429 → arXiv title search 404 → ACL 404 → Semantic Scholar 200
        with patch.object(verifier, '_make_request_with_retry',
                          side_effect=[mock_429, mock_404, mock_404, mock_200_semantic]):
            findable, url, logs = verifier._check_findable_online(entry)

        assert findable is True
        log_text = ' '.join(logs)
        assert '429' in log_text

    def test_doi_search_skipped_for_invalid_doi(self):
        """Entries with malformed DOIs should not try CrossRef search."""
        verifier = CitationVerifier()
        entry = _make_entry(doi='not-a-doi')

        # Should not call CrossRef at all; will fall through to arXiv etc.
        mock_404 = _make_crossref_response(404)
        with patch.object(verifier, '_make_request_with_retry', return_value=mock_404) as mock_req:
            verifier._check_findable_online(entry)

        # First call should NOT be to crossref (should be arXiv)
        if mock_req.call_count > 0:
            first_url = mock_req.call_args_list[0][0][1]
            assert 'crossref.org' not in first_url

    def test_doi_search_skipped_when_no_doi(self):
        """Entries without a DOI should skip CrossRef search."""
        verifier = CitationVerifier()
        entry = _make_entry()
        del entry['doi']

        mock_404 = _make_crossref_response(404)
        with patch.object(verifier, '_make_request_with_retry', return_value=mock_404) as mock_req:
            verifier._check_findable_online(entry)

        if mock_req.call_count > 0:
            first_url = mock_req.call_args_list[0][0][1]
            assert 'crossref.org' not in first_url

    def test_doi_search_uses_crossref_mailto(self):
        """CrossRef DOI search should include mailto when configured."""
        verifier = CitationVerifier(crossref_mailto='me@university.edu')
        entry = _make_entry()

        cr_message = {'title': ['Some paper']}
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp) as mock_req:
            verifier._check_findable_online(entry)

        called_url = mock_req.call_args_list[0][0][1]
        assert 'mailto=me@university.edu' in called_url

    def test_doi_search_handles_network_error(self):
        """Network errors during CrossRef DOI search should fall through gracefully."""
        verifier = CitationVerifier()
        entry = _make_entry()  # no eprint/url, so arXiv-by-ID is skipped

        mock_200_semantic = Mock()
        mock_200_semantic.status_code = 200
        mock_200_semantic.json.return_value = {
            'data': [{'title': 'Implicit-Explicit numerical schemes for jump-diffusion processes',
                       'paperId': 'abc123'}]
        }

        # CrossRef error → arXiv title search 404 → ACL 404 → Semantic Scholar 200
        with patch.object(verifier, '_make_request_with_retry',
                          side_effect=[
                              requests.exceptions.ConnectionError("timeout"),
                              Mock(status_code=404),  # arXiv title search
                              Mock(status_code=404),  # ACL
                              mock_200_semantic,       # Semantic Scholar
                          ]):
            findable, url, logs = verifier._check_findable_online(entry)

        assert findable is True
        log_text = ' '.join(logs)
        assert 'Error resolving DOI' in log_text


class TestCrossrefMetadata:
    """Tests for _check_metadata with doi.org URLs."""

    def test_metadata_verified_via_crossref(self):
        """Title and authors should be verified against CrossRef data."""
        verifier = CitationVerifier()
        entry = {
            'ID': 'dufeps1992',
            'title': 'Stochastic differential utility',
            'author': 'Duffie, D. and Epstein, L.G.',
            'year': '1992',
            'journal': 'Econometrica',
            'doi': '10.2307/2951600',
        }

        cr_message = {
            'title': ['Stochastic Differential Utility'],
            'author': [
                {'given': 'Darrell', 'family': 'Duffie'},
                {'given': 'Larry G.', 'family': 'Epstein'},
            ],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_metadata(
                entry, 'https://doi.org/10.2307/2951600')

        assert correct is True
        assert 'verified' in msg.lower()

    def test_metadata_title_mismatch_via_crossref(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['A totally different paper'],
            'author': [
                {'given': 'M.', 'family': 'Briani'},
                {'given': 'R.', 'family': 'Natalini'},
                {'given': 'G.', 'family': 'Russo'},
            ],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_metadata(
                entry, f"https://doi.org/{entry['doi']}")

        assert correct is False
        assert details is not None
        assert details['title_match'] is False

    def test_metadata_author_mismatch_via_crossref(self):
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'author': [
                {'given': 'John', 'family': 'Smith'},
                {'given': 'Jane', 'family': 'Doe'},
            ],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_metadata(
                entry, f"https://doi.org/{entry['doi']}")

        assert correct is False
        assert 'author' in msg.lower()

    def test_metadata_crossref_institutional_author(self):
        """Institutional authors (using 'name' instead of given/family) should be handled."""
        verifier = CitationVerifier()
        entry = _make_entry(author='Council, National Research')

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'author': [
                {'name': 'National Research Council'},
            ],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_metadata(
                entry, f"https://doi.org/{entry['doi']}")

        # Should not crash; details should have author info
        assert correct is not None or correct is None  # no crash
        log_text = ' '.join(logs)
        assert 'National Research Council' in log_text

    def test_metadata_crossref_uses_mailto(self):
        """CrossRef metadata check should include mailto in API URL."""
        verifier = CitationVerifier(crossref_mailto='me@uni.edu')
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'author': [{'given': 'M.', 'family': 'Briani'}],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp) as mock_req:
            verifier._check_metadata(entry, f"https://doi.org/{entry['doi']}")

        called_url = mock_req.call_args[0][1]
        assert 'mailto=me@uni.edu' in called_url

    def test_metadata_et_al_via_crossref(self):
        """Entries with 'and others' should use the et-al matching logic."""
        verifier = CitationVerifier()
        entry = _make_entry(author='Briani, M. and Natalini, R. and others')

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
            'author': [
                {'given': 'M.', 'family': 'Briani'},
                {'given': 'R.', 'family': 'Natalini'},
                {'given': 'G.', 'family': 'Russo'},
            ],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_metadata(
                entry, f"https://doi.org/{entry['doi']}")

        # Briani is found in the online list, so should pass
        assert correct is True


class TestUserExamples:
    """Tests based on the user's reported problem entries."""

    def test_duffie_epstein_1992_found_via_doi(self):
        """Duffie & Epstein (1992) should be found via CrossRef DOI, not arXiv."""
        verifier = CitationVerifier()
        entry = {
            'ID': 'dufeps1992',
            'title': 'Stochastic differential utility',
            'author': 'Duffie, D. and L.G. Epstein',
            'journal': 'Econometrica',
            'volume': '60',
            'pages': '353-394',
            'year': '1992',
            'doi': '10.2307/2951600',
        }

        cr_message = {
            'title': ['Stochastic Differential Utility'],
            'author': [
                {'given': 'Darrell', 'family': 'Duffie'},
                {'given': 'Larry G.', 'family': 'Epstein'},
            ],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            findable, url, logs = verifier._check_findable_online(entry)

        assert findable is True
        assert url == 'https://doi.org/10.2307/2951600'
        log_text = ' '.join(logs)
        assert 'CrossRef' in log_text

    def test_duffie_epstein_1992_metadata_matches(self):
        """Duffie & Epstein metadata should match via CrossRef (not arXiv mismatch)."""
        verifier = CitationVerifier()
        entry = {
            'ID': 'dufeps1992',
            'title': 'Stochastic differential utility',
            'author': 'Duffie, D. and L.G. Epstein',
            'journal': 'Econometrica',
            'volume': '60',
            'pages': '353-394',
            'year': '1992',
            'doi': '10.2307/2951600',
        }

        cr_message = {
            'title': ['Stochastic Differential Utility'],
            'author': [
                {'given': 'Darrell', 'family': 'Duffie'},
                {'given': 'Larry G.', 'family': 'Epstein'},
            ],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_metadata(
                entry, 'https://doi.org/10.2307/2951600')

        assert correct is True
        assert 'verified' in msg.lower()

    def test_golosov_2014_found_via_doi(self):
        """Golosov et al. (2014) should be found via CrossRef DOI, not Semantic Scholar."""
        verifier = CitationVerifier()
        entry = {
            'ID': 'golosov2014',
            'title': 'Optimal Taxes on Fossil Fuels in General Equilibrium',
            'author': 'Golosov, M. and J. Hassler and P. Krusell and A. Tsyvinski',
            'journal': 'Econometrica',
            'volume': '82',
            'number': '1',
            'pages': '41-88',
            'year': '2014',
            'doi': '10.3982/ECTA10217',
        }

        cr_message = {
            'title': ['Optimal Taxes on Fossil Fuel in General Equilibrium'],
            'author': [
                {'given': 'Mikhail', 'family': 'Golosov'},
                {'given': 'John', 'family': 'Hassler'},
                {'given': 'Per', 'family': 'Krusell'},
                {'given': 'Aleh', 'family': 'Tsyvinski'},
            ],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            findable, url, logs = verifier._check_findable_online(entry)

        assert findable is True
        assert url == 'https://doi.org/10.3982/ECTA10217'

    def test_golosov_2014_metadata_matches(self):
        """Golosov et al. metadata should match via CrossRef."""
        verifier = CitationVerifier()
        entry = {
            'ID': 'golosov2014',
            'title': 'Optimal Taxes on Fossil Fuels in General Equilibrium',
            'author': 'Golosov, M. and J. Hassler and P. Krusell and A. Tsyvinski',
            'journal': 'Econometrica',
            'volume': '82',
            'year': '2014',
            'doi': '10.3982/ECTA10217',
        }

        cr_message = {
            'title': ['Optimal Taxes on Fossil Fuel in General Equilibrium'],
            'author': [
                {'given': 'Mikhail', 'family': 'Golosov'},
                {'given': 'John', 'family': 'Hassler'},
                {'given': 'Per', 'family': 'Krusell'},
                {'given': 'Aleh', 'family': 'Tsyvinski'},
            ],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            correct, msg, details, logs = verifier._check_metadata(
                entry, 'https://doi.org/10.3982/ECTA10217')

        assert correct is True

    def test_full_pipeline_duffie_epstein(self):
        """Full verify_citation pipeline for Duffie & Epstein should pass."""
        verifier = CitationVerifier()
        entry = {
            'ID': 'dufeps1992',
            'title': 'Stochastic differential utility',
            'author': 'Duffie, D. and L.G. Epstein',
            'journal': 'Econometrica',
            'volume': '60',
            'year': '1992',
            'doi': '10.2307/2951600',
        }

        cr_message = {
            'title': ['Stochastic Differential Utility'],
            'author': [
                {'given': 'Darrell', 'family': 'Duffie'},
                {'given': 'Larry G.', 'family': 'Epstein'},
            ],
            'published': {'date-parts': [[1992]]},
            'volume': '60',
            'container-title': ['Econometrica'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            result = verifier.verify_citation(entry)

        assert result['status'] == 'verified'
        assert result['checks']['findable_online'] is True
        assert result['checks']['metadata_correct'] is True
        assert result['checks']['doi_correct'] is True


class TestVerifyCitationDoiIntegration:
    """Tests for DOI check integration in verify_citation."""

    def test_doi_correct_in_checks_dict(self):
        """verify_citation result should include doi_correct key."""
        verifier = CitationVerifier()
        entry = _make_entry()

        result = verifier.verify_citation(entry)

        assert 'doi_correct' in result['checks']

    def test_doi_details_in_result(self):
        """verify_citation result should include doi_details when there's a DOI mismatch."""
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['A completely wrong paper'],
            'published': {'date-parts': [[2020]]},
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            result = verifier.verify_citation(entry)

        assert result['checks']['doi_correct'] is False
        assert result.get('doi_details') is not None

    def test_no_doi_field_skips_check(self):
        """Entries without a DOI should skip the CrossRef check entirely."""
        verifier = CitationVerifier()
        entry = _make_entry()
        del entry['doi']

        result = verifier.verify_citation(entry)

        assert result['checks']['doi_correct'] is None

    def test_empty_doi_field_skips_check(self):
        """Entries with an empty DOI should skip the CrossRef check."""
        verifier = CitationVerifier()
        entry = _make_entry(doi='')

        result = verifier.verify_citation(entry)

        assert result['checks']['doi_correct'] is None

    def test_doi_mismatch_sets_issues_found(self):
        """A DOI mismatch should set overall status to issues_found."""
        verifier = CitationVerifier()
        entry = _make_entry()

        # Mock _check_findable_online to return not found (simplifies the test)
        with patch.object(verifier, '_check_findable_online', return_value=(False, None, [])):
            cr_message = {
                'title': ['Wrong paper entirely'],
                'published': {'date-parts': [[2020]]},
            }
            mock_resp = _make_crossref_response(200, cr_message)
            with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
                result = verifier.verify_citation(entry)

        assert result['status'] == 'issues_found'

    def test_verbose_logs_include_crossref(self):
        """Verbose logs should contain CrossRef checking details."""
        verifier = CitationVerifier()
        entry = _make_entry()

        cr_message = {
            'title': ['Implicit-Explicit numerical schemes for jump-diffusion processes'],
        }
        mock_resp = _make_crossref_response(200, cr_message)

        with patch.object(verifier, '_make_request_with_retry', return_value=mock_resp):
            result = verifier.verify_citation(entry)

        log_text = ' '.join(result.get('verbose_logs', []))
        assert 'crossref' in log_text.lower()
