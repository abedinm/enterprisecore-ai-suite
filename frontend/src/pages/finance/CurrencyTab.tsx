import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Plus, Trash2, ArrowRightLeft, Banknote } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDate } from '../../lib/utils';

type Rate = { id: string; base_currency: string; quote_currency: string; rate: string; effective_date: string };
type ConvOut = { amount: string; converted: string; rate: string; from_currency: string; to_currency: string; as_of: string };

export function CurrencyTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['finance', 'currency', 'rates'],
    queryFn: async () => (await api.get<Rate[]>('/finance/currency/rates')).data,
  });

  const [base, setBase] = useState('USD');
  const [quote, setQuote] = useState('EUR');
  const [rate, setRate] = useState(0.92);
  const [effective, setEffective] = useState(new Date().toISOString().slice(0, 10));

  const [convFrom, setConvFrom] = useState('USD');
  const [convTo, setConvTo] = useState('EUR');
  const [convAmount, setConvAmount] = useState(100);
  const [conv, setConv] = useState<ConvOut | null>(null);

  const [search, setSearch] = useState('');

  const saveRate = useMutation({
    mutationFn: async () => (await api.post('/finance/currency/rates', {
      base_currency: base, quote_currency: quote, rate, effective_date: effective,
    })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['finance', 'currency', 'rates'] }),
  });
  const removeRate = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/finance/currency/rates/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['finance', 'currency', 'rates'] }),
  });
  const convert = useMutation({
    mutationFn: async () => (await api.post<ConvOut>('/finance/currency/convert', {
      amount: convAmount, from_currency: convFrom, to_currency: convTo,
    })).data,
    onSuccess: (d) => setConv(d),
  });

  const filtered = useMemo(() => {
    const term = search.toUpperCase();
    return (data ?? []).filter((r) => !term || r.base_currency.includes(term) || r.quote_currency.includes(term));
  }, [data, search]);

  const pairs = useMemo(() => {
    const seen = new Set<string>();
    return (data ?? []).filter((r) => {
      const k = `${r.base_currency}-${r.quote_currency}`;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
  }, [data]);

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="ec-card p-5 space-y-3">
          <p className="flex items-center gap-2 text-sm font-semibold"><Banknote size={16} />Add or update exchange rate</p>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="ec-label">From</label><input className="ec-input" maxLength={3} value={base} onChange={(e) => setBase(e.target.value.toUpperCase())} /></div>
            <div><label className="ec-label">To</label><input className="ec-input" maxLength={3} value={quote} onChange={(e) => setQuote(e.target.value.toUpperCase())} /></div>
            <div><label className="ec-label">Rate</label><input type="number" step="0.000001" className="ec-input" value={rate} onChange={(e) => setRate(Number(e.target.value))} /></div>
            <div><label className="ec-label">Effective date</label><input type="date" className="ec-input" value={effective} onChange={(e) => setEffective(e.target.value)} /></div>
          </div>
          <button className="ec-btn-primary w-full" onClick={() => saveRate.mutate()} disabled={saveRate.isPending}>
            <Plus size={16} />{saveRate.isPending ? 'Saving…' : 'Save rate'}
          </button>
          <p className="text-xs text-ink-muted">Tip: rates are stored offline. Triangulation via USD is automatic.</p>
        </div>

        <div className="ec-card p-5 space-y-3">
          <p className="flex items-center gap-2 text-sm font-semibold"><ArrowRightLeft size={16} />Convert</p>
          <div className="grid grid-cols-3 gap-3">
            <div><label className="ec-label">Amount</label><input type="number" step="any" className="ec-input" value={convAmount} onChange={(e) => setConvAmount(Number(e.target.value))} /></div>
            <div><label className="ec-label">From</label><input className="ec-input" maxLength={3} value={convFrom} onChange={(e) => setConvFrom(e.target.value.toUpperCase())} /></div>
            <div><label className="ec-label">To</label><input className="ec-input" maxLength={3} value={convTo} onChange={(e) => setConvTo(e.target.value.toUpperCase())} /></div>
          </div>
          <button className="ec-btn-primary w-full" onClick={() => convert.mutate()} disabled={convert.isPending}>
            {convert.isPending ? 'Converting…' : 'Convert'}
          </button>
          {conv && (
            <div className="rounded-lg border border-border bg-surface-muted p-3 text-sm">
              <p>{conv.amount} <strong>{conv.from_currency}</strong> = <strong className="text-brand-600">{conv.converted} {conv.to_currency}</strong></p>
              <p className="mt-1 text-xs text-ink-muted">Rate {conv.rate} · effective {formatDate(conv.as_of)}</p>
            </div>
          )}
        </div>
      </div>

      <div className="ec-card p-3 grid gap-3 md:grid-cols-4">
        {pairs.slice(0, 4).map((r) => (
          <div key={r.id} className="rounded-lg border border-border bg-surface-muted p-3">
            <p className="text-xs text-ink-muted">{r.base_currency} / {r.quote_currency}</p>
            <p className="mt-1 text-lg font-semibold">{parseFloat(r.rate).toFixed(4)}</p>
            <p className="text-xs text-ink-muted">{formatDate(r.effective_date)}</p>
          </div>
        ))}
      </div>

      <div className="ec-card overflow-hidden">
        <div className="border-b border-border bg-surface-muted p-3 flex items-center justify-between gap-3">
          <p className="text-sm font-semibold">All exchange rates ({data?.length ?? 0})</p>
          <input className="ec-input !w-48" placeholder="Search USD, EUR…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <table className="ec-table">
          <thead><tr><th>Base</th><th>Quote</th><th>Rate</th><th>Effective</th><th></th></tr></thead>
          <tbody>
            {filtered.length ? filtered.map((r) => (
              <tr key={r.id}>
                <td className="font-medium">{r.base_currency}</td>
                <td>{r.quote_currency}</td>
                <td>{parseFloat(r.rate).toFixed(6)}</td>
                <td>{formatDate(r.effective_date)}</td>
                <td className="text-right">
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete rate?')) removeRate.mutate(r.id); }}><Trash2 size={16} /></button>
                </td>
              </tr>
            )) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No rates match.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
