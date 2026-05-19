import { useState } from 'react';
import {
  Banknote, BarChart3, Calculator, FileText, Gauge, History, Landmark,
  LineChart, PiggyBank, Receipt, Repeat, ScrollText, TrendingUp, Truck, Wallet,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { InvoicesTab } from './InvoicesTab';
import { ExpensesTab } from './ExpensesTab';
import { PayrollTab } from './PayrollTab';
import { TaxTab } from './TaxTab';
import { BudgetsTab } from './BudgetsTab';
import { PnLTab } from './PnLTab';
import { BalanceSheetTab } from './BalanceSheetTab';
import { CashFlowTab } from './CashFlowTab';
import { ForecastTab } from './ForecastTab';
import { CurrencyTab } from './CurrencyTab';
import { RecurringTab } from './RecurringTab';
import { VendorPaymentsTab } from './VendorPaymentsTab';
import { AuditTab } from './AuditTab';
import { MultiCurrencyTab } from './MultiCurrencyTab';
import { DashboardTab } from './DashboardTab';

type TabKey =
  | 'dashboard' | 'invoices' | 'expenses' | 'payroll' | 'tax'
  | 'budgets' | 'pnl' | 'balance' | 'cashflow' | 'forecast'
  | 'currency' | 'recurring' | 'vendors' | 'audit' | 'multicurrency';

const tabs: { key: TabKey; label: string; icon: typeof FileText; group: string }[] = [
  { key: 'dashboard', label: 'Dashboard', icon: Gauge, group: 'overview' },
  { key: 'invoices', label: 'Invoices', icon: FileText, group: 'transactions' },
  { key: 'expenses', label: 'Expenses', icon: Receipt, group: 'transactions' },
  { key: 'payroll', label: 'Payroll', icon: Wallet, group: 'transactions' },
  { key: 'tax', label: 'Tax', icon: Calculator, group: 'transactions' },
  { key: 'budgets', label: 'Budgets', icon: PiggyBank, group: 'planning' },
  { key: 'pnl', label: 'P&L', icon: BarChart3, group: 'reports' },
  { key: 'balance', label: 'Balance Sheet', icon: Landmark, group: 'reports' },
  { key: 'cashflow', label: 'Cash Flow', icon: LineChart, group: 'reports' },
  { key: 'forecast', label: 'Forecast', icon: TrendingUp, group: 'reports' },
  { key: 'currency', label: 'Currency', icon: Banknote, group: 'utilities' },
  { key: 'multicurrency', label: 'Multi-Currency', icon: Banknote, group: 'utilities' },
  { key: 'recurring', label: 'Recurring', icon: Repeat, group: 'utilities' },
  { key: 'vendors', label: 'Vendor Payments', icon: Truck, group: 'utilities' },
  { key: 'audit', label: 'Audit Trail', icon: History, group: 'utilities' },
];

export function FinancePage() {
  const [active, setActive] = useState<TabKey>('dashboard');
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Module workspace</p>
        <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
          <ScrollText className="text-brand-600" size={26} />
          Finance &amp; Accounting
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          15 fully-offline financial tools — invoices, expenses, payroll, tax, budgets, P&amp;L, balance sheet,
          cash flow, forecasting, currency conversion, multi-currency, recurring payments, vendor payments,
          audit trail, and a unified reports dashboard. All data lives on this machine.
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
          {active === 'dashboard' && <DashboardTab />}
          {active === 'invoices' && <InvoicesTab />}
          {active === 'expenses' && <ExpensesTab />}
          {active === 'payroll' && <PayrollTab />}
          {active === 'tax' && <TaxTab />}
          {active === 'budgets' && <BudgetsTab />}
          {active === 'pnl' && <PnLTab />}
          {active === 'balance' && <BalanceSheetTab />}
          {active === 'cashflow' && <CashFlowTab />}
          {active === 'forecast' && <ForecastTab />}
          {active === 'currency' && <CurrencyTab />}
          {active === 'multicurrency' && <MultiCurrencyTab />}
          {active === 'recurring' && <RecurringTab />}
          {active === 'vendors' && <VendorPaymentsTab />}
          {active === 'audit' && <AuditTab />}
        </div>
      </div>
    </div>
  );
}
