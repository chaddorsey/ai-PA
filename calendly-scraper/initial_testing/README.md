# Initial Testing and Prototype Files

This folder contains various prototype implementations and test scripts that were developed during the exploration phase of the Calendly scraping functionality.

## Production Implementation

The production-ready implementation is in the parent directory:
- **`calendly_slots.py`** - The functional, verified implementation used for the MCP server

## Files in this Directory

These files are kept for reference but should not be used in production:

- `calendly_letta_tool.py` - Early prototype Letta tool (unverified)
- `calendly_hybrid_scraper.py` - Hybrid approach with various fallbacks  
- `calendly_scrape.py` - Simple scraper using undocumented API
- `calendly_event_to_times.py` - Event-focused scraper
- `calendly_from_event.py` - Another event variant
- `calendly_list_events.py` - Event listing tool
- `calendly_profile_autodiscover_to_hours.py` - Profile-based discovery
- `calendly_profile_to_times.py` - Profile to times conversion
- `calendly_sniff_and_scrape.py` - Network sniffing approach
- `calendly_url_to_times_bsoup.py` - BeautifulSoup-based scraper

## Usage Note

For new development, reference and extend `../calendly_slots.py` only.

