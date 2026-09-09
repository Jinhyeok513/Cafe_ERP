import { ArrowLeft, BadgeDollarSign, CheckCircle2, Coffee, ShoppingCart } from "lucide-react";
import Link from "next/link";
import { PosImporter } from "@/components/pos-importer";
import { RefreshButton } from "@/components/refresh-button";
import { Sidebar } from "@/components/sidebar";
import { getPosData } from "@/lib/api";

export const dynamic = "force-dynamic";

const dateFormatter = new Intl.DateTimeFormat("en-AU", { day: "2-digit", month: "short", year: "numeric" });
const currencyFormatter = new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD", maximumFractionDigits: 0 });
const quantityFormatter = new Intl.NumberFormat("en-AU", { maximumFractionDigits: 3 });

export default async function PosUsagePage() {
  const { days, usage, menuItems } = await getPosData();
  const latest = days[0];
  const chartDays = [...days].reverse();
  const maxRevenue = Math.max(...chartDays.map((day) => Number(day.gross_revenue)), 1);

  return (
    <div className="app-shell">
      <Sidebar activeLabel="POS usage" />
      <main className="main-content">
        <header className="topbar">
          <div>
            <Link className="back-link" href="/"><ArrowLeft size={15} aria-hidden="true" /> Operations overview</Link>
            <h1>POS usage</h1>
          </div>
          <RefreshButton />
        </header>

        <section className="pos-summary" aria-label="Latest POS posting summary">
          <div><ShoppingCart size={18} aria-hidden="true" /><span>Items sold</span><strong>{latest?.items_sold.toLocaleString("en-AU") ?? 0}</strong></div>
          <div><BadgeDollarSign size={18} aria-hidden="true" /><span>Gross revenue</span><strong>{currencyFormatter.format(Number(latest?.gross_revenue ?? 0))}</strong></div>
          <div><Coffee size={18} aria-hidden="true" /><span>Menu lines</span><strong>{latest?.menu_lines ?? 0}</strong></div>
          <div><CheckCircle2 size={18} aria-hidden="true" /><span>Ledger status</span><strong>{latest?.pending_lines === 0 && latest?.missing_recipe_lines === 0 ? "Posted" : "Review"}</strong></div>
          <p>{latest ? dateFormatter.format(new Date(`${latest.sale_date}T00:00:00`)) : "No sales loaded"}</p>
        </section>

        <div className="pos-grid">
          <section className="panel sales-chart-panel" aria-labelledby="sales-title">
            <div className="panel-header"><div><h2 id="sales-title">Daily POS sales</h2><p>Revenue and items sold across the latest 14 days</p></div><span className="panel-count">AUD</span></div>
            <div className="sales-chart" aria-label="Daily revenue bar chart">
              {chartDays.map((day) => (
                <div className="sales-bar-column" key={day.sale_date} title={`${day.sale_date}: ${currencyFormatter.format(Number(day.gross_revenue))}`}>
                  <span className="bar-value">{currencyFormatter.format(Number(day.gross_revenue))}</span>
                  <div className="sales-bar-track"><span style={{ height: `${Math.max(8, Number(day.gross_revenue) / maxRevenue * 100)}%` }} /></div>
                  <small>{new Date(`${day.sale_date}T00:00:00`).toLocaleDateString("en-AU", { day: "2-digit" })}</small>
                </div>
              ))}
            </div>
          </section>
          <PosImporter menuItems={menuItems} />
        </div>

        <section className="panel usage-panel" aria-labelledby="usage-title">
          <div className="panel-header"><div><h2 id="usage-title">Recipe-derived inventory usage</h2><p>Ingredient consumption posted for the latest sales day</p></div><span className="panel-count">{usage.length} products</span></div>
          <div className="table-scroll">
            <table className="usage-table">
              <thead><tr><th>Ingredient</th><th>Category</th><th className="numeric">Usage</th><th className="numeric">Menu sources</th><th>Ledger</th></tr></thead>
              <tbody>
                {usage.map((item) => (
                  <tr key={item.product_id}>
                    <td><strong>{item.product_name}</strong><span className="cell-subtitle">{item.product_id}</span></td>
                    <td>{item.category}</td>
                    <td className="numeric order-quantity"><strong>{quantityFormatter.format(Number(item.usage_quantity))}</strong> {item.inventory_unit}</td>
                    <td className="numeric">{item.contributing_menu_items}</td>
                    <td><span className="status status-in_stock">USE posted</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
