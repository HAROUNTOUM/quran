# Changes Log

## Phase 1: Data Migration Conflict
- **Data fix**: Merged duplicate batch `الدفعة الأولى`/`1446` (ID=1→2). Moved `sub_admin` from ID=1 to ID=2, deleted ID=1.
- **Data fix**: Set batch ID=3 `number` from `1` to `NULL` to pass new `unique=True` constraint.
- **Migrations applied**: `0008`, `0009`, `circles.0020`

## Phase 2a: Batch List M2M Scope
- `apps/accounts/views/admin.py:2621`: Changed `Batch.objects.filter(sub_admin=request.user)` → `Q(sub_admin=request.user) | Q(sub_admins=request.user)`

## Phase 2b: Teachers/Students Scope
- `apps/accounts/views/admin.py:475`: `admin_teachers` now uses `scoping.scoped_batch_ids()` instead of `_sub_admin_batch()`
- `apps/accounts/views/admin.py:521`: `admin_students` now uses `scoping.scoped_batch_ids()` instead of `_sub_admin_batch()`
- `apps/accounts/views/admin.py:550,556`: Updated remaining `batch` variable references to `batch_ids`

## Phase 2c: Supervisor Board Scope
- `apps/accounts/views/supervisor.py:107`: Replaced `user.managed_batch.first()` with `Batch.objects.filter(Q(sub_admin=user) | Q(sub_admins=user), pk=circle.batch_id).exists()`
- Added `from django.db.models import Q` import

## Phase 3: admin_batch_circles View
- **New view**: `admin_batch_circles(request, pk)` in `apps/accounts/views/admin.py` — shows circles of a batch with links to detailed report and circle management
- **New URL**: `dashboard/batches/<pk>/circles/` in `apps/accounts/urls.py`
- **New template**: `templates/dashboard/admin/batches/circles.html`
- **Exported** in `apps/accounts/views/__init__.py`

## Phase 3: Nav Links Update
- `templates/dashboard/admin/batches/list.html`: Batch name + "الحلقات" button → `admin_batch_circles`; new "الإعدادات" button → `admin_batch_detail`
- `templates/dashboard/admin/batches/detail.html`: Added "إدارة الحلقات" button linking to `admin_batch_circles`

## Phase 4: Sidebar Links
- `templates/dashboard/partials/sidebar.html`:
  - Added `admin_batch_circles` to batch nav active state
  - Added "متابعة الدفعات" → `supervisor_groups`
  - Included `_chat_link.html` → `chat:inbox`
  - Added "الإعلانات" → `admin_announcements`
  - Added "الإشعارات" → `admin_notifications`

## Phase 5: User Transfer Between Batches
- `apps/accounts/views/admin.py`: Removed `batch__isnull=True` from `assign_users` action — now allows reassigning users from other batches
- `apps/accounts/views/admin.py`: Updated `unassigned_users` queryset to show all approved teachers/students (`exclude(batch=batch)` instead of `batch__isnull=True`)
- `templates/dashboard/admin/batches/detail.html`: Updated labels and help text to indicate transfer is possible
