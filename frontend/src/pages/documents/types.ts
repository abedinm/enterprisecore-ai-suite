export type Document = {
  id: string;
  title: string;
  content: string;
  file_path: string | null;
  owner_id: string | null;
  visibility: string;
  created_at: string;
  updated_at: string;
};

export type DocumentVersion = {
  id: string;
  document_id: string;
  version_number: number;
  content: string;
  author_id: string | null;
  created_at: string;
};

export type DocumentTag = { id: string; document_id: string; tag: string };
export type DocumentShare = { id: string; document_id: string; user_id: string | null; permission: string };
export type DocumentTemplate = { id: string; name: string; body: string; category: string | null };
export type ESignature = {
  id: string; document_id: string; signer_name: string; signer_email: string | null;
  signature_hash: string; is_verified: boolean;
};
