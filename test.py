import os
import asyncio
import aiohttp
from datetime import date, datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

GB_API_KEY = "AIzaSyDLkBxT_3B-G4eXbXFvQLzd7ol83usWYI4"


# ---------- Google Books API ----------
async def fetch_book_by_isbn(isbn):
    """Fetch book details from Google Books API by ISBN."""
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    if GB_API_KEY:
        url += f"&key={GB_API_KEY}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                
                if not data.get("items"):
                    return None
                    
                info = data["items"][0]["volumeInfo"]
                return {
                    "title": info.get("title", "Unbekannt"),
                    "authors": info.get("authors", []),
                    "description": info.get("description", ""),
                    "cover": info.get("imageLinks", {}).get("thumbnail")
                }
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(f"Error fetching book by ISBN {isbn}: {e}")
        return None

async def fetch_book_by_title(title: str) -> Optional[dict]:
    """Fetch book details from Google Books API by title."""
    url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{title}"
    if GB_API_KEY:
        url += f"&key={GB_API_KEY}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                
                if not data.get("items"):
                    return None
                    
                info = data["items"][0]["volumeInfo"]
                return {
                    "title": info.get("title", "Unbekannt"),
                    "authors": info.get("authors", []),
                    "description": info.get("description", ""),
                    "cover": info.get("imageLinks", {}).get("thumbnail")
                }
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(f"Error fetching book by title {title}: {e}")
        return None

async def main():
    isbn = input("ISBN: ")
    book_info = await fetch_book_by_isbn(isbn)
    print(book_info)

# Run the async main function
if __name__ == "__main__":
    asyncio.run(main())
