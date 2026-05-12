import time
import logging
from datetime import datetime
import json

import pandas as pd
from fake_useragent import UserAgent
from playwright.sync_api import sync_playwright

# =========================================================
# LOGGING CONFIGURATION
# =========================================================

logging.basicConfig(
    filename="logs/scraper.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =========================================================
# GLOBAL CONFIG
# =========================================================

BASE_URL = "https://www.amazon.in/gp/bestsellers/sports/3403930031/ref=zg_bs_nav_sports_2_206211218031"

OUTPUT_CSV = "output/amazon_bestsellers.csv"
OUTPUT_XLSX = "output/amazon_bestsellers.xlsx"

# =========================================================
# GET USER AGENT
# =========================================================

def get_random_user_agent():
    """Generate random user-agent"""
    ua = UserAgent()
    return ua.random

# =========================================================
# EXTRACT PRODUCTS USING JAVASCRIPT
# =========================================================

def extract_products_js(page):
    """
    Extract products using JavaScript evaluation
    """
    print("Extracting products using JavaScript...")
    
    products_data = page.evaluate("""
    () => {
        const products = [];
        const containers = document.querySelectorAll('div[data-asin]');
        
        console.log('Found containers:', containers.length);
        
        containers.forEach((container, index) => {
            try {
                const asin = container.getAttribute('data-asin');
                const innerText = container.innerText || '';
                
                // Extract rank from the text (usually starts with #)
                let rank = '#' + (index + 1);
                const rankMatch = innerText.match(/#\d+/);
                if (rankMatch) {
                    rank = rankMatch[0];
                }
                
                // Get all text lines
                const lines = innerText.split('\\n').map(l => l.trim()).filter(l => l);
                
                // Product name is usually the longest line
                let productName = '';
                let price = '';
                let rating = '';
                let reviews = '';
                
                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];
                    
                    // Skip rank line
                    if (line.startsWith('#')) continue;
                    
                    // Check for price (contains ₹)
                    if (line.includes('₹')) {
                        price = line;
                    }
                    
                    // Check for rating (contains "out of 5")
                    if (line.includes('out of 5')) {
                        rating = line.split('out of 5')[0].trim();
                        // Next line might be reviews
                        if (i + 1 < lines.length && !lines[i + 1].includes('out of 5') && !lines[i + 1].includes('₹')) {
                            reviews = lines[i + 1];
                        }
                    }
                    
                    // Product name is the first substantial line that's not rank, rating, price
                    if (!productName && 
                        !line.startsWith('#') && 
                        !line.includes('₹') && 
                        !line.includes('out of 5') &&
                        !line.includes('stars') &&
                        line.length > 10) {
                        productName = line;
                    }
                }
                
                // Get product URL from links
                let productUrl = '';
                const link = container.querySelector('a[href*="/dp/"]');
                if (link) {
                    let href = link.getAttribute('href');
                    if (href) {
                        if (!href.startsWith('http')) {
                            productUrl = 'https://www.amazon.in' + href;
                        } else {
                            productUrl = href;
                        }
                    }
                }
                
                // Get image
                let imageUrl = '';
                const img = container.querySelector('img');
                if (img) {
                    imageUrl = img.getAttribute('src') || '';
                }
                
                // Get brand (first word of product name)
                let brand = '';
                if (productName) {
                    brand = productName.split(' ')[0];
                }
                
                if (productName) {  // Only add if we have a name
                    products.push({
                        rank: rank,
                        productName: productName,
                        brand: brand,
                        price: price,
                        rating: rating,
                        reviews: reviews,
                        productUrl: productUrl,
                        imageUrl: imageUrl,
                        asin: asin
                    });
                }
                
            } catch (e) {
                console.error('Error processing container:', e);
            }
        });
        
        return products;
    }
    """)
    
    return products_data

# =========================================================
# FORMAT PRODUCT DATA
# =========================================================

def format_products(products_data):
    """
    Format extracted product data into dataframe format
    """
    formatted_products = []
    category_name = "Sports & Fitness"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for product in products_data:
        formatted_products.append({
            "Product Rank": product.get('rank'),
            "Product Name": product.get('productName'),
            "Brand Name": product.get('brand'),
            "Product Price": product.get('price'),
            "Discount Percentage": None,
            "Original Price": None,
            "Product Rating": product.get('rating'),
            "Number of Reviews": product.get('reviews'),
            "Product URL": product.get('productUrl'),
            "Product Image URL": product.get('imageUrl'),
            "Availability": "Available",
            "Category": category_name,
            "ASIN": product.get('asin'),
            "Timestamp": timestamp
        })
    
    return formatted_products

# =========================================================
# MAIN SCRAPER
# =========================================================

def run_scraper():
    """Main scraper function"""
    all_data = []
    
    try:
        print("\n" + "="*60)
        print("Initializing Playwright Browser...")
        print("="*60)
        
        with sync_playwright() as p:
            
            browser = p.chromium.launch(
                headless=False,
                slow_mo=50
            )
            
            context = browser.new_context(
                user_agent=get_random_user_agent(),
                viewport={"width": 1400, "height": 900}
            )
            
            page = context.new_page()
            
            print(f"Opening Amazon URL...")
            logging.info("Opening Amazon Bestseller URL")
            
            page.goto(BASE_URL, timeout=60000, wait_until="networkidle")
            
            print("Page loaded, waiting for content...")
            time.sleep(3)
            
            # Scroll to load products
            print("Scrolling to load products...")
            for i in range(8):
                page.mouse.wheel(0, 2000)
                time.sleep(0.5)
            
            time.sleep(2)
            
            print("\nExtracting product data...")
            
            # Extract using JavaScript
            products_data = extract_products_js(page)
            
            print(f"Found {len(products_data)} products")
            logging.info(f"Extracted {len(products_data)} products")
            
            # Format the data
            all_data = format_products(products_data)
            
            # Print sample
            if all_data:
                print(f"\nSample products:")
                for i, product in enumerate(all_data[:3]):
                    print(f"{i+1}. {product['Product Name'][:50]}... ({product['Product Price']})")
            
            browser.close()
            print("\nBrowser closed")
    
    except Exception as e:
        print(f"Error: {str(e)}")
        logging.error(f"Error: {e}")
    
    return all_data

# =========================================================
# SAVE DATA
# =========================================================

def save_data(data):
    """Save data to CSV and Excel"""
    
    if not data:
        print("❌ No data found to export")
        logging.error("No data found")
        return
    
    print(f"\n{'='*60}")
    print(f"Exporting {len(data)} products...")
    print(f"{'='*60}")
    
    df = pd.DataFrame(data)
    
    # Remove duplicates
    initial_count = len(df)
    df.drop_duplicates(
        subset=["Product Name"],
        inplace=True
    )
    final_count = len(df)
    
    print(f"Initial products: {initial_count}")
    print(f"After duplicates: {final_count}")
    print(f"Duplicates removed: {initial_count - final_count}")
    
    # Export CSV
    try:
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        print(f"✓ CSV: {OUTPUT_CSV}")
    except Exception as e:
        print(f"❌ CSV Error: {e}")
    
    # Export Excel
    try:
        df.to_excel(OUTPUT_XLSX, index=False, engine="openpyxl")
        
        # Format Excel
        try:
            from openpyxl import load_workbook
            from openpyxl.styles import Alignment, PatternFill, Font
            
            wb = load_workbook(OUTPUT_XLSX)
            ws = wb.active
            
            # Header formatting
            header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            header_font = Font(color="FFFFFF", bold=True)
            
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            
            # Auto-width columns
            for column in ws.columns:
                max_length = 0
                col_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                ws.column_dimensions[col_letter].width = min(max_length + 2, 50)
            
            wb.save(OUTPUT_XLSX)
        except:
            pass
        
        print(f"✓ Excel: {OUTPUT_XLSX}")
    except Exception as e:
        print(f"❌ Excel Error: {e}")
    
    print(f"\n{'='*60}")
    print("✓ Export Complete!")
    print(f"{'='*60}\n")

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Amazon Bestseller Scraper")
    print("="*60 + "\n")
    
    scraped_data = run_scraper()
    save_data(scraped_data)
    
    print("✓ Done!\n")
