# PR: Prioritize CrossRef DOI resolution in paper search

## Problem

When a BibTeX entry has a valid DOI, the tool ignores it during the paper search (Check 1) and metadata verification (Check 3). Instead it searches by title across arXiv, Semantic Scholar, DBLP, etc. — which can match the **wrong paper** with a similar title.

This is especially common for economics/non-CS papers where title-based search on arXiv or Semantic Scholar returns unrelated results.

### Examples

**Duffie & Epstein (1992)** — DOI `10.2307/2951600`

The title search finds a different paper on arXiv (`1601.03562v1`), producing a false author mismatch:

```
  ✓ Paper found online via search: https://arxiv.org/abs/1601.03562v1
  ⚠ Title matches but author list mismatch detected
    BibTeX authors: Duffie, D. and L.G. Epstein
    Online authors: Anis Matoussi, Hao Xing
```

**Golosov et al. (2014)** — DOI `10.3982/ECTA10217`

Semantic Scholar finds a different paper with a similar title:

```
  ⚠ Both title and author mismatches detected
    BibTeX title: Optimal Taxes on Fossil Fuels in General Equilibrium
    Online title: Optimal taxes on fossil fuels, carbon taxes and environmental targets...
```

Both entries have correct DOIs that resolve to the right papers in CrossRef.

## Solution

Add CrossRef DOI resolution as the **first** (highest-priority) search source. When an entry has a valid DOI, resolve it via the CrossRef API before trying arXiv, Semantic Scholar, or any other title-based source.

### Changes

#### `verify_citations/verifier.py`

**`_check_findable_online()`** — New CrossRef DOI search block at the top of the source list

- If the entry has a DOI matching the `10.XXXX/...` pattern, try `https://api.crossref.org/works/{doi}` first
- On success, return `https://doi.org/{doi}` as the search URL
- On failure (404, 429, network error), fall through to the existing sources (arXiv, Semantic Scholar, etc.)
- Respects `crossref_mailto` for the polite pool

**`_check_metadata()`** — New `doi.org` URL handler

- When the paper was found via DOI resolution, `_check_metadata` now recognizes `doi.org` URLs
- Calls the CrossRef API to retrieve title and author metadata
- Compares using the same `METADATA_SIMILARITY_THRESHOLD` and author matching logic as other sources
- Handles both personal authors (`given`/`family`) and institutional authors (`name`)
- Supports `and others` / `et al` entries via the existing coverage-based matching

**`_check_doi_crossref()`** (from previous PR)

- Added bogus DOI detection: rejects known non-DOI values (`mimeo`, `N/A`, `none`, `TBD`, `forthcoming`, `unpublished`) and strings that don't match the `10.XXXX/` pattern
- URL-encodes DOIs with `quote_plus` for safety

#### `tests/test_doi_crossref.py`

56 tests across 6 test classes:

| Class | Tests | Covers |
|-------|-------|--------|
| `TestCheckDoiCrossref` | 17 | `_check_doi_crossref` method: field matching, mismatches, HTTP errors, fallbacks |
| `TestBogusDoiDetection` | 14 | Bogus/malformed DOI pre-check |
| `TestCrossrefDoiSearch` | 8 | DOI search in `_check_findable_online`: priority, fallthrough, mailto, network errors |
| `TestCrossrefMetadata` | 6 | `_check_metadata` with `doi.org` URLs: title/author matching, institutional authors, et-al |
| `TestUserExamples` | 5 | Exact reproduction of the two reported problem entries (Duffie 1992, Golosov 2014) |
| `TestVerifyCitationDoiIntegration` | 6 | End-to-end `verify_citation` pipeline with DOI |

### Search priority order (updated)

1. **CrossRef DOI resolution** (new — highest priority when DOI present)
2. arXiv by ID
3. arXiv by title
4. ACL Anthology
5. Semantic Scholar
6. DBLP
7. Google Scholar
8. DuckDuckGo

### Design decisions

- **DOI search is first, not exclusive**: if CrossRef fails (404, 429, network error), the existing title-based sources still run as fallback
- **No new dependencies**: uses `requests` (already required) and the CrossRef public API
- **`doi.org` as search URL**: user-friendly link that also lets `_check_metadata` detect the source
- **Follows existing conventions**: same retry logic (`_make_request_with_retry`), same thresholds (`METADATA_SIMILARITY_THRESHOLD`), same tuple return pattern

### No new dependencies

Only uses `requests` (already required) and the public CrossRef API (`api.crossref.org`).

## Testing

```bash
# Run all tests (excluding live integration tests)
pytest tests/ -k "not integration" -v

# Run only the new CrossRef tests
pytest tests/test_doi_crossref.py -v
```

All 84 unit tests pass (50 new + 34 existing).
