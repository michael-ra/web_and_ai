import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


class SimpleCrawler:
    """
    A simple web crawler for indexing and searching web pages.

    Attributes:
    - base_url (str): The base URL to start crawling from.
    - visited_urls (set): A set of URLs that have already been visited.
    - index (dict): The indexed data from crawled web pages.
    - pai_methods (dict): A dictionary of methods for parsing and indexing (pai).
    - pai (str): The current parsing and indexing method in use.
    """
    def __init__(self, base_url):
        """
        Initializes the SimpleCrawler with a specified base URL.

        Parameters:
        - base_url (str): The starting URL for the crawler.
        """
        self.pai = "freq"
        self.base_url = base_url
        self.visited_urls = set()
        self.index = {}
        self.pai_methods = {
            "freq": self.parse_and_index_freq,
            "simple": self.parse_and_index_simple
        }

    def crawl(self, url):
        """
        Crawls a website starting from the given URL.

        Recursively visits and parses all accessible pages within the same domain, avoiding revisits.

        Parameters:
        - url (str): The URL to start crawling from.
        """
        if url in self.visited_urls:
            return
        self.visited_urls.add(url)

        try:
            response = requests.get(url)
            if 'text/html' in response.headers['Content-Type']:
                parse_method = self.pai_methods.get(self.pai)
                if parse_method:
                    parse_method(url, response.text)
                soup = BeautifulSoup(response.text, 'html.parser')
                for link in soup.find_all('a', href=True):
                    full_url = urljoin(url, link['href'])
                    if urlparse(full_url).netloc == urlparse(url).netloc:
                        self.crawl(full_url)
        except requests.RequestException:
            pass

    def parse_and_index_simple(self, url, html_content):
        """
        Parses and indexes the HTML content of a page using a simple method.

        Extracts text from HTML and indexes each word with the corresponding URL.

        Parameters:
        - url (str): The URL of the page being parsed.
        - html_content (str): The HTML content of the page.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        text = soup.get_text()
        for word in text.split():
            if word not in self.index:
                self.index[word] = []
            self.index[word].append(url)

    def parse_and_index_freq(self, url, html_content):
        """
        Parses and indexes the HTML content of a page, focusing on word frequency.

        Extracts text from HTML and creates a frequency count of each word associated with the URL.

        Parameters:
        - url (str): The URL of the page being parsed.
        - html_content (str): The HTML content of the page.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        text = soup.get_text()
        for word in text.split():
            if word not in self.index:
                self.index[word] = {}
            if url not in self.index[word]:
                self.index[word][url] = 0
            self.index[word][url] += 1

    def search(self, words):
        """
        Searches the index for the given words and returns matching URLs.

        Parameters:
        - words (list of str): The words to search in the index.

        Returns:
        - list of str: A list of URLs where the search words were found.
        """
        return [url for word in words if word in self.index for url in self.index[word]]


if __name__ == "__main__":
    crawler = SimpleCrawler("https://vm009.rz.uos.de/crawl/index.html")
    crawler.crawl(crawler.base_url)
    print(crawler.search(["platypus"]))
    print(crawler.index)