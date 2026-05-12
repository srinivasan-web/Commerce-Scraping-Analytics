"""
Debug utility to inspect Amazon page structure and identify working selectors.
Use this when extraction fails to understand what's actually on the page.
"""

from __future__ import annotations

import json
from playwright.async_api import async_playwright, Page


async def debug_page_structure(url: str, headless: bool = False) -> dict:
    """
    Inspect a page and return debugging information about its structure.
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="en-IN",
        )
        page = await context.new_page()
        
        try:
            print(f"\n📍 Loading: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Scroll to trigger lazy loading
            for _ in range(3):
                await page.mouse.wheel(0, 1000)
                await page.wait_for_timeout(500)
            
            # Gather debugging info
            debug_info = await page.evaluate("""
                () => {
                  const info = {
                    page_title: document.title,
                    page_url: window.location.href,
                    body_text_length: document.body && document.body.innerText ? document.body.innerText.length : 0,
                    
                    // Check for common selectors
                    selectors_found: {},
                    
                    // Product containers to try
                    product_containers: [
                      { name: 'div.p13n-sc-uncoverable-faceout', count: 0 },
                      { name: 'li.zg-carousel-general-faceout', count: 0 },
                      { name: 'div[data-asin]', count: 0 },
                      { name: 'div.a-cardui', count: 0 },
                      { name: 'div.s-result-item', count: 0 },
                      { name: 'div.zg-item-row', count: 0 },
                      { name: 'li.zg-item-row', count: 0 },
                      { name: 'div.zg-card', count: 0 },
                      { name: 'div[class*="p13n"]', count: 0 },
                      { name: 'article[data-asin]', count: 0 },
                    ],
                    
                    // Sample products found
                    sample_products: []
                  };
                  
                  // Count each selector
                  info.product_containers.forEach(selector => {
                    selector.count = document.querySelectorAll(selector.name).length;
                  });
                  
                  // Try to find products with broad selector
                  const products = document.querySelectorAll('[data-asin], [data-item-id], [data-component-type="s-search-result"]');
                  
                  // Get sample HTML of first few products
                  Array.from(products).slice(0, 3).forEach((el, idx) => {
                    info.sample_products.push({
                      index: idx,
                      className: el.className,
                      dataAttributes: {
                        asin: el.getAttribute('data-asin'),
                        itemId: el.getAttribute('data-item-id'),
                        componentType: el.getAttribute('data-component-type'),
                      },
                      text_sample: (el.innerText || '').substring(0, 200),
                      html_tag: el.tagName,
                      children_count: el.children.length,
                    });
                  });
                  
                  // Check for carousel/bestseller specific selectors
                  info.bestseller_specific = {
                    has_zg_item_row: document.querySelectorAll('.zg-item-row').length,
                    has_zg_carousel: document.querySelectorAll('.zg-carousel-general-faceout').length,
                    has_a_carousel_container: document.querySelectorAll('.a-carousel-container').length,
                    body_classes: document.body.className,
                  };
                  
                  return info;
                }
            """)
            
            print("\n" + "="*60)
            print("📊 PAGE STRUCTURE DEBUG REPORT")
            print("="*60)
            print(f"\n📄 Page Title: {debug_info['page_title']}")
            print(f"🔗 Page URL: {debug_info['page_url']}")
            print(f"📏 Body Text Length: {debug_info['body_text_length']} characters")
            
            print("\n📦 PRODUCT CONTAINER SELECTORS:")
            for selector in debug_info['product_containers']:
                status = "✅" if selector['count'] > 0 else "❌"
                print(f"  {status} {selector['name']}: {selector['count']} found")
            
            print("\n🎯 BESTSELLER-SPECIFIC SELECTORS:")
            for key, value in debug_info['bestseller_specific'].items():
                if isinstance(value, int):
                    status = "✅" if value > 0 else "❌"
                    print(f"  {status} {key}: {value}")
                else:
                    print(f"  {key}: {value[:100]}")
            
            if debug_info['sample_products']:
                print("\n📦 SAMPLE PRODUCT STRUCTURE (First 3):")
                for sample in debug_info['sample_products']:
                    print(f"\n  Product {sample['index']}:")
                    print(f"    Tag: {sample['html_tag']}")
                    print(f"    Class: {sample['className'][:80]}")
                    print(f"    ASIN: {sample['dataAttributes']['asin']}")
                    print(f"    Item ID: {sample['dataAttributes']['itemId']}")
                    print(f"    Component: {sample['dataAttributes']['componentType']}")
                    print(f"    Children: {sample['children_count']}")
                    print(f"    Text: {sample['text_sample'][:100]}")
            
            print("\n" + "="*60)
            
            return debug_info
            
        finally:
            await context.close()
            await browser.close()


async def test_extraction_script(url: str, headless: bool = False) -> list[dict]:
    """
    Test the current extraction script on a page and return results.
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="en-IN",
        )
        page = await context.new_page()
        
        try:
            print(f"\n🧪 Testing extraction on: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Scroll to trigger lazy loading
            for _ in range(3):
                await page.mouse.wheel(0, 1000)
                await page.wait_for_timeout(500)
            
            # Test current extraction script
            EXTRACT_SCRIPT = """
            ({ maxProducts }) => {
              const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              const rows = [];
              const seen = new Set();
              const getText = (element) => element ? (element.innerText || element.textContent || '').replace(/\\s+/g, ' ').trim() : '';
              const getAttr = (element, attr) => element ? (element.getAttribute(attr) || '').replace(/\\s+/g, ' ').trim() : '';
              const candidates = Array.from(document.querySelectorAll([
                'div.p13n-sc-uncoverable-faceout',
                'li.zg-carousel-general-faceout',
                'div[data-asin]',
                '[data-asin]'
              ].join(',')));

              console.log('Found candidates:', candidates.length);
              
              for (const node of candidates) {
                const rawText = node.innerText || '';
                const text = clean(rawText);
                const linkNode = node.querySelector('a[href*="/dp/"], a[href*="/gp/product/"]');
                const link = linkNode ? (linkNode.href || linkNode.getAttribute('href') || '') : '';
                const id = node.getAttribute('data-asin') || '';
                const img = node.querySelector('img');
                const name = clean(getAttr(img, 'alt') || getText(linkNode) || text.split('\\n')[0] || '');
                
                const key = id || link || name;
                if (!key || seen.has(key) || !name || !link) continue;
                seen.add(key);
                
                rows.push({
                  id, link, name,
                  rank: '#' + (rows.length + 1),
                  price: clean((text.match(/[₹$]\\s*[\\d,]+/) || [''])[0] || ''),
                });
                if (rows.length >= maxProducts) break;
              }
              
              return rows;
            }
            """
            
            results = await page.evaluate(EXTRACT_SCRIPT, {"maxProducts": 50})
            
            print(f"\n✅ Extraction Results: {len(results)} products found")
            if results:
                print("\n📋 First 3 products:")
                for i, product in enumerate(results[:3]):
                    print(f"  {i+1}. {product.get('name', 'N/A')[:60]}")
                    print(f"     Price: {product.get('price', 'N/A')}")
                    print(f"     Link: {product.get('link', 'N/A')[:80]}")
            else:
                print("\n❌ No products extracted!")
            
            return results
            
        finally:
            await context.close()
            await browser.close()


# Interactive debug script
if __name__ == "__main__":
    import asyncio
    import sys
    
    if len(sys.argv) > 1:
        url = sys.argv[1]
        headless = "--show" not in sys.argv
    else:
        url = "https://www.amazon.in/gp/bestsellers/sports/3404687031/ref=zg_bs_nav_sports_3_3404684031"
        headless = True
    
    print(f"\n🔍 Debugging URL: {url}")
    print(f"🎬 Headless: {headless}\n")
    
    # Run debug
    debug_info = asyncio.run(debug_page_structure(url, headless=headless))
    
    # Test extraction
    results = asyncio.run(test_extraction_script(url, headless=headless))
    
    print("\n💾 Full debug info saved above")
