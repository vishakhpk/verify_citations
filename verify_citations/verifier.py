"""
Core citation verification logic.
"""

import re
from difflib import SequenceMatcher
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
            'verbose_logs': [],  # Add verbose logging details
            'status': 'pending',
            'metadata_details': None,  # Store detailed metadata comparison
            'has_403': False  # Track if a 403 error occurred
        }

        # Check 1: Can the paper be found online?
        findable, search_url, findable_logs = self._check_findable_online(entry)
        result['checks']['findable_online'] = findable
        if findable_logs:
            result['verbose_logs'].extend(findable_logs)
        if findable:
            result['messages'].append(f"✓ Paper found online via search: {search_url}")
            result['search_url'] = search_url
        else:
            result['messages'].append(f"✗ Could not find paper online")

        # Check 2: Verify URL if provided
        url = entry.get('url', '') or entry.get('eprint', '')
        if url:
            url_valid, url_msg = self._check_url_valid(url)
            result['checks']['url_valid'] = url_valid
            result['messages'].append(url_msg)
            # Track 403 errors: _check_url_valid returns None specifically for 403 Forbidden responses
            if url_valid is None:
                result['has_403'] = True
        else:
            result['messages'].append("- No URL provided to verify")

        # Check 3: Metadata verification (title/authors from search)
        if findable and search_url:
            metadata_correct, metadata_msg, metadata_details, verbose_logs = self._check_metadata(entry, search_url)
            result['checks']['metadata_correct'] = metadata_correct
            result['messages'].append(metadata_msg)
            # Track when metadata could not be verified (when message says "Could not verify metadata automatically")
            if metadata_correct is None and metadata_msg == "- Could not verify metadata automatically":
                result['metadata_not_verified'] = True
            if metadata_details:
                result['metadata_details'] = metadata_details
            if verbose_logs:
                result['verbose_logs'].extend(verbose_logs)

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

    def _check_findable_online(self, entry: Dict) -> Tuple[bool, Optional[str], List[str]]:
        """
        Check if paper can be found online via search.
        
        Returns:
            Tuple of (findable, search_url, verbose_logs)
        """
        verbose_logs = []
        title = self._remove_curly_braces(entry.get('title', ''))
        if not title:
            verbose_logs.append("  ✗ No title found in entry")
            return False, None, verbose_logs

        # Try arXiv first by ID if available (most reliable)
        arxiv_id = entry.get('eprint', '') or self._extract_arxiv_id(entry.get('url', ''))
        if arxiv_id:
            verbose_logs.append(f"  Trying arXiv by ID: {arxiv_id}")
            try:
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
                response = self.session.get(arxiv_url, timeout=self.timeout)
                if response.status_code == 200:
                    verbose_logs.append(f"    ✓ Found on arXiv: {arxiv_url}")
                    return True, arxiv_url, verbose_logs
                else:
                    verbose_logs.append(f"    ✗ arXiv returned status {response.status_code}")
            except Exception as e:
                verbose_logs.append(f"    ✗ Error accessing arXiv: {str(e)}")

        # Try arXiv search by title
        verbose_logs.append(f"  Trying arXiv search by title")
        try:
            import xml.etree.ElementTree as ET
            # arXiv API search endpoint (using HTTPS)
            search_query = quote_plus(f'ti:"{title}"')
            arxiv_search_url = f"https://export.arxiv.org/api/query?search_query={search_query}&max_results=1"
            response = self.session.get(arxiv_search_url, timeout=self.timeout)
            
            if response.status_code == 200:
                # Parse XML response properly
                try:
                    root = ET.fromstring(response.content)
                    # Define namespace for arXiv API
                    ns = {'atom': 'http://www.w3.org/2005/Atom'}
                    
                    # Find the first entry
                    entry = root.find('atom:entry', ns)
                    if entry is not None:
                        # Extract ID and title
                        id_elem = entry.find('atom:id', ns)
                        title_elem = entry.find('atom:title', ns)
                        
                        if id_elem is not None and title_elem is not None:
                            # Extract arXiv ID from URL
                            arxiv_id_url = id_elem.text
                            if 'arxiv.org/abs/' in arxiv_id_url:
                                found_arxiv_id = arxiv_id_url.split('arxiv.org/abs/')[-1]
                                arxiv_url = f"https://arxiv.org/abs/{found_arxiv_id}"
                                
                                # Verify title similarity
                                found_title = title_elem.text.strip()
                                if self._titles_similar(title, found_title):
                                    verbose_logs.append(f"    ✓ Found matching paper on arXiv: {arxiv_url}")
                                    return True, arxiv_url, verbose_logs
                                else:
                                    verbose_logs.append(f"    ✗ Title mismatch: '{found_title}'")
                    else:
                        verbose_logs.append(f"    ✗ No results found in arXiv search")
                except ET.ParseError:
                    verbose_logs.append(f"    ✗ Failed to parse arXiv response")
            else:
                verbose_logs.append(f"    ✗ arXiv search returned status {response.status_code}")
        except Exception as e:
            verbose_logs.append(f"    ✗ Error searching arXiv: {str(e)}")

        # Try ACL Anthology
        verbose_logs.append(f"  Trying ACL Anthology search")
        try:
            # ACL Anthology search via their website
            acl_search_url = f"https://aclanthology.org/search/?q={quote_plus(title)}"
            response = self.session.get(acl_search_url, timeout=self.timeout)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                # Look for paper results in search
                results = soup.find_all('strong', class_='align-middle')
                if results:
                    # Check first result
                    first_result = results[0]
                    result_link = first_result.find('a')
                    if result_link:
                        found_title = result_link.get_text(strip=True)
                        if self._titles_similar(title, found_title):
                            paper_url = result_link.get('href', '')
                            if paper_url:
                                # Make absolute URL if relative
                                if paper_url.startswith('/'):
                                    paper_url = f"https://aclanthology.org{paper_url}"
                                verbose_logs.append(f"    ✓ Found on ACL Anthology: {paper_url}")
                                return True, paper_url, verbose_logs
                        else:
                            verbose_logs.append(f"    ✗ Title mismatch: '{found_title}'")
                else:
                    verbose_logs.append(f"    ✗ No results found")
            else:
                verbose_logs.append(f"    ✗ ACL Anthology returned status {response.status_code}")
        except Exception as e:
            verbose_logs.append(f"    ✗ Error searching ACL Anthology: {str(e)}")

        # Try Semantic Scholar API
        verbose_logs.append(f"  Trying Semantic Scholar API")
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
                    found_title = paper.get('title', '')
                    
                    if self._titles_similar(title, found_title):
                        paper_id = paper.get('paperId', '')
                        if paper_id:
                            semantic_url = f"https://www.semanticscholar.org/paper/{paper_id}"
                            verbose_logs.append(f"    ✓ Found on Semantic Scholar: {semantic_url}")
                            return True, semantic_url, verbose_logs
                    else:
                        verbose_logs.append(f"    ✗ Title mismatch: '{found_title}'")
                else:
                    verbose_logs.append(f"    ✗ No results found")
            else:
                verbose_logs.append(f"    ✗ Semantic Scholar API returned status {response.status_code}")
        except Exception as e:
            verbose_logs.append(f"    ✗ Error querying Semantic Scholar: {str(e)}")

        # Try DBLP
        verbose_logs.append(f"  Trying DBLP search")
        try:
            # DBLP API search
            dblp_search_url = f"https://dblp.org/search/publ/api?q={quote_plus(title)}&format=json&h=1"
            response = self.session.get(dblp_search_url, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                hits = data.get('result', {}).get('hits', {}).get('hit', [])
                if hits:
                    paper = hits[0].get('info', {})
                    found_title = paper.get('title', '')
                    if found_title and self._titles_similar(title, found_title):
                        # Get the DBLP URL
                        dblp_url = paper.get('url', '')
                        if dblp_url:
                            verbose_logs.append(f"    ✓ Found on DBLP: {dblp_url}")
                            return True, dblp_url, verbose_logs
                    else:
                        verbose_logs.append(f"    ✗ Title mismatch: '{found_title}'")
                else:
                    verbose_logs.append(f"    ✗ No results found")
            else:
                verbose_logs.append(f"    ✗ DBLP returned status {response.status_code}")
        except Exception as e:
            verbose_logs.append(f"    ✗ Error searching DBLP: {str(e)}")

        # Try Google Scholar search
        verbose_logs.append(f"  Trying Google Scholar search")
        try:
            # Create search query with title
            query = f'"{title}"'
            search_url = f"https://scholar.google.com/scholar?q={quote_plus(query)}"
            verbose_logs.append(f"    Query: {search_url}")
            
            response = self.session.get(search_url, timeout=self.timeout)
            
            if response.status_code == 200:
                verbose_logs.append(f"    Response status: 200 OK")
                # Parse HTML to extract first result title and authors
                parsed_title, parsed_authors = self._parse_google_scholar_first_result(response.text)
                
                if parsed_title:
                    verbose_logs.append(f"    Extracted title from first result: '{parsed_title}'")
                    if parsed_authors:
                        verbose_logs.append(f"    Extracted authors: {', '.join(parsed_authors)}")
                    else:
                        verbose_logs.append(f"    No authors extracted")
                    
                    # Use difflib to compare titles
                    title_similarity = self._calculate_title_similarity(title, parsed_title.lower())
                    verbose_logs.append(f"    Title similarity: {title_similarity:.2%} (threshold: {self.TITLE_MATCH_THRESHOLD * 100:.0%})")
                    
                    if title_similarity >= self.TITLE_MATCH_THRESHOLD:
                        verbose_logs.append(f"    ✓ Title match - paper found on Google Scholar")
                        return True, search_url, verbose_logs
                    else:
                        verbose_logs.append(f"    ✗ Title similarity below threshold")
                else:
                    verbose_logs.append(f"    ✗ Could not extract title from first result (no results or parsing failed)")
            else:
                verbose_logs.append(f"    ✗ Google Scholar returned status {response.status_code}")
        except Exception as e:
            verbose_logs.append(f"    ✗ Error searching Google Scholar: {str(e)}")

        # Try regular web search (DuckDuckGo as a fallback)
        verbose_logs.append(f"  Trying DuckDuckGo web search")
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
                    verbose_logs.append(f"    ✓ Found via DuckDuckGo: {matches}/{len(title_words)} title words matched")
                    return True, search_url, verbose_logs
                else:
                    verbose_logs.append(f"    ✗ Insufficient word matches: {matches}/{len(title_words)}")
            else:
                verbose_logs.append(f"    ✗ DuckDuckGo returned status {response.status_code}")
        except Exception as e:
            verbose_logs.append(f"    ✗ Error searching DuckDuckGo: {str(e)}")

        verbose_logs.append("  ✗ Paper not found via any search method")
        return False, None, verbose_logs

    def _check_url_valid(self, url: str) -> Tuple[Optional[bool], str]:
        """
        Check if provided URL is valid and accessible.
        
        Returns:
            Tuple of (valid, message) where valid can be:
            - True: URL is accessible
            - False: URL has critical error (404, invalid format, etc.)
            - None: Warning/transient state (403 - server blocking, connection errors)
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
            elif response.status_code == 403:
                # 403 Forbidden - server is blocking automated access
                # Try GET as fallback, but note the restriction
                try:
                    response = self.session.get(url, timeout=self.timeout)
                    if response.status_code == 200:
                        return True, f"✓ URL is accessible (server restricts HEAD requests): {url}"
                except requests.exceptions.RequestException:
                    pass
                return None, f"⚠ URL returns 403 (Forbidden - server blocks automated access): {url}"
            elif response.status_code == 404:
                return False, f"✗ URL returns 404 (not found): {url}"
            else:
                # Try GET if HEAD fails
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 200:
                    return True, f"✓ URL is valid and accessible: {url}"
                elif response.status_code == 403:
                    return None, f"⚠ URL returns 403 (Forbidden - server blocks automated access): {url}"
                return False, f"✗ URL returned status {response.status_code}: {url}"
        except (requests.exceptions.InvalidURL, requests.exceptions.InvalidSchema, 
                requests.exceptions.MissingSchema) as e:
            # URL format errors are genuine citation problems - treat as failure
            return False, f"✗ Invalid URL: {str(e)}"
        except requests.exceptions.ConnectionError as e:
            # Connection errors are transient - treat as warning, not failure
            return None, f"⚠ Connection error (may be transient): {str(e)}"
        except requests.exceptions.Timeout:
            # Timeout errors are transient - treat as warning, not failure
            return None, f"⚠ Connection timeout (may be transient)"
        except requests.exceptions.RequestException as e:
            # Other network errors - treat as warning since they may be transient
            # (e.g., SSLError, ProxyError, ChunkedEncodingError, etc.)
            return None, f"⚠ Network error (may be transient): {str(e)}"

    def _check_metadata(self, entry: Dict, search_url: str) -> Tuple[Optional[bool], str, Optional[Dict], List[str]]:
        """
        Check if metadata (title, authors) matches what's found online.
        
        Returns:
            Tuple of (correct, message, details_dict, verbose_logs)
        """
        title = self._remove_curly_braces(entry.get('title', '')).lower()
        entry_authors = self._remove_curly_braces(entry.get('author', ''))
        verbose_logs = []
        
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
                        
                        verbose_logs.append(f"  Comparing titles:")
                        verbose_logs.append(f"    BibTeX: {self._remove_curly_braces(entry.get('title', ''))}")
                        verbose_logs.append(f"    Online: {online_title_original}")
                        
                        title_similarity = self._calculate_title_similarity(title, online_title)
                        title_match = title_similarity >= self.METADATA_SIMILARITY_THRESHOLD
                        
                        verbose_logs.append(f"    Similarity: {title_similarity:.2%}, Threshold: {self.METADATA_SIMILARITY_THRESHOLD:.2%}")
                        verbose_logs.append(f"    Result: {'✓ Match' if title_match else '✗ Mismatch'}")
                    
                    # Check authors
                    authors_div = soup.find('div', class_='authors')
                    author_match = None
                    online_authors_original = None
                    if authors_div and entry_authors:
                        online_authors_original = authors_div.get_text().replace('Authors:', '').strip()
                        online_authors = online_authors_original.lower()
                        
                        verbose_logs.append(f"  Comparing authors:")
                        verbose_logs.append(f"    BibTeX: {entry_authors}")
                        verbose_logs.append(f"    Online: {online_authors_original}")
                        
                        # Extract author last names for comparison
                        entry_author_names = self._extract_author_names(entry_authors)
                        online_author_names = self._extract_author_names(online_authors)
                        
                        verbose_logs.append(f"    Extracted BibTeX authors ({len(entry_author_names)}): {', '.join(entry_author_names)}")
                        verbose_logs.append(f"    Extracted online authors ({len(online_author_names)}): {', '.join(online_author_names)}")
                        
                        # Check if entry has "and others"
                        has_et_al = 'and others' in entry_authors.lower() or 'et al' in entry_authors.lower()
                        
                        if entry_author_names and online_author_names:
                            if has_et_al:
                                verbose_logs.append(f"    Note: BibTeX has 'and others' - checking if listed authors are complete")
                                # For "and others", check if all listed authors appear in online list
                                # and if coverage is sufficient (50%+)
                                if len(entry_author_names) > len(online_author_names):
                                    author_similarity = 0.0  # Can't match if BibTeX has more than online
                                    verbose_logs.append(f"    ✗ BibTeX has more authors than online ({len(entry_author_names)} > {len(online_author_names)})")
                                else:
                                    # Check if all listed authors appear in online list
                                    matching = sum(1 for name in entry_author_names if name in online_author_names)
                                    verbose_logs.append(f"    Matching authors: {matching}/{len(entry_author_names)}")
                                    # But we need to be strict: if not all authors match, it's incomplete
                                    if matching == len(entry_author_names):
                                        # All listed authors found, but check if it's significantly incomplete
                                        coverage = len(entry_author_names) / len(online_author_names)
                                        verbose_logs.append(f"    Coverage: {coverage:.2%} of total authors")
                                        # If less than 50% of authors are listed, flag as issue
                                        author_similarity = coverage
                                    else:
                                        author_similarity = 0.0
                                        verbose_logs.append(f"    ✗ Not all listed authors found online")
                            else:
                                author_similarity = self._calculate_author_similarity(entry_author_names, online_author_names)
                                verbose_logs.append(f"    Similarity: {author_similarity:.2%}, Threshold: 50%")
                            
                            author_match = author_similarity >= 0.5  # At least 50% of authors should match
                            verbose_logs.append(f"    Result: {'✓ Match' if author_match else '✗ Mismatch'}")
                    
                    # Build details dictionary
                    details = {
                        'entry_title': self._remove_curly_braces(entry.get('title', '')),
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
                    return result, message, (None if result else details), verbose_logs
            
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
                            
                            # Check if entry has "and others"
                            has_et_al = 'and others' in entry_authors.lower() or 'et al' in entry_authors.lower()
                            
                            if entry_author_names and online_last_names:
                                if has_et_al:
                                    # For "and others", we need ALL authors to match
                                    if len(entry_author_names) > len(online_last_names):
                                        author_similarity = 0.0
                                    else:
                                        matching = sum(1 for name in entry_author_names if name in online_last_names)
                                        if matching == len(entry_author_names):
                                            coverage = len(entry_author_names) / len(online_last_names)
                                            author_similarity = coverage
                                        else:
                                            author_similarity = 0.0
                                else:
                                    author_similarity = self._calculate_author_similarity(entry_author_names, online_last_names)
                                author_match = author_similarity >= 0.5
                        
                        # Build details dictionary
                        details = {
                            'entry_title': self._remove_curly_braces(entry.get('title', '')),
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
                        return result, message, (None if result else details), verbose_logs
            
            # Check DBLP metadata
            elif parsed_url.netloc == 'dblp.org' or parsed_url.netloc.endswith('.dblp.org'):
                # Query DBLP using search API with the paper title (same approach as in _check_findable_online)
                # This is more reliable than trying to parse the key from the URL
                dblp_search_url = f"https://dblp.org/search/publ/api?q={quote_plus(title)}&format=json&h=1"
                response = self.session.get(dblp_search_url, timeout=self.timeout)
                
                if response.status_code == 200:
                    data = response.json()
                    hits = data.get('result', {}).get('hits', {}).get('hit', [])
                    if hits:
                        paper_info = hits[0].get('info', {})
                        online_title_original = paper_info.get('title', '')
                        online_title = online_title_original.lower() if online_title_original else ''
                        
                        verbose_logs.append(f"  Comparing titles:")
                        verbose_logs.append(f"    BibTeX: {self._remove_curly_braces(entry.get('title', ''))}")
                        verbose_logs.append(f"    Online: {online_title_original}")
                        
                        # Check title
                        title_match = None
                        if online_title:
                            title_similarity = self._calculate_title_similarity(title, online_title)
                            title_match = title_similarity >= self.METADATA_SIMILARITY_THRESHOLD
                            
                            verbose_logs.append(f"    Similarity: {title_similarity:.2%}, Threshold: {self.METADATA_SIMILARITY_THRESHOLD:.2%}")
                            verbose_logs.append(f"    Result: {'✓ Match' if title_match else '✗ Mismatch'}")
                        
                        # Check authors
                        author_match = None
                        online_authors_original = None
                        authors_data = paper_info.get('authors', {})
                        if authors_data and entry_authors:
                            # DBLP authors can be a dict with 'author' key containing array
                            author_list = authors_data.get('author', [])
                            if isinstance(author_list, list):
                                online_author_names_list = [auth.get('text', '') if isinstance(auth, dict) else str(auth) 
                                                           for auth in author_list]
                                online_authors_original = ', '.join(online_author_names_list)
                            elif isinstance(author_list, dict):
                                # Single author case
                                online_authors_original = author_list.get('text', '')
                            else:
                                online_authors_original = str(author_list)
                            
                            verbose_logs.append(f"  Comparing authors:")
                            verbose_logs.append(f"    BibTeX: {entry_authors}")
                            verbose_logs.append(f"    Online: {online_authors_original}")
                            
                            # Extract author last names for comparison
                            entry_author_names = self._extract_author_names(entry_authors)
                            online_author_names = self._extract_author_names(online_authors_original)
                            
                            verbose_logs.append(f"    Extracted BibTeX authors ({len(entry_author_names)}): {', '.join(entry_author_names)}")
                            verbose_logs.append(f"    Extracted online authors ({len(online_author_names)}): {', '.join(online_author_names)}")
                            
                            # Check if entry has "and others"
                            has_et_al = 'and others' in entry_authors.lower() or 'et al' in entry_authors.lower()
                            
                            if entry_author_names and online_author_names:
                                if has_et_al:
                                    verbose_logs.append(f"    Note: BibTeX has 'and others' - checking if listed authors are complete")
                                    if len(entry_author_names) > len(online_author_names):
                                        author_similarity = 0.0
                                        verbose_logs.append(f"    ✗ BibTeX has more authors than online ({len(entry_author_names)} > {len(online_author_names)})")
                                    else:
                                        matching = sum(1 for name in entry_author_names if name in online_author_names)
                                        verbose_logs.append(f"    Matching authors: {matching}/{len(entry_author_names)}")
                                        if matching == len(entry_author_names):
                                            coverage = len(entry_author_names) / len(online_author_names)
                                            verbose_logs.append(f"    Coverage: {coverage:.2%} of total authors")
                                            author_similarity = coverage
                                        else:
                                            author_similarity = 0.0
                                            verbose_logs.append(f"    ✗ Not all listed authors found online")
                                else:
                                    author_similarity = self._calculate_author_similarity(entry_author_names, online_author_names)
                                    verbose_logs.append(f"    Similarity: {author_similarity:.2%}, Threshold: 50%")
                                
                                author_match = author_similarity >= 0.5
                                verbose_logs.append(f"    Result: {'✓ Match' if author_match else '✗ Mismatch'}")
                        
                        # Build details dictionary
                        details = {
                            'entry_title': self._remove_curly_braces(entry.get('title', '')),
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
                        return result, message, (None if result else details), verbose_logs
            
            # Check Google Scholar metadata
            elif parsed_url.netloc == 'scholar.google.com' or parsed_url.netloc.endswith('.scholar.google.com'):
                verbose_logs.append(f"  Checking Google Scholar metadata from: {search_url}")
                response = self.session.get(search_url, timeout=self.timeout)
                if response.status_code == 200:
                    verbose_logs.append(f"    Response status: 200 OK")
                    # Parse HTML to extract first result title and authors
                    parsed_title, parsed_authors = self._parse_google_scholar_first_result(response.text)
                    
                    if not parsed_title:
                        verbose_logs.append(f"    ✗ Could not extract title from Google Scholar results")
                    if not parsed_authors:
                        verbose_logs.append(f"    ℹ No authors extracted from Google Scholar results")
                    
                    # Check title
                    title_match = None
                    online_title_original = None
                    if parsed_title:
                        online_title_original = parsed_title
                        online_title = online_title_original.lower()
                        
                        verbose_logs.append(f"  Comparing titles:")
                        verbose_logs.append(f"    BibTeX: {self._remove_curly_braces(entry.get('title', ''))}")
                        verbose_logs.append(f"    Online: {online_title_original}")
                        
                        title_similarity = self._calculate_title_similarity(title, online_title)
                        title_match = title_similarity >= self.METADATA_SIMILARITY_THRESHOLD
                        
                        verbose_logs.append(f"    Similarity: {title_similarity:.2%}, Threshold: {self.METADATA_SIMILARITY_THRESHOLD:.2%}")
                        verbose_logs.append(f"    Result: {'✓ Match' if title_match else '✗ Mismatch'}")
                    
                    # Check authors
                    author_match = None
                    online_authors_original = None
                    if parsed_authors and entry_authors:
                        online_authors_original = ', '.join(parsed_authors)
                        
                        verbose_logs.append(f"  Comparing authors:")
                        verbose_logs.append(f"    BibTeX: {entry_authors}")
                        verbose_logs.append(f"    Online: {online_authors_original}")
                        
                        # Extract author last names for comparison
                        entry_author_names = self._extract_author_names(entry_authors)
                        online_author_names = self._extract_author_names(online_authors_original)
                        
                        verbose_logs.append(f"    Extracted BibTeX authors ({len(entry_author_names)}): {', '.join(entry_author_names)}")
                        verbose_logs.append(f"    Extracted online authors ({len(online_author_names)}): {', '.join(online_author_names)}")
                        
                        # Check if entry has "and others"
                        has_et_al = 'and others' in entry_authors.lower() or 'et al' in entry_authors.lower()
                        
                        if entry_author_names and online_author_names:
                            if has_et_al:
                                verbose_logs.append(f"    Note: BibTeX has 'and others' - checking if listed authors are complete")
                                if len(entry_author_names) > len(online_author_names):
                                    author_similarity = 0.0
                                    verbose_logs.append(f"    ✗ BibTeX has more authors than online ({len(entry_author_names)} > {len(online_author_names)})")
                                else:
                                    matching = sum(1 for name in entry_author_names if name in online_author_names)
                                    verbose_logs.append(f"    Matching authors: {matching}/{len(entry_author_names)}")
                                    if matching == len(entry_author_names):
                                        coverage = len(entry_author_names) / len(online_author_names)
                                        verbose_logs.append(f"    Coverage: {coverage:.2%} of total authors")
                                        author_similarity = coverage
                                    else:
                                        author_similarity = 0.0
                                        verbose_logs.append(f"    ✗ Not all listed authors found online")
                            else:
                                author_similarity = self._calculate_author_similarity(entry_author_names, online_author_names)
                                verbose_logs.append(f"    Similarity: {author_similarity:.2%}, Threshold: 50%")
                            
                            author_match = author_similarity >= 0.5
                            verbose_logs.append(f"    Result: {'✓ Match' if author_match else '✗ Mismatch'}")
                        elif not entry_author_names:
                            verbose_logs.append(f"    ✗ Could not extract author names from BibTeX entry")
                        elif not online_author_names:
                            verbose_logs.append(f"    ✗ Could not extract author names from online source")
                    elif not parsed_authors:
                        verbose_logs.append(f"  ℹ Skipping author comparison - no authors found online")
                    elif not entry_authors:
                        verbose_logs.append(f"  ℹ Skipping author comparison - no authors in BibTeX entry")
                    
                    # Build details dictionary
                    details = {
                        'entry_title': self._remove_curly_braces(entry.get('title', '')),
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
                    return result, message, (None if result else details), verbose_logs
                else:
                    verbose_logs.append(f"    ✗ Google Scholar returned status {response.status_code}")
        except Exception as e:
            verbose_logs.append(f"  ✗ Error checking Google Scholar metadata: {str(e)}")

        return None, "- Could not verify metadata automatically", None, []
    
    def _extract_author_names(self, author_string: str) -> List[str]:
        """
        Extract author last names from author string.
        
        Args:
            author_string: String containing author names
            
        Returns:
            List of author last names in lowercase
        """
        author_string_lower = author_string.lower()
        
        # Determine separator: "and" for BibTeX, comma for online formats
        # Check if we have "and" separators (BibTeX style)
        if ' and ' in author_string_lower:
            authors = re.split(r'\s+and\s+', author_string_lower)
        else:
            # Assume comma-separated format (online style)
            # But need to distinguish from "Last, First" commas
            # Strategy: split by comma, then check if each part looks like "First Last"
            parts = author_string_lower.split(',')
            authors = []
            i = 0
            while i < len(parts):
                part = parts[i].strip()
                # Check if this looks like a first name (single word or ends with period)
                # and the next part exists (would be the last name)
                if i + 1 < len(parts):
                    next_part = parts[i + 1].strip()
                    # If next part has multiple words, it's likely "First Last" format
                    # not "Last, First" format
                    if len(next_part.split()) >= 2:
                        # This part is complete author name
                        authors.append(part)
                        i += 1
                    else:
                        # This is "Last, First" format - combine them
                        authors.append(f"{part}, {next_part}")
                        i += 2
                else:
                    authors.append(part)
                    i += 1
        
        # Extract last names
        last_names = []
        for author in authors:
            author = author.strip()
            if not author or author == 'others':  # Skip "and others"
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
            
            # Clean up any remaining punctuation and special characters
            last_name = re.sub(r'[^\w\s-]', '', last_name)
            # Remove common LaTeX formatting patterns
            last_name = re.sub(r'\\[a-z]', '', last_name)  # Remove LaTeX commands like \L
            last_name = re.sub(r'[{}]', '', last_name)  # Remove braces
            last_name = last_name.strip()
            
            if last_name and len(last_name) > 1:
                last_names.append(last_name)
        
        return last_names
    
    def _remove_curly_braces(self, text: str) -> str:
        """
        Remove all curly braces from text.
        
        Args:
            text: Text that may contain curly braces
            
        Returns:
            Text with all curly braces removed
        """
        return text.replace('{', '').replace('}', '')
    
    def _parse_google_scholar_first_result(self, html_content: str) -> Tuple[Optional[str], Optional[List[str]]]:
        """
        Parse Google Scholar HTML to extract title and authors from the first search result.
        
        Args:
            html_content: HTML content from Google Scholar search
            
        Returns:
            Tuple of (title, authors_list) where both can be None if parsing fails
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find the main results container
            results_container = soup.find('div', id='gs_res_ccl_mid')
            if not results_container:
                return None, None
            
            # Find the first result - prefer gs_r gs_or, fallback to gs_r
            first_result = results_container.find('div', class_='gs_r gs_or')
            if not first_result:
                first_result = results_container.find('div', class_='gs_r')
            
            if not first_result:
                return None, None
            
            # Extract title
            title = None
            title_elem = first_result.find(class_='gs_rt')
            if title_elem:
                # Prefer anchor tag if it exists
                title_link = title_elem.find('a')
                if title_link:
                    title_text = title_link.get_text(strip=True)
                else:
                    title_text = title_elem.get_text(strip=True)
                
                # Clean the title - remove leading bracketed labels like [PDF], [HTML], [C], [CITATION]
                # Using specific pattern to avoid removing other brackets
                title = re.sub(r'^\s*\[(PDF|HTML|C|CITATION|BOOK)\]\s*', '', title_text, flags=re.IGNORECASE)
            
            # Extract authors
            authors_list = None
            authors_elem = first_result.find(class_='gs_a')
            if authors_elem:
                authors_text = authors_elem.get_text(strip=True)
                
                # Split on the first dash separator to separate authors from venue/year
                # Using regex to handle non-breaking spaces and other whitespace variations
                parts = re.split(r'\s*-\s*', authors_text, maxsplit=1)
                if parts:
                    authors_part = parts[0]
                    
                    # Remove trailing ellipsis if present (both Unicode and ASCII variants)
                    authors_part = authors_part.rstrip('…...').strip()
                    
                    # Split by commas to get individual authors
                    if authors_part:
                        authors_list = [name.strip() for name in authors_part.split(',') if name.strip()]
            
            return title, authors_list
            
        except Exception:
            return None, None
    
    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """
        Calculate similarity between two titles using difflib.
        
        Args:
            title1: First title
            title2: Second title
            
        Returns:
            Similarity score between 0 and 1
        """
        # Convert to lowercase and remove curly braces for comparison
        title1_processed = self._remove_curly_braces(title1.lower())
        title2_processed = self._remove_curly_braces(title2.lower())
        
        # Use SequenceMatcher from difflib to calculate similarity
        return SequenceMatcher(None, title1_processed, title2_processed).ratio()
    
    def _titles_similar(self, title1: str, title2: str) -> bool:
        """
        Check if two titles are similar enough to be considered the same paper.
        
        Args:
            title1: First title
            title2: Second title
            
        Returns:
            True if titles are similar enough
        """
        similarity = self._calculate_title_similarity(title1, title2)
        return similarity >= self.TITLE_MATCH_THRESHOLD
    
    def _calculate_author_similarity(self, entry_names: List[str], online_names: List[str]) -> float:
        """
        Calculate similarity between two author lists using fuzzy matching.
        
        Args:
            entry_names: List of author last names from BibTeX entry
            online_names: List of author last names from online source
            
        Returns:
            Similarity score between 0 and 1
        """
        if not entry_names or not online_names:
            return 0.0
        
        # Use fuzzy matching on last names to handle misspellings and variations
        matching_authors = 0
        for entry_name in entry_names:
            for online_name in online_names:
                # Exact match
                if entry_name == online_name:
                    matching_authors += 1
                    break
                # Check if one is substring of the other (e.g., "kaiser" vs "kaiserlukasz")
                elif entry_name in online_name or online_name in entry_name:
                    matching_authors += 1
                    break
                # Fuzzy match using simple edit distance heuristic
                # If names are similar length and differ by only 1-2 characters
                elif self._fuzzy_match(entry_name, online_name):
                    matching_authors += 1
                    break
        
        return matching_authors / max(len(entry_names), len(online_names))
    
    def _fuzzy_match(self, str1: str, str2: str, threshold: int = 2) -> bool:
        """
        Simple fuzzy matching for author names.
        
        Args:
            str1: First string
            str2: Second string
            threshold: Maximum edit distance to consider a match
            
        Returns:
            True if strings are similar enough
        """
        # If length difference is too large, not a match
        if abs(len(str1) - len(str2)) > threshold:
            return False
        
        # Simple Levenshtein distance calculation
        if len(str1) < len(str2):
            str1, str2 = str2, str1
        
        if len(str2) == 0:
            return len(str1) <= threshold
        
        previous_row = range(len(str2) + 1)
        for i, c1 in enumerate(str1):
            current_row = [i + 1]
            for j, c2 in enumerate(str2):
                # Cost of insertions, deletions, or substitutions
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1] <= threshold
    
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
                msg = "⚠ Title matches but author list mismatch detected"
                if details and details.get('online_authors'):
                    msg += f"\n    BibTeX authors: {details['entry_authors']}"
                    msg += f"\n    Online authors: {details['online_authors']}"
                    msg += f"\n    Source: {details['source_url']}"
                return False, msg
            elif not title_match and author_match:
                msg = "⚠ Title mismatch detected"
                if details and details.get('online_title'):
                    msg += f"\n    BibTeX title: {details['entry_title']}"
                    msg += f"\n    Online title: {details['online_title']}"
                    msg += f"\n    Source: {details['source_url']}"
                return False, msg
            else:
                msg = "⚠ Both title and author mismatches detected"
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
                msg = "⚠ Title mismatch detected"
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
