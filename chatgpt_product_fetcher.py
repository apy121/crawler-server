# chatgpt_product_fetcher.py
import aiohttp
import asyncio
from typing import List

class ChatGPTProductFetcher:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def fetch_product_urls(self, domain: str, batch_size: int = 50, total_urls: int = 200) -> List[str]:
        """Fetch product page URLs from ChatGPT in batches and validate them"""
        all_product_urls = set()
        batches = (total_urls + batch_size - 1) // batch_size  # Ceiling division
        
        async with aiohttp.ClientSession() as session:
            for _ in range(batches):
                urls = await self._fetch_batch(session, domain, batch_size)
                if urls:
                    # Validate URLs and filter out 404s
                    valid_urls = await self._validate_urls(session, urls)
                    all_product_urls.update(valid_urls)
                if len(all_product_urls) >= total_urls:
                    break
                await asyncio.sleep(1)  # Rate limiting delay
            
        return sorted(list(all_product_urls))[:total_urls]

    async def _fetch_batch(self, session: aiohttp.ClientSession, domain: str, batch_size: int) -> List[str]:
        """Fetch a batch of product URLs from ChatGPT"""
        try:
            prompt = f"""
            Provide a list of {batch_size} URLs from the website {domain} that are single product detail pages.
            Each URL should:
            - Be a valid, specific product page URL for one unique product on {domain}.
            - Follow the URL structure typical of {domain}’s product pages (e.g., include product IDs, slugs, or categories).
            - Be realistic and based on common e-commerce patterns like '/products/[product-name]', '/p/[product-id]', or '/shop/[category]/[product-slug]'.
            - Avoid generic or placeholder URLs that might not exist.
            Return the URLs as a numbered list (1. URL, 2. URL, etc.).
            If exact URLs cannot be generated, provide plausible examples based on {domain}'s likely structure.
            """
            
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "You are an expert in web navigation and e-commerce URL patterns."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.5,  # Lower temperature for more precise outputs
                "max_tokens": 1000
            }

            async with session.post(self.api_url, headers=self.headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    response_text = data["choices"][0]["message"]["content"].strip()
                    # Parse numbered list into URLs
                    urls = []
                    for line in response_text.split('\n'):
                        if line.strip() and line[0].isdigit() and '.' in line:
                            url = line.split('.', 1)[1].strip()
                            if url.startswith('http'):
                                urls.append(url)
                    return urls
                return []
        except Exception as e:
            print(f"Error fetching product URLs from ChatGPT for {domain}: {e}")
            return []

    async def _validate_urls(self, session: aiohttp.ClientSession, urls: List[str]) -> List[str]:
        """Validate URLs by checking their status codes, filtering out 404s"""
        valid_urls = []
        tasks = []
        
        async def check_url(url):
            try:
                async with session.head(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 404:
                        return url
            except Exception as e:
                print(f"Error validating {url}: {e}")
            return None
        
        for url in urls:
            tasks.append(check_url(url))
        
        results = await asyncio.gather(*tasks)
        valid_urls = [url for url in results if url is not None]
        
        print(f"Validated {len(valid_urls)} out of {len(urls)} URLs for {urls[0].split('/')[2] if urls else 'unknown'}")
        return valid_urls