# Verify BibTeX Citations

A simple CLI utility to verify citations in BibTeX files by checking if they are valid or potentially hallucinated.

## Features

This tool performs automated checks to verify citations:

1. **Online Findability**: Checks if the paper can be found online with multiple search engines:
   - **arXiv**: Direct lookup when arXiv ID is available, plus API-based title search
   - **ACL Anthology**: Natural language processing and computational linguistics papers
   - **Semantic Scholar**: Academic paper database with comprehensive API
   - **DBLP**: Computer science bibliography
   - **Google Scholar**: Broad scholarly articles search
   - **DuckDuckGo**: General web search as fallback

2. **URL Validation**: Verifies that provided links are correct and accessible
   - Handles HTTP status codes with appropriate error reporting
   - **403 Forbidden handling**: Recognizes when servers block automated access and flags for manual verification
   - Distinguishes between critical errors (404) and warnings (403, connection issues)
   - Supports automatic conversion of arXiv IDs to full URLs

3. **Metadata Verification**: Checks if both the title AND author list match what's found online
   - Compares paper titles with word-overlap similarity (70% threshold for metadata verification, 50% for initial findability)
   - Validates author lists by extracting and comparing author last names (50% match threshold)
   - **Handles name format differences**: Recognizes "Last, First" and "First Last" as the same author
   - **Fuzzy matching**: Tolerates small misspellings (up to 2 character differences) in author names
   - **Special character handling**: Correctly processes LaTeX special characters in names
   - **"et al" / "and others" support**: Validates that all explicitly listed authors appear in online source
   - Works with arXiv, Semantic Scholar, and DBLP sources

4. **Version Information**: Identifies the correct version among different ones online
   - arXiv preprints with version numbers
   - Journal publications
   - Conference proceedings
   - DOI information when available

5. **Color-Coded Output**: Clear visual feedback
   - 🟢 **Green (✓)**: Successfully verified
   - 🔴 **Red (✗)**: Critical errors (URL invalid, paper not found, metadata mismatch)
   - 🟡 **Yellow (⚠)**: Warnings (403 errors, metadata couldn't be verified)
   - 🔵 **Cyan (ℹ)**: Informational messages (version info, verbose logs)

## Installation

```bash
# Clone the repository
git clone https://github.com/vishakhpk/verify_citations.git
cd verify_citations

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

## Usage

### Basic Usage

```bash
verify-citations path/to/references.bib
```

### Options

```bash
verify-citations references.bib --verbose        # Show detailed output
verify-citations references.bib --summary-only   # Show only summary
verify-citations references.bib --timeout 20     # Set request timeout
```

### Example Output

When citations are verified successfully:
```
=== Citation Verification Tool ===

Processing: examples/sample.bib

Found 3 citation(s) to verify

[1/3] Verifying:
  [vaswani2017attention] Attention is All you Need (Vaswani et al., 2017)
  Status: ✓ VERIFIED
    ✓ Paper found online via search
    ✓ URL is valid and accessible
    ✓ Metadata (title and authors) verified
    ℹ Version: arXiv:1706.03762
```

When there are metadata mismatches (shown in yellow/red), detailed information is provided:
```
[2/3] Verifying:
  [wrong2023] Wrong Paper Entry (Smith, John, 2023)
  Status: ⚠ ISSUES FOUND
    ✓ Paper found online via search
    ⚠ Title matches but author list mismatch detected
      BibTeX authors: Smith, John and Doe, Jane
      Online authors: Johnson, Alice and Brown, Bob
      Source: https://arxiv.org/abs/1706.03762
```

When there are critical errors (shown in red):
```
[3/3] Verifying:
  [fake2023paper] This is a Fake Paper (Nobody et al., 2023)
  Status: ✗ ISSUES FOUND
    ✗ Could not find paper online
    ✗ URL returns 404 (not found)
```

Summary:
```
============================================================
SUMMARY

Total citations: 3
Verified: 1
Issues found: 2
Incomplete: 0

Citations with issues:
  - wrong2023: Wrong Paper Entry
  - fake2023paper: This is a Fake Paper

Citations where you should manually check the links due to a 403 error:
  - example2023: Example Paper Title

Citations where author list could not be verified:
Count: 1

  - another2023: Another Example Paper
```

## Example BibTeX File

See `examples/sample.bib` for an example BibTeX file with various citation types.

## How It Works

The tool:
- Parses BibTeX files to extract citation metadata
- Performs web searches across multiple sources to verify paper existence:
  - **arXiv**: Direct ID lookup and API-based title search for preprints
  - **ACL Anthology**: NLP/computational linguistics papers via website search
  - **Semantic Scholar API**: Academic papers with structured metadata
  - **DBLP**: Computer science bibliography search
  - **Google Scholar**: Broad scholarly article search
  - **DuckDuckGo**: General web search fallback
- Validates URLs by making HTTP requests
  - Handles HEAD requests with GET fallback
  - Distinguishes critical errors (404, invalid format) from warnings (403, timeouts)
- Extracts and compares both title AND author metadata from online sources
  - Uses word-overlap similarity for title matching (50% for findability, 70% for metadata verification)
  - Compares author last names with fuzzy matching to detect mismatches
  - Handles "et al" / "and others" by validating listed authors
- Identifies different versions (preprints vs. published)
- Provides a clear report of verification results with color-coded output

## Requirements

- Python 3.8+
- Internet connection for verification

## Dependencies

- `bibtexparser` - BibTeX file parsing
- `requests` - HTTP requests for URL validation
- `beautifulsoup4` - HTML parsing for metadata extraction
- `lxml` - XML/HTML parsing library (used by BeautifulSoup)
- `click` - CLI interface
- `colorama` - Colored terminal output

## Future Enhancements

- GUI interface
- More sophisticated metadata matching algorithms
- Additional scholarly databases (PubMed, IEEE Xplore, ACM Digital Library)
- Enhanced DOI resolution and verification
- Citation style validation (APA, MLA, Chicago, etc.)
- Batch processing with parallelization for faster verification
- Export reports in multiple formats (JSON, CSV, HTML)
- Integration with reference managers (Zotero, Mendeley)

## License

MIT License
