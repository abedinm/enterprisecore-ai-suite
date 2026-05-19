import { useState } from 'react';
import { FileText, FileSignature, FileType, FolderTree, History, Edit3, Replace, Share2, Files } from 'lucide-react';
import { cn } from '../../lib/utils';
import { EditorTab } from './EditorTab';
import { PDFTab } from './PDFTab';
import { ESignTab } from './ESignTab';
import { TemplatesTab } from './TemplatesTab';
import { OrganizerTab } from './OrganizerTab';
import { VersionsTab } from './VersionsTab';
import { BulkRenameTab } from './BulkRenameTab';
import { SharingTab } from './SharingTab';

type TabKey = 'editor' | 'pdf' | 'esign' | 'templates' | 'organizer' | 'versions' | 'bulk' | 'sharing';

const tabs: { key: TabKey; label: string; icon: typeof FileText }[] = [
  { key: 'editor', label: 'Editor', icon: Edit3 },
  { key: 'pdf', label: 'PDF Export', icon: FileType },
  { key: 'esign', label: 'E-Signature', icon: FileSignature },
  { key: 'templates', label: 'Templates', icon: Files },
  { key: 'organizer', label: 'Organizer', icon: FolderTree },
  { key: 'versions', label: 'Versions', icon: History },
  { key: 'bulk', label: 'Bulk Rename', icon: Replace },
  { key: 'sharing', label: 'Sharing', icon: Share2 },
];

export function DocumentsPage() {
  const [active, setActive] = useState<TabKey>('editor');
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-brand-600">Module workspace</p>
        <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
          <FileText className="text-brand-600" size={26} />
          Documents
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          8 offline document tools — rich editor with auto-versioning, PDF export, e-signature with hash binding,
          templates with variable substitution, tag-based organizer, version history with restore, bulk rename, and sharing.
        </p>
      </div>
      <div className="ec-card overflow-hidden">
        <div className="flex flex-wrap gap-1 border-b border-border bg-surface-muted px-2 py-2">
          {tabs.map((t) => {
            const Icon = t.icon;
            return (
              <button key={t.key} onClick={() => setActive(t.key)}
                className={cn('flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition',
                  active === t.key ? 'bg-brand-600 text-white shadow-sm' : 'text-ink-muted hover:bg-surface-elevated hover:text-ink')}>
                <Icon size={15} /> {t.label}
              </button>
            );
          })}
        </div>
        <div className="p-5">
          {active === 'editor' && <EditorTab />}
          {active === 'pdf' && <PDFTab />}
          {active === 'esign' && <ESignTab />}
          {active === 'templates' && <TemplatesTab />}
          {active === 'organizer' && <OrganizerTab />}
          {active === 'versions' && <VersionsTab />}
          {active === 'bulk' && <BulkRenameTab />}
          {active === 'sharing' && <SharingTab />}
        </div>
      </div>
    </div>
  );
}
