import {
  BarChart3,
  BriefcaseBusiness,
  Boxes,
  ClipboardCheck,
  FileSpreadsheet,
  LayoutDashboard,
  PackagePlus,
  ReceiptText,
  ShoppingCart,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";

const navigation = [
  { label: "Overview", icon: LayoutDashboard, href: "/" },
  { label: "Inventory", icon: Boxes, href: "/#inventory-title" },
  { label: "Receiving", icon: ReceiptText, href: "/#exceptions-title" },
  { label: "Stocktakes", icon: ClipboardCheck, href: "/#accuracy-title" },
  { label: "Reorder", icon: PackagePlus, href: "/reorder" },
  { label: "POS usage", icon: ShoppingCart, href: "/pos-usage" },
  { label: "Forecast", icon: TrendingUp, href: "/forecast" },
  { label: "Reports", icon: FileSpreadsheet, href: "/reports" },
  { label: "Case study", icon: BriefcaseBusiness, href: "/portfolio" },
];

export function Sidebar({ activeLabel = "Overview", reorderCount = 0 }: { activeLabel?: string; reorderCount?: number }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true"><BarChart3 size={19} /></span>
        <div>
          <strong>Cafe ERP</strong>
          <span>Operations</span>
        </div>
      </div>
      <nav aria-label="Main navigation">
        {navigation.map(({ label, icon: Icon, href }) => (
          <Link key={label} className={label === activeLabel ? "nav-item active" : "nav-item"} href={href}>
            <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
            <span>{label}</span>
            {label === "Reorder" && reorderCount ? <span className="nav-count">{reorderCount}</span> : null}
          </Link>
        ))}
      </nav>
      <div className="sidebar-footer">
        <span className="avatar" aria-hidden="true">JM</span>
        <div>
          <strong>Jin Manager</strong>
          <span>Store manager</span>
        </div>
      </div>
    </aside>
  );
}
