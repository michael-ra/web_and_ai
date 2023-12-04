from flask import Flask, request, render_template
from openai import AsyncOpenAI

from evolving_crawler import SimpleCrawler

app = Flask(__name__)

cur_url = "https://vm009.rz.uos.de/crawl/index.html"


async def get_completion(prompt, keywords):
    """
    Asynchronously retrieves two types of completions from OpenAI's GPT-3.5 and GPT-4 models.

    Parameters:
    - prompt (str): Text to be summarized.
    - keywords (str): Keywords to evaluate their relevancy towards the prompt.

    Returns:
    - Tuple[Completion]: A tuple containing two elements:
      1. Summary of the prompt using GPT-3.5.
      2. Relevancy score (0-1) and a three-word reason using GPT-4, based on the provided keywords and prompt.

    This function requires an AsyncOpenAI client with a valid API key.
    """
    aclient = AsyncOpenAI(
        api_key=""
    )
    completion1 = await aclient.chat.completions.create(model="gpt-3.5-turbo-1106", messages=[
        {"role": "user", "content": "Summarize this in a very short sentence: " + prompt}])
    completion2 = await aclient.chat.completions.create(model="gpt-4-1106-preview", messages=[{"role": "user",
                                                                                               "content": "Return ONLY a float value from 0-1 with the relevancy score and a 3 word reason for " + keywords + " towards the text: " + prompt}])
    return completion1, completion2


@app.route('/')
def home():
    """
    Handles the root URL ('/') of the web application.

    Renders the 'search_form.html' template, passing 'searchable_dir' as a context variable set to 'cur_url'.

    Returns:
    - Rendered template: The 'search_form.html' page with the context variable.
    """
    return render_template('search_form.html',
                           searchable_dir=cur_url)


@app.route('/search')
async def search():
    """
    Asynchronous route handler for '/search'. Processes user search queries.

    Retrieves the query from request arguments, performs a search, and processes each result asynchronously
    to get a summary and relevancy score. Returns a rendered template with search results and related information.

    Returns:
    - Rendered template: The 'search_results.html' page populated with search results, the query,
      the number of hits, and the current URL.
    """
    query = request.args.get('q')
    results = perform_search(query)  # Assuming this is a synchronous function
    for result in range(len(results)):
        response, score = await get_completion(results[result]['content'], query)  # Await the async call
        results[result]['summary'] = response.choices[0].message.content  # Extract the response content
        results[result]['score'] = score.choices[0].message.content  # Extract the response content
    return render_template('search_results.html', results=results, query=query, num_hits=len(results),
                           searchable_dir=cur_url)


def perform_search(query):
    """
    Performs a search based on the given query. Initializes a SimpleCrawler with the current URL and a flag to rebuild the index.
    Executes a crawl starting from the base URL of the crawler, and then performs a search using the provided query.

    Parameters:
    - query (str): The search query.

    Returns:
    - list: Search results returned by the crawler's search method.
    """
    crawler = SimpleCrawler(cur_url, rebuild_index=True)
    crawler.crawl(crawler.base_url)
    return crawler.search(query)
    pass


if __name__ == '__main__':
    app.run(debug=True)
