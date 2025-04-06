# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from chatgpt_client import ChatGPTClient
from chatgpt_product_fetcher import ChatGPTProductFetcher  # New import
import os
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env file

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000","https://mocktest-ai.com/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DomainsRequest(BaseModel):
    domains: list[str]

# Constants
MAX_CONCURRENT_REQUESTS = 10
MAX_PRODUCTS = 500

# Initialize ChatGPT clients
chatgpt_client = ChatGPTClient(os.getenv("OPENAI_API_KEY"))
chatgpt_fetcher = ChatGPTProductFetcher(os.getenv("OPENAI_API_KEY"))  # New fetcher


async def fetch_page(session, url, semaphore):
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.text()
        except Exception as e:
            print(f"Failed to fetch {url}: {e}")
        return None

def extract_all_links(soup, base_url):
    """Extract all URLs from various HTML elements"""
    links = set()
    for link in soup.find_all('a', href=True):
        full_url = urljoin(base_url, link['href'])
        links.add(full_url)
    for link in soup.find_all('link', href=True):
        full_url = urljoin(base_url, link['href'])
        links.add(full_url)
    for img in soup.find_all('img', src=True):
        full_url = urljoin(base_url, img['src'])
        links.add(full_url)
    for script in soup.find_all('script', src=True):
        total_url = urljoin(base_url, script['src'])
        links.add(total_url)
    for meta in soup.find_all('meta', attrs={'content': True}):
        if 'http' in meta['content']:
            full_url = urljoin(base_url, meta['content'])
            links.add(full_url)
    for form in soup.find_all('form', action=True):
        full_url = urljoin(base_url, form['action'])
        links.add(full_url)
    return links

def filter_domain_links(links, domain_prefix):
    """Filter links to only include those with the domain prefix"""
    return [url for url in links if url.startswith(domain_prefix)]

async def crawl_domain(domain):
    result = {domain: []}
    visited = set()
    domain_prefix = domain.rstrip('/') + '/'
    
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        homepage_html = await fetch_page(session, domain, semaphore)
        if not homepage_html:
            return {domain: []}
            
        with ThreadPoolExecutor() as executor:
            loop = asyncio.get_event_loop()
            soup = await loop.run_in_executor(executor, BeautifulSoup, homepage_html, 'html.parser')
            first_layer_urls = await loop.run_in_executor(
                executor, extract_all_links, soup, domain
            )
        
        second_layer_tasks = []
        for url in first_layer_urls:
            if url not in visited and urlparse(url).scheme in ('http', 'https'):
                visited.add(url)
                second_layer_tasks.append(fetch_page(session, url, semaphore))
                
        second_layer_htmls = await asyncio.gather(*second_layer_tasks)
        
        with ThreadPoolExecutor() as executor:
            loop = asyncio.get_event_loop()
            all_urls = []
            for html in second_layer_htmls:
                if html:
                    soup = await loop.run_in_executor(executor, BeautifulSoup, html, 'html.parser')
                    new_links = await loop.run_in_executor(
                        executor, extract_all_links, soup, domain
                    )
                    filtered_urls = filter_domain_links(new_links, domain_prefix)
                    all_urls.extend(filtered_urls)
                    if len(all_urls) >= MAX_PRODUCTS * 2:
                        break
            

            # Filter URLs through ChatGPT to get only product pages
            product_urls = await chatgpt_client.filter_product_pages(all_urls)
            result[domain] = sorted(product_urls)[:MAX_PRODUCTS]

    # If no product URLs found, fetch from ChatGPT
    if not result[domain]:
        print(f"No product URLs found for {domain}, fetching from ChatGPT...")
        chatgpt_urls = await chatgpt_fetcher.fetch_product_urls(domain, batch_size=50, total_urls=200)
        result[domain] = sorted(chatgpt_urls)[:MAX_PRODUCTS]
        print(f"ChatGPT provided URLs for {domain}: {result[domain]}")
    
    return result

@app.post("/crawl")
async def get_product_urls(request: DomainsRequest):
    tasks = [crawl_domain(domain) for domain in request.domains]
    crawled_results = await asyncio.gather(*tasks)
    
    final_result = {}
    for domain, result in zip(request.domains, crawled_results):
        final_result[domain] = result.get(domain, [])
    
    return final_result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)