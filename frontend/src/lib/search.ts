// Helpers for the FTS5-backed cross-module search.
//
// Keeps the entity_type -> route mapping in one place so every search
// surface (the global popover, the dedicated /search page, future Cmd-K
// palettes) routes consistently when the user clicks a result.

import type { FtsSearchResult } from './api';

// Module label used for the colored badge on each result + the grouping
// header on the SearchPage. Falls back to the entity_type prefix.
export function moduleLabel(entityType: string): string {
  const [module] = entityType.split('.', 1);
  switch (module) {
    case 'crm':
      return 'CRM';
    case 'hr':
      return 'HR';
    case 'finance':
      return 'Finance';
    case 'projects':
      return 'Projects';
    case 'inventory':
      return 'Inventory';
    case 'documents':
      return 'Documents';
    case 'communication':
      return 'Communication';
    case 'knowledge':
      return 'Knowledge';
    case 'webchat':
      return 'Web Chat';
    case 'marketing':
      return 'Marketing';
    case 'construction':
      return 'Construction';
    default:
      return module.charAt(0).toUpperCase() + module.slice(1);
  }
}

// Resolve an entity-type + id to the in-app route that displays it.
// Routes are best-effort — if the underlying frontend module hasn't
// shipped a detail page yet we land on the module index, which is
// strictly better than a 404.
export function resultHref(result: FtsSearchResult): string {
  const { entity_type, entity_id } = result;
  switch (entity_type) {
    case 'crm.contact':
      return `/crm/contacts/${entity_id}`;
    case 'crm.lead':
      return `/crm/leads/${entity_id}`;
    case 'crm.deal':
      return `/crm/deals/${entity_id}`;
    case 'hr.employee':
      return `/hr/employees/${entity_id}`;
    case 'hr.candidate':
      return `/hr/candidates/${entity_id}`;
    case 'hr.job_opening':
      return `/hr/openings/${entity_id}`;
    case 'finance.customer':
      return `/finance/customers/${entity_id}`;
    case 'finance.vendor':
      return `/finance/vendors/${entity_id}`;
    case 'finance.invoice':
      return `/finance/invoices/${entity_id}`;
    case 'finance.expense':
      return `/finance/expenses/${entity_id}`;
    case 'projects.project':
      return `/projects/${entity_id}`;
    case 'projects.task':
      return `/projects/tasks/${entity_id}`;
    case 'inventory.product':
      return `/inventory/products/${entity_id}`;
    case 'documents.document':
      return `/documents/${entity_id}`;
    case 'communication.announcement':
      return `/communication/announcements/${entity_id}`;
    case 'communication.wiki_page':
      return `/communication/wiki/${entity_id}`;
    case 'knowledge.document':
      return `/ai-brain/knowledge/${entity_id}`;
    case 'webchat.bot':
      return `/webchat/bots/${entity_id}`;
    case 'marketing.post':
      return `/marketing/posts/${entity_id}`;
    case 'marketing.project':
      return `/marketing/projects/${entity_id}`;
    case 'marketing.team_member':
      return `/marketing/team/${entity_id}`;
    case 'construction.project':
      return `/construction/projects/${entity_id}`;
    case 'construction.risk':
      return `/construction/risks/${entity_id}`;
    default: {
      // Fall back to the module index for unknown entity types.
      const [module] = entity_type.split('.', 1);
      return `/${module}`;
    }
  }
}

// Group a flat result list by module for the SearchPage's section
// headers. Preserves the rank-sorted order within each group.
export function groupByModule(
  results: FtsSearchResult[],
): Array<{ module: string; items: FtsSearchResult[] }> {
  const groups: Record<string, FtsSearchResult[]> = {};
  const order: string[] = [];
  for (const r of results) {
    const [module] = r.entity_type.split('.', 1);
    if (!groups[module]) {
      groups[module] = [];
      order.push(module);
    }
    groups[module].push(r);
  }
  return order.map((module) => ({ module, items: groups[module] }));
}
