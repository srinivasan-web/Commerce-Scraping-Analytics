CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS scraping_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id TEXT NOT NULL DEFAULT 'demo-org',
  url TEXT NOT NULL,
  website TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  progress INTEGER NOT NULL DEFAULT 0,
  current_product TEXT NOT NULL DEFAULT '',
  completed_products INTEGER NOT NULL DEFAULT 0,
  remaining_products INTEGER NOT NULL DEFAULT 0,
  revenue NUMERIC(14,2) NOT NULL DEFAULT 0,
  units_sold INTEGER NOT NULL DEFAULT 0,
  visible_bought_count INTEGER NOT NULL DEFAULT 0,
  estimated_units INTEGER NOT NULL DEFAULT 0,
  captcha_alert BOOLEAN NOT NULL DEFAULT FALSE,
  options JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES scraping_jobs(id) ON DELETE CASCADE,
  organization_id TEXT NOT NULL DEFAULT 'demo-org',
  website TEXT NOT NULL,
  product_rank TEXT NOT NULL DEFAULT '',
  rank_number INTEGER NOT NULL DEFAULT 0,
  name TEXT NOT NULL,
  brand_name TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT 'General',
  subcategory TEXT NOT NULL DEFAULT '',
  parent_asin TEXT NOT NULL DEFAULT '',
  product_url TEXT NOT NULL DEFAULT '',
  image_url TEXT NOT NULL DEFAULT '',
  raw_card_text TEXT NOT NULL DEFAULT '',
  scraped_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS variants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID REFERENCES products(id) ON DELETE CASCADE,
  job_id UUID NOT NULL REFERENCES scraping_jobs(id) ON DELETE CASCADE,
  parent_asin TEXT NOT NULL DEFAULT '',
  variant_asin TEXT NOT NULL DEFAULT '',
  variant_name TEXT NOT NULL DEFAULT 'Default',
  variant_type TEXT NOT NULL DEFAULT 'Default',
  color TEXT NOT NULL DEFAULT '',
  size TEXT NOT NULL DEFAULT '',
  weight TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  package TEXT NOT NULL DEFAULT '',
  flavor TEXT NOT NULL DEFAULT '',
  storage TEXT NOT NULL DEFAULT '',
  combo TEXT NOT NULL DEFAULT '',
  sku TEXT NOT NULL DEFAULT '',
  current_price NUMERIC(14,2) NOT NULL DEFAULT 0,
  original_price NUMERIC(14,2) NOT NULL DEFAULT 0,
  discount_percent NUMERIC(6,2) NOT NULL DEFAULT 0,
  discount_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
  coupon_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
  final_effective_price NUMERIC(14,2) NOT NULL DEFAULT 0,
  bought_in_past_month INTEGER NOT NULL DEFAULT 0,
  monthly_units_sold INTEGER NOT NULL DEFAULT 0,
  estimated_monthly_revenue NUMERIC(14,2) NOT NULL DEFAULT 0,
  sales_velocity NUMERIC(12,2) NOT NULL DEFAULT 0,
  demand_score NUMERIC(6,2) NOT NULL DEFAULT 0,
  in_stock BOOLEAN NOT NULL DEFAULT TRUE,
  out_of_stock BOOLEAN NOT NULL DEFAULT FALSE,
  limited_stock BOOLEAN NOT NULL DEFAULT FALSE,
  bestseller_badge BOOLEAN NOT NULL DEFAULT FALSE,
  marketplace_choice_badge BOOLEAN NOT NULL DEFAULT FALSE,
  sponsored_status BOOLEAN NOT NULL DEFAULT FALSE,
  gallery_images JSONB NOT NULL DEFAULT '[]'::jsonb,
  video_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
  scores JSONB NOT NULL DEFAULT '{}'::jsonb,
  scraped_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS offers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  variant_id UUID REFERENCES variants(id) ON DELETE CASCADE,
  job_id UUID NOT NULL REFERENCES scraping_jobs(id) ON DELETE CASCADE,
  bank_offers TEXT NOT NULL DEFAULT '',
  emi_offers TEXT NOT NULL DEFAULT '',
  cashback_offers TEXT NOT NULL DEFAULT '',
  coupon_offers TEXT NOT NULL DEFAULT '',
  partner_offers TEXT NOT NULL DEFAULT '',
  exchange_offers TEXT NOT NULL DEFAULT '',
  offer_strength NUMERIC(6,2) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  variant_id UUID REFERENCES variants(id) ON DELETE CASCADE,
  job_id UUID NOT NULL REFERENCES scraping_jobs(id) ON DELETE CASCADE,
  rating NUMERIC(3,2) NOT NULL DEFAULT 0,
  rating_count INTEGER NOT NULL DEFAULT 0,
  review_count INTEGER NOT NULL DEFAULT 0,
  positive_review_percent NUMERIC(6,2) NOT NULL DEFAULT 0,
  negative_review_percent NUMERIC(6,2) NOT NULL DEFAULT 0,
  review_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
  review_quality_score NUMERIC(6,2) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analytics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES scraping_jobs(id) ON DELETE CASCADE,
  product_id UUID REFERENCES products(id) ON DELETE CASCADE,
  variant_id UUID REFERENCES variants(id) ON DELETE CASCADE,
  variant_revenue NUMERIC(14,2) NOT NULL DEFAULT 0,
  parent_product_revenue NUMERIC(14,2) NOT NULL DEFAULT 0,
  revenue_growth_potential NUMERIC(6,2) NOT NULL DEFAULT 0,
  trend_score NUMERIC(6,2) NOT NULL DEFAULT 0,
  popularity_score NUMERIC(6,2) NOT NULL DEFAULT 0,
  price_competitiveness NUMERIC(6,2) NOT NULL DEFAULT 0,
  discount_strength NUMERIC(6,2) NOT NULL DEFAULT 0,
  product_performance_score NUMERIC(8,2) NOT NULL DEFAULT 0,
  variant_performance_score NUMERIC(8,2) NOT NULL DEFAULT 0,
  conversion_potential NUMERIC(6,2) NOT NULL DEFAULT 0,
  ai_insights JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID REFERENCES scraping_jobs(id) ON DELETE SET NULL,
  organization_id TEXT NOT NULL DEFAULT 'demo-org',
  format TEXT NOT NULL,
  file_name TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'ready',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS logs (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID REFERENCES scraping_jobs(id) ON DELETE CASCADE,
  level TEXT NOT NULL DEFAULT 'info',
  message TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_job_id ON products(job_id);
CREATE INDEX IF NOT EXISTS idx_variants_job_id ON variants(job_id);
CREATE INDEX IF NOT EXISTS idx_variants_parent_asin ON variants(parent_asin);
CREATE INDEX IF NOT EXISTS idx_analytics_job_id ON analytics(job_id);
CREATE INDEX IF NOT EXISTS idx_logs_job_id_created_at ON logs(job_id, created_at DESC);
