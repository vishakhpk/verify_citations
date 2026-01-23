"""
Command-line interface for citation verification.
"""

import sys
from pathlib import Path

import click
from colorama import init, Fore, Style

from .parser import parse_bibtex_file, format_entry_summary
from .verifier import CitationVerifier


@click.command()
@click.argument('bibtex_file', type=click.Path(exists=True))
@click.option('--timeout', default=10, help='Request timeout in seconds')
@click.option('--max-retries', default=3, help='Maximum retries for 429 rate limit errors')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed output')
@click.option('--summary-only', '-s', is_flag=True, help='Show only summary')
def main(bibtex_file, timeout, max_retries, verbose, summary_only):
    """
    Verify citations in a BibTeX file.
    
    This tool checks if citations are valid by:
    1. Verifying the paper can be found online with a quick search
    2. Validating provided URLs are correct and accessible
    3. Checking title and author metadata
    4. Identifying version information (arXiv, published, etc.)
    
    Example:
        verify-citations references.bib
        verify-citations references.bib --verbose
        verify-citations references.bib --max-retries 5
    """
    # Initialize colorama for cross-platform colored output
    init(autoreset=True)
    
    click.echo(f"{Fore.CYAN}=== Citation Verification Tool ==={Style.RESET_ALL}\n")
    click.echo(f"Processing: {bibtex_file}\n")
    
    try:
        # Parse BibTeX file
        entries = parse_bibtex_file(bibtex_file)
        click.echo(f"Found {len(entries)} citation(s) to verify\n")
        
        if not entries:
            click.echo(f"{Fore.YELLOW}No citations found in file{Style.RESET_ALL}")
            return
        
        # Verify each citation
        verifier = CitationVerifier(timeout=timeout, max_retries=max_retries)
        results = []
        
        for i, entry in enumerate(entries, 1):
            if not summary_only:
                click.echo(f"{Fore.CYAN}[{i}/{len(entries)}] Verifying:{Style.RESET_ALL}")
                click.echo(f"  {format_entry_summary(entry)}")
            
            result = verifier.verify_citation(entry)
            results.append(result)
            
            if not summary_only:
                _print_result(result, verbose)
                click.echo()  # Blank line between entries
        
        # Print summary
        _print_summary(results)
        
    except FileNotFoundError:
        click.echo(f"{Fore.RED}Error: File not found: {bibtex_file}{Style.RESET_ALL}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"{Fore.RED}Error: {str(e)}{Style.RESET_ALL}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _print_result(result: dict, verbose: bool):
    """Print verification result for a single citation."""
    status = result['status']
    
    # Status indicator
    if status == 'verified':
        status_msg = f"{Fore.GREEN}✓ VERIFIED{Style.RESET_ALL}"
    elif status == 'issues_found':
        status_msg = f"{Fore.RED}✗ ISSUES FOUND{Style.RESET_ALL}"
    else:
        status_msg = f"{Fore.YELLOW}⚠ INCOMPLETE{Style.RESET_ALL}"
    
    click.echo(f"  Status: {status_msg}")
    
    # Print verbose logs if in verbose mode
    if verbose and result.get('verbose_logs'):
        for log in result['verbose_logs']:
            click.echo(f"  {Fore.CYAN}{log}{Style.RESET_ALL}")
    
    # Print messages
    if verbose or result['status'] != 'verified':
        for msg in result['messages']:
            # Color code messages
            if msg.startswith('✓'):
                colored_msg = f"{Fore.GREEN}{msg}{Style.RESET_ALL}"
            elif msg.startswith('✗'):
                # Red for critical errors (URL invalid, paper not found)
                colored_msg = f"{Fore.RED}{msg}{Style.RESET_ALL}"
            elif msg.startswith('⚠'):
                # Yellow for warnings (metadata mismatches)
                colored_msg = f"{Fore.YELLOW}{msg}{Style.RESET_ALL}"
            elif msg.startswith('ℹ'):
                colored_msg = f"{Fore.CYAN}{msg}{Style.RESET_ALL}"
            else:
                colored_msg = msg
            click.echo(f"    {colored_msg}")


def _print_summary(results: list):
    """Print summary of all verification results."""
    click.echo(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}SUMMARY{Style.RESET_ALL}\n")
    
    verified = sum(1 for r in results if r['status'] == 'verified')
    issues = sum(1 for r in results if r['status'] == 'issues_found')
    incomplete = sum(1 for r in results if r['status'] == 'incomplete')
    
    # Count citations with actual 403 errors (where has_403 flag is True)
    citations_with_403 = [r for r in results if r.get('has_403', False)]
    
    # Count citations where metadata could not be verified automatically
    # This matches the count of "Could not verify metadata automatically" messages
    citations_no_metadata_verification = [
        r for r in results 
        if r.get('metadata_not_verified', False)
    ]
    
    total = len(results)
    
    click.echo(f"Total citations: {total}")
    click.echo(f"{Fore.GREEN}Verified: {verified}{Style.RESET_ALL}")
    click.echo(f"{Fore.RED}Issues found: {issues}{Style.RESET_ALL}")
    click.echo(f"{Fore.YELLOW}Incomplete: {incomplete}{Style.RESET_ALL}")
    
    # Show citations with issues (excluding those that only have 403 errors)
    if issues > 0:
        click.echo(f"\n{Fore.YELLOW}Citations with issues:{Style.RESET_ALL}")
        for result in results:
            if result['status'] == 'issues_found':
                click.echo(f"- {result['id']}: {result['title']}")
    
    # Show citations with 403 errors separately
    if citations_with_403:
        click.echo(f"\n{Fore.YELLOW}Citations where you should manually check the links due to a 403 error:{Style.RESET_ALL}")
        for result in citations_with_403:
            click.echo(f"- {result['id']}: {result['title']}")
    
    # Show citations where authors could not be verified
    if citations_no_metadata_verification:
        click.echo(f"\n{Fore.YELLOW}Citations where author list could not be verified:{Style.RESET_ALL}")
        click.echo(f"Count: {len(citations_no_metadata_verification)}\n")
        for result in citations_no_metadata_verification:
            click.echo(f"- {result['id']}: {result['title']}")


if __name__ == '__main__':
    main()
