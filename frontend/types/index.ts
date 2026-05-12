export type Website = "amazon" | "flipkart" | "myntra" | "ajio" | "ebay" | "alibaba" | "walmart" | "auto";
export type JobStatus = "queued" | "running" | "paused" | "completed" | "failed" | "stopped";

export interface Product {
  id: string;
  job_id: string;
  product_rank: string;
  rank_number: number;
  name: string;
  brand_name: string;
  website: Website;
  category: string;
  subcategory: string;
  parent_asin: string;
  variant_asin: string;
  variant: string;
  variant_name: string;
  variant_type: string;
  color: string;
  size: string;
  weight: string;
  model: string;
  package: string;
  flavor: string;
  storage: string;
  combo: string;
  sku: string;
  price: number;
  original_price: number;
  discount: number;
  discount_amount: number;
  coupon_amount: number;
  final_effective_price: number;
  discount_text: string;
  price_text: string;
  original_price_text: string;
  rating: number;
  rating_text: string;
  reviews: number;
  reviews_text: string;
  positive_review_percent: number;
  negative_review_percent: number;
  review_keywords: string[];
  units_sold: number;
  monthly_units_sold: number;
  visible_bought_count: number;
  units_sold_estimated: boolean;
  bought_count_source: string;
  bought_count_text: string;
  revenue: number;
  estimated_monthly_revenue: number;
  sales_velocity: number;
  demand_score: number;
  parent_product_revenue: number;
  offers: string;
  bank_offers: string;
  emi_offers: string;
  cashback_offers: string;
  coupon_offers: string;
  partner_offers: string;
  exchange_offers: string;
  delivery: string;
  fast_delivery: boolean;
  delivery_days: string;
  installation_available: boolean;
  warranty: string;
  availability: string;
  prime_available: boolean;
  free_delivery: boolean;
  in_stock: boolean;
  out_of_stock: boolean;
  limited_stock: boolean;
  limited_time_deal: boolean;
  coupon_available: boolean;
  sponsored_status: boolean;
  bestseller_badge: boolean;
  raw_card_text: string;
  image_url: string;
  variant_images: string[];
  gallery_images: string[];
  video_urls: string[];
  product_url: string;
  scraped_at: string;
  scores: Record<string, number>;
}

export interface Job {
  id: string;
  status: JobStatus;
  url: string;
  website: Website;
  progress: number;
  current_product: string;
  completed_products: number;
  remaining_products: number;
  revenue: number;
  units_sold: number;
  visible_bought_count: number;
  estimated_units: number;
  captcha_alert: boolean;
  external_job_id: string;
  external_status_url: string;
  organization_id: string;
  logs: string[];
  products: Product[];
  created_at: string;
  updated_at: string;
}

export interface Analytics {
  summary: {
    total_products: number;
    total_variants: number;
    total_revenue: number;
    average_rating: number;
    units_sold: number;
    visible_bought_count: number;
    estimated_units: number;
    top_category: string;
    active_jobs: number;
    success_rate: number;
  };
  revenue_by_category: Array<{ name: string; revenue: number }>;
  revenue_trend: Array<{ date: string; revenue: number }>;
  variant_distribution: Array<{ name: string; value: number }>;
  top_products: Product[];
  ai_insights: Array<{ title: string; detail: string; score: number }>;
  revenue_forecast: Array<{ period: string; forecast: number; growth_rate: number }>;
}

export interface AuthSession {
  access_token: string;
  organization_id: string;
  organization_name: string;
  user_email: string;
  api_key: string;
}

export interface ApiKey {
  id: string;
  organization_id: string;
  name: string;
  key_preview: string;
  key: string;
  created_at: string;
  active: boolean;
}
