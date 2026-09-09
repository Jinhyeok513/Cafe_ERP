import {
  BarChart3,
  Boxes,
  ClipboardCheck,
  FileSpreadsheet,
  LayoutDashboard,
  PackagePlus,
  ReceiptText,
  ShoppingCart,
  TrendingUp,
} from "lucide-react";

const navigation = [
  { label: "Overview", icon: LayoutDashboard, active: true },
  { label: "Inventory", icon: Boxes },
  { label: "Receiving", icon: ReceiptText },
  { label: "Stocktakes", icon: ClipboardCheck },
  { label: "Reorder", icon: PackagePlus, count: 1 },
  { label: "POS usage", icon: ShoppingCart },
  { label: "Forecast", icon: TrendingUp },
  { label: "Reports", icon: FileSpreadsheet },
];

export function Sidebar() {
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
        {navigation.map(({ label, icon: Icon, active, count }) => (
          <a key={label} className={active ? "nav-item active" : "nav-item"} href={active ? "/" : `/#${label.toLowerCase().replace(" ", "-")}`}>
            <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
            <span>{label}</span>
            {count ? <span className="nav-count">{count}</span> : null}
          </a>
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
