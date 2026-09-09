import { ArrowLeft, CalendarRange, ChartNoAxesCombined, CircleAlert, PackageOpen } from "lucide-react";
import Link from "next/link";
import { RefreshButton } from "@/components/refresh-button";
import { Sidebar } from "@/components/sidebar";
import { getForecastData, type InventoryForecast } from "@/lib/api";

export const dynamic = "force-dynamic";

const currency = new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD", maximumFractionDigits: 0 });
const quantity = new Intl.NumberFormat("en-AU", { maximumFractionDigits: 2 });
const shortDate = new Intl.DateTimeFormat("en-AU", { day: "2-digit", month: "short" });

function riskLabel(status: InventoryForecast["risk_status"]) {
  return { STOCKOUT: "Stockout", CRITICAL: "Critical", WATCH: "Watch", HEALTHY: "Healthy", NO_USAGE: "No usage" }[status];
}

export default async function ForecastPage() {
  const { sales, inventory, history } = await getForecastData();
  const forecastRevenue = sales.reduce((total, day) => total + Number(day.forecast_revenue), 0);
  const forecastItems = sales.reduce((total, day) => total + day.forecast_items_sold, 0);
  const historicalDailyAverage = history.reduce((total, day) => total + Number(day.gross_revenue), 0) / Math.max(history.length, 1);
  const forecastDailyAverage = forecastRevenue / Math.max(sales.length, 1);
  const change = historicalDailyAverage ? (forecastDailyAverage / historicalDailyAverage - 1) * 100 : 0;
  const riskCount = inventory.filter((item) => item.risk_status === "STOCKOUT" || item.risk_status === "CRITICAL" || item.risk_status === "WATCH").length;
  const maxRevenue = Math.max(...sales.map((day) => Number(day.revenue_upper_bound)), 1);

  return (
    <div className="app-shell">
      <Sidebar activeLabel="Forecast" />
      <main className="main-content">
        <header className="topbar">
          <div>
            <Link className="back-link" href="/"><ArrowLeft size={15} aria-hidden="true" /> Operations overview</Link>
            <h1>Demand forecast</h1>
          </div>
          <RefreshButton />
        </header>

        <section className="forecast-summary" aria-label="Fourteen day forecast summary">
          <div><CalendarRange size={18} aria-hidden="true" /><span>14-day revenue</span><strong>{currency.format(forecastRevenue)}</strong></div>
          <div><ChartNoAxesCombined size={18} aria-hidden="true" /><span>Expected items</span><strong>{forecastItems.toLocaleString("en-AU")}</strong></div>
          <div><PackageOpen size={18} aria-hidden="true" /><span>Daily revenue trend</span><strong className={change < 0 ? "negative" : "positive"}>{change >= 0 ? "+" : ""}{change.toFixed(1)}%</strong></div>
          <div><CircleAlert size={18} aria-hidden="true" /><span>At-risk stock</span><strong>{riskCount}</strong></div>
        </section>

        <section className="panel forecast-chart-panel" aria-labelledby="forecast-chart-title">
          <div className="panel-header">
            <div><h2 id="forecast-chart-title">Revenue outlook</h2><p>Weekday baseline with capped recent trend and observed variance</p></div>
            <div className="chart-legend"><span><i className="legend-range" /> Range</span><span><i className="legend-point" /> Forecast</span></div>
          </div>
          <div className="forecast-chart" aria-label="Fourteen-day revenue forecast with confidence ranges">
            {sales.map((day) => {
              const lower = Number(day.revenue_lower_bound) / maxRevenue * 100;
              const upper = Number(day.revenue_upper_bound) / maxRevenue * 100;
              const predicted = Number(day.forecast_revenue) / maxRevenue * 100;
              return (
                <div className="forecast-column" key={day.forecast_date} title={`${day.forecast_date}: ${currency.format(Number(day.forecast_revenue))}`}>
                  <strong>{currency.format(Number(day.forecast_revenue))}</strong>
                  <div className="forecast-track">
                    <span className="forecast-range" style={{ bottom: `${lower}%`, height: `${Math.max(3, upper - lower)}%` }} />
                    <span className="forecast-point" style={{ bottom: `${predicted}%` }} />
                  </div>
                  <small>{day.weekday_name}<b>{new Date(`${day.forecast_date}T00:00:00`).getDate()}</b></small>
                </div>
              );
            })}
          </div>
        </section>

        <section className="panel depletion-panel" aria-labelledby="depletion-title">
          <div className="panel-header"><div><h2 id="depletion-title">Inventory depletion</h2><p>Projected from recent POS usage, waste and open purchase orders</p></div><span className="panel-count">{inventory.length} products</span></div>
          <div className="table-scroll">
            <table className="forecast-table">
              <thead><tr><th>Product</th><th className="numeric">On hand</th><th className="numeric">Daily depletion</th><th className="numeric">Days cover</th><th className="numeric">7-day stock</th><th>Expected stockout</th><th>Risk</th></tr></thead>
              <tbody>
                {inventory.map((item) => (
                  <tr key={item.product_id}>
                    <td><strong>{item.product_name}</strong><span className="cell-subtitle">{item.supplier_name}</span></td>
                    <td className="numeric quantity-cell"><strong>{quantity.format(Number(item.current_quantity))}</strong><span>{item.inventory_unit}</span></td>
                    <td className="numeric">{quantity.format(Number(item.average_daily_depletion))}</td>
                    <td className="numeric"><strong>{item.days_of_cover ?? "N/A"}</strong></td>
                    <td className={Number(item.projected_quantity_7_days) < 0 ? "numeric negative" : "numeric"}>{quantity.format(Number(item.projected_quantity_7_days))}</td>
                    <td>{item.expected_stockout_date ? shortDate.format(new Date(`${item.expected_stockout_date}T00:00:00`)) : "Not projected"}</td>
                    <td><span className={`risk risk-${item.risk_status.toLowerCase()}`}>{riskLabel(item.risk_status)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <footer className="content-footer"><span>Method: weekday average × capped 7-day trend factor</span><span>Baseline forecast; retrain after real operating history is available.</span></footer>
      </main>
    </div>
  );
}
