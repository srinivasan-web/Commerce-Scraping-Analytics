# Amazon Best Seller Analytics Scraper

## Install

```powershell
cd H:\new\amazon_bestseller_scraper
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m playwright install chromium
```

If you prefer the global Python already configured on this machine:

```powershell
cd H:\new\amazon_bestseller_scraper
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## Run

```powershell
cd H:\new\amazon_bestseller_scraper
python main.py
```

The browser opens visibly because `HEADLESS = False` in `main.py`.

The simpler active scraper can also scrape a live URL dynamically:

```powershell
python scraper.py "https://www.amazon.in/gp/bestsellers/sports/3403930031/ref=zg_bs_nav_sports_2_206211218031"
python scraper.py "https://www.amazon.in/gp/bestsellers/sports/3403930031/ref=zg_bs_nav_sports_2_206211218031" --max-products 30
python scraper.py "https://www.amazon.in/s?k=yoga+mat" --max-pages 1 --max-products 30
python scraper.py "https://www.amazon.in/dp/B0XXXXXXXX"
python scraper.py "https://www.amazon.in/dp/B0XXXXXXXX" --headless
```

By default, `scraper.py` is optimized for top-bestseller runs and scrapes only
the first 30 products from the first page.

You can also set the default URL without editing code:

```powershell
$env:TARGET_URL="https://www.amazon.in/s?k=yoga+mat"
python scraper.py --max-pages 1 --max-products 30
```

You can also pass the URL to scrape directly. This works for both bestseller
category pages and individual product detail pages:

```powershell
python main.py "https://www.amazon.in/gp/bestsellers/sports/3404687031/ref=pd_zg_hrsr_sports"
python main.py "https://www.amazon.in/dp/B0XXXXXXXX"
```

Or set it through an environment variable:

```powershell
$env:TARGET_URL="https://www.amazon.in/dp/B0XXXXXXXX"
python main.py
```

## Fast And Full Modes

The scraper is configurable with environment variables. The defaults are tuned
for a reasonable balance of speed and block avoidance:

```text
DETAIL_PAGE_CONCURRENCY=4
MAX_BESTSELLER_PAGES=2
MAX_PARENT_PRODUCTS=0
MAX_VARIANTS_PER_PRODUCT=30
SCRAPE_VARIANTS=true
BLOCK_STATIC_ASSETS=true
SLOW_MO_MS=80
TARGET_URL=https://www.amazon.in/gp/bestsellers/sports/3404687031/ref=pd_zg_hrsr_sports
```

Fast test run with fewer products:

```powershell
$env:MAX_PARENT_PRODUCTS="10"
$env:MAX_BESTSELLER_PAGES="1"
$env:DETAIL_PAGE_CONCURRENCY="4"
python main.py
```

Fuller coverage run:

```powershell
$env:MAX_PARENT_PRODUCTS="0"
$env:MAX_BESTSELLER_PAGES="2"
$env:DETAIL_PAGE_CONCURRENCY="3"
$env:SCRAPE_VARIANTS="true"
python main.py
```

Maximum-speed run, with higher block risk:

```powershell
$env:DETAIL_PAGE_CONCURRENCY="6"
$env:SLOW_MO_MS="0"
$env:DETAIL_LOAD_DELAY="0.3"
python main.py
```

If Amazon starts showing CAPTCHA, reduce `DETAIL_PAGE_CONCURRENCY` to `1` or
`2`, increase `DETAIL_LOAD_DELAY`, and scrape fewer products per run.

## Output Files

```text
output\amazon_bestsellers.csv
output\amazon_bestsellers.xlsx
logs\amazon_bestseller_analytics.log
```

## Excel Preview

The workbook contains these sheets:

1. Parent Products
2. Product Variants
3. Revenue Analytics
4. Top Revenue Products
5. Top Selling Variants
6. Budget Products
7. Premium Products
8. Offer Analytics
9. Review Analytics
10. Sales Analytics

Formatting includes filters, frozen header rows, bold headers, auto widths,
currency formats, and conditional color scales for revenue and demand metrics.

The main product and variant exports include price details from the product
page, including current price, original price, discount percentage, raw visible
price text, all visible price strings, deal badge, coupon text, availability,
delivery, manufacturer, country of origin, item weight, dimensions, date first
available, product bullets, and the full visible details text where Amazon
exposes it.

## Selector Strategy

The scraper uses layered fallback selectors instead of relying on one fragile
Amazon class name. Main selector groups:

- Bestseller cards: `div.p13n-sc-uncoverable-faceout`, `div[data-asin]`, carousel cards.
- Bestseller pagination: `li.a-last`, `aria-label='Next page'`, and visible Next links.
- Product title: `#productTitle`, fallback heading selectors.
- Price: core price display, price-to-pay, deal price, generic `.a-price`.
- Rating and reviews: `#acrPopover`, `#acrCustomerReviewText`.
- Variants: `#variation_color_name`, `#variation_size_name`, style, pattern, quantity, configuration, and swatch list items.
- Offers, delivery, warranty, EMI: visible feature blocks on the product detail page.

When Amazon changes markup, update the selector lists near the top of `main.py`.

## CAPTCHA Handling Strategy

The scraper detects robot-check/CAPTCHA text and stops cleanly. It does not
bypass CAPTCHA. If this happens:

1. Reduce concurrency in `DETAIL_PAGE_CONCURRENCY`.
2. Increase random delays.
3. Scrape fewer products with `MAX_PARENT_PRODUCTS`.
4. Use a compliant data provider or authorized API for large-scale collection.

## Proxy Rotation Suggestions

For production, add proxies at the Playwright context or browser launch layer:

- Use reputable residential or ISP proxies with explicit permission.
- Rotate by session, not every request.
- Keep country consistent with the marketplace, for example India for Amazon.in.
- Track block rate, latency, and success rate per proxy.
- Respect robots, terms, and legal requirements.

## Scaling Strategy

Start small and scale deliberately:

- Keep static resource blocking enabled to avoid wasting time on images, fonts,
  media, and stylesheets while still reading image URLs from the DOM.
- Use `MAX_PARENT_PRODUCTS` while testing selector changes.
- Increase `DETAIL_PAGE_CONCURRENCY` slowly and watch the log file for CAPTCHA
  or timeout spikes.
- Store raw HTML snapshots for debugging selector changes.
- Persist rows into PostgreSQL before exporting Excel.
- Queue product URLs and process with async workers.
- Keep concurrency low per domain.
- Add checkpointing so failed products can be retried.
- Use Keepa, Helium 10, or Jungle Scout for stronger sales estimates.
- Separate scraping, cleaning, analytics, and export into independent jobs.
