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

const API_URL = process.env.CAFE_API_URL ?? "http://127.0.0.1:8010";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Cafe API request failed (${response.status}): ${path}`);
  }
  return response.json() as Promise<T>;
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
