import { ArrowLeft, CalendarDays, Clock3, PackagePlus, TrendingDown } from "lucide-react";
import Link from "next/link";
import { DraftOrderButton } from "@/components/draft-order-button";
import { RefreshButton } from "@/components/refresh-button";
import { Sidebar } from "@/components/sidebar";
import { getReorderRecommendations, type ReorderRecommendation } from "@/lib/api";

export const dynamic = "force-dynamic";

const numberFormatter = new Intl.NumberFormat("en-AU", { maximumFractionDigits: 3 });
const dateFormatter = new Intl.DateTimeFormat("en-AU", { weekday: "short", day: "2-digit", month: "short" });

function number(value: string) {
  return numberFormatter.format(Number(value));
}

function urgencyLabel(urgency: ReorderRecommendation["urgency"]) {
  return { CRITICAL: "Critical", ORDER_NOW: "Order now", REVIEW: "Review", PLANNED: "Planned" }[urgency];
}

export default async function ReorderPage() {
  const recommendations = await getReorderRecommendations();
  const groups = Map.groupBy(recommendations, (item) => `${item.supplier_id}|${item.expected_delivery_date}`);
  const urgentCount = recommendations.filter((item) => item.urgency === "CRITICAL" || item.urgency === "ORDER_NOW").length;
  const supplierCount = new Set(recommendations.map((item) => item.supplier_id)).size;

  return (
    <div className="app-shell">
      <Sidebar activeLabel="Reorder" reorderCount={urgentCount} />
      <main className="main-content">
        <header className="topbar">
          <div>
            <Link className="back-link" href="/"><ArrowLeft size={15} aria-hidden="true" /> Operations overview</Link>
            <h1>Reorder planning</h1>
          </div>
          <RefreshButton />
        </header>

        <section className="reorder-summary" aria-label="Reorder plan summary">
          <div><span>Recommended lines</span><strong>{recommendations.length}</strong></div>
          <div><span>Order now</span><strong>{urgentCount}</strong></div>
          <div><span>Suppliers</span><strong>{supplierCount}</strong></div>
          <p><TrendingDown size={17} aria-hidden="true" /> Uses the last 14 trading days of POS usage and waste.</p>
        </section>

        <div className="reorder-groups">
          {[...groups.entries()].map(([key, items]) => {
            const first = items[0];
            return (
              <section className="panel reorder-panel" key={key}>
                <div className="reorder-panel-header">
                  <div className="supplier-heading">
                    <span className="supplier-icon"><PackagePlus size={18} aria-hidden="true" /></span>
                    <div><h2>{first.supplier_name}</h2><p>{first.supplier_id} · {items.length} order {items.length === 1 ? "line" : "lines"}</p></div>
                  </div>
                  <div className="delivery-meta">
                    <span><CalendarDays size={15} aria-hidden="true" /> {dateFormatter.format(new Date(`${first.expected_delivery_date}T00:00:00`))}</span>
                    <span><Clock3 size={15} aria-hidden="true" /> {first.lead_time_days} day lead</span>
                  </div>
                  <DraftOrderButton
                    supplierId={first.supplier_id}
                    expectedDeliveryDate={first.expected_delivery_date}
                    items={items.map((item) => ({ product_id: item.product_id, ordered_quantity: item.recommended_order_quantity }))}
                  />
                </div>
                <div className="table-scroll">
                  <table className="reorder-table">
                    <thead><tr><th>Product</th><th className="numeric">On hand</th><th className="numeric">Daily use</th><th className="numeric">At delivery</th><th className="numeric">Order</th><th>Priority</th></tr></thead>
                    <tbody>
                      {items.map((item) => (
                        <tr key={item.product_id}>
                          <td><strong>{item.product_name}</strong><span className="cell-subtitle">Safety {number(item.safety_stock_inventory_qty)} {item.inventory_unit}</span><span className={`mobile-urgency urgency-${item.urgency.toLowerCase()}`}>{urgencyLabel(item.urgency)}</span></td>
                          <td className="numeric quantity-cell"><strong>{number(item.current_quantity)}</strong><span>{item.inventory_unit}</span></td>
                          <td className="numeric">{number(item.average_daily_usage)} <span className="unit-inline">{item.inventory_unit}</span></td>
                          <td className={Number(item.projected_on_delivery) < 0 ? "numeric negative" : "numeric"}>{number(item.projected_on_delivery)} <span className="unit-inline">{item.inventory_unit}</span></td>
                          <td className="numeric order-quantity"><strong>{number(item.recommended_order_quantity)}</strong> {item.order_unit}</td>
                          <td><span className={`urgency urgency-${item.urgency.toLowerCase()}`}>{urgencyLabel(item.urgency)}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            );
          })}
        </div>

        <section className="calculation-note">
          <h2>Calculation basis</h2>
          <p>Projected stock at delivery = current stock + open orders - average daily usage × supplier lead time. Recommended quantities include the review period and safety stock, then round up to the product&apos;s order unit.</p>
        </section>
      </main>
    </div>
  );
}
