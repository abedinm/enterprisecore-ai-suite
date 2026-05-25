/**
 * Vitest setup — runs before each test file. Provides a deterministic
 * localStorage mock and clears it between tests.
 */
import { afterEach, beforeEach } from 'vitest';

beforeEach(() => {
  // jsdom's localStorage is already real, but we wipe between tests
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
  // Detach any test-installed Electron bridge so the next test starts clean
  delete (window as any).enterpriseCore;
});
