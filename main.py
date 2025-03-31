from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from chatgpt_helper import ChatGPTHelper;
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DomainsRequest(BaseModel):
    domains: list[str]

# Constants
PRODUCT_KEYWORDS = ["/product/", "/item/", "/p/", "/sku/", "product"]
MAX_CONCURRENT_REQUESTS = 10  # Reduced for ChatGPT API limits
MAX_DEPTH = 1  # Only follow category links from homepage
MAX_PRODUCTS = 500  # Limit total products per domain

chatgpt = ChatGPTHelper()

async def is_product_url(url):
    return any(keyword in url.lower() for keyword in PRODUCT_KEYWORDS)

async def fetch_page(session, url, semaphore):
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.text()
        except Exception as e:
            print(f"Failed to fetch {url}: {e}")
        return None

def extract_product_links(soup, base_url):
    """Extract product links from page HTML"""
    product_links = set()
    
    # Common patterns
    for link in soup.find_all('a', href=True):
        href = link['href'].lower()
        if any(kw in href for kw in PRODUCT_KEYWORDS):
            product_links.add(urljoin(base_url, link['href']))
    
    # Product cards
    for card in soup.select('[class*="product"], [class*="item"], [class*="card"]'):
        link = card.find('a', href=True)
        if link and any(kw in link['href'].lower() for kw in PRODUCT_KEYWORDS):
            product_links.add(urljoin(base_url, link['href']))
    
    return product_links

async def crawl_domain(domain):
    all_product_urls = set()
    visited = set()
    domain_base = urlparse(domain).netloc
    
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        # Step 1: Get homepage and identify categories with ChatGPT
        homepage_html = await fetch_page(session, domain, semaphore)
        if not homepage_html:
            return []
            
        category_urls = await chatgpt.get_category_links(homepage_html, domain)
        category_urls = [url for url in category_urls if urlparse(url).netloc == domain_base][:10]  # Limit to 10 categories
        
        # Step 2: Crawl each category page for products
        tasks = []
        for category_url in category_urls:
            if category_url not in visited:
                tasks.append(process_category_page(session, category_url, semaphore, domain_base))
        
        results = await asyncio.gather(*tasks)
        for product_urls in results:
            all_product_urls.update(product_urls)
            
            if len(all_product_urls) >= MAX_PRODUCTS:
                break
    
    return sorted(all_product_urls)[:MAX_PRODUCTS]

async def process_category_page(session, url, semaphore, domain_base):
    """Process a single category page to extract products"""
    product_urls = set()
    
    html = await fetch_page(session, url, semaphore)
    if not html:
        return product_urls
    
    with ThreadPoolExecutor() as executor:
        loop = asyncio.get_event_loop()
        soup = await loop.run_in_executor(executor, BeautifulSoup, html, 'html.parser')
        product_urls = await loop.run_in_executor(executor, extract_product_links, soup, url)
    
    return product_urls

@app.post("/crawl")
async def get_product_urls(request: DomainsRequest):
    tasks = [crawl_domain(domain) for domain in request.domains]
    crawled_results = await asyncio.gather(*tasks)
    
    return {
        domain: urls 
        for domain, urls in zip(request.domains, crawled_results)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)