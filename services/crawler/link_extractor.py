from typing import List, Set, Optional
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode
from bs4 import BeautifulSoup
import re
from loguru import logger
import robotexclusionrulesparser
import requests
from models.crawler_request import CrawlerRequest

class LinkExtractor:
    """
    Extracts and validates links from HTML content.
    Handles URL normalization, filtering, and robots.txt compliance.
    """
    
    def __init__(self, request: CrawlerRequest):
        """
        Initialize the LinkExtractor with crawler request settings.
        
        Args:
            request (CrawlerRequest): The crawler request containing settings
        """
        self.base_domain = urlparse(str(request.url)).netloc
        self.exclude_patterns = [re.compile(p) for p in request.exclude_patterns] if request.exclude_patterns else []
        self.include_patterns = [re.compile(p) for p in request.include_patterns] if request.include_patterns else []
        self.respect_robots = request.respect_robots_txt
        self._robots_parser = robotexclusionrulesparser.RobotExclusionRulesParser()
        self._load_robots_txt(str(request.url))

    def _load_robots_txt(self, url: str) -> None:
        """Load and parse robots.txt if it exists"""
        try:
            if self.respect_robots:
                parsed_url = urlparse(url)
                robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
                response = requests.get(robots_url, timeout=10)
                if response.status_code == 200:
                    self._robots_parser.parse(response.text)
        except Exception as e:
            logger.warning(f"Failed to load robots.txt: {e}")

    def _is_allowed_by_robots(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt"""
        if not self.respect_robots:
            return True
        return self._robots_parser.is_allowed("*", url)

    def _normalize_url(self, url: str, base_url: str) -> Optional[str]:
        """Normalize URL to absolute form while keeping pagination queries"""
        try:
            absolute_url = urljoin(base_url, url)
            parsed = urlparse(absolute_url)

            # Filter query params to keep common pagination keys
            query_params = parse_qsl(parsed.query, keep_blank_values=True)
            allowed = {"page", "p", "start"}
            filtered = [(k, v) for k, v in query_params if k in allowed]
            query = urlencode(filtered, doseq=True)

            normalized = parsed._replace(
                fragment="",
                params="",
                query=query
            ).geturl()

            return normalized
        except Exception as e:
            logger.debug(f"URL normalization failed for {url}: {e}")
            return None

    def _should_include_url(self, url: str) -> bool:
        """
        Check if URL should be included based on patterns and domain.
        
        Args:
            url (str): URL to check
            
        Returns:
            bool: True if URL should be included
        """
        # Check domain
        if urlparse(url).netloc != self.base_domain:
            return False

        # Check exclude patterns
        for pattern in self.exclude_patterns:
            if pattern.search(url):
                return False

        # Check include patterns
        if self.include_patterns:
            return any(pattern.search(url) for pattern in self.include_patterns)

        return True

    def extract_links(self, html: str, base_url: str) -> List[str]:
        """
        Extract valid links from HTML content.
        
        Args:
            html (str): HTML content to parse
            base_url (str): Base URL for resolving relative links
            
        Returns:
            List[str]: Ordered list of valid, normalized URLs
        """
        seen: Set[str] = set()
        profile_links: List[str] = []
        pagination_links: List[str] = []
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Find all links
            for link in soup.find_all('a', href=True):
                url = link['href']
                rel_values = link.get('rel', [])

                normalized_url = self._normalize_url(url, base_url)
                if not normalized_url or normalized_url in seen:
                    continue

                if (self._should_include_url(normalized_url) and
                    self._is_allowed_by_robots(normalized_url)):
                    if 'next' in [r.lower() for r in rel_values] or re.search(r'(?:page|p|start)=\d+', normalized_url):
                        pagination_links.append(normalized_url)
                    else:
                        profile_links.append(normalized_url)
                    seen.add(normalized_url)

        except Exception as e:
            logger.error(f"Error extracting links from {base_url}: {e}")

        return profile_links + pagination_links
