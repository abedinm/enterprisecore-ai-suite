import { useState } from 'react';
import {
  AlertTriangle, BarChart3, Boxes, ClipboardList, Gauge, Package,
  PackageCheck, RotateCcw, ScanBarcode, ShoppingCart, Truck, Warehouse as WarehouseIcon,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { StockManagerTab } from './StockManagerTab';
import { PurchaseOrdersTab } from './PurchaseOrdersTab';
import { SuppliersTab } from './SuppliersTab';
import { WarehouseTab } from './WarehouseTab';
import { AlertsTab } from './AlertsTab';
import { BarcodeTab } from './BarcodeTab';
import { ShipmentsTab } from './ShipmentsTab';
import { CatalogTab } from './CatalogTab';
import { ReturnsTab } from './ReturnsTab';
import { InventoryAnalyticsTab } from './InventoryAnalyticsTab';

type TabKey =
  | 'analytics' | 'stock' | 'po' | 'suppliers' | 'warehouse'
  | 'alerts' | 'barcode' | 'shipments' | 'catalog' | 'returns';

const tabs: { key: TabKey; label: string; icon: typeof Package }[] = [
  { key: 'analytics', label: 'Analytics', icon: Gauge },
  { key: 'stock', label: 'Stock Manager', icon: Boxes },
  { key: 'catalog', label: 'Catalog', icon: ClipboardList },
  { key: 'po', label: 'Purchase Orders', icon: ShoppingCart },
  { key: 'suppliers', label: 'Suppliers', icon: PackageCheck },
  { key: 'warehouse', label: 'Warehouses', icon: WarehouseIcon },
  { key: 'alerts', label: 'Alerts', icon: AlertTriangle },
  { key: 'barcode', label: 'Barcode', icon: ScanBarcode },
  { key: 'shipments', label: 'Shipments', icon: Truck },
  { key: 'returns', label: 'Returns', icon: RotateCcw },
];

export function InventoryPage() {
  const [active, setActive] = useState<TabKey>('analytics');
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Module workspace</p>
        <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
          <Boxes className="text-brand-600" size={26} />
          Inventory &amp; Supply Chain
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          10 fully-offline operations tools — stock manager, purchase orders, suppliers, warehouses,
          low-stock alerts, barcode generator &amp; scanner, shipment tracker, product catalog, returns,
          and inventory analytics.
        </p>
      </div>
      <div className="ec-card overflow-hidden">
        <div className="flex flex-wrap gap-1 border-b border-border bg-surface-muted px-2 py-2">
          {tabs.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.key}
                onClick={() => setActive(t.key)}
                className={cn(
                  'flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition',
                  active === t.key
                    ? 'bg-brand-600 text-white shadow-sm'
                    : 'text-ink-muted hover:bg-surface-elevated hover:text-ink',
                )}
              >
                <Icon size={15} /> {t.label}
              </button>
            );
          })}
        </div>
        <div className="p-5">
          {active === 'analytics' && <InventoryAnalyticsTab />}
          {active === 'stock' && <StockManagerTab />}
          {active === 'catalog' && <CatalogTab />}
          {active === 'po' && <PurchaseOrdersTab />}
          {active === 'suppliers' && <SuppliersTab />}
          {active === 'warehouse' && <WarehouseTab />}
          {active === 'alerts' && <AlertsTab />}
          {active === 'barcode' && <BarcodeTab />}
          {active === 'shipments' && <ShipmentsTab />}
          {active === 'returns' && <ReturnsTab />}
        </div>
      </div>
    </div>
  );
}
