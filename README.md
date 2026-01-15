# verify_citations

A simple CLI utility to verify citations in BibTeX files by checking if they are valid or potentially hallucinated.

## Features

This tool performs automated checks to verify citations:

1. **Online Findability**: Checks if the paper can be found online with multiple search engines:
   - arXiv (direct lookup when arXiv ID is available)
   - Semantic Scholar (academic paper database with API)
   - Google Scholar (scholarly articles search)
   - DuckDuckGo (general web search as fallback)

2. **URL Validation**: Verifies that provided links are correct and accessible

3. **Metadata Verification**: Checks if both the title AND author list match what's found online
   - Compares paper titles with word-overlap similarity (70% threshold)
   - Validates author lists by extracting and comparing author last names (50% match threshold)
   - Works with arXiv and Semantic Scholar sources

4. **Version Information**: Identifies the correct version among different ones online (arXiv, journal, conference)

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

```
=== Citation Verification Tool ===

Processing: examples/sample.bib

Found 3 citation(s) to verify

[1/3] Verifying:
  [vaswani2017attention] Attention is All you Need (Vaswani et al., 2017)
  Status: ✓ VERIFIED
    ✓ Paper found online via search
    ✓ URL is valid and accessible
    ℹ Version: arXiv:1706.03762

[2/3] Verifying:
  [fake2023paper] This is a Fake Paper (Nobody et al., 2023)
  Status: ✗ ISSUES FOUND
    ✗ Could not find paper online
    ✗ URL returns 404 (not found)

============================================================
SUMMARY

Total citations: 3
Verified: 2
Issues found: 1
Incomplete: 0
```

## Example BibTeX File

See `examples/sample.bib` for an example BibTeX file with various citation types.

## How It Works

The tool:
- Parses BibTeX files to extract citation metadata
- Performs web searches across multiple sources to verify paper existence:
  - arXiv for papers with arXiv IDs
  - Semantic Scholar API for academic papers
  - Google Scholar for scholarly articles
  - DuckDuckGo for general web search
- Validates URLs by making HTTP requests
- Extracts and compares both title AND author metadata from online sources
- Uses word-overlap similarity for title matching
- Compares author last names to detect author list mismatches
- Identifies different versions (preprints vs. published)
- Provides a clear report of verification results

## Requirements

- Python 3.8+
- Internet connection for verification

## Dependencies

- `bibtexparser` - BibTeX file parsing
- `requests` - HTTP requests for URL validation
- `beautifulsoup4` - HTML parsing for metadata extraction
- `click` - CLI interface
- `colorama` - Colored terminal output

## Future Enhancements

- GUI interface
- More sophisticated metadata matching
- Support for more scholarly databases (PubMed, IEEE, ACM)
- DOI resolution and verification
- Citation style validation
- Batch processing with parallelization

## License

MIT License
