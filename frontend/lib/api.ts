import axios from "axios";
import type { Analytics, ApiKey, AuthSession, Job, Product, Website } from "@/types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = API_URL.replace(/^http/, "ws");

export const api = axios.create({
  baseURL: API_URL,
  timeout: 120000
});

export function getAuthSession(): AuthSession | undefined {
  if (typeof window === "undefined") return undefined;
  const raw = window.localStorage.getItem("commerce-auth-session");
  return raw ? (JSON.parse(raw) as AuthSession) : undefined;
}

export function setAuthSession(session?: AuthSession) {
  if (typeof window === "undefined") return;
  if (session) {
    window.localStorage.setItem("commerce-auth-session", JSON.stringify(session));
  } else {
    window.localStorage.removeItem("commerce-auth-session");
  }
}

api.interceptors.request.use((config) => {
  const session = getAuthSession();
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`;
  }
  if (session?.api_key) {
    config.headers["X-API-Key"] = session.api_key;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && typeof window !== "undefined") {
      setAuthSession(undefined);
      window.dispatchEvent(new Event("commerce-auth-expired"));
    }
    return Promise.reject(error);
  }
);

export async function login(input: { email: string; password: string; organization: string }) {
  const { data } = await api.post<AuthSession>("/api/auth/login", input);
  setAuthSession(data);
  return data;
}

export async function fetchApiKeys() {
  const { data } = await api.get<ApiKey[]>("/api/org/api-keys");
  return data;
}

export async function createApiKey(name: string) {
  const { data } = await api.post<ApiKey>("/api/org/api-keys", { name });
  return data;
}

export async function fetchAnalytics() {
  const { data } = await api.get<Analytics>("/api/analytics");
  return data;
}

export async function fetchJobs() {
  const { data } = await api.get<Job[]>("/api/jobs");
  return data;
}

export async function fetchProducts(jobId?: string) {
  const { data } = await api.get<Product[]>("/api/products", { params: { job_id: jobId } });
  return data;
}

export async function startScrape(input: {
  url: string;
  website: Website;
  useProxy: boolean;
  headless: boolean;
  maxProducts: number;
  variantDepth?: number;
  externalService: boolean;
}) {
  const { data } = await api.post<Job>("/api/scrape", {
    url: input.url,
    website: input.website,
    options: {
      use_proxy: input.useProxy,
      headless: input.headless,
      max_products: input.maxProducts,
      variant_depth: input.variantDepth ?? 2,
      include_reviews: true,
      include_variants: true,
      external_service: input.externalService
    }
  });
  return data;
}

export async function controlJob(jobId: string, action: "pause" | "resume" | "stop" | "retry") {
  const { data } = await api.post<Job>(`/api/jobs/${jobId}/${action}`);
  return data;
}

export function exportUrl(format: "xlsx" | "csv" | "json" | "txt" | "images", jobId?: string) {
  const session = getAuthSession();
  const params = new URLSearchParams();
  if (jobId) params.set("job_id", jobId);
  if (session?.api_key) params.set("api_key", session.api_key);
  const query = params.toString();
  return `${API_URL}/api/export/${format}${query ? `?${query}` : ""}`;
}
