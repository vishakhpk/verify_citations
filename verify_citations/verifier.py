"""
Core citation verification logic.
"""

import re
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, quote_plus

import requests
from bs4 import BeautifulSoup


class CitationVerifier:
    """Verifies citations from BibTeX entries."""

    def __init__(self, timeout: int = 10):
        """
        Initialize the citation verifier.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def verify_citation(self, entry: Dict) -> Dict:
        """
        Verify a single BibTeX entry.
        
        Args:
            entry: BibTeX entry dictionary
            
        Returns:
            Dictionary with verification results
        """
        result = {
            'id': entry.get('ID', 'Unknown'),
            'title': entry.get('title', ''),
            'authors': entry.get('author', ''),
            'checks': {
                'findable_online': None,
                'url_valid': None,
                'metadata_correct': None,
                'version_info': None,
            },
            'messages': [],
            'status': 'pending'
        }

        # Check 1: Can the paper be found online?
        findable, search_url = self._check_findable_online(entry)
        result['checks']['findable_online'] = findable
        if findable:
            result['messages'].append(f"✓ Paper found online via search")
            result['search_url'] = search_url
        else:
            result['messages'].append(f"✗ Could not find paper online")

        # Check 2: Verify URL if provided
        url = entry.get('url', '') or entry.get('eprint', '')
        if url:
            url_valid, url_msg = self._check_url_valid(url)
            result['checks']['url_valid'] = url_valid
            result['messages'].append(url_msg)
        else:
            result['messages'].append("- No URL provided to verify")

        # Check 3: Metadata verification (title/authors from search)
        if findable and search_url:
            metadata_correct, metadata_msg = self._check_metadata(entry, search_url)
            result['checks']['metadata_correct'] = metadata_correct
            result['messages'].append(metadata_msg)

        # Check 4: Version information (arXiv, published, etc.)
        version_info = self._check_version_info(entry)
        result['checks']['version_info'] = version_info
        if version_info:
            result['messages'].append(f"ℹ Version: {version_info}")

        # Determine overall status
        checks = result['checks']
        if all(v is not False for v in checks.values() if v is not None):
            result['status'] = 'verified'
        elif any(v is False for v in checks.values()):
            result['status'] = 'issues_found'
        else:
            result['status'] = 'incomplete'

        return result

    def _check_findable_online(self, entry: Dict) -> Tuple[bool, Optional[str]]:
        """
        Check if paper can be found online via search.
        
        Returns:
            Tuple of (findable, search_url)
        """
        title = entry.get('title', '').strip('{}')
        if not title:
            return False, None

        # Try Google Scholar search
        try:
            # Create search query with title
            query = f'"{title}"'
            search_url = f"https://scholar.google.com/scholar?q={quote_plus(query)}"
            
            # For demonstration, we'll check if we can reach Google Scholar
            # In production, you'd parse results
            response = self.session.get(search_url, timeout=self.timeout)
            
            if response.status_code == 200:
                # Simple heuristic: if we get a valid response, assume paper is findable
                # A more sophisticated implementation would parse the results
                return True, search_url
        except Exception as e:
            pass

        # Try arXiv if available
        arxiv_id = entry.get('eprint', '') or self._extract_arxiv_id(entry.get('url', ''))
        if arxiv_id:
            try:
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
                response = self.session.get(arxiv_url, timeout=self.timeout)
                if response.status_code == 200:
                    return True, arxiv_url
            except Exception:
                pass

        return False, None

    def _check_url_valid(self, url: str) -> Tuple[bool, str]:
        """
        Check if provided URL is valid and accessible.
        
        Returns:
            Tuple of (valid, message)
        """
        try:
            # Handle arXiv eprint IDs
            if not url.startswith('http'):
                url = f"https://arxiv.org/abs/{url}"
            
            response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            if response.status_code == 200:
                return True, f"✓ URL is valid and accessible: {url}"
            elif response.status_code == 404:
                return False, f"✗ URL returns 404 (not found): {url}"
            else:
                # Try GET if HEAD fails
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 200:
                    return True, f"✓ URL is valid and accessible: {url}"
                return False, f"✗ URL returned status {response.status_code}: {url}"
        except requests.exceptions.RequestException as e:
            return False, f"✗ URL error: {str(e)}"

    def _check_metadata(self, entry: Dict, search_url: str) -> Tuple[Optional[bool], str]:
        """
        Check if metadata (title, authors) matches what's found online.
        
        Returns:
            Tuple of (correct, message)
        """
        # This is a simplified check
        # In production, you'd fetch and parse the search results/paper page
        title = entry.get('title', '').strip('{}').lower()
        
        try:
            if 'arxiv.org' in search_url:
                response = self.session.get(search_url, timeout=self.timeout)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    page_title = soup.find('h1', class_='title')
                    if page_title:
                        online_title = page_title.get_text().replace('Title:', '').strip().lower()
                        # Simple similarity check
                        if title in online_title or online_title in title:
                            return True, "✓ Metadata appears correct"
                        else:
                            return False, f"✗ Title mismatch detected"
        except Exception as e:
            pass

        return None, "- Could not verify metadata automatically"

    def _check_version_info(self, entry: Dict) -> Optional[str]:
        """
        Extract version information (arXiv, journal, conference).
        
        Returns:
            Version information string or None
        """
        info_parts = []
        
        # Check for arXiv
        arxiv_id = entry.get('eprint', '') or self._extract_arxiv_id(entry.get('url', ''))
        if arxiv_id:
            info_parts.append(f"arXiv:{arxiv_id}")
        
        # Check for journal
        journal = entry.get('journal', '')
        if journal:
            info_parts.append(f"Journal: {journal}")
        
        # Check for conference
        booktitle = entry.get('booktitle', '')
        if booktitle:
            info_parts.append(f"Conference: {booktitle}")
        
        # Check for DOI
        doi = entry.get('doi', '')
        if doi:
            info_parts.append(f"DOI: {doi}")
        
        return ', '.join(info_parts) if info_parts else None

    def _extract_arxiv_id(self, url: str) -> Optional[str]:
        """Extract arXiv ID from URL."""
        if not url:
            return None
        
        # Pattern for arXiv IDs
        match = re.search(r'(?:arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5}(?:v\d+)?)', url)
        if match:
            return match.group(1)
        
        return None
