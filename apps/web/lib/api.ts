export type Health = {
  status: string;
  database_connected: boolean;
  scenario: string | null;
  dataset_sha256: string | null;
  imported_at: string | null;
};

export type Kpis = {
  active_products: number;
  reorder_due_products: number;
  negative_stock_products: number;
  receipt_lines: number;
  discrepancy_lines: number;
  receiving_accuracy_percent: number | null;
  waste_events: number;
  movement_count: number;
  latest_inventory_accuracy_percent: string | null;
  data_quality_issue_count: number;
};

export type InventoryItem = {
  product_id: string;
  product_name: string;
  category: string;
  inventory_unit: string;
  current_quantity: string;
  reorder_point_inventory_qty: string | null;
  stock_status: "NEGATIVE_STOCK" | "REORDER_DUE" | "IN_STOCK" | "NO_REORDER_POINT";
};

export type Discrepancy = {
  receipt_source_key: string | null;
  received_datetime: string;
  supplier_id: string;
  receipt_item_source_key: string | null;
  product_id: string;
  product_name: string;
  order_unit: string;
  invoice_quantity: string;
  received_quantity: string;
  damaged_quantity: string;
  accepted_quantity: string;
  wrong_item_flag: boolean;
  discrepancy_reason: string;
};

export type StocktakeAccuracy = {
  stocktake_id: number;
  source_key: string | null;
  stocktake_date: string;
  products_counted: number;
  products_matched: number;
  products_with_variance: number;
  inventory_accuracy_percent: string;
  absolute_variance_quantity: string;
};

export type DashboardData = {
  health: Health;
  kpis: Kpis;
  inventory: InventoryItem[];
  discrepancies: Discrepancy[];
  stocktakes: StocktakeAccuracy[];
};

export type ReorderRecommendation = {
  product_id: string;
  product_name: string;
  category: string;
  supplier_id: string;
  supplier_name: string;
  inventory_unit: string;
  order_unit: string;
  pack_size: string;
  current_quantity: string;
  on_order_quantity: string;
  average_daily_usage: string;
  lead_time_days: number;
  safety_stock_inventory_qty: string;
  reorder_point_inventory_qty: string | null;
  projected_on_delivery: string;
  target_inventory_quantity: string;
  recommended_order_quantity: string;
  expected_delivery_date: string;
  urgency: "CRITICAL" | "ORDER_NOW" | "REVIEW" | "PLANNED";
};

export type PosDay = {
  sale_date: string;
  menu_lines: number;
  items_sold: number;
  gross_revenue: string;
  posted_lines: number;
  pending_lines: number;
  missing_recipe_lines: number;
};

export type PosUsage = {
  sale_date: string;
  product_id: string;
  product_name: string;
  category: string;
  inventory_unit: string;
  usage_quantity: string;
  contributing_menu_items: number;
};

export type MenuItem = {
  menu_item_id: string;
  menu_item_name: string;
  menu_category: string;
  selling_price: string;
  recipe_ingredient_count: number;
};

export type PosData = {
  days: PosDay[];
  usage: PosUsage[];
  menuItems: MenuItem[];
};

export type SalesForecast = {
  forecast_date: string;
  weekday_name: string;
  forecast_items_sold: number;
  forecast_revenue: string;
  revenue_lower_bound: string;
  revenue_upper_bound: string;
  trend_factor: string;
  forecast_method: string;
};

export type InventoryForecast = {
  product_id: string;
  product_name: string;
  category: string;
  inventory_unit: string;
  supplier_id: string;
  supplier_name: string;
  lead_time_days: number;
  current_quantity: string;
  on_order_quantity: string;
  average_daily_depletion: string;
  days_of_cover: string | null;
  projected_quantity_7_days: string;
  projected_quantity_14_days: string;
  expected_stockout_date: string | null;
  risk_status: "STOCKOUT" | "CRITICAL" | "WATCH" | "HEALTHY" | "NO_USAGE";
};

export type ForecastData = {
  sales: SalesForecast[];
  inventory: InventoryForecast[];
  history: PosDay[];
};

function apiBaseUrl() {
  if (process.env.CAFE_API_URL) {
    return process.env.CAFE_API_URL.replace(/\/$/, "");
  }
  const vercelHost =
    process.env.VERCEL_PROJECT_PRODUCTION_URL ?? process.env.VERCEL_URL;
  if (vercelHost) {
    const deploymentUrl = vercelHost.replace(/\/$/, "");
    const origin = deploymentUrl.startsWith("http")
      ? deploymentUrl
      : `https://${deploymentUrl}`;
    return `${origin}/backend`;
  }
  if (process.env.BACKEND_URL) {
    const backendUrl = process.env.BACKEND_URL.replace(/\/$/, "");
    return backendUrl.endsWith("/backend") ? backendUrl : `${backendUrl}/backend`;
  }
  return "http://127.0.0.1:8010";
}

const API_URL = apiBaseUrl();

export function cafeApiUrl(path: string) {
  return `${API_URL}${path}`;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(cafeApiUrl(path), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Cafe API request failed (${response.status}): ${path}`);
  }
  return response.json() as Promise<T>;
}

export async function getReorderRecommendations(): Promise<ReorderRecommendation[]> {
  return getJson<ReorderRecommendation[]>("/api/reorder/recommendations");
}

export async function getPosData(): Promise<PosData> {
  const [days, usage, menuItems] = await Promise.all([
    getJson<PosDay[]>("/api/pos/days?limit=14"),
    getJson<PosUsage[]>("/api/pos/usage"),
    getJson<MenuItem[]>("/api/pos/menu-items"),
  ]);
  return { days, usage, menuItems };
}

export async function getForecastData(): Promise<ForecastData> {
  const [sales, inventory, history] = await Promise.all([
    getJson<SalesForecast[]>("/api/forecast/sales?days=14"),
    getJson<InventoryForecast[]>("/api/forecast/inventory"),
    getJson<PosDay[]>("/api/pos/days?limit=14"),
  ]);
  return { sales, inventory, history };
}

export async function getDashboardData(): Promise<DashboardData> {
  const [health, kpis, inventory, discrepancies, stocktakes] = await Promise.all([
    getJson<Health>("/api/health"),
    getJson<Kpis>("/api/kpis"),
    getJson<InventoryItem[]>("/api/inventory?limit=100"),
    getJson<Discrepancy[]>("/api/discrepancies?limit=8"),
    getJson<StocktakeAccuracy[]>("/api/stocktakes/accuracy?limit=8"),
  ]);

  return { health, kpis, inventory, discrepancies, stocktakes };
}
