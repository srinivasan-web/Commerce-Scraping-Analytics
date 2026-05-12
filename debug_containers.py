"""
Debug container contents
"""
import time
from fake_useragent import UserAgent
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.amazon.in/gp/bestsellers/sports/3403930031/ref=zg_bs_nav_sports_2_206211218031"

def debug_containers():
    ua = UserAgent()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Opening URL...")
        page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
        
        time.sleep(3)
        
        # Scroll
        for i in range(5):
            page.mouse.wheel(0, 3000)
            time.sleep(0.5)
        
        print("\n=== Container Debug ===\n")
        
        # Get product containers
        containers = page.locator("div[data-asin]")
        count = containers.count()
        print(f"Total containers: {count}\n")
        
        for i in range(min(5, count)):
            print(f"\n{'='*60}")
            print(f"Container {i+1} (data-asin)")
            print(f"{'='*60}")
            
            container = containers.nth(i)
            asin = container.get_attribute("data-asin")
            print(f"ASIN: {asin}")
            
            # Get all links in container
            links = container.locator("a")
            print(f"Links in container: {links.count()}")
            
            for j in range(min(3, links.count())):
                link = links.nth(j)
                href = link.get_attribute("href")
                text = link.inner_text()
                print(f"  Link {j+1}: {text[:50]}... -> {href[:60]}")
            
            # Get all text content
            try:
                text_content = container.inner_text()
                print(f"\nText content (first 200 chars):\n{text_content[:200]}")
            except:
                pass
            
            # Check for specific elements
            print(f"\nElement count:")
            print(f"  Spans: {container.locator('span').count()}")
            print(f"  Divs: {container.locator('div').count()}")
            print(f"  Images: {container.locator('img').count()}")
            print(f"  Paragraphs: {container.locator('p').count()}")
        
        browser.close()

if __name__ == "__main__":
    debug_containers()
