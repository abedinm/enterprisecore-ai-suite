import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Download, ScanBarcode, Search, Wand2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';
import { Product } from './types';

type BarcodeOut = { sku: string; barcode_value: string; png_base64: string };
type ScanResult = { found: boolean; value: string; product?: { id: string; sku: string; name: string; barcode: string | null; unit_price: number; unit_cost: number; on_hand: number; low_stock_threshold: number; }; };

export function BarcodeTab() {
  const [productId, setProductId] = useState<string>('');
  const [customValue, setCustomValue] = useState('');
  const [barcodeType, setBarcodeType] = useState<'code128' | 'ean13' | 'code39'>('code128');
  const [generated, setGenerated] = useState<BarcodeOut | null>(null);
  const [scanInput, setScanInput] = useState('');
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);

  const products = useQuery({
    queryKey: ['inventory', 'products'],
    queryFn: async () => (await api.get<Product[]>('/inventory/products')).data,
  });

  const generateForProduct = useMutation({
    mutationFn: async (id: string) => (await api.get<BarcodeOut>(`/inventory/products/${id}/barcode`)).data,
    onSuccess: (data) => { setGenerated(data); toast.success('Barcode generated'); },
    onError: () => toast.error('Generation failed'),
  });

  const generateCustom = useMutation({
    mutationFn: async () => (await api.post<BarcodeOut>(`/inventory/barcode/generate`, { value: customValue }, {
      params: { barcode_type: barcodeType },
    })).data,
    onSuccess: (data) => { setGenerated(data); toast.success('Barcode generated'); },
    onError: () => toast.error('Generation failed'),
  });

  const scan = useMutation({
    mutationFn: async () => (await api.post<ScanResult>('/inventory/barcode/scan', { value: scanInput })).data,
    onSuccess: (data) => {
      setScanResult(data);
      if (data.found) toast.success(`Found: ${data.product?.name}`);
      else toast(`No match for ${data.value}`, { icon: '❓' });
    },
  });

  function downloadBarcode() {
    if (!generated?.png_base64) return;
    const a = document.createElement('a');
    a.href = `data:image/png;base64,${generated.png_base64}`;
    a.download = `${generated.barcode_value}.png`;
    a.click();
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs uppercase tracking-wider text-ink-muted">Barcode Generator &amp; Scanner</p>
        <p className="text-sm text-ink-muted">Generate Code 128 / EAN-13 / Code 39 barcodes and scan codes to look up products.</p>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="ec-card p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Wand2 size={16} className="text-brand-600" />
            <p className="text-sm font-semibold">Generate barcode</p>
          </div>

          <div>
            <label className="ec-label">From product</label>
            <div className="flex gap-2">
              <select className="ec-input" value={productId} onChange={(e) => setProductId(e.target.value)}>
                <option value="">—</option>
                {products.data?.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}
              </select>
              <button className="ec-btn-primary" disabled={!productId || generateForProduct.isPending} onClick={() => generateForProduct.mutate(productId)}>Generate</button>
            </div>
          </div>

          <div>
            <label className="ec-label">Or custom value</label>
            <div className="grid gap-2 md:grid-cols-[1fr_140px_auto]">
              <input className="ec-input" value={customValue} onChange={(e) => setCustomValue(e.target.value)} placeholder="ABC123..." />
              <select className="ec-input" value={barcodeType} onChange={(e) => setBarcodeType(e.target.value as any)}>
                <option value="code128">Code 128</option>
                <option value="ean13">EAN-13</option>
                <option value="code39">Code 39</option>
              </select>
              <button className="ec-btn-primary" disabled={!customValue || generateCustom.isPending} onClick={() => generateCustom.mutate()}>Generate</button>
            </div>
          </div>

          {generated && (
            <div className="rounded-lg border border-border bg-surface-muted p-4 text-center">
              {generated.png_base64 ? (
                <img alt={generated.barcode_value} src={`data:image/png;base64,${generated.png_base64}`} className="mx-auto max-h-32" />
              ) : <p className="text-xs text-rose-600">PNG not available — install python-barcode for full output.</p>}
              <p className="mt-2 font-mono text-sm">{generated.barcode_value}</p>
              <p className="text-xs text-ink-muted">SKU: {generated.sku}</p>
              <button className="ec-btn-secondary mt-3" onClick={downloadBarcode}><Download size={14} /> Download PNG</button>
            </div>
          )}
        </div>

        <div className="ec-card p-4 space-y-3">
          <div className="flex items-center gap-2">
            <ScanBarcode size={16} className="text-brand-600" />
            <p className="text-sm font-semibold">Scan barcode</p>
          </div>
          <p className="text-xs text-ink-muted">Paste or type the barcode value below — the lookup matches against product barcode or SKU.</p>
          <form onSubmit={(e) => { e.preventDefault(); scan.mutate(); }} className="flex gap-2">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-subtle" />
              <input
                className="ec-input pl-8 font-mono"
                value={scanInput}
                onChange={(e) => setScanInput(e.target.value)}
                placeholder="Scan or type barcode…"
                autoFocus
              />
            </div>
            <button className="ec-btn-primary" disabled={!scanInput || scan.isPending} type="submit">Lookup</button>
          </form>

          {scanResult && (
            <div className={`rounded-lg border p-4 ${scanResult.found ? 'border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20' : 'border-rose-300 bg-rose-50 dark:bg-rose-900/20'}`}>
              {scanResult.found && scanResult.product ? (
                <div>
                  <p className="text-lg font-semibold">{scanResult.product.name}</p>
                  <p className="font-mono text-xs text-ink-muted">SKU: {scanResult.product.sku} · Barcode: {scanResult.product.barcode ?? '—'}</p>
                  <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
                    <div><p className="text-xs text-ink-muted">Price</p><p className="font-semibold">{formatCurrency(scanResult.product.unit_price)}</p></div>
                    <div><p className="text-xs text-ink-muted">Cost</p><p>{formatCurrency(scanResult.product.unit_cost)}</p></div>
                    <div><p className="text-xs text-ink-muted">On hand</p><p className={scanResult.product.on_hand <= scanResult.product.low_stock_threshold ? 'text-rose-600 font-semibold' : 'font-semibold'}>{scanResult.product.on_hand}</p></div>
                  </div>
                </div>
              ) : (
                <p className="text-sm">No product found matching <span className="font-mono">{scanResult.value}</span>.</p>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="ec-card overflow-x-auto">
        <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Products with barcodes</div>
        <table className="ec-table">
          <thead><tr><th>SKU</th><th>Name</th><th>Barcode</th><th>Type</th><th></th></tr></thead>
          <tbody>
            {products.data?.filter((p) => p.barcode).slice(0, 50).map((p) => (
              <tr key={p.id}>
                <td className="font-mono text-xs">{p.sku}</td>
                <td>{p.name}</td>
                <td className="font-mono text-xs">{p.barcode}</td>
                <td>{p.barcode_type}</td>
                <td className="text-right"><button className="ec-btn-ghost" onClick={() => { setProductId(p.id); generateForProduct.mutate(p.id); }}><Download size={14} /></button></td>
              </tr>
            ))}
            {products.data?.filter((p) => p.barcode).length === 0 && <tr><td colSpan={5} className="py-6 text-center text-ink-muted">No products have barcodes yet — set the barcode field in Catalog.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
