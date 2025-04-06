# chatgpt_client.py
import aiohttp
import asyncio
from typing import List, Optional

class ChatGPTClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def is_product_page(self, url: str, session: aiohttp.ClientSession) -> Optional[bool]:
        """Check if a URL is a single product page using ChatGPT 4o"""
        try:
            prompt = f"""
            Given the URL: {url}
            Determine if this is a single product page URL (a page dedicated to one specific product).
            Return only 'True' or 'False' as the response.
            """
            
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that identifies webpage types based on URLs."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 10
            }

            async with session.post(self.api_url, headers=self.headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    answer = data["choices"][0]["message"]["content"].strip()
                    return answer.lower() == "true"
                return None
        except Exception as e:
            print(f"Error calling ChatGPT API for {url}: {e}")
            return None

    async def filter_product_pages(self, urls: List[str]) -> List[str]:
        """Filter a list of URLs to keep only single product pages"""
        connector = aiohttp.TCPConnector(limit=10)  # Limit concurrent connections
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [self.is_product_page(url, session) for url in urls]
            results = await asyncio.gather(*tasks)
            return [url for url, is_product in zip(urls, results) if (is_product is True or is_product is "True" or is_product is "true")]