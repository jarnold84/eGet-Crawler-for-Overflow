# services/crawler/content_extractor.py
"""
Extract the “main article” or primary content from raw HTML.

A full implementation might use:
* readability‑lxml / trafilatura,
* custom heuristics to drop nav/footer,
* language detection, title extraction, etc.

Here we return the raw HTML as both markdown and HTML so the
scraper can continue to work.  Swap this out with your real
extraction logic whenever you’re ready.
"""
"""
Placeholder content‑extractor.

The production scraper currently uses the richer implementation defined in
`services/scraper/scraper.py`.  This module is retained as a convenient
location for a minimal stub that can be swapped in during early prototyping
or when experimenting with alternative extraction libraries (e.g. readability‑lxml).

If you decide to use this stub, import it explicitly:
    from services.crawler.content_extractor import ContentExtractor
"""

class ContentExtractor:
    """Very small placeholder – replace with a real extractor later."""

    async def extract_content(self, html: str, only_main: bool = True) -> dict:
        """
        Return a dictionary mimicking the shape expected by the scraper.

        Parameters
        ----------
        html: str
            The full page source.
        only_main: bool
            Ignored in the stub – kept for signature compatibility.

        Returns
        -------
        dict
            Keys: ``markdown``, ``html``, ``metadata``.
        """
        # In a real extractor you’d convert HTML → markdown, pull title, etc.
        return {
            "markdown": html,      # placeholder – raw HTML as markdown
            "html": html,
            "metadata": {}         # empty metadata dict for now
        }
