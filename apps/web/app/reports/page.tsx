import { ArrowLeft, Calculator, Database, FileSpreadsheet, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { Sidebar } from "@/components/sidebar";

const sheets = [
  ["Summary", "KPIs, priority orders and the 14-day revenue outlook"],
  ["Reorder", "Supplier plans, current stock and recommended quantities"],
  ["POS Daily", "Posted daily sales, revenue and item counts"],
  ["Sales Forecast", "30-day weekday baseline with confidence bounds"],
  ["Inventory Forecast", "Depletion, incoming stock and risk status"],
  ["Receiving", "Short delivery, missing item and wrong item exceptions"],
  ["Stocktakes", "Daily count accuracy and absolute variance"],
  ["Inventory", "Current quantity, units and reorder status"],
  ["Ledger", "Signed immutable inventory movements with source traceability"],
] as const;

export default async function ReportsPage() {
  return (
    <div className="app-shell">
      <Sidebar activeLabel="Reports" />
      <main className="main-content">
        <header className="topbar">
          <div>
            <Link className="back-link" href="/"><ArrowLeft size={15} aria-hidden="true" /> Operations overview</Link>
            <h1>Excel operations report</h1>
          </div>
        </header>

        <section className="report-summary" aria-label="Report file summary">
          <div><FileSpreadsheet size={19} aria-hidden="true" /><span>Workbook</span><strong>Cafe ERP Operations</strong></div>
          <div><Database size={19} aria-hidden="true" /><span>Worksheets</span><strong>{sheets.length} operational views</strong></div>
          <div><ShieldCheck size={19} aria-hidden="true" /><span>Validation</span><strong>0 formula errors</strong></div>
        </section>

        <div className="report-layout">
          <section className="panel" aria-labelledby="report-preview-title">
            <div className="panel-header"><div><h2 id="report-preview-title">Report controls</h2><p>Quality checks applied to the generated workbook</p></div><Calculator size={18} aria-hidden="true" /></div>
            <div className="sheet-list">
              <div className="sheet-item"><strong>Formula calculation</strong><span>Summary KPIs recalculate from detail-sheet references before export.</span></div>
              <div className="sheet-item"><strong>Error scan</strong><span>Workbook cells are checked for reference, value, name and calculation errors.</span></div>
              <div className="sheet-item"><strong>Native value types</strong><span>Dates, quantities, percentages and AUD currency remain sortable Excel values.</span></div>
              <div className="sheet-item"><strong>Operational units</strong><span>Inventory remains in bottle, carton, bag or each according to Product Master.</span></div>
              <div className="sheet-item"><strong>Table filters</strong><span>Every detail dataset is formatted as a filterable Excel table.</span></div>
              <div className="sheet-item"><strong>Frozen headers</strong><span>Column headings remain visible across long operational ledgers.</span></div>
            </div>
          </section>

          <section className="panel" aria-labelledby="worksheet-title">
            <div className="panel-header"><div><h2 id="worksheet-title">Workbook contents</h2><p>Native dates, quantities and AUD currency values</p></div></div>
            <div className="sheet-list">
              {sheets.map(([name, description]) => <div className="sheet-item" key={name}><strong>{name}</strong><span>{description}</span></div>)}
            </div>
          </section>
        </div>

        <p className="report-note">The validated workbook is generated as a local operational artifact. Public deployment exposes this report definition without publishing the underlying workbook data.</p>
      </main>
    </div>
  );
}
