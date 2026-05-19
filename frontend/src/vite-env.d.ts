/// <reference types="vite/client" />

interface EnterpriseCoreVault {
  get(key: string): Promise<string | null>;
  set(key: string, value: string | null): Promise<true>;
  listKeys(): Promise<string[]>;
  clear(): Promise<true>;
  available(): Promise<{ encrypted: boolean }>;
}

interface EnterpriseCoreDialog {
  openDirectory(): Promise<string | null>;
  openFile(filters?: { name: string; extensions: string[] }[]): Promise<string | null>;
  saveFile(
    defaultPath?: string,
    filters?: { name: string; extensions: string[] }[],
  ): Promise<string | null>;
}

interface EnterpriseCoreShell {
  openExternal(url: string): Promise<boolean>;
}

interface EnterpriseCoreBridge {
  isDesktop: true;
  platform: NodeJS.Platform | string;
  getBackendUrl(): Promise<string>;
  getPlatform(): Promise<string>;
  vault: EnterpriseCoreVault;
  dialog: EnterpriseCoreDialog;
  shell: EnterpriseCoreShell;
  on(channel: string, listener: (...args: unknown[]) => void): () => void;
}

declare global {
  interface Window {
    enterpriseCore?: EnterpriseCoreBridge;
  }
}

export {};
