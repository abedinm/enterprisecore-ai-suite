import type { UserRole } from './api';

/**
 * Role categories for the academic module pack. The backend's UserRole enum
 * carries the truth (Admin/Manager/Employee/Developer + Student/Teacher/
 * Registrar/Dean); this just groups them for UI conditioning so each page
 * doesn't repeat the same big OR-chain.
 *
 * - admin: Admin, Manager, Registrar, Dean — full read/write on academic data
 * - teacher: Teacher — staff that grades + marks attendance for their classes
 * - student: Student, Employee — read-only / own-records view (Employee is
 *   the platform default; if someone is in an academic SKU without a role
 *   upgrade they get the student view, which is the safest fallback)
 */
export type AcademicRoleView = 'admin' | 'teacher' | 'student';

const ADMIN_ROLES: readonly UserRole[] = ['Admin', 'Manager', 'Registrar', 'Dean'];
const TEACHER_ROLES: readonly UserRole[] = ['Teacher'];

export function academicRoleView(role: UserRole | string | undefined | null): AcademicRoleView {
  if (!role) return 'student';
  if ((ADMIN_ROLES as readonly string[]).includes(role)) return 'admin';
  if ((TEACHER_ROLES as readonly string[]).includes(role)) return 'teacher';
  return 'student';
}

/** Staff = can author/edit academic data (admin + teacher views). */
export function isAcademicStaff(role: UserRole | string | undefined | null): boolean {
  const view = academicRoleView(role);
  return view === 'admin' || view === 'teacher';
}

/** Admin-only = scheduling, finance management, semester creation. */
export function isAcademicAdmin(role: UserRole | string | undefined | null): boolean {
  return academicRoleView(role) === 'admin';
}
