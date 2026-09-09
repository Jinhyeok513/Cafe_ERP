import { ArrowLeft, ArrowRight, ArrowUpRight, ChartNoAxesCombined, Coffee, Database, FileSpreadsheet, Github, LayoutDashboard, PackageCheck, PackagePlus, ShoppingCart, TrendingUp, Upload } from "lucide-react";
import Link from "next/link";
import { Sidebar } from "@/components/sidebar";

const gallery = [
  { title: "Operations dashboard", description: "Live balances, reorder attention, receiving exceptions and stocktake accuracy.", href: "/", icon: LayoutDashboard },
  { title: "Replenishment planning", description: "Supplier schedules, consumption-based quantities and draft purchase orders.", href: "/reorder", icon: PackagePlus },
  { title: "POS usage", description: "Validated CSV posting with recipe-derived immutable inventory movements.", href: "/pos-usage", icon: Upload },
  { title: "Demand forecast", description: "Explainable weekday revenue baseline and projected inventory depletion risk.", href: "/forecast", icon: ChartNoAxesCombined },
] as const;

export default function PortfolioPage() {
  return (
    <div className="app-shell">
      <Sidebar activeLabel="Case study" />
      <main className="main-content">
        <header className="topbar">
          <div>
            <Link className="back-link" href="/"><ArrowLeft size={15} aria-hidden="true" /> Operations overview</Link>
            <h1>Cafe ERP case study</h1>
          </div>
        </header>

        <section className="portfolio-summary" aria-label="Project delivery summary">
          <div><span>Operational history</span><strong>30 days</strong></div>
          <div><span>Inventory products</span><strong>9 products</strong></div>
          <div><span>Automated verification</span><strong>26 Python tests</strong></div>
          <div><span>Excel delivery</span><strong>9 worksheets</strong></div>
        </section>

        <section className="portfolio-story">
          <h2>Operating problem</h2>
          <p>Cafe stock was counted and ordered in familiar package units, while recipes consumed physical quantities. The system separates those concepts so managers continue to work in bottles, cartons, bags and individual items while recipe conversions remain accurate. Purchasing, receiving, POS use, waste and stocktake corrections all meet in one traceable inventory ledger.</p>
        </section>

        <section className="panel portfolio-section" aria-labelledby="architecture-title">
          <div className="panel-header"><div><h2 id="architecture-title">System flow</h2><p>One signed movement model from source operations to management decisions</p></div></div>
          <div className="architecture-flow">
            <div className="architecture-node"><ShoppingCart size={20} aria-hidden="true" /><strong>POS & purchasing</strong><span>Operational sources</span></div>
            <ArrowRight className="architecture-arrow" size={17} aria-hidden="true" />
            <div className="architecture-node"><Coffee size={20} aria-hidden="true" /><strong>FastAPI</strong><span>Validation and posting</span></div>
            <ArrowRight className="architecture-arrow" size={17} aria-hidden="true" />
            <div className="architecture-node"><Database size={20} aria-hidden="true" /><strong>PostgreSQL ledger</strong><span>Immutable movements</span></div>
            <ArrowRight className="architecture-arrow" size={17} aria-hidden="true" />
            <div className="architecture-node"><TrendingUp size={20} aria-hidden="true" /><strong>Decision outputs</strong><span>Dashboard, forecast, Excel</span></div>
          </div>
        </section>

        <section className="portfolio-section" aria-labelledby="screens-title">
          <div className="portfolio-section-heading"><h2 id="screens-title">Delivered operations</h2><p>Validated against the PostgreSQL synthetic error scenario</p></div>
          <div className="portfolio-gallery">
            {gallery.map((item) => {
              const Icon = item.icon;
              return (
              <article className="portfolio-shot" key={item.title}>
                <Link href={item.href}>
                  <div className="portfolio-shot-image" aria-hidden="true"><Icon size={36} strokeWidth={1.5} /><div className="module-lines"><span /><span /><span /></div></div>
                  <div className="portfolio-shot-copy"><strong>{item.title}</strong><p>{item.description}</p><ArrowUpRight size={17} aria-hidden="true" /></div>
                </Link>
              </article>
            )})}
          </div>
        </section>

        <section className="panel portfolio-section" aria-labelledby="decisions-title">
          <div className="panel-header"><div><h2 id="decisions-title">Key design decisions</h2><p>Operational fidelity, auditability and explainable outputs</p></div><PackageCheck size={18} aria-hidden="true" /></div>
          <div className="table-scroll">
            <table className="portfolio-decisions">
              <thead><tr><th>Decision</th><th>Implementation</th><th>Operational value</th></tr></thead>
              <tbody>
                <tr><td><strong>Human stock units</strong></td><td>Milk in bottle/carton, beans in bag, eggs in each</td><td>Counts and orders match real manager language</td></tr>
                <tr><td><strong>Immutable ledger</strong></td><td>RECEIVE positive; USE and WASTE negative; corrections as ADJUSTMENT</td><td>Every balance is reproducible and auditable</td></tr>
                <tr><td><strong>Receiving exceptions</strong></td><td>Short delivery, missing item and wrong product drive synthetic errors</td><td>Accepted quantity alone reaches stock</td></tr>
                <tr><td><strong>Explainable forecast</strong></td><td>Weekday baseline with a bounded recent trend</td><td>Useful prototype without overstating model certainty</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <div className="portfolio-links">
          <a className="secondary-button" href="https://github.com/Jinhyeok513/Cafe_ERP" target="_blank" rel="noreferrer"><Github size={16} aria-hidden="true" /> GitHub repository <ArrowUpRight size={14} aria-hidden="true" /></a>
          <Link className="primary-button" href="/reports"><FileSpreadsheet size={16} aria-hidden="true" /> Excel report design</Link>
        </div>
      </main>
    </div>
  );
}
