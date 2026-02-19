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
