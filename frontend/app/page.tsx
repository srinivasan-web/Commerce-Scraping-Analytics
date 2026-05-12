"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Boxes,
  ChevronDown,
  ChevronsRight,
  Check,
  CheckCircle2,
  Circle,
  Clock3,
  Database,
  FileJson,
  FileSpreadsheet,
  FileText,
  Gauge,
  KeyRound,
  LayoutDashboard,
  Link2,
  Loader2,
  LogOut,
  MousePointerClick,
  Pause,
  Play,
  RefreshCcw,
  Rocket,
  Search,
  Settings,
  ShieldCheck,
  ShoppingBag,
  SlidersHorizontal,
  Sparkles,
  Square,
  Star,
  Tags,
  TrendingUp,
  Zap
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { Button, Card, Field, inputClass } from "@/components/ui";
import { API_URL, WS_URL, controlJob, createApiKey, exportUrl, fetchAnalytics, fetchApiKeys, fetchJobs, fetchProducts, getAuthSession, login, setAuthSession, startScrape } from "@/lib/api";
import { cn, compact, currency } from "@/lib/utils";
import { useJobStore } from "@/store/job-store";
import type { AuthSession, Job, Product, Website } from "@/types";
import { Providers } from "@/components/providers";

const navItems = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "scraper", label: "Scraper", icon: Play },
  { id: "products", label: "Products", icon: ShoppingBag },
  { id: "variants", label: "Variants", icon: Boxes },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
  { id: "revenue", label: "Revenue", icon: TrendingUp },
  { id: "reviews", label: "Reviews", icon: Star },
  { id: "offers", label: "Offers", icon: Tags },
  { id: "export", label: "Exports", icon: FileSpreadsheet },
  { id: "insights", label: "AI Insights", icon: Sparkles },
  { id: "jobs", label: "Jobs", icon: Activity },
  { id: "settings", label: "Settings", icon: Settings }
] as const;

const websites: Website[] = ["auto", "amazon", "flipkart", "myntra", "ajio", "ebay", "alibaba", "walmart"];
const colors = ["#2dd4bf", "#fb7185", "#fbbf24", "#60a5fa", "#a78bfa", "#34d399", "#f97316"];
const scrapePhases = [
  { threshold: 1, label: "Queued", detail: "Job accepted by backend" },
  { threshold: 8, label: "Loading URL", detail: "Opening browser and live page" },
  { threshold: 18, label: "Scanning", detail: "Scrolling and collecting cards" },
  { threshold: 48, label: "Enriching", detail: "Opening detail pages for price, discount, bought count" },
  { threshold: 62, label: "Calculating", detail: "Computing bought count x price revenue" },
  { threshold: 70, label: "Saving", detail: "Storing products for dashboard analytics" },
  { threshold: 100, label: "Ready", detail: "Dashboard data and exports are available" }
] as const;
const scraperSteps = [
  { id: "source", label: "Source", detail: "Marketplace URL", icon: Link2 },
  { id: "runtime", label: "Runtime", detail: "Browser options", icon: SlidersHorizontal },
  { id: "launch", label: "Launch", detail: "Confirm run", icon: Rocket }
] as const;
const productPresets = [12, 24, 50, 100] as const;
type ScraperStep = (typeof scraperSteps)[number]["id"];

function isActiveJob(job?: Job) {
  return job?.status === "queued" || job?.status === "running" || job?.status === "paused";
}

function phaseIndex(job?: Job) {
  if (!job) return -1;
  if (job.status === "completed") return scrapePhases.length - 1;
  if (job.status === "failed" || job.status === "stopped") return Math.max(scrapePhases.findIndex((phase) => (job.progress ?? 0) < phase.threshold), 0);
  const index = scrapePhases.findIndex((phase) => (job.progress ?? 0) < phase.threshold);
  return index === -1 ? scrapePhases.length - 1 : Math.max(index - 1, 0);
}

function latestLog(job?: Job) {
  return job?.logs?.[job.logs.length - 1] ?? "Waiting for backend events.";
}

export default function Home() {
  return (
    <ProvidersShell>
      <DashboardApp />
    </ProvidersShell>
  );
}

function ProvidersShell({ children }: { children: React.ReactNode }) {
  return <Providers>{children}</Providers>;
}

function AuthPanel({ onAuthenticated }: { onAuthenticated: (session: AuthSession) => void }) {
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("demo-password");
  const [organization, setOrganization] = useState("India Commerce Team");
  const mutation = useMutation({ mutationFn: login, onSuccess: onAuthenticated });

  return (
    <Card className="w-full">
      <div className="mb-5 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm text-slate-400">Authorized workspace</p>
          <h1 className="text-2xl font-semibold text-white">Sign in to scrape and analyze</h1>
        </div>
        <KeyRound className="size-7 text-teal-200" />
      </div>
      <div className="grid gap-4">
        <Field label="Organization">
          <input className={inputClass} value={organization} onChange={(event) => setOrganization(event.target.value)} />
        </Field>
        <Field label="Email">
          <input className={inputClass} value={email} onChange={(event) => setEmail(event.target.value)} />
        </Field>
        <Field label="Password">
          <input className={inputClass} type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </Field>
        <Button disabled={mutation.isPending} onClick={() => mutation.mutate({ email, password, organization })}>
          <KeyRound className="size-4" />
          Continue
        </Button>
        {mutation.error && <div className="rounded-md border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-sm text-rose-100">Authentication failed. Check the backend is running.</div>}
      </div>
    </Card>
  );
}

function ScrapeNotice({
  notice,
  onClose
}: {
  notice?: { id: string; kind: "success" | "error" | "info"; title: string; message: string };
  onClose: () => void;
}) {
  useEffect(() => {
    if (!notice || notice.kind === "info") return;
    const timeout = window.setTimeout(onClose, 6500);
    return () => window.clearTimeout(timeout);
  }, [notice, onClose]);

  const Icon = notice?.kind === "success" ? CheckCircle2 : notice?.kind === "error" ? AlertTriangle : Loader2;

  return (
    <AnimatePresence>
      {notice && (
        <motion.div
          key={notice.id}
          initial={{ opacity: 0, y: -16, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -16, scale: 0.98 }}
          className="fixed right-4 top-4 z-50 w-[min(420px,calc(100vw-2rem))] rounded-lg border border-white/12 bg-slate-950/90 p-4 shadow-2xl backdrop-blur-xl"
        >
          <div className="flex items-start gap-3">
            <div
              className={cn(
                "grid size-10 shrink-0 place-items-center rounded-md",
                notice.kind === "success" && "bg-emerald-300/15 text-emerald-200",
                notice.kind === "error" && "bg-rose-300/15 text-rose-200",
                notice.kind === "info" && "bg-teal-300/15 text-teal-200"
              )}
            >
              <Icon className={cn("size-5", notice.kind === "info" && "animate-spin")} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-white">{notice.title}</div>
              <div className="mt-1 line-clamp-3 text-sm leading-5 text-slate-300">{notice.message}</div>
            </div>
            <button onClick={onClose} className="rounded-md px-2 py-1 text-sm text-slate-400 transition hover:bg-white/10 hover:text-white">
              Dismiss
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function DashboardApp() {
  const [mounted, setMounted] = useState(false);
  const [active, setActive] = useState<(typeof navItems)[number]["id"]>("dashboard");
  const [query, setQuery] = useState("");
  const [session, setSession] = useState<AuthSession | undefined>();
  const [notice, setNotice] = useState<{ id: string; kind: "success" | "error" | "info"; title: string; message: string }>();
  const queryClient = useQueryClient();
  const { liveJob, setLiveJob } = useJobStore();
  const analyticsQuery = useQuery({ queryKey: ["analytics"], queryFn: fetchAnalytics, refetchInterval: 5000, enabled: !!session });
  const jobsQuery = useQuery({ queryKey: ["jobs"], queryFn: fetchJobs, refetchInterval: 5000, enabled: !!session });
  const productsQuery = useQuery({ queryKey: ["products"], queryFn: () => fetchProducts(), refetchInterval: 5000, enabled: !!session });

  useEffect(() => {
    setSession(getAuthSession());
    setMounted(true);
  }, []);

  useEffect(() => {
    const onExpired = () => {
      setSession(undefined);
      setLiveJob(undefined);
      queryClient.clear();
    };
    window.addEventListener("commerce-auth-expired", onExpired);
    return () => window.removeEventListener("commerce-auth-expired", onExpired);
  }, [queryClient, setLiveJob]);

  useEffect(() => {
    const job = liveJob ?? jobsQuery.data?.find((item) => item.status === "running" || item.status === "queued" || item.status === "paused");
    if (!job) return;
    const socket = new WebSocket(`${WS_URL}/api/ws/jobs/${job.id}`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.job) {
        setLiveJob(payload.job);
        queryClient.invalidateQueries({ queryKey: ["jobs"] });
        queryClient.invalidateQueries({ queryKey: ["products"] });
        queryClient.invalidateQueries({ queryKey: ["analytics"] });
      }
    };
    return () => socket.close();
  }, [jobsQuery.data, liveJob, queryClient, setLiveJob]);

  useEffect(() => {
    if (!liveJob) return;
    if (liveJob.status === "completed") {
      setNotice({
        id: `${liveJob.id}-completed-${liveJob.updated_at}`,
        kind: "success",
        title: "Scrape completed",
        message: `${liveJob.completed_products} products saved with ${compact(liveJob.visible_bought_count ?? 0)} scraped bought count. Export files are ready.`
      });
    } else if (liveJob.status === "failed") {
      setNotice({
        id: `${liveJob.id}-failed-${liveJob.updated_at}`,
        kind: "error",
        title: "Scrape failed",
        message: latestLog(liveJob)
      });
    } else if (isActiveJob(liveJob)) {
      setNotice({
        id: `${liveJob.id}-running`,
        kind: "info",
        title: "Live scrape running",
        message: liveJob.current_product || latestLog(liveJob)
      });
    }
  }, [liveJob?.id, liveJob?.status, liveJob?.progress, liveJob?.updated_at]);

  const products = productsQuery.data ?? [];
  const filteredProducts = useMemo(() => {
    const needle = query.toLowerCase();
    return products.filter((product) => [product.name, product.variant, product.category, product.website].join(" ").toLowerCase().includes(needle));
  }, [products, query]);

  const activeJob = liveJob ?? jobsQuery.data?.[0];

  if (!mounted) {
    return <main className="grid-bg min-h-screen" />;
  }

  if (!session) {
    return (
      <main className="grid-bg min-h-screen">
        <div className="mx-auto grid min-h-screen w-full max-w-xl place-items-center px-4">
          <AuthPanel
            onAuthenticated={(nextSession) => {
              setSession(nextSession);
              queryClient.invalidateQueries();
            }}
          />
        </div>
      </main>
    );
  }

  return (
    <main className="grid-bg min-h-screen">
      <ScrapeNotice notice={notice} onClose={() => setNotice(undefined)} />
      <div className="mx-auto flex w-full max-w-[1500px] gap-5 px-4 py-4 lg:px-6">
        <Sidebar active={active} setActive={setActive} />
        <section className="min-w-0 flex-1">
          <Topbar
            apiUrl={API_URL}
            query={query}
            setQuery={setQuery}
            session={session}
            onLogout={() => {
              setAuthSession(undefined);
              setSession(undefined);
              setLiveJob(undefined);
              queryClient.clear();
            }}
          />
          <div className="mt-5 grid gap-5">
            <AnimatePresence mode="wait">
              <motion.div key={active} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
                {active === "dashboard" && <DashboardView analytics={analyticsQuery.data} activeJob={activeJob} />}
                {active === "scraper" && <ScraperPanel onStarted={setLiveJob} activeJob={activeJob} />}
                {active === "products" && <ProductTable products={filteredProducts} title="Products" />}
                {active === "variants" && <VariantView products={filteredProducts} />}
                {active === "analytics" && <AnalyticsView analytics={analyticsQuery.data} products={products} />}
                {active === "revenue" && <RevenueView analytics={analyticsQuery.data} />}
                {active === "reviews" && <ReviewAnalyticsView products={filteredProducts} />}
                {active === "offers" && <OfferAnalyticsView products={filteredProducts} />}
                {active === "export" && <ExportCenter jobs={jobsQuery.data ?? []} products={products} />}
                {active === "insights" && <InsightsView analytics={analyticsQuery.data} products={products} />}
                {active === "jobs" && <JobsView jobs={jobsQuery.data ?? []} setLiveJob={setLiveJob} />}
                {active === "settings" && <SettingsView session={session} />}
              </motion.div>
            </AnimatePresence>
          </div>
        </section>
      </div>
    </main>
  );
}

function Sidebar({ active, setActive }: { active: string; setActive: (id: any) => void }) {
  return (
    <aside className="sticky top-4 hidden h-[calc(100vh-2rem)] w-64 shrink-0 rounded-lg border border-white/10 bg-slate-950/55 p-3 backdrop-blur-xl lg:block">
      <div className="mb-5 flex items-center gap-3 px-2 py-2">
        <div className="grid size-10 place-items-center rounded-md bg-teal-300 text-slate-950">
          <Sparkles className="size-5" />
        </div>
        <div>
          <div className="font-semibold">Commerce IQ</div>
          <div className="text-xs text-slate-400">Scraping Analytics</div>
        </div>
      </div>
      <nav className="grid gap-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => setActive(item.id)}
              className={cn(
                "flex h-11 items-center gap-3 rounded-md px-3 text-left text-sm text-slate-300 transition hover:bg-white/8 hover:text-white",
                active === item.id && "bg-white/12 text-white"
              )}
            >
              <Icon className="size-4" />
              {item.label}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}

function Topbar({
  apiUrl,
  query,
  setQuery,
  session,
  onLogout
}: {
  apiUrl: string;
  query: string;
  setQuery: (value: string) => void;
  session: AuthSession;
  onLogout: () => void;
}) {
  return (
    <header className="glass flex flex-col gap-4 rounded-lg p-4 md:flex-row md:items-center md:justify-between">
      <div>
        <div className="text-sm text-slate-400">Revenue intelligence platform</div>
        <h1 className="mt-1 text-2xl font-semibold tracking-normal text-white md:text-3xl">Scrape, analyze, monitor</h1>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} className={cn(inputClass, "w-full pl-9 sm:w-72")} placeholder="Search products, variants, jobs" />
        </div>
        <div className="flex items-center gap-2 rounded-md border border-emerald-300/20 bg-emerald-300/8 px-3 py-2 text-xs text-emerald-200">
          <ShieldCheck className="size-4" />
          {session.organization_name} · {apiUrl.replace("http://", "")}
        </div>
        <Button variant="muted" onClick={onLogout}>
          <LogOut className="size-4" />
          Sign out
        </Button>
      </div>
    </header>
  );
}

function DashboardView({ analytics, activeJob }: { analytics?: Awaited<ReturnType<typeof fetchAnalytics>>; activeJob?: Job }) {
  const summary = analytics?.summary;
  const kpis = [
    ["Total Products", summary?.total_products ?? 0, ShoppingBag, "text-teal-200"],
    ["Total Variants", summary?.total_variants ?? 0, Boxes, "text-sky-200"],
    ["Live Revenue", currency(summary?.total_revenue ?? 0), TrendingUp, "text-emerald-200"],
    ["Average Rating", summary?.average_rating ?? 0, Star, "text-amber-200"],
    ["Scraped Bought", compact(summary?.visible_bought_count ?? 0), Gauge, "text-rose-200"],
    ["Monthly Units Used", compact(summary?.units_sold ?? 0), Zap, "text-cyan-200"],
    ["Top Category", summary?.top_category ?? "None", Tags, "text-violet-200"],
    ["Active Jobs", summary?.active_jobs ?? 0, Activity, "text-orange-200"],
    ["Success Rate", `${summary?.success_rate ?? 0}%`, ShieldCheck, "text-lime-200"]
  ] as const;

  return (
    <div className="grid gap-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map(([label, value, Icon, color]) => (
          <Card key={label} className="min-h-32">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm text-slate-400">{label}</p>
                <p className="mt-3 break-words text-2xl font-semibold text-white">{value}</p>
              </div>
              <Icon className={cn("size-6", color)} />
            </div>
          </Card>
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <RevenueChart data={analytics?.revenue_trend ?? []} />
        <LiveProgress job={activeJob} />
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <CategoryChart data={analytics?.revenue_by_category ?? []} />
        <TopProducts products={analytics?.top_products ?? []} />
      </div>
    </div>
  );
}

function ScraperPanel({ onStarted, activeJob }: { onStarted: (job: Job) => void; activeJob?: Job }) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("https://www.amazon.in/gp/bestsellers/sports/3404687031/ref=pd_zg_hrsr_sports");
  const [website, setWebsite] = useState<Website>("amazon");
  const [useProxy, setUseProxy] = useState(false);
  const [headless, setHeadless] = useState(true);
  const [externalService, setExternalService] = useState(false);
  const [maxProducts, setMaxProducts] = useState(24);
  const [variantDepth, setVariantDepth] = useState(2);
  const [step, setStep] = useState<ScraperStep>("source");
  const running = isActiveJob(activeJob);
  const mutation = useMutation({
    mutationFn: startScrape,
    onSuccess: (job) => {
      onStarted(job);
      setStep("launch");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    }
  });

  const control = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "pause" | "resume" | "stop" | "retry" }) => controlJob(id, action),
    onSuccess: (job) => {
      onStarted(job);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    }
  });
  const stepIndex = scraperSteps.findIndex((item) => item.id === step);
  const canLaunch = Boolean(url.trim()) && maxProducts > 0 && !mutation.isPending && !running;
  const selectedHost = useMemo(() => {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return "URL pending";
    }
  }, [url]);
  const startRun = () => {
    if (!canLaunch) return;
    mutation.mutate({ url, website, useProxy, headless, maxProducts, variantDepth, externalService });
  };
  const goToStep = (direction: -1 | 1) => {
    const next = scraperSteps[Math.min(Math.max(stepIndex + direction, 0), scraperSteps.length - 1)];
    setStep(next.id);
  };

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
      <Card className="overflow-hidden p-0">
        <div className="border-b border-white/10 p-5">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm text-slate-400">Scraper control</p>
              <h2 className="text-xl font-semibold text-white">Step-by-step launch desk</h2>
            </div>
            <div className="grid size-11 place-items-center rounded-md border border-teal-300/25 bg-teal-300/10 text-teal-100">
              <Database className="size-5" />
            </div>
          </div>
          <ScraperStepTabs active={step} onChange={setStep} />
        </div>
        <div className="p-5">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 18 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -18 }}
              transition={{ duration: 0.18 }}
              className="min-h-[404px]"
            >
              {step === "source" && (
                <div className="grid gap-5">
                  <Field label="eCommerce URL">
                    <div className="relative">
                      <Link2 className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                      <input className={cn(inputClass, "h-12 w-full pl-10")} value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://..." />
                    </div>
                  </Field>
                  <div>
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div className="text-sm text-slate-300">Marketplace</div>
                      <div className="truncate rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-400">{selectedHost}</div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                      {websites.map((item) => {
                        const selected = website === item;
                        return (
                          <button
                            key={item}
                            type="button"
                            aria-pressed={selected}
                            onClick={() => setWebsite(item)}
                            className={cn(
                              "flex h-12 items-center justify-between rounded-md border px-3 text-left text-sm capitalize transition",
                              selected ? "border-teal-300/50 bg-teal-300/12 text-teal-50 shadow-[0_0_0_1px_rgba(45,212,191,0.16)]" : "border-white/10 bg-white/5 text-slate-300 hover:border-white/20 hover:bg-white/10"
                            )}
                          >
                            <span>{item}</span>
                            {selected ? <Check className="size-4" /> : <Circle className="size-3 text-slate-600" />}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div className="grid gap-3 rounded-md border border-sky-300/15 bg-sky-300/8 p-4 text-sm text-sky-100 sm:grid-cols-[auto_1fr]">
                    <ShieldCheck className="mt-0.5 size-5" />
                    <div>
                      <div className="font-semibold">Source locked to {website}</div>
                      <div className="mt-1 text-sky-100/75">The next step tunes browser behavior and product volume before the backend job is created.</div>
                    </div>
                  </div>
                </div>
              )}
              {step === "runtime" && (
                <div className="grid gap-5">
                  <ProductLimitSlider value={maxProducts} onChange={setMaxProducts} />
                  <Field label="Variant depth">
                    <select className={cn(inputClass, "w-full")} value={variantDepth} onChange={(event) => setVariantDepth(Number(event.target.value))}>
                      <option value={0}>Parent products only</option>
                      <option value={1}>Fast variant pass</option>
                      <option value={2}>Standard variant intelligence</option>
                      <option value={3}>Deep variant click automation</option>
                      <option value={5}>Maximum depth</option>
                    </select>
                  </Field>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Toggle checked={useProxy} label="Proxy routing" description="Route the request through the configured proxy pool." icon={ShieldCheck} onChange={setUseProxy} />
                    <Toggle checked={headless} label="Headless browser" description="Run Chromium in background mode for faster jobs." icon={Zap} onChange={setHeadless} />
                    <Toggle checked={externalService} label="External service" description="Use the external scraper API when it is configured." icon={Database} onChange={setExternalService} />
                    <div className="rounded-md border border-white/10 bg-white/5 p-4">
                      <div className="flex items-center gap-2 text-sm font-semibold text-white">
                        <Activity className="size-4 text-emerald-200" />
                        Live updates
                      </div>
                      <div className="mt-2 text-sm leading-5 text-slate-400">Jobs stream progress, product counts, revenue, alerts, and logs into the dashboard.</div>
                    </div>
                  </div>
                </div>
              )}
              {step === "launch" && (
                <div className="grid gap-5">
                  <RunSummary url={url} website={website} maxProducts={maxProducts} variantDepth={variantDepth} useProxy={useProxy} headless={headless} externalService={externalService} />
                  <SlideToStart disabled={!canLaunch} loading={mutation.isPending || running} onConfirm={startRun} />
                  <Button disabled={!canLaunch} onClick={startRun} className="h-12">
                    {mutation.isPending || running ? <Loader2 className="size-4 animate-spin" /> : <Rocket className="size-4" />}
                    {mutation.isPending ? "Sending request" : running ? "Scraping in progress" : "Start Scraping"}
                  </Button>
                  {running && (
                    <div className="rounded-md border border-teal-300/20 bg-teal-300/8 p-3 text-sm text-teal-100">
                      Backend is processing the live page. Keep this tab open to watch logs, phases, product counts, and dashboard metrics update automatically.
                    </div>
                  )}
                  {mutation.error && <div className="rounded-md border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-sm text-rose-100">Could not start the scraper. If you were signed out, sign in again so the backend can issue a fresh organization API key.</div>}
                </div>
              )}
            </motion.div>
          </AnimatePresence>
          <div className="mt-5 flex items-center justify-between gap-3 border-t border-white/10 pt-4">
            <Button variant="muted" disabled={stepIndex === 0} onClick={() => goToStep(-1)}>
              <ArrowLeft className="size-4" />
              Back
            </Button>
            <div className="text-xs text-slate-500">Step {stepIndex + 1} of {scraperSteps.length}</div>
            <Button variant="muted" disabled={stepIndex === scraperSteps.length - 1} onClick={() => goToStep(1)}>
              Next
              <ArrowRight className="size-4" />
            </Button>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <Button variant="muted" disabled={!activeJob || control.isPending} onClick={() => activeJob && control.mutate({ id: activeJob.id, action: activeJob.status === "paused" ? "resume" : "pause" })}>
              {activeJob?.status === "paused" ? <Play className="size-4" /> : <Pause className="size-4" />}
              {activeJob?.status === "paused" ? "Resume" : "Pause"}
            </Button>
            <Button variant="danger" disabled={!activeJob || control.isPending} onClick={() => activeJob && control.mutate({ id: activeJob.id, action: "stop" })}>
              <Square className="size-4" />
              Stop
            </Button>
            <Button variant="muted" disabled={!activeJob || control.isPending} onClick={() => activeJob && control.mutate({ id: activeJob.id, action: "retry" })}>
              <RefreshCcw className="size-4" />
              Retry
            </Button>
          </div>
        </div>
      </Card>
      <LiveProgress job={activeJob} expanded />
    </div>
  );
}

function ScraperStepTabs({ active, onChange }: { active: ScraperStep; onChange: (step: ScraperStep) => void }) {
  const activeIndex = scraperSteps.findIndex((step) => step.id === active);
  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {scraperSteps.map((step, index) => {
        const Icon = step.icon;
        const selected = step.id === active;
        const passed = index < activeIndex;
        return (
          <button
            key={step.id}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(step.id)}
            className={cn(
              "relative min-h-20 rounded-md border p-3 text-left transition",
              selected && "border-teal-300/55 bg-teal-300/12 text-white",
              passed && !selected && "border-emerald-300/30 bg-emerald-300/8 text-emerald-50",
              !selected && !passed && "border-white/10 bg-white/5 text-slate-300 hover:border-white/20 hover:bg-white/10"
            )}
          >
            <div className="flex items-center justify-between gap-3">
              <div className={cn("grid size-8 place-items-center rounded-md", selected ? "bg-teal-300 text-slate-950" : passed ? "bg-emerald-300/15 text-emerald-100" : "bg-slate-900 text-slate-400")}>
                {passed ? <Check className="size-4" /> : <Icon className="size-4" />}
              </div>
              <span className="text-xs text-slate-500">0{index + 1}</span>
            </div>
            <div className="mt-3 text-sm font-semibold">{step.label}</div>
            <div className="mt-1 text-xs text-slate-400">{step.detail}</div>
          </button>
        );
      })}
    </div>
  );
}

function ProductLimitSlider({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  const progress = ((value - 1) / 99) * 100;
  return (
    <div className="rounded-md border border-white/10 bg-slate-950/35 p-4">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <SlidersHorizontal className="size-4 text-teal-200" />
            Product volume
          </div>
          <div className="mt-1 text-sm text-slate-400">Choose how deep the bestseller page should be processed.</div>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-semibold text-white">{value}</span>
          <span className="text-sm text-slate-400">products</span>
        </div>
      </div>
      <input
        className="action-range"
        type="range"
        min={1}
        max={100}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        style={{ background: `linear-gradient(90deg, #2dd4bf ${progress}%, rgba(51,65,85,0.88) ${progress}%)` }}
      />
      <div className="mt-4 grid grid-cols-4 gap-2">
        {productPresets.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => onChange(preset)}
            className={cn(
              "h-9 rounded-md border text-sm font-semibold transition",
              value === preset ? "border-teal-300/55 bg-teal-300/15 text-teal-50" : "border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
            )}
          >
            {preset}
          </button>
        ))}
      </div>
    </div>
  );
}

function RunSummary({
  url,
  website,
  maxProducts,
  variantDepth,
  useProxy,
  headless,
  externalService
}: {
  url: string;
  website: Website;
  maxProducts: number;
  variantDepth: number;
  useProxy: boolean;
  headless: boolean;
  externalService: boolean;
}) {
  const host = useMemo(() => {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return "Invalid URL";
    }
  }, [url]);
  const items = [
    ["Website", website],
    ["Host", host],
    ["Limit", `${maxProducts}`],
    ["Variant depth", `${variantDepth}`],
    ["Mode", externalService ? "External" : headless ? "Headless" : "Visible"],
    ["Proxy", useProxy ? "On" : "Off"]
  ];
  return (
    <div className="rounded-md border border-white/10 bg-white/5 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
        <CheckCircle2 className="size-4 text-emerald-200" />
        Launch summary
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {items.map(([label, value]) => (
          <div key={label} className="rounded-md border border-white/10 bg-slate-950/45 p-3">
            <div className="text-xs text-slate-500">{label}</div>
            <div className="mt-1 truncate text-sm font-semibold text-slate-100">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SlideToStart({ disabled, loading, onConfirm }: { disabled: boolean; loading: boolean; onConfirm: () => void }) {
  const [value, setValue] = useState(0);
  const [armed, setArmed] = useState(false);
  const fill = Math.min(value, 100);

  useEffect(() => {
    if (!disabled && !loading) return;
    setValue(0);
    setArmed(false);
  }, [disabled, loading]);

  const handleChange = (nextValue: number) => {
    if (disabled || loading) return;
    setValue(nextValue);
    if (nextValue < 96 || armed) return;
    setArmed(true);
    window.setTimeout(() => {
      onConfirm();
      setValue(0);
      setArmed(false);
    }, 160);
  };

  return (
    <div className={cn("relative overflow-hidden rounded-md border border-white/10 bg-slate-950/45 p-3", disabled && "opacity-60")}>
      <div
        className="pointer-events-none absolute inset-y-0 left-0 bg-gradient-to-r from-teal-300/24 via-emerald-300/18 to-amber-300/16 transition-[width]"
        style={{ width: `${fill}%` }}
      />
      <div className="relative mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-white">
          {loading ? <Loader2 className="size-4 animate-spin text-teal-200" /> : <MousePointerClick className="size-4 text-teal-200" />}
          Slide action
        </div>
        <div className="text-xs text-slate-400">{loading ? "Running" : `${fill}%`}</div>
      </div>
      <div className="relative flex items-center gap-3">
        <ChevronsRight className="pointer-events-none absolute left-3 z-10 size-5 text-slate-950" />
        <input
          aria-label="Slide to start scraping"
          className="launch-slider"
          type="range"
          min={0}
          max={100}
          value={value}
          disabled={disabled || loading}
          onChange={(event) => handleChange(Number(event.target.value))}
          style={{ background: `linear-gradient(90deg, #2dd4bf ${fill}%, rgba(30,41,59,0.9) ${fill}%)` }}
        />
      </div>
    </div>
  );
}

function Toggle({
  checked,
  label,
  onChange,
  description,
  icon: Icon
}: {
  checked: boolean;
  label: string;
  onChange: (value: boolean) => void;
  description?: string;
  icon?: React.ElementType;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "flex min-h-20 items-start justify-between gap-3 rounded-md border p-4 text-left text-sm transition",
        checked ? "border-teal-300/35 bg-teal-300/10 text-teal-50" : "border-white/10 bg-slate-950/40 text-slate-200 hover:bg-white/8"
      )}
    >
      <span className="flex min-w-0 gap-3">
        {Icon && (
          <span className={cn("mt-0.5 grid size-8 shrink-0 place-items-center rounded-md", checked ? "bg-teal-300 text-slate-950" : "bg-white/8 text-slate-400")}>
            <Icon className="size-4" />
          </span>
        )}
        <span className="min-w-0">
          <span className="block font-semibold">{label}</span>
          {description && <span className="mt-1 block text-xs leading-4 text-slate-400">{description}</span>}
        </span>
      </span>
      <span className={cn("mt-1 h-6 w-11 shrink-0 rounded-full p-1 transition", checked ? "bg-teal-300" : "bg-slate-700")}>
        <span className={cn("block size-4 rounded-full bg-slate-950 transition", checked && "translate-x-5")} />
      </span>
    </button>
  );
}

function LiveProgress({ job, expanded = false }: { job?: Job; expanded?: boolean }) {
  const activePhase = phaseIndex(job);
  const active = isActiveJob(job);
  const failed = job?.status === "failed";
  const completed = job?.status === "completed";
  const statusTone = completed ? "border-emerald-300/25 bg-emerald-300/10 text-emerald-100" : failed ? "border-rose-300/25 bg-rose-300/10 text-rose-100" : active ? "border-teal-300/25 bg-teal-300/10 text-teal-100" : "border-white/10 text-slate-300";

  return (
    <Card className={cn("min-h-72", expanded && "min-h-[520px]")}>
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-slate-400">Live scraping system</p>
          <h2 className="text-xl font-semibold text-white">{job?.current_product || "Waiting for job"}</h2>
          <p className="mt-2 text-sm text-slate-400">{job ? latestLog(job) : "Enter a URL and start scraping to watch backend progress here."}</p>
        </div>
        <span className={cn("inline-flex items-center gap-2 rounded-md border px-3 py-1 text-xs uppercase tracking-wide", statusTone)}>
          {active && <Loader2 className="size-3.5 animate-spin" />}
          {completed && <CheckCircle2 className="size-3.5" />}
          {failed && <AlertTriangle className="size-3.5" />}
          {job?.status ?? "idle"}
        </span>
      </div>
      <div className="mb-3 flex items-center justify-between text-xs text-slate-400">
        <span>Backend processing</span>
        <span>{job?.progress ?? 0}%</span>
      </div>
      <div className="mb-5 h-3 overflow-hidden rounded-full bg-slate-800">
        <motion.div
          className={cn("h-full", failed ? "bg-rose-400" : "bg-gradient-to-r from-teal-300 via-emerald-300 to-amber-300")}
          animate={{ width: `${job?.progress ?? 0}%` }}
          transition={{ type: "spring", stiffness: 80, damping: 18 }}
        />
      </div>
      <PhaseTimeline activePhase={activePhase} job={job} />
      <div className="grid gap-3 text-sm sm:grid-cols-5">
        <Metric label="Completed" value={job?.completed_products ?? 0} />
        <Metric label="Remaining" value={job?.remaining_products ?? 0} />
        <Metric label="Scraped Bought" value={compact(job?.visible_bought_count ?? 0)} />
        <Metric label="Monthly Units" value={compact(job?.units_sold ?? 0)} />
        <Metric label="Bought x Price" value={currency(job?.revenue ?? 0)} />
      </div>
      <ExportReadyActions job={job} />
      {job?.captcha_alert && <div className="mt-4 rounded-md border border-amber-300/25 bg-amber-300/10 px-3 py-2 text-sm text-amber-100">Captcha alert detected during extraction.</div>}
      {job?.external_job_id && <div className="mt-4 rounded-md border border-sky-300/25 bg-sky-300/10 px-3 py-2 text-sm text-sky-100">External scraper job: {job.external_job_id}</div>}
      <div className={cn("mt-5 overflow-hidden rounded-md border border-white/10 bg-slate-950/50", expanded ? "h-72" : "h-36")}>
        <div className="h-full overflow-auto p-3 font-mono text-xs leading-6 text-slate-300">
          {(job?.logs?.length ? job.logs : ["No live logs yet."]).map((line, index) => (
            <div key={`${line}-${index}`}>{line}</div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function ExportReadyActions({ job }: { job?: Job }) {
  const ready = job?.status === "completed" && (job.completed_products ?? 0) > 0;
  if (!ready) return null;
  const exports = [
    ["Excel", "xlsx", FileSpreadsheet],
    ["CSV", "csv", FileText],
    ["JSON", "json", FileJson],
    ["TXT", "txt", FileText]
  ] as const;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-4 rounded-md border border-emerald-300/25 bg-emerald-300/8 p-4"
    >
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-50">
            <CheckCircle2 className="size-4" />
            Export ready
          </div>
          <div className="mt-1 text-xs text-emerald-100/70">
            {job.completed_products} products saved - {compact(job.visible_bought_count ?? 0)} scraped bought - {compact(job.units_sold ?? 0)} monthly units - {currency(job.revenue)} bought x price revenue
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {exports.map(([label, format, Icon]) => (
          <a
            key={format}
            href={exportUrl(format, job.id)}
            className="group flex h-11 items-center justify-center gap-2 rounded-md border border-white/10 bg-slate-950/45 px-3 text-sm font-semibold text-slate-100 transition hover:border-teal-200/45 hover:bg-white/10"
          >
            <Icon className="size-4 text-teal-200" />
            {label}
          </a>
        ))}
      </div>
    </motion.div>
  );
}

function PhaseTimeline({ activePhase, job }: { activePhase: number; job?: Job }) {
  const currentIndex = job ? Math.max(activePhase, 0) : -1;
  const currentPhase = currentIndex >= 0 ? scrapePhases[currentIndex] : undefined;
  const progress = Math.min(Math.max(job?.progress ?? 0, 0), 100);
  return (
    <div className="mb-5 rounded-md border border-white/10 bg-slate-950/35 p-3">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-sm font-semibold text-white">Processing phases</div>
          <div className="mt-1 text-xs text-slate-400">{currentPhase ? currentPhase.detail : "Idle queue"}</div>
        </div>
        <div className="inline-flex w-fit items-center gap-2 rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300">
          <Clock3 className="size-3.5 text-teal-200" />
          {currentPhase ? `Step ${currentIndex + 1} / ${scrapePhases.length}` : "Idle"}
        </div>
      </div>
      <div className="mb-4 h-2 overflow-hidden rounded-full bg-slate-800">
        <motion.div
          className="h-full bg-gradient-to-r from-teal-300 via-emerald-300 to-amber-300"
          animate={{ width: `${progress}%` }}
          transition={{ type: "spring", stiffness: 80, damping: 18 }}
        />
      </div>
      <div className="grid gap-2 md:grid-cols-7">
        {scrapePhases.map((phase, index) => {
          const done = job && (job.status === "completed" || index < activePhase);
          const current = job && index === activePhase && isActiveJob(job);
          const blocked = job?.status === "failed" && index === activePhase;
          const Icon = done ? CheckCircle2 : current ? Loader2 : blocked ? AlertTriangle : Circle;
          return (
            <motion.div
              key={phase.label}
              whileHover={{ y: -2 }}
              className={cn(
                "min-h-24 rounded-md border p-2 transition",
                done && "border-emerald-300/25 bg-emerald-300/8",
                current && "border-teal-300/30 bg-teal-300/10",
                blocked && "border-rose-300/30 bg-rose-300/10",
                !done && !current && !blocked && "border-white/10 bg-white/5"
              )}
            >
              <div className="mb-2 flex items-center justify-between">
                <Icon className={cn("size-4", done && "text-emerald-200", current && "animate-spin text-teal-200", blocked && "text-rose-200", !done && !current && !blocked && "text-slate-500")} />
                <span className="text-[11px] text-slate-500">{phase.threshold}%</span>
              </div>
              <div className="text-xs font-semibold text-slate-100">{phase.label}</div>
              <div className="mt-1 text-[11px] leading-4 text-slate-400">{phase.detail}</div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-white/10 bg-white/5 p-3">
      <div className="text-slate-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

function RevenueChart({ data }: { data: Array<{ date: string; revenue: number }> }) {
  return (
    <Card className="h-96">
      <h2 className="mb-4 text-xl font-semibold text-white">Revenue Trend</h2>
      <ResponsiveContainer width="100%" height="85%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#2dd4bf" stopOpacity={0.5} />
              <stop offset="95%" stopColor="#2dd4bf" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(148,163,184,0.12)" />
          <XAxis dataKey="date" stroke="#94a3b8" />
          <YAxis stroke="#94a3b8" tickFormatter={(value) => compact(Number(value))} />
          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,.12)" }} formatter={(value) => currency(Number(value))} />
          <Area type="monotone" dataKey="revenue" stroke="#2dd4bf" fill="url(#revenueFill)" strokeWidth={3} />
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  );
}

function CategoryChart({ data }: { data: Array<{ name: string; revenue: number }> }) {
  return (
    <Card className="h-96">
      <h2 className="mb-4 text-xl font-semibold text-white">Category Distribution</h2>
      <ResponsiveContainer width="100%" height="85%">
        <BarChart data={data}>
          <CartesianGrid stroke="rgba(148,163,184,0.12)" />
          <XAxis dataKey="name" stroke="#94a3b8" />
          <YAxis stroke="#94a3b8" tickFormatter={(value) => compact(Number(value))} />
          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,.12)" }} formatter={(value) => currency(Number(value))} />
          <Bar dataKey="revenue" radius={[6, 6, 0, 0]}>
            {data.map((_, index) => (
              <Cell key={index} fill={colors[index % colors.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}

function TopProducts({ products }: { products: Product[] }) {
  return (
    <Card className="h-96 overflow-hidden">
      <h2 className="mb-4 text-xl font-semibold text-white">Top Revenue Products</h2>
      <div className="grid gap-3 overflow-auto pr-1">
        {products.map((product) => (
          <div key={product.id} className="flex items-center justify-between gap-4 rounded-md border border-white/10 bg-white/5 p-3">
            <div className="min-w-0">
              <div className="truncate font-medium text-white">{product.name}</div>
              <div className="text-sm text-slate-400">{product.variant}</div>
            </div>
            <div className="shrink-0 text-right">
              <div className="font-semibold text-teal-100">{currency(product.revenue)}</div>
              <div className="text-xs text-slate-400">{compact(product.visible_bought_count)} scraped bought</div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ProductTable({ products, title }: { products: Product[]; title: string }) {
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<keyof Product>("revenue");
  const sorted = useMemo(() => [...products].sort((a, b) => Number(b[sort] ?? 0) - Number(a[sort] ?? 0)), [products, sort]);
  const rows = sorted.slice(page * 10, page * 10 + 10);
  return (
    <Card>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-slate-400">{products.length} rows</p>
          <h2 className="text-xl font-semibold text-white">{title}</h2>
        </div>
        <select className={cn(inputClass, "w-44")} value={sort} onChange={(event) => setSort(event.target.value as keyof Product)}>
          <option value="revenue">Bought x Price Revenue</option>
          <option value="units_sold">Units sold</option>
          <option value="rating">Rating</option>
          <option value="reviews">Reviews</option>
          <option value="price">Price</option>
        </select>
      </div>
      <div className="overflow-x-auto rounded-md border border-white/10">
        <table className="min-w-[1080px] w-full border-collapse text-left text-sm">
          <thead className="bg-white/8 text-xs uppercase text-slate-400">
            <tr>
              {["Rank", "Product Name", "Brand", "ASIN", "Variant", "Price", "Original Price", "Discount", "Rating", "Reviews", "Scraped Bought", "Monthly Units", "Bought Source", "Bought x Price Revenue", "Product Total Revenue", "Availability", "Prime", "Offers", "Product URL"].map((header) => (
                <th key={header} className="px-3 py-3 font-medium">
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((product) => (
              <tr key={product.id} className="border-t border-white/8 align-top">
                <td className="px-3 py-3">{product.product_rank}</td>
                <td className="max-w-72 px-3 py-3 text-white">{product.name}</td>
                <td className="px-3 py-3">{product.brand_name}</td>
                <td className="px-3 py-3">{product.parent_asin}</td>
                <td className="px-3 py-3">{product.variant}</td>
                <td className="px-3 py-3">{product.price_text || currency(product.price)}</td>
                <td className="px-3 py-3">{product.original_price_text || currency(product.original_price)}</td>
                <td className="px-3 py-3">{product.discount_text || `${product.discount}%`}</td>
                <td className="px-3 py-3">{product.rating_text || product.rating}</td>
                <td className="px-3 py-3">{product.reviews_text || compact(product.reviews)}</td>
                <td className="px-3 py-3">{compact(product.visible_bought_count)}</td>
                <td className="px-3 py-3">{compact(product.units_sold)}</td>
                <td className="px-3 py-3">{product.bought_count_source || (product.units_sold_estimated ? "rank_estimate" : "visible")}</td>
                <td className="px-3 py-3 font-semibold text-teal-100">{currency(product.revenue)}</td>
                <td className="px-3 py-3 font-semibold text-emerald-100">{currency(product.parent_product_revenue || product.revenue)}</td>
                <td className="px-3 py-3">{product.availability}</td>
                <td className="px-3 py-3">{product.prime_available ? "Yes" : "No"}</td>
                <td className="px-3 py-3">{product.offers}</td>
                <td className="max-w-56 truncate px-3 py-3">{product.product_url}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex items-center justify-between">
        <Button variant="muted" disabled={page === 0} onClick={() => setPage((value) => Math.max(value - 1, 0))}>
          Previous
        </Button>
        <span className="text-sm text-slate-400">Page {page + 1}</span>
        <Button variant="muted" disabled={(page + 1) * 10 >= sorted.length} onClick={() => setPage((value) => value + 1)}>
          Next
        </Button>
      </div>
    </Card>
  );
}

function VariantView({ products }: { products: Product[] }) {
  const variants = products.map((product) => ({
    ...product,
    demand_score: product.scores?.demand_score ?? 0,
    conversion_score: product.scores?.performance_score ?? 0
  }));
  return (
    <div className="grid gap-5">
      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="Color Variants" value={new Set(products.map((item) => item.color).filter(Boolean)).size} />
        <Metric label="Size Variants" value={new Set(products.map((item) => item.size).filter(Boolean)).size} />
        <Metric label="Variant Revenue" value={currency(products.reduce((sum, item) => sum + item.revenue, 0))} />
        <Metric label="Demand Peak" value={compact(Math.max(...products.map((item) => item.units_sold), 0))} />
      </div>
      <ProductTable products={variants} title="Product Variants" />
    </div>
  );
}

function AnalyticsView({ analytics, products }: { analytics?: Awaited<ReturnType<typeof fetchAnalytics>>; products: Product[] }) {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <CategoryChart data={analytics?.revenue_by_category ?? []} />
      <VariantPie data={analytics?.variant_distribution ?? []} />
      <ProductTable products={products} title="Analytics Data Table" />
    </div>
  );
}

function RevenueView({ analytics }: { analytics?: Awaited<ReturnType<typeof fetchAnalytics>> }) {
  return (
    <div className="grid gap-5">
      <RevenueChart data={analytics?.revenue_trend ?? []} />
      <div className="grid gap-5 xl:grid-cols-2">
        <CategoryChart data={analytics?.revenue_by_category ?? []} />
        <VariantPie data={analytics?.variant_distribution ?? []} />
      </div>
    </div>
  );
}

function VariantPie({ data }: { data: Array<{ name: string; value: number }> }) {
  return (
    <Card className="h-96">
      <h2 className="mb-4 text-xl font-semibold text-white">Variant Revenue Distribution</h2>
      <ResponsiveContainer width="100%" height="85%">
        <PieChart>
          <Pie data={data} innerRadius={68} outerRadius={112} paddingAngle={3} dataKey="value" nameKey="name">
            {data.map((_, index) => (
              <Cell key={index} fill={colors[index % colors.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,.12)" }} formatter={(value) => currency(Number(value))} />
        </PieChart>
      </ResponsiveContainer>
    </Card>
  );
}

function ReviewAnalyticsView({ products }: { products: Product[] }) {
  const avgPositive = products.length ? products.reduce((sum, item) => sum + (item.positive_review_percent || (item.rating ? (item.rating / 5) * 100 : 0)), 0) / products.length : 0;
  return (
    <div className="grid gap-5">
      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="Average Rating" value={(products.reduce((sum, item) => sum + item.rating, 0) / Math.max(products.length, 1)).toFixed(2)} />
        <Metric label="Review Count" value={compact(products.reduce((sum, item) => sum + item.reviews, 0))} />
        <Metric label="Positive Review %" value={`${avgPositive.toFixed(1)}%`} />
        <Metric label="Review Keywords" value={new Set(products.flatMap((item) => item.review_keywords ?? [])).size} />
      </div>
      <ProductTable products={products} title="Review Analytics" />
    </div>
  );
}

function OfferAnalyticsView({ products }: { products: Product[] }) {
  const couponRows = products.filter((item) => item.coupon_available || item.coupon_offers);
  return (
    <div className="grid gap-5">
      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="Coupon Offers" value={couponRows.length} />
        <Metric label="Bank Offers" value={products.filter((item) => item.bank_offers || item.offers.toLowerCase().includes("bank")).length} />
        <Metric label="Exchange Offers" value={products.filter((item) => item.exchange_offers || item.offers.toLowerCase().includes("exchange")).length} />
        <Metric label="Avg Discount" value={`${(products.reduce((sum, item) => sum + item.discount, 0) / Math.max(products.length, 1)).toFixed(1)}%`} />
      </div>
      <ProductTable products={products} title="Offer Analytics" />
    </div>
  );
}

function ExportCenter({ jobs, products }: { jobs: Job[]; products: Product[] }) {
  const completed = jobs.find((job) => job.status === "completed") ?? jobs[0];
  const formats = [
    ["Excel", "xlsx", FileSpreadsheet],
    ["CSV", "csv", FileText],
    ["JSON", "json", FileJson],
    ["TXT", "txt", FileText],
    ["Images", "images", Database]
  ] as const;
  return (
    <Card>
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-slate-400">{products.length} analytics rows available</p>
          <h2 className="text-xl font-semibold text-white">Live Export Center</h2>
        </div>
        <div className="rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-300">{completed?.id ?? "No job selected"}</div>
      </div>
      <div className="grid gap-3 sm:grid-cols-5">
        {formats.map(([label, format, Icon]) => (
          <a key={format} href={exportUrl(format, completed?.id)} className="flex h-24 flex-col items-center justify-center gap-2 rounded-md border border-white/10 bg-white/5 text-sm font-semibold text-slate-100 transition hover:border-teal-300/45 hover:bg-teal-300/10">
            <Icon className="size-5 text-teal-200" />
            {label}
          </a>
        ))}
      </div>
      <div className="mt-5 rounded-md border border-emerald-300/20 bg-emerald-300/8 p-4 text-sm text-emerald-50">
        Excel exports include Parent Products, Product Variants, Revenue Analytics, Variant Revenue, Demand, Offer, Delivery, Review, AI Insights, and Sales Forecasting sheets with filters, frozen headers, currency formats, and conditional highlighting.
      </div>
    </Card>
  );
}

function InsightsView({ analytics, products }: { analytics?: Awaited<ReturnType<typeof fetchAnalytics>>; products: Product[] }) {
  return (
    <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
      <Card>
        <h2 className="mb-4 text-xl font-semibold text-white">AI Insights</h2>
        <div className="grid gap-3">
          {(analytics?.ai_insights ?? []).map((insight) => (
            <div key={insight.title} className="rounded-md border border-white/10 bg-white/5 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold text-white">{insight.title}</div>
                <div className="rounded-md border border-teal-300/25 bg-teal-300/10 px-2 py-1 text-xs text-teal-100">{Number(insight.score).toFixed(1)}</div>
              </div>
              <div className="mt-2 text-sm leading-5 text-slate-400">{insight.detail}</div>
            </div>
          ))}
        </div>
      </Card>
      <Card className="h-96">
        <h2 className="mb-4 text-xl font-semibold text-white">Revenue Forecasting</h2>
        <ResponsiveContainer width="100%" height="85%">
          <AreaChart data={analytics?.revenue_forecast ?? []}>
            <CartesianGrid stroke="rgba(148,163,184,0.12)" />
            <XAxis dataKey="period" stroke="#94a3b8" />
            <YAxis stroke="#94a3b8" tickFormatter={(value) => compact(Number(value))} />
            <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,.12)" }} formatter={(value) => currency(Number(value))} />
            <Area type="monotone" dataKey="forecast" stroke="#fb7185" fill="#fb718555" strokeWidth={3} />
          </AreaChart>
        </ResponsiveContainer>
      </Card>
      <ProductTable products={products} title="High Conversion Products" />
    </div>
  );
}

function JobsView({ jobs, setLiveJob }: { jobs: Job[]; setLiveJob: (job?: Job) => void }) {
  return (
    <Card>
      <h2 className="mb-4 text-xl font-semibold text-white">Scraping Jobs</h2>
      <div className="grid gap-3">
        {jobs.map((job) => (
          <button key={job.id} onClick={() => setLiveJob(job)} className="rounded-md border border-white/10 bg-white/5 p-4 text-left transition hover:bg-white/10">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0">
                <div className="truncate font-semibold text-white">{job.url}</div>
                <div className="text-sm text-slate-400">{job.website} · {job.completed_products} products · {currency(job.revenue)}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="h-2 w-32 overflow-hidden rounded-full bg-slate-800">
                  <div className="h-full bg-teal-300" style={{ width: `${job.progress}%` }} />
                </div>
                <span className="w-24 rounded-md border border-white/10 px-3 py-1 text-center text-xs uppercase text-slate-300">{job.status}</span>
                <ChevronDown className="size-4 text-slate-400" />
              </div>
            </div>
          </button>
        ))}
      </div>
    </Card>
  );
}

function ApiKeyManager() {
  const [name, setName] = useState("Operations Export Key");
  const queryClient = useQueryClient();
  const keysQuery = useQuery({ queryKey: ["api-keys"], queryFn: fetchApiKeys });
  const mutation = useMutation({
    mutationFn: createApiKey,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["api-keys"] })
  });

  return (
    <Card>
      <h2 className="mb-4 text-xl font-semibold text-white">Organization API Keys</h2>
      <div className="grid gap-3">
        <Field label="New key name">
          <input className={inputClass} value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Button disabled={mutation.isPending} onClick={() => mutation.mutate(name)}>
          <KeyRound className="size-4" />
          Create API Key
        </Button>
        <div className="grid gap-2">
          {(keysQuery.data ?? []).map((key) => (
            <div key={key.id} className="rounded-md border border-white/10 bg-white/5 p-3 text-sm text-slate-300">
              <div className="font-semibold text-white">{key.name}</div>
              <div className="mt-1 font-mono text-xs">{key.key_preview}</div>
              <div className="mt-2 break-all rounded-md bg-slate-950/70 p-2 font-mono text-xs text-teal-100">{key.key}</div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function SettingsView({ session }: { session: AuthSession }) {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Card>
        <h2 className="mb-4 text-xl font-semibold text-white">Scraper Settings</h2>
        <div className="grid gap-3">
          <div className="rounded-md border border-white/10 bg-white/5 p-3 text-sm text-slate-300">Organization: {session.organization_name}</div>
          <Toggle checked label="Retry logic" onChange={() => undefined} />
          <Toggle checked label="Fallback selectors" onChange={() => undefined} />
          <Toggle checked label="Captcha alerts" onChange={() => undefined} />
          <Toggle checked label="Revenue calculations" onChange={() => undefined} />
        </div>
      </Card>
      <Card>
        <h2 className="mb-4 text-xl font-semibold text-white">Deployment Targets</h2>
        <div className="grid gap-3 text-sm text-slate-300">
          <div className="rounded-md border border-white/10 bg-white/5 p-3">Frontend: Vercel-ready Next.js app</div>
          <div className="rounded-md border border-white/10 bg-white/5 p-3">Backend: Render-ready FastAPI service</div>
          <div className="rounded-md border border-white/10 bg-white/5 p-3">Workers: Playwright inside Docker</div>
          <div className="rounded-md border border-white/10 bg-white/5 p-3">Exports: CSV, Excel, JSON, TXT</div>
        </div>
      </Card>
      <ApiKeyManager />
    </div>
  );
}
