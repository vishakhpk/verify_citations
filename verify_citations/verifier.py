"""
Core citation verification logic.
"""

import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, quote_plus

import requests
from bs4 import BeautifulSoup


class CitationVerifier:
    """Verifies citations from BibTeX entries."""
    
    # Constants for verification thresholds
    MIN_WORD_LENGTH = 3  # Minimum word length to consider in matching
    TITLE_MATCH_THRESHOLD = 0.5  # Minimum fraction of title words to match for findability
    METADATA_SIMILARITY_THRESHOLD = 0.7  # Minimum word overlap for metadata verification

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
            'status': 'pending',
            'metadata_details': None  # Store detailed metadata comparison
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
            metadata_correct, metadata_msg, metadata_details = self._check_metadata(entry, search_url)
            result['checks']['metadata_correct'] = metadata_correct
            result['messages'].append(metadata_msg)
            if metadata_details:
                result['metadata_details'] = metadata_details

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

        # Try arXiv first if available (most reliable)
        arxiv_id = entry.get('eprint', '') or self._extract_arxiv_id(entry.get('url', ''))
        if arxiv_id:
            try:
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
                response = self.session.get(arxiv_url, timeout=self.timeout)
                if response.status_code == 200:
                    return True, arxiv_url
            except Exception:
                pass

        # Try Semantic Scholar API
        try:
            # Semantic Scholar API for paper search
            api_url = f"https://api.semanticscholar.org/graph/v1/paper/search"
            params = {
                'query': title,
                'limit': 1,
                'fields': 'title,authors,url'
            }
            response = self.session.get(api_url, params=params, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('data') and len(data['data']) > 0:
                    paper = data['data'][0]
                    # Check if the title matches reasonably well
                    found_title = paper.get('title', '').lower()
                    title_words = set(word for word in title.lower().split() 
                                    if len(word) > self.MIN_WORD_LENGTH)
                    found_words = set(word for word in found_title.split() 
                                    if len(word) > self.MIN_WORD_LENGTH)
                    
                    if title_words and found_words:
                        overlap = len(title_words & found_words)
                        similarity = overlap / max(len(title_words), len(found_words))
                        
                        if similarity >= self.TITLE_MATCH_THRESHOLD:
                            paper_id = paper.get('paperId', '')
                            if paper_id:
                                semantic_url = f"https://www.semanticscholar.org/paper/{paper_id}"
                                return True, semantic_url
        except Exception as e:
            pass

        # Try Google Scholar search
        try:
            # Create search query with title
            query = f'"{title}"'
            search_url = f"https://scholar.google.com/scholar?q={quote_plus(query)}"
            
            response = self.session.get(search_url, timeout=self.timeout)
            
            if response.status_code == 200:
                # Check if results contain the title (basic heuristic)
                content = response.text.lower()
                title_words = title.lower().split()
                # Consider found if at least threshold fraction of title words appear in results
                matches = sum(1 for word in title_words 
                            if len(word) > self.MIN_WORD_LENGTH and word in content)
                if matches >= len(title_words) * self.TITLE_MATCH_THRESHOLD:
                    return True, search_url
        except Exception as e:
            pass

        # Try regular web search (DuckDuckGo as a fallback)
        try:
            # Use DuckDuckGo HTML search
            query = f'"{title}" paper pdf'
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            
            response = self.session.get(search_url, timeout=self.timeout)
            
            if response.status_code == 200:
                content = response.text.lower()
                title_words = title.lower().split()
                # Consider found if at least threshold fraction of title words appear in results
                matches = sum(1 for word in title_words 
                            if len(word) > self.MIN_WORD_LENGTH and word in content)
                if matches >= len(title_words) * self.TITLE_MATCH_THRESHOLD:
                    return True, search_url
        except Exception as e:
            pass

        return False, None

    def _check_url_valid(self, url: str) -> Tuple[bool, str]:
        """
        Check if provided URL is valid and accessible.
        
        Returns:
            Tuple of (valid, message)
        """
        try:
            # Handle arXiv eprint IDs - convert to full URL
            # Assumes bare IDs like "1706.03762" are arXiv IDs
            if not url.startswith('http'):
                # Check if it looks like an arXiv ID
                if re.match(r'\d{4}\.\d{4,5}', url):
                    url = f"https://arxiv.org/abs/{url}"
                else:
                    return False, f"✗ Invalid URL format: {url}"
            
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

    def _check_metadata(self, entry: Dict, search_url: str) -> Tuple[Optional[bool], str, Optional[Dict]]:
        """
        Check if metadata (title, authors) matches what's found online.
        
        Returns:
            Tuple of (correct, message, details_dict)
        """
        title = entry.get('title', '').strip('{}').lower()
        entry_authors = entry.get('author', '').strip('{}')
        
        try:
            # Properly check if URL is from arxiv.org domain
            parsed_url = urlparse(search_url)
            if parsed_url.netloc == 'arxiv.org' or parsed_url.netloc.endswith('.arxiv.org'):
                response = self.session.get(search_url, timeout=self.timeout)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Check title
                    page_title = soup.find('h1', class_='title')
                    title_match = None
                    online_title_original = None
                    if page_title:
                        online_title_original = page_title.get_text().replace('Title:', '').strip()
                        online_title = online_title_original.lower()
                        title_similarity = self._calculate_title_similarity(title, online_title)
                        title_match = title_similarity >= self.METADATA_SIMILARITY_THRESHOLD
                    
                    # Check authors
                    authors_div = soup.find('div', class_='authors')
                    author_match = None
                    online_authors_original = None
                    if authors_div and entry_authors:
                        online_authors_original = authors_div.get_text().replace('Authors:', '').strip()
                        online_authors = online_authors_original.lower()
                        # Extract author last names for comparison
                        entry_author_names = self._extract_author_names(entry_authors)
                        online_author_names = self._extract_author_names(online_authors)
                        
                        if entry_author_names and online_author_names:
                            author_similarity = self._calculate_author_similarity(entry_author_names, online_author_names)
                            author_match = author_similarity >= 0.5  # At least 50% of authors should match
                    
                    # Build details dictionary
                    details = {
                        'entry_title': entry.get('title', '').strip('{}'),
                        'online_title': online_title_original,
                        'entry_authors': entry_authors,
                        'online_authors': online_authors_original,
                        'source_url': search_url,
                        'title_match': title_match,
                        'author_match': author_match
                    }
                    
                    # Format and return result
                    result, message = self._format_metadata_result(title_match, author_match, details)
                    # Only include details when there's a mismatch
                    return result, message, (None if result else details)
            
            # Check Semantic Scholar metadata
            elif parsed_url.netloc == 'www.semanticscholar.org' or parsed_url.netloc == 'semanticscholar.org':
                # Extract paper ID from URL
                paper_id_match = re.search(r'/paper/([a-f0-9]+)', search_url)
                if paper_id_match:
                    paper_id = paper_id_match.group(1)
                    api_url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
                    params = {'fields': 'title,authors'}
                    
                    response = self.session.get(api_url, params=params, timeout=self.timeout)
                    if response.status_code == 200:
                        data = response.json()
                        online_title_original = data.get('title', '')
                        online_title = online_title_original.lower()
                        online_authors = data.get('authors', [])
                        
                        # Check title
                        title_match = None
                        if online_title:
                            title_similarity = self._calculate_title_similarity(title, online_title)
                            title_match = title_similarity >= self.METADATA_SIMILARITY_THRESHOLD
                        
                        # Check authors
                        author_match = None
                        online_authors_str = None
                        if online_authors and entry_authors:
                            online_author_names = [author.get('name', '').lower() 
                                                  for author in online_authors]
                            online_authors_str = ', '.join([author.get('name', '') for author in online_authors])
                            
                            # Extract last names from online authors
                            online_last_names = []
                            for name in online_author_names:
                                parts = name.split()
                                if parts:
                                    online_last_names.append(parts[-1])
                            
                            entry_author_names = self._extract_author_names(entry_authors)
                            
                            if entry_author_names and online_last_names:
                                author_similarity = self._calculate_author_similarity(entry_author_names, online_last_names)
                                author_match = author_similarity >= 0.5
                        
                        # Build details dictionary
                        details = {
                            'entry_title': entry.get('title', '').strip('{}'),
                            'online_title': online_title_original,
                            'entry_authors': entry_authors,
                            'online_authors': online_authors_str,
                            'source_url': search_url,
                            'title_match': title_match,
                            'author_match': author_match
                        }
                        
                        # Format and return result
                        result, message = self._format_metadata_result(title_match, author_match, details)
                        # Only include details when there's a mismatch
                        return result, message, (None if result else details)
        except Exception as e:
            pass

        return None, "- Could not verify metadata automatically", None
    
    def _extract_author_names(self, author_string: str) -> List[str]:
        """
        Extract author last names from author string.
        
        Args:
            author_string: String containing author names
            
        Returns:
            List of author last names in lowercase
        """
        # Split by "and" first to separate authors
        authors = re.split(r'\s+and\s+', author_string.lower())
        
        # Extract last names
        last_names = []
        for author in authors:
            author = author.strip()
            if not author:
                continue
            
            # Handle "Last, First Middle" format
            if ',' in author:
                last_name = author.split(',')[0].strip()
            else:
                # Handle "First Middle Last" format - take last word
                words = author.split()
                if words:
                    last_name = words[-1].strip()
                else:
                    continue
            
            # Clean up any remaining punctuation
            last_name = re.sub(r'[^\w\s-]', '', last_name)
            if last_name and len(last_name) > 1:
                last_names.append(last_name)
        
        return last_names
    
    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """
        Calculate similarity between two titles based on word overlap.
        
        Args:
            title1: First title (lowercase)
            title2: Second title (lowercase)
            
        Returns:
            Similarity score between 0 and 1
        """
        words1 = set(word for word in title1.split() 
                    if len(word) > self.MIN_WORD_LENGTH)
        words2 = set(word for word in title2.split() 
                    if len(word) > self.MIN_WORD_LENGTH)
        
        if not words1 or not words2:
            return 0.0
        
        overlap = len(words1 & words2)
        return overlap / max(len(words1), len(words2))
    
    def _calculate_author_similarity(self, entry_names: List[str], online_names: List[str]) -> float:
        """
        Calculate similarity between two author lists.
        
        Args:
            entry_names: List of author last names from BibTeX entry
            online_names: List of author last names from online source
            
        Returns:
            Similarity score between 0 and 1
        """
        if not entry_names or not online_names:
            return 0.0
        
        # Use exact matching on last names to avoid false positives
        matching_authors = sum(1 for name in entry_names 
                             if name in online_names)
        return matching_authors / max(len(entry_names), len(online_names))
    
    def _format_metadata_result(self, title_match: Optional[bool], author_match: Optional[bool], 
                                details: Optional[Dict] = None) -> Tuple[Optional[bool], str]:
        """
        Format metadata verification result based on title and author matches.
        
        Args:
            title_match: Whether title matches (True/False/None)
            author_match: Whether authors match (True/False/None)
            details: Dictionary with detailed comparison information
            
        Returns:
            Tuple of (overall_match, message)
        """
        if title_match is not None and author_match is not None:
            if title_match and author_match:
                return True, "✓ Metadata (title and authors) verified"
            elif title_match and not author_match:
                msg = "✗ Title matches but author list mismatch detected"
                if details and details.get('online_authors'):
                    msg += f"\n    BibTeX authors: {details['entry_authors']}"
                    msg += f"\n    Online authors: {details['online_authors']}"
                    msg += f"\n    Source: {details['source_url']}"
                return False, msg
            elif not title_match and author_match:
                msg = "✗ Title mismatch detected"
                if details and details.get('online_title'):
                    msg += f"\n    BibTeX title: {details['entry_title']}"
                    msg += f"\n    Online title: {details['online_title']}"
                    msg += f"\n    Source: {details['source_url']}"
                return False, msg
            else:
                msg = "✗ Both title and author mismatches detected"
                if details:
                    if details.get('online_title'):
                        msg += f"\n    BibTeX title: {details['entry_title']}"
                        msg += f"\n    Online title: {details['online_title']}"
                    if details.get('online_authors'):
                        msg += f"\n    BibTeX authors: {details['entry_authors']}"
                        msg += f"\n    Online authors: {details['online_authors']}"
                    msg += f"\n    Source: {details['source_url']}"
                return False, msg
        elif title_match is not None:
            if title_match:
                return True, "✓ Title verified (authors not checked)"
            else:
                msg = "✗ Title mismatch detected"
                if details and details.get('online_title'):
                    msg += f"\n    BibTeX title: {details['entry_title']}"
                    msg += f"\n    Online title: {details['online_title']}"
                    msg += f"\n    Source: {details['source_url']}"
                return False, msg
        
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
