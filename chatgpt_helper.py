import os
import openai
from dotenv import load_dotenv
import asyncio

load_dotenv()

class ChatGPTHelper:
    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def get_category_links(self, html, domain):
        try:
            prompt = f"""
            Analyze this HTML from {domain} and identify all (a) or (href) tag/urls that would lead to product list page.
            Please make sure all URL pages must have multiple products listed.
            Return ONLY the URLs in a comma-separated list with no additional text or explanation.
            You have to make sure any URL in list must not return 404 error.
            
            HTML content:
            {html[:10000]}
            """

            response = await asyncio.to_thread(  # Run in a separate thread
                self.client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful e-commerce website analyzer."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.3
            )

            # ✅ Correct way to access the content
            urls_text = response.choices[0].message.content.strip()  
            
            # Convert comma-separated string into a list of URLs
            urls = [url.strip() for url in urls_text.split(",") if url.strip()]

            print(urls)
            
            return urls  # Ensure this returns a list
        
        except Exception as e:
            print(f"Error in get_category_links: {e}")
            return []
