import { useState } from 'react';
import {
  Shield, KeyRound, Database, Eye, ClipboardCheck, History, UsersIcon, ScrollText,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { VaultTab } from './VaultTab';
import { LoginMonitorTab } from './LoginMonitorTab';
import { GDPRTab } from './GDPRTab';
import { AuditLogTab } from './AuditLogTab';
import { ComplianceTab } from './ComplianceTab';
import { BackupsTab } from './BackupsTab';
import { AccessTab } from './AccessTab';

type TabKey = 'vault' | 'access' | 'login-monitor' | 'gdpr' | 'compliance' | 'backups' | 'audit';

const TABS: { key: TabKey; label: string; icon: typeof Shield }[] = [
  { key: 'vault', label: 'Password Vault', icon: KeyRound },
  { key: 'access', label: 'Access Control', icon: UsersIcon },
  { key: 'login-monitor', label: 'Login Monitor', icon: Eye },
  { key: 'gdpr', label: 'GDPR', icon: ClipboardCheck },
  { key: 'compliance', label: 'Compliance', icon: ScrollText },
  { key: 'backups', label: 'Backups', icon: Database },
  { key: 'audit', label: 'Audit Log', icon: History },
];

export function SecurityPage() {
  const [active, setActive] = useState<TabKey>('vault');
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Module workspace</p>
        <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
          <Shield className="text-brand-600" size={26} />
          Security &amp; Compliance
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          Encrypted password vault, role-based access, login monitoring, GDPR/SOC2/HIPAA/
          ISO27001 compliance tracking, encrypted backups, and a full audit trail.
        </p>
      </div>

      <div className="ec-card overflow-hidden">
        <div className="flex flex-wrap gap-1 border-b border-border bg-surface-muted px-2 py-2">
          {TABS.map((t) => {
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
          {active === 'vault' && <VaultTab />}
          {active === 'access' && <AccessTab />}
          {active === 'login-monitor' && <LoginMonitorTab />}
          {active === 'gdpr' && <GDPRTab />}
          {active === 'compliance' && <ComplianceTab />}
          {active === 'backups' && <BackupsTab />}
          {active === 'audit' && <AuditLogTab />}
        </div>
      </div>
    </div>
  );
}
