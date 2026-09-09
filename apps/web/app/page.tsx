import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  ClipboardCheck,
  PackageCheck,
  PackageSearch,
  ShieldCheck,
} from "lucide-react";
import { RefreshButton } from "@/components/refresh-button";
import { Sidebar } from "@/components/sidebar";
import { getDashboardData, type InventoryItem } from "@/lib/api";

export const dynamic = "force-dynamic";

const quantityFormatter = new Intl.NumberFormat("en-AU", { maximumFractionDigits: 3 });
const dateFormatter = new Intl.DateTimeFormat("en-AU", { day: "2-digit", month: "short", year: "numeric" });

function quantity(value: string | null) {
  return value === null ? "Not set" : quantityFormatter.format(Number(value));
}

function statusLabel(status: InventoryItem["stock_status"]) {
  return {
    NEGATIVE_STOCK: "Negative stock",
    REORDER_DUE: "Reorder due",
    IN_STOCK: "In stock",
    NO_REORDER_POINT: "Not monitored",
  }[status];
}

function reasonLabel(reason: string) {
  return reason.toLowerCase().replaceAll("_", " ").replace(/^\w/, (letter) => letter.toUpperCase());
}

export default async function DashboardPage() {
  const { health, kpis, inventory, discrepancies, stocktakes } = await getDashboardData();
  const latestStocktake = stocktakes[0];
  const reorderItems = inventory.filter((item) => item.stock_status === "REORDER_DUE" || item.stock_status === "NEGATIVE_STOCK");

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Inventory control / Overview</p>
            <h1>Operations overview</h1>
          </div>
          <div className="topbar-actions">
            <div className="connection-state">
              <span className="live-dot" aria-hidden="true" />
              <span>{health.database_connected ? "Live data" : "Offline"}</span>
              <span className="scenario-label">{health.scenario ?? "No dataset"}</span>
            </div>
            <RefreshButton />
          </div>
        </header>

        <section className="kpi-grid" aria-label="Key inventory measures">
          <article className="kpi-card">
            <div className="kpi-heading"><PackageSearch size={18} aria-hidden="true" /><span>Active products</span></div>
            <strong>{kpis.active_products}</strong>
            <p>{kpis.movement_count.toLocaleString("en-AU")} ledger movements</p>
          </article>
          <article className={kpis.reorder_due_products ? "kpi-card attention" : "kpi-card"}>
            <div className="kpi-heading"><CircleAlert size={18} aria-hidden="true" /><span>Reorder due</span></div>
            <strong>{kpis.reorder_due_products}</strong>
            <p>{kpis.negative_stock_products} negative stock items</p>
          </article>
          <article className="kpi-card">
            <div className="kpi-heading"><PackageCheck size={18} aria-hidden="true" /><span>Receiving accuracy</span></div>
            <strong>{kpis.receiving_accuracy_percent?.toFixed(1) ?? "N/A"}%</strong>
            <p>{kpis.discrepancy_lines} exceptions from {kpis.receipt_lines} lines</p>
          </article>
          <article className="kpi-card">
            <div className="kpi-heading"><ClipboardCheck size={18} aria-hidden="true" /><span>Stocktake accuracy</span></div>
            <strong>{latestStocktake ? Number(latestStocktake.inventory_accuracy_percent).toFixed(1) : "N/A"}%</strong>
            <p>{latestStocktake ? dateFormatter.format(new Date(`${latestStocktake.stocktake_date}T00:00:00`)) : "No stocktake"}</p>
          </article>
        </section>

        {reorderItems.length ? (
          <section className="action-banner" aria-label="Reorder alert">
            <span className="action-icon"><AlertTriangle size={19} aria-hidden="true" /></span>
            <div>
              <strong>{reorderItems.length} item needs an order decision</strong>
              <p>{reorderItems.map((item) => item.product_name).join(", ")} reached the reorder point.</p>
            </div>
            <a href="#reorder">Review reorder <ArrowRight size={16} aria-hidden="true" /></a>
          </section>
        ) : null}

        <div className="dashboard-grid">
          <section className="panel inventory-panel" aria-labelledby="inventory-title">
            <div className="panel-header">
              <div><h2 id="inventory-title">Current inventory</h2><p>Stock-unit balances from the movement ledger</p></div>
              <span className="panel-count">{inventory.length} products</span>
            </div>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Product</th><th>Category</th><th className="numeric">On hand</th><th className="numeric">Reorder at</th><th>Status</th></tr></thead>
                <tbody>
                  {inventory.map((item) => (
                    <tr key={item.product_id}>
                      <td><strong>{item.product_name}</strong><span className="cell-subtitle">{item.product_id}</span></td>
                      <td>{item.category}</td>
                      <td className="numeric quantity-cell"><strong>{quantity(item.current_quantity)}</strong><span>{item.inventory_unit}</span></td>
                      <td className="numeric">{quantity(item.reorder_point_inventory_qty)}</td>
                      <td><span className={`status status-${item.stock_status.toLowerCase()}`}>{statusLabel(item.stock_status)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel accuracy-panel" aria-labelledby="accuracy-title">
            <div className="panel-header">
              <div><h2 id="accuracy-title">Stocktake accuracy</h2><p>Most recent physical counts</p></div>
              <ShieldCheck size={20} aria-hidden="true" />
            </div>
            <div className="accuracy-list">
              {stocktakes.map((stocktake) => {
                const accuracy = Number(stocktake.inventory_accuracy_percent);
                return (
                  <div className="accuracy-row" key={stocktake.stocktake_id}>
                    <div className="accuracy-meta"><span>{dateFormatter.format(new Date(`${stocktake.stocktake_date}T00:00:00`))}</span><strong>{accuracy.toFixed(1)}%</strong></div>
                    <div className="accuracy-track"><span style={{ width: `${accuracy}%` }} /></div>
                    <p>{stocktake.products_with_variance ? `${stocktake.products_with_variance} variance` : "All products matched"}</p>
                  </div>
                );
              })}
            </div>
            <div className="quality-footer">
              {kpis.data_quality_issue_count === 0 ? <CheckCircle2 size={17} aria-hidden="true" /> : <CircleAlert size={17} aria-hidden="true" />}
              <span>{kpis.data_quality_issue_count === 0 ? "No data quality issues" : `${kpis.data_quality_issue_count} data quality issues`}</span>
            </div>
          </section>
        </div>

        <section className="panel exception-panel" aria-labelledby="exceptions-title">
          <div className="panel-header">
            <div><h2 id="exceptions-title">Receiving exceptions</h2><p>Latest short, missing, and incorrect deliveries</p></div>
            <span className="panel-count">{kpis.discrepancy_lines} total</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Received</th><th>Product</th><th>Supplier</th><th className="numeric">Invoiced</th><th className="numeric">Accepted</th><th>Reason</th></tr></thead>
              <tbody>
                {discrepancies.map((item) => (
                  <tr key={item.receipt_item_source_key}>
                    <td>{dateFormatter.format(new Date(item.received_datetime))}</td>
                    <td><strong>{item.product_name}</strong></td>
                    <td>{item.supplier_id}</td>
                    <td className="numeric">{quantity(item.invoice_quantity)} {item.order_unit}</td>
                    <td className="numeric">{quantity(item.accepted_quantity)} {item.order_unit}</td>
                    <td><span className="reason-badge">{reasonLabel(item.discrepancy_reason)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <footer className="content-footer">
          <span>Dataset imported {health.imported_at ? dateFormatter.format(new Date(health.imported_at)) : "not available"}</span>
          <span>Stock quantities follow each product&apos;s inventory unit.</span>
        </footer>
      </main>
    </div>
  );
}
