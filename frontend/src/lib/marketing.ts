import { api } from './api';

/* -------------------------------------------------------------------------- */
/*  Entity types — mirrored from the backend Pydantic schemas.                */
/* -------------------------------------------------------------------------- */

export type ThemeMode = 'light' | 'dark';
export type ButtonStyle = 'square' | 'rounded';
export type Density = 'comfortable' | 'compact';
export type SectionType = 'hero' | 'services' | 'projects' | 'testimonials' | 'about' | 'cta';
export type PostStatus = 'draft' | 'published';

export type MarketingSettings = {
  name: string;
  tagline: string;
  description: string;
  logoText: string;
  logoDot: boolean;
  baseUrl: string;
  seoTitle: string;
  seoDescription: string;
  themeMode: ThemeMode;
  primaryColor: string;
  accentColor: string;
  headingFont: string;
  bodyFont: string;
  buttonStyle: ButtonStyle;
  density: Density;
  radius: number;
  contactEmail: string;
  contactPhone: string;
  contactAddress: string;
  contactHours: string;
};

export type MarketingNavItem = {
  id: string;
  label: string;
  route: string;
  enabled: boolean;
  order: number;
};

export type MarketingSection = {
  id: string;
  type: SectionType;
  enabled: boolean;
  eyebrow: string;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  order: number;
};

export type MarketingProject = {
  id: string;
  title: string;
  client: string;
  category: string;
  summary: string;
  body: string;
  year: string;
  tags: string[];
  featured: boolean;
  imageId: string | null;
  externalUrl: string;
};

export type MarketingPost = {
  id: string;
  title: string;
  slug: string;
  excerpt: string;
  body: string;
  author: string;
  category: string;
  tags: string[];
  publishDate: string; // ISO
  status: PostStatus;
  seoTitle: string;
  seoDescription: string;
};

export type MarketingService = {
  id: string;
  icon: string;
  title: string;
  summary: string;
  details: string;
  price: string;
  featured: boolean;
  order: number;
};

export type MarketingTestimonial = {
  id: string;
  quote: string;
  author: string;
  role: string;
  order: number;
};

export type MarketingFAQ = {
  id: string;
  question: string;
  answer: string;
  order: number;
};

export type MarketingTeamMember = {
  id: string;
  name: string;
  role: string;
  imageId: string | null;
  order: number;
};

export type MarketingSocialLink = {
  id: string;
  platform: string;
  label: string;
  url: string;
  order: number;
};

export type MarketingUpload = {
  id: string;
  filename: string;
  contentType: string;
  sizeBytes: number;
  url: string;
  createdAt: string;
};

export type MarketingChecklistItem = {
  id: string;
  label: string;
  complete: boolean;
};

export type MarketingState = {
  settings: MarketingSettings;
  navigation: MarketingNavItem[];
  sections: MarketingSection[];
  projects: MarketingProject[];
  posts: MarketingPost[];
  services: MarketingService[];
  testimonials: MarketingTestimonial[];
  faqs: MarketingFAQ[];
  team: MarketingTeamMember[];
  social_links: MarketingSocialLink[];
  contact_info: {
    email: string;
    phone: string;
    address: string;
    hours: string;
  };
};

export type MarketingStateOut = MarketingState;

export type MarketingTemplateSummary = {
  id: string;
  name: string;
  description: string;
  preview_image: string | null;
};

export type MarketingTemplate = MarketingTemplateSummary & MarketingState;

/* -------------------------------------------------------------------------- */
/*  Create/update payload aliases — backend accepts partials for PATCH.        */
/* -------------------------------------------------------------------------- */

export type SectionInput = Omit<MarketingSection, 'id'>;
export type ProjectInput = Omit<MarketingProject, 'id'>;
export type PostInput = Omit<MarketingPost, 'id'>;
export type ServiceInput = Omit<MarketingService, 'id'>;
export type TestimonialInput = Omit<MarketingTestimonial, 'id'>;
export type FAQInput = Omit<MarketingFAQ, 'id'>;
export type TeamInput = Omit<MarketingTeamMember, 'id'>;
export type SocialLinkInput = Omit<MarketingSocialLink, 'id'>;
export type NavItemInput = Omit<MarketingNavItem, 'id'>;

export type ReorderEntry = { id: string; order: number };

/* -------------------------------------------------------------------------- */
/*  Helper — some backends return camelCase, others snake_case. The wrapper   */
/*  normalises a few known fields so pages stay typed against camelCase.      */
/* -------------------------------------------------------------------------- */

type RawUpload = Partial<MarketingUpload> & {
  content_type?: string;
  size_bytes?: number;
  created_at?: string;
};

function normaliseUpload(raw: RawUpload): MarketingUpload {
  return {
    id: String(raw.id ?? ''),
    filename: raw.filename ?? '',
    contentType: raw.contentType ?? raw.content_type ?? 'application/octet-stream',
    sizeBytes: raw.sizeBytes ?? raw.size_bytes ?? 0,
    url: raw.url ?? '',
    createdAt: raw.createdAt ?? raw.created_at ?? new Date().toISOString(),
  };
}

/* -------------------------------------------------------------------------- */
/*  API surface — every endpoint in the marketing contract.                    */
/* -------------------------------------------------------------------------- */

const PREFIX = '/marketing';

export const marketingApi = {
  getState: () => api.get<MarketingState>(`${PREFIX}/state`).then((r) => r.data),

  // Settings — singleton; PATCH accepts any subset of MarketingSettings.
  updateSettings: (body: Partial<MarketingSettings>) =>
    api.patch<MarketingSettings>(`${PREFIX}/settings`, body).then((r) => r.data),

  // Navigation — atomic replace of the full nav list (server assigns IDs).
  replaceNavigation: (items: (Partial<MarketingNavItem> & { label: string; route: string })[]) =>
    api.put<MarketingNavItem[]>(`${PREFIX}/navigation`, items).then((r) => r.data),

  // Sections
  listSections: () => api.get<MarketingSection[]>(`${PREFIX}/sections`).then((r) => r.data),
  createSection: (body: Partial<SectionInput>) =>
    api.post<MarketingSection>(`${PREFIX}/sections`, body).then((r) => r.data),
  updateSection: (id: string, body: Partial<SectionInput>) =>
    api.patch<MarketingSection>(`${PREFIX}/sections/${id}`, body).then((r) => r.data),
  deleteSection: (id: string) =>
    api.delete(`${PREFIX}/sections/${id}`).then(() => true),
  reorderSections: (order: ReorderEntry[]) =>
    api.put(`${PREFIX}/sections/reorder`, order).then(() => true),

  // Projects
  listProjects: () => api.get<MarketingProject[]>(`${PREFIX}/projects`).then((r) => r.data),
  getProject: (id: string) =>
    api.get<MarketingProject>(`${PREFIX}/projects/${id}`).then((r) => r.data),
  createProject: (body: Partial<ProjectInput>) =>
    api.post<MarketingProject>(`${PREFIX}/projects`, body).then((r) => r.data),
  updateProject: (id: string, body: Partial<ProjectInput>) =>
    api.patch<MarketingProject>(`${PREFIX}/projects/${id}`, body).then((r) => r.data),
  deleteProject: (id: string) =>
    api.delete(`${PREFIX}/projects/${id}`).then(() => true),
  reorderProjects: (order: ReorderEntry[]) =>
    api.put(`${PREFIX}/projects/reorder`, order).then(() => true),

  // Posts
  listPosts: () => api.get<MarketingPost[]>(`${PREFIX}/posts`).then((r) => r.data),
  getPost: (id: string) => api.get<MarketingPost>(`${PREFIX}/posts/${id}`).then((r) => r.data),
  createPost: (body: Partial<PostInput>) =>
    api.post<MarketingPost>(`${PREFIX}/posts`, body).then((r) => r.data),
  updatePost: (id: string, body: Partial<PostInput>) =>
    api.patch<MarketingPost>(`${PREFIX}/posts/${id}`, body).then((r) => r.data),
  deletePost: (id: string) =>
    api.delete(`${PREFIX}/posts/${id}`).then(() => true),
  reorderPosts: (order: ReorderEntry[]) =>
    api.put(`${PREFIX}/posts/reorder`, order).then(() => true),

  // Services
  listServices: () => api.get<MarketingService[]>(`${PREFIX}/services`).then((r) => r.data),
  createService: (body: Partial<ServiceInput>) =>
    api.post<MarketingService>(`${PREFIX}/services`, body).then((r) => r.data),
  updateService: (id: string, body: Partial<ServiceInput>) =>
    api.patch<MarketingService>(`${PREFIX}/services/${id}`, body).then((r) => r.data),
  deleteService: (id: string) =>
    api.delete(`${PREFIX}/services/${id}`).then(() => true),
  reorderServices: (order: ReorderEntry[]) =>
    api.put(`${PREFIX}/services/reorder`, order).then(() => true),

  // Testimonials
  listTestimonials: () =>
    api.get<MarketingTestimonial[]>(`${PREFIX}/testimonials`).then((r) => r.data),
  createTestimonial: (body: Partial<TestimonialInput>) =>
    api.post<MarketingTestimonial>(`${PREFIX}/testimonials`, body).then((r) => r.data),
  updateTestimonial: (id: string, body: Partial<TestimonialInput>) =>
    api.patch<MarketingTestimonial>(`${PREFIX}/testimonials/${id}`, body).then((r) => r.data),
  deleteTestimonial: (id: string) =>
    api.delete(`${PREFIX}/testimonials/${id}`).then(() => true),
  reorderTestimonials: (order: ReorderEntry[]) =>
    api.put(`${PREFIX}/testimonials/reorder`, order).then(() => true),

  // FAQs
  listFaqs: () => api.get<MarketingFAQ[]>(`${PREFIX}/faqs`).then((r) => r.data),
  createFaq: (body: Partial<FAQInput>) =>
    api.post<MarketingFAQ>(`${PREFIX}/faqs`, body).then((r) => r.data),
  updateFaq: (id: string, body: Partial<FAQInput>) =>
    api.patch<MarketingFAQ>(`${PREFIX}/faqs/${id}`, body).then((r) => r.data),
  deleteFaq: (id: string) => api.delete(`${PREFIX}/faqs/${id}`).then(() => true),
  reorderFaqs: (order: ReorderEntry[]) =>
    api.put(`${PREFIX}/faqs/reorder`, order).then(() => true),

  // Team
  listTeam: () => api.get<MarketingTeamMember[]>(`${PREFIX}/team`).then((r) => r.data),
  createTeam: (body: Partial<TeamInput>) =>
    api.post<MarketingTeamMember>(`${PREFIX}/team`, body).then((r) => r.data),
  updateTeam: (id: string, body: Partial<TeamInput>) =>
    api.patch<MarketingTeamMember>(`${PREFIX}/team/${id}`, body).then((r) => r.data),
  deleteTeam: (id: string) => api.delete(`${PREFIX}/team/${id}`).then(() => true),
  reorderTeam: (order: ReorderEntry[]) =>
    api.put(`${PREFIX}/team/reorder`, order).then(() => true),

  // Social
  listSocial: () =>
    api.get<MarketingSocialLink[]>(`${PREFIX}/social-links`).then((r) => r.data),
  createSocial: (body: Partial<SocialLinkInput>) =>
    api.post<MarketingSocialLink>(`${PREFIX}/social-links`, body).then((r) => r.data),
  updateSocial: (id: string, body: Partial<SocialLinkInput>) =>
    api.patch<MarketingSocialLink>(`${PREFIX}/social-links/${id}`, body).then((r) => r.data),
  deleteSocial: (id: string) =>
    api.delete(`${PREFIX}/social-links/${id}`).then(() => true),
  reorderSocial: (order: ReorderEntry[]) =>
    api.put(`${PREFIX}/social-links/reorder`, order).then(() => true),

  // Uploads / media library
  listUploads: () =>
    api
      .get<RawUpload[]>(`${PREFIX}/uploads`)
      .then((r) => (r.data ?? []).map(normaliseUpload)),
  uploadFile: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return api
      .post<RawUpload>(`${PREFIX}/uploads`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => normaliseUpload(r.data));
  },
  deleteUpload: (id: string) =>
    api.delete(`${PREFIX}/uploads/${id}`).then(() => true),

  // Launch checklist
  getChecklist: () =>
    api.get<MarketingChecklistItem[]>(`${PREFIX}/launch-checklist`).then((r) => r.data),

  // Industry templates
  listTemplates: () =>
    api.get<MarketingTemplateSummary[]>(`${PREFIX}/templates`).then((r) => r.data),
  getTemplate: (id: string) =>
    api.get<MarketingTemplate>(`${PREFIX}/templates/${id}`).then((r) => r.data),
  useTemplate: (id: string, options: { wipe_existing: boolean }) =>
    api
      .post<MarketingStateOut>(`${PREFIX}/templates/${id}/use`, options)
      .then((r) => r.data),

  // SiteForge JSON export import. Multipart upload of an exported JSON file
  // from SiteForge Studio's Settings → Data → Export. Replaces existing
  // marketing content on success.
  importSiteforge: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api
      .post<MarketingStateOut>(`${PREFIX}/import-siteforge`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data);
  },
};

/* -------------------------------------------------------------------------- */
/*  Static option lists used by editor UIs.                                    */
/* -------------------------------------------------------------------------- */

export const SECTION_TYPE_OPTIONS: { value: SectionType; label: string; helper: string }[] = [
  { value: 'hero', label: 'Hero', helper: 'Big headline + stats above the fold' },
  { value: 'services', label: 'Services', helper: 'List of what you offer' },
  { value: 'projects', label: 'Projects', helper: 'Portfolio showcase grid' },
  { value: 'testimonials', label: 'Testimonials', helper: 'Social proof quotes' },
  { value: 'about', label: 'About', helper: 'Story / team intro' },
  { value: 'cta', label: 'Call to action', helper: 'Single conversion block' },
];

export const FONT_OPTIONS: string[] = [
  'Inter',
  'Manrope',
  'Plus Jakarta Sans',
  'Space Grotesk',
  'Sora',
  'IBM Plex Sans',
  'Source Sans 3',
  'Roboto',
  'Lora',
  'Playfair Display',
  'Merriweather',
  'JetBrains Mono',
];

export const SOCIAL_PLATFORM_OPTIONS: { value: string; label: string }[] = [
  { value: 'twitter', label: 'X / Twitter' },
  { value: 'linkedin', label: 'LinkedIn' },
  { value: 'github', label: 'GitHub' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'facebook', label: 'Facebook' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'dribbble', label: 'Dribbble' },
  { value: 'behance', label: 'Behance' },
  { value: 'medium', label: 'Medium' },
  { value: 'mastodon', label: 'Mastodon' },
  { value: 'other', label: 'Other' },
];

/** Derive a URL-safe slug from a plain-text title. */
export function slugify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/['"`]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}

/** Cap-friendly label for an unknown entity type (used in section badges). */
export function sectionTypeLabel(type: string): string {
  const match = SECTION_TYPE_OPTIONS.find((o) => o.value === type);
  return match?.label ?? type;
}
