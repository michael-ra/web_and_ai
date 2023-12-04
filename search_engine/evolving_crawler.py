import math
import shutil
from collections import Counter

import requests
from bs4 import BeautifulSoup
from whoosh.analysis import RegexTokenizer, LowercaseFilter, StandardAnalyzer
from whoosh.highlight import Highlighter
from whoosh.index import create_in
from whoosh.fields import Schema, TEXT, ID
from whoosh.qparser import WildcardPlugin
from whoosh.qparser import QueryParser, MultifieldParser, AndGroup
from whoosh.query import Phrase, Term, And
import re
from whoosh.qparser import FuzzyTermPlugin
import os
from urllib.parse import urljoin, urlparse
import urllib.robotparser

from whoosh.query import Variations
from whoosh.searching import NoTermsException


def calculate_tf(text):
    """
    Calculates the term frequency (TF) for each token in the given text.

    Parameters:
    - text (str): The text to analyze.

    Returns:
    - Counter: A collection that maps each token to its frequency in the text.
    """
    tokens = text.split()
    tf = Counter(tokens)
    return tf


class SimpleCrawler:
    """
    A simple web crawler that crawls, indexes, and searches web pages.

    Attributes:
    - base_url (str): The base URL for crawling.
    - visited_urls (set): Set of URLs that have already been visited.
    - index (dict): Dictionary to store the indexed data from crawled pages.
    - pai_methods (dict): Dictionary mapping parse and index methods.
    - pai (str): Current parse and index method.
    - case_sensitive_analyzer (RegexTokenizer): Analyzer for case-sensitive text.
    - default_analyzer (StandardAnalyzer): Default analyzer for text.
    - links (dict): Dictionary to store links found during crawling.
    - robot_parser (RobotFileParser): Parser to check 'robots.txt' for allowed URLs.
    - popularity_scores (dict): Scores for page popularity.
    - schema (Schema): Schema for the Whoosh index.
    - index_dir (str): Directory path for storing the index.
    - ix (Index): The Whoosh index object.
    """
    def __init__(self, base_url, rebuild_index=False):
        """
        Initializes the SimpleCrawler with a specified base URL and rebuild index option.

        Parameters:
        - base_url (str): The base URL to start crawling from.
        - rebuild_index (bool): Whether to rebuild the index on initialization.
        """
        self.pai_methods = {
            "one": self.parse_and_index
        }
        self.pai = "one"
        self.base_url = base_url
        self.visited_urls = set()
        self.index = {}
        self.case_sensitive_analyzer = RegexTokenizer()
        self.default_analyzer = StandardAnalyzer()
        self.links = {}
        self.robot_parser = urllib.robotparser.RobotFileParser()
        self.popularity_scores = None

        self.schema = Schema(
            title=TEXT(stored=True,analyzer=self.default_analyzer),
            url=ID(stored=True, unique=True),
            content_cs=TEXT(stored=True, analyzer=self.case_sensitive_analyzer),  # Case-Sensitive
            content_ci=TEXT(stored=True, analyzer=self.default_analyzer)  # Case-Insensitive
        )

        self.index_dir = "indexdir"
        if rebuild_index and os.path.exists(self.index_dir):
            shutil.rmtree(self.index_dir) # todo for me, look into why meta is no copied rmtree

        if not os.path.exists(self.index_dir):
            os.mkdir(self.index_dir)

        self.ix = create_in(self.index_dir, self.schema)

    def calculate_idf(self):
        """
        Calculates the inverse document frequency (IDF) for each term in the index.

        Returns:
        - dict: A dictionary mapping terms to their IDF scores.
        """
        idf_scores = {}
        with self.ix.searcher() as searcher:
            doc_count = searcher.doc_count()
            all_terms = set(searcher.lexicon("content_ci"))

            for term in all_terms:
                # doc freq across case insensetive
                df_ci = searcher.doc_frequency("content_ci", term)
                total_df = df_ci

                idf_scores[term.decode('utf-8')] = math.log(doc_count / total_df) if total_df else 0
        print("idfscores:" + idf_scores.__str__())
        return idf_scores

    def isallowedurl(self, url):
        """
        Checks if the given URL is allowed to be fetched based on the robots.txt rules.

        Parameters:
        - url (str): The URL to check.

        Returns:
        - bool: True if the URL is allowed, False otherwise.
        """
        domain = urlparse(url).scheme + "://" + urlparse(url).netloc
        self.robot_parser.set_url(domain + "/robots.txt")
        self.robot_parser.read()
        return self.robot_parser.can_fetch("*", url)

    def crawl(self, url):
        """
        Crawls a website starting from the given URL.

        Parameters:
        - url (str): The URL to start crawling from.
        """
        if not self.isallowedurl(url):
            print(f"Crawling blocked by robots.txt: {url}")
            return
        if url in self.visited_urls:
            return
        self.visited_urls.add(url)
        self.links[url] = set()

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
                        self.links[url].add(full_url)
                        self.crawl(full_url)
        except requests.RequestException:
            pass

        self.popularity_scores = self.compute_popularity_scores(self.links)

    def compute_popularity_scores(self, links):
        """
        Computes popularity scores for each page based on the link structure.

        Parameters:
        - links (dict): A dictionary of pages and their linked pages.

        Returns:
        - dict: A dictionary mapping pages to their popularity scores.
        """
        scores = {page: 1.0 for page in links}
        for _ in range(100):  # todo cvar
            new_scores = {page: 0 for page in links}
            for page, linked_pages in links.items():
                for linked_page in linked_pages:
                    new_scores[linked_page] += scores[page] / len(linked_pages)
            scores = new_scores
        return scores

    def parse_and_index(self, url, html_content):
        """
        Parses and indexes a web page.

        Parameters:
        - url (str): The URL of the page.
        - html_content (str): The HTML content of the page.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        title = soup.title.string if soup.title else url
        text = soup.get_text()

        writer = self.ix.writer()
        writer.add_document(title=title, url=url, content_ci=text, content_cs=text)
        writer.commit()

    def search(self, query_string):
        """
        Performs a search in the indexed data for the given query string.

        Parameters:
        - query_string (str): The query string to search for.

        Returns:
        - list: A list of search results, each containing a title, URL, highlight, and content.
        """
        idf_scores = self.calculate_idf()
        phrase_matches = re.findall(r'"([^"]+)"', query_string)  # phrases without quotes extraction
        non_phrase_query = re.sub(r'"[^"]+"', '', query_string).strip()  # quotes removal and extraction of "" phrases
        with self.ix.searcher() as searcher:

            final_query_parts = []
            highlight_fields = []

            # exact matches in quotes ""
            for phrase in phrase_matches:
                phrase_terms = phrase.split()
                phrase_query = Phrase("content_cs", phrase_terms)
                final_query_parts.append(phrase_query)
                highlight_fields.append("content_cs")

            # normal query
            if non_phrase_query:
                non_phrase_parser = QueryParser("content_ci", schema=self.ix.schema)
                non_phrase_parser.add_plugin(FuzzyTermPlugin())
                non_phrase_query_parsed = non_phrase_parser.parse(non_phrase_query+"~")
                print(non_phrase_query_parsed)
                final_query_parts.append(non_phrase_query_parsed)
                highlight_fields.append("content_ci")

            final_query = And(final_query_parts) if final_query_parts else None

            results = searcher.search(final_query, limit=None, terms=True) if final_query else []
                                                                                                #todo correct spellingmistakes
            scored_results = []
            # I know whooosh can tfidf - but making it yourself is cool also and can include pageRank :D
            # If we should use that it would be weighting=scoring.TF_IDF()
            for result in results:
                try:
                    # make tf
                    matched_terms = result.matched_terms()
                    terms = [term.decode('utf-8') for _, term in matched_terms]
                    text_tf = result.fields()["content_ci"]
                    tf_scores = calculate_tf(text_tf)
                    tf_values = [(term, tf_scores.get(term, 0)) for term in terms]
                    tf_idf_score = sum(frequency * idf_scores.get(term, 0) for term, frequency in tf_values)
                    # tf idf closed, now popularity
                    popularity_score = self.popularity_scores[result['url']]
                    scored_results.append((tf_idf_score+popularity_score, result))
                except NoTermsException:
                    pass

            scored_results.sort(reverse=True, key=lambda x: x[0])

            # make highlights for results
            combined_highlights = {}
            for score, result in scored_results:  # Iterate over scored_results
                url = result['url']
                if url not in combined_highlights:
                    combined_highlights[url] = []

                for field in highlight_fields:
                    if result.highlights(field):
                        combined_highlights[url].append(result.highlights(field))

            # make final results
            final_results = []
            for score, result in scored_results:
                content = result['content_ci']
                url = result['url']
                title = result['title']
                # highlights combining
                combined_excerpt = ' ... '.join(set(combined_highlights[url]))  # Remove duplicates and join
                final_results.append({'title': title, 'url': url, 'highlight': combined_excerpt, 'content': content})

            return final_results

if __name__ == "__main__":
    crawler = SimpleCrawler("https://vm009.rz.uos.de/crawl/index.html", rebuild_index=True)
    crawler.crawl(crawler.base_url)
    print(crawler.search('platypu'))
