# Role-Based Access Control (RBAC)

EnterpriseCore ships with two layers of access control:

1. **Built-in roles** — eight enum-typed `UserRole` values that every user
   carries on the `users.role` column.
2. **Custom roles + permission catalog** — granular permissions a
   customer can mix and match to define their own roles on top.

Together they let small installs run on the defaults while enterprises
can carve out fine-grained access like "Finance Auditor — read-only
across all finance entities, no write anywhere."

---

## 1. Built-in roles

| Role        | Description                                                              |
|-------------|--------------------------------------------------------------------------|
| `Admin`     | Full tenant administration. Holds every permission in the catalog.       |
| `Manager`   | Reads everything; writes most business modules. Can't admin the tenant.  |
| `Employee`  | Reads modules they typically touch; writes own attendance / tasks / time. |
| `Developer` | Employee perms plus coding/AI/knowledge writes.                          |
| `Student`   | Academic SKU — read classes/grades + chat.                               |
| `Teacher`   | Student perms plus grade entry + attendance + LMS upload.                |
| `Registrar` | Teacher perms plus enrolment management + user read.                    |
| `Dean`      | Registrar perms plus full academic + audit + settings read.             |

The static mapping lives in `app/core/permissions.py::BUILT_IN_ROLE_PERMISSIONS`.

---

## 2. Permission catalog

Every permission is a dotted key of the form `<module>.<entity>.<verb>`.
Verbs: `read`, `write`, `delete`, `admin`, `export`, `sign`, `publish`,
`terminate`, `approve`, `use`.

Categories shipped today:

- `tenant.*` — tenant administration (users, billing, settings, audit, encryption)
- `finance.*` — invoices, expenses, payroll, budgets, tax, journal, customers, vendors
- `hr.*` — employees, attendance, leave, reviews, recruiting (+ `hr.employees.terminate`)
- `crm.*` — leads, deals, contacts, contracts (+ `crm.contracts.sign`), campaigns
- `projects.*` — projects, tasks, time
- `inventory.*` — products, stock, PO, suppliers
- `documents.*` — read/write/delete/share + `documents.esign.sign`
- `communication.*` — messages, announcements, wiki
- `marketing.*` — posts, publishing, site settings
- `construction.*` — projects, contracts (+ sign), permits, risks
- `academic.*` — classes, grades, attendance, enrolment
- `coding.*`, `ai.*`, `knowledge.*`, `webchat.*` — module access

The full list (~100 keys) is in `PERMISSION_CATALOG` and seeded into the
`permissions` table by migration `0017_rbac_security`.

---

## 3. Custom roles

A custom role is a tenant-scoped row in `custom_roles` holding a
**name**, optional description, and a JSON list of **permission_keys**.

API:

```
GET    /api/v1/rbac/permissions                # Admin only
GET    /api/v1/rbac/roles                      # built-ins + custom
POST   /api/v1/rbac/roles                      # admin — create
PATCH  /api/v1/rbac/roles/{role_id}            # admin — edit
DELETE /api/v1/rbac/roles/{role_id}            # admin — delete
POST   /api/v1/rbac/users/{user_id}/roles      # assign
DELETE /api/v1/rbac/users/{user_id}/roles/{role_id}
GET    /api/v1/rbac/users/{user_id}/effective-permissions
```

Unknown permission keys in a `permission_keys` list are rejected with a
400 (`Unknown permission keys: ...`).

---

## 4. Resolution

The effective permission set for a user is the **union** of:

- The built-in role's keys (`BUILT_IN_ROLE_PERMISSIONS[user.role]`)
- Every custom role assigned via `user_role_assignments`

Resolution helpers:

```python
from app.core.permissions import has_permission, require_permission

# In a handler
if not has_permission(user, "finance.invoices.write", db):
    raise PermissionDenied(...)

# As a FastAPI dep
@router.post("/invoices", dependencies=[Depends(require_permission("finance.invoices.write"))])
def create_invoice(...): ...
```

Legacy `require_roles(...)` is preserved; new endpoints prefer
`require_permission(...)` so customers can grant access without
promoting users.

---

## 5. Cross-tenant isolation

`custom_roles` and `user_role_assignments` both carry `tenant_id` and
are routed through the auto-filter in `app/core/tenant_orm.py`. Tenant
A cannot grant Tenant B's user a role; the FK + auto-filter make
cross-tenant leakage impossible.

---

## 6. Auditing

Every RBAC change is recorded in `audit_logs` (action
`rbac.role.create`, `rbac.role.update`, `rbac.role.delete`,
`rbac.role.assign`, `rbac.role.revoke`). Combined with the audit-stream
destinations (see `docs/SOC2_CONTROLS.md`) this satisfies SOC 2 CC6.2
authorisation evidence.
