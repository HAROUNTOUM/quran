# Issue Log

## [#1] Fixed: context_processors.py assumes request.user is always set

- **File**: `apps/core/context_processors.py:6`
- **Description**: `pending_count` and `unread_notifications` context processors call `request.user.is_authenticated` without checking if `request.user` is `None`. Debug Toolbar's template panel runs context processors with bare `request` objects whose `user` attribute may be `None`, causing `/api/v1/docs/` to crash with HTTP 500.
- **Fix**: Changed to `getattr(request, "user", None)` guard.
- **Status**: Fixed

## [#2] Schema generation: 12 APIViews lack serializer_class

- **File**: `apps/api/views.py`
- **Description**: These APIViews have no `serializer_class`, causing drf-spectacular warnings:
  `AttendanceTrendView, AttendanceChartView, ChangePasswordView, CustomTokenObtainView, LogoutView, MeView, StudentHomeView, DashboardStatsView, StudentStatsView, TeacherStatsView, UrgentAlertsView`
- **Impact**: Graceful fallback — views still work, but OpenAPI schema lacks typed responses for these endpoints.
- **Status**: Open (low priority, mild impact on Flutter codegen)

## [#3] operationId collision: grades/teacher-chart vs grades/teacher_chart

- **File**: `apps/api/views.py` (RecitationGradeViewSet)
- **Description**: The router registers both `/api/v1/grades/teacher-chart/` and `/api/v1/grades/teacher_chart/` (from the `teacher_chart` action name), causing OpenAPI operationId collision. Resolved with numeral suffixes.
- **Impact**: Minor — generated client names are slightly ugly.
- **Status**: Open (low priority)

## [#4] Schema warnings: untyped SerializerMethodFields

Several serializers use `SerializerMethodField` without `@extend_schema_field`:
- `AttendanceRecordSerializer.get_student_avatar`
- `CertificateSerializer.get_pdf_url`
- `CircleDetailSerializer.get_enrolled_students`
- `RecitationGradeSerializer.get_overall_grade`
- `SessionListSerializer.get_meeting_platform_display`
- `UserListSerializer.get_circles_count`
- `UserDetailSerializer.get_circles_count`
- `UserDetailSerializer.get_active_circles`
- **Status**: Open (low priority, defaults to `string` in schema)

## [#5] Enum naming collisions for "status" and "type" fields

Multiple models use fields named "status" with different choice sets. drf-spectacular auto-renames them. Adding `ENUM_NAME_OVERRIDES` in settings would fix.
- **Status**: Open (low priority)
