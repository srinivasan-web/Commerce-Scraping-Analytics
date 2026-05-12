"""
Quick test script to verify extraction on the failing URL.
Run this to diagnose why "No products extracted" is happening.
"""

import asyncio
import sys
from backend.app.services.async_scraper import (
    BrowserPool, EXTRACT_SCRIPT, scroll_and_extract_async
)
from playwright.async_api import async_playwright


async def quick_test():
    """Test extraction on the failing URL."""
    
    failing_url = "https://www.amazon.in/gp/bestsellers/sports/3404687031/ref=zg_bs_nav_sports_3_3404684031"
    
    print("\n" + "="*70)
    print("🧪 QUICK TEST: Extraction on Your Failing URL")
    print("="*70)
    print(f"\n📍 URL: {failing_url}")
    print(f"🎯 Expected: 20+ products extracted")
    print(f"❌ Actual result: No products extracted\n")
    
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        page = await context.new_page()
        
        try:
            print("📍 STEP 1: Loading page...")
            await page.goto(failing_url, wait_until="domcontentloaded", timeout=60000)
            title = await page.title()
            print(f"  ✅ Page loaded: {title}")
            
            print("\n📍 STEP 2: Scrolling and extracting...")
            
            # Test initial extraction without scrolling
            print("  - Checking without scroll...")
            products_before = await page.evaluate(EXTRACT_SCRIPT, {"maxProducts": 50})
            print(f"    Found: {len(products_before)} products")
            
            # Now scroll and try again
            print("  - Scrolling to trigger lazy loading...")
            for i in range(3):
                await page.mouse.wheel(0, 1000)
                await page.wait_for_timeout(500)
                products_after = await page.evaluate(EXTRACT_SCRIPT, {"maxProducts": 50})
                print(f"    After scroll {i+1}: {len(products_after)} products")
                
                if len(products_after) >= 20:
                    print(f"  ✅ Found enough products! ({len(products_after)})")
                    break
            
            print(f"\n📍 STEP 3: Checking page structure...")
            
            # Check for CAPTCHA
            body_text = await page.locator("body").inner_text()
            if "captcha" in body_text.lower() or "robot" in body_text.lower():
                print("  ⚠️  CAPTCHA DETECTED - Amazon is blocking the request")
                print("  💡 Solution: Wait 10 minutes and retry")
                return False
            
            # Check for Amazon error
            if "sorry" in body_text.lower() or "error" in body_text.lower():
                print("  ⚠️  AMAZON ERROR PAGE DETECTED")
                print("  💡 Solution: Try again later or check if URL is correct")
                return False
            
            # Check selector counts
            print("  - Checking CSS selectors...")
            selector_results = await page.evaluate("""
                () => ({
                  p13n: document.querySelectorAll('div.p13n-sc-uncoverable-faceout').length,
                  dataAsin: document.querySelectorAll('div[data-asin]').length,
                  aCardui: document.querySelectorAll('div.a-cardui').length,
                  anyDataAsin: document.querySelectorAll('[data-asin]').length,
                })
            """)
            
            for selector, count in selector_results.items():
                status = "✅" if count > 0 else "❌"
                print(f"    {status} {selector}: {count}")
            
            if sum(selector_results.values()) == 0:
                print("\n  ⚠️  NO SELECTORS FOUND - Selectors may be outdated")
                print("  💡 Solution: Amazon changed page structure, selectors need update")
                
                # Try to find what's on the page
                print("\n  Finding alternative selectors...")
                alt_selectors = await page.evaluate("""
                    () => ({
                      divWithClass: document.querySelectorAll('div[class*="zg"]').length,
                      liItems: document.querySelectorAll('li[data-asin]').length,
                      articleAsin: document.querySelectorAll('article[data-asin]').length,
                      sResultItem: document.querySelectorAll('div.s-result-item').length,
                    })
                """)
                
                for selector, count in alt_selectors.items():
                    if count > 0:
                        print(f"    ✅ Found alternative: {selector}: {count}")
                
                return False
            
            if products_after:
                print(f"\n✅ SUCCESS: Found {len(products_after)} products!")
                print(f"\nFirst 3 products:")
                for i, product in enumerate(products_after[:3]):
                    print(f"  {i+1}. {product.get('name', 'N/A')[:60]}")
                return True
            else:
                print(f"\n❌ FAILED: Selectors found but extraction returned 0 products")
                print(f"  This might be:")
                print(f"  - Selectors match but products not populated")
                print(f"  - Page structure is different")
                print(f"  - JavaScript not executed")
                return False
        
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            await context.close()
            await browser.close()


async def main():
    """Run the test."""
    print("\n")
    success = await quick_test()
    
    print("\n" + "="*70)
    if success:
        print("✅ DIAGNOSIS: Extraction is working correctly")
        print("\n💡 Your issue might be:")
        print("  • Job being retried too quickly")
        print("  • CAPTCHA only on retry")
        print("  • Network issue (try again later)")
        print("\n🔧 Next: Try job again in UI")
    else:
        print("❌ DIAGNOSIS: There's an extraction problem")
        print("\n💡 Solutions to try:")
        print("  1. Wait 10 minutes (CAPTCHA cooldown)")
        print("  2. Use external service")
        print("  3. Use VPN if behind corporate firewall")
        print("  4. Update selectors if Amazon changed structure")
        print("\n📖 Read: FIX_NO_PRODUCTS_EXTRACTED.md for detailed guide")
    print("="*70 + "\n")
    
    return success


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
