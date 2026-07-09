from rest_framework.permissions import BasePermission

from apps.accounts.models import User


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.MAIN_ADMIN
        )


class IsSupervisorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN)
        )


class IsTeacherOrAbove(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN, User.Role.TEACHER)
        )


class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == User.Role.MAIN_ADMIN:
            return True
        user_field = getattr(view, "owner_field", "user")
        owner = getattr(obj, user_field, None)
        if owner is None and hasattr(obj, "student"):
            owner = getattr(obj, "student", None)
        if owner is None and hasattr(obj, "teacher"):
            owner = getattr(obj, "teacher", None)
        if owner is None and hasattr(obj, "submitted_by"):
            owner = getattr(obj, "submitted_by", None)
        return owner == request.user


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "student"
        )


class IsTeacher(BasePermission):
    """Exact-role check (teacher only) — unlike IsTeacherOrAbove."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "teacher"
        )


class IsTeacherOfStudent(BasePermission):
    """Teacher may only touch data of students actually assigned to them.

    Admin/supervisor pass. The actual relationship check delegates to
    User.teaches_student() (active CircleEnrollment) — never URL obscurity.
    Apply as an object-level permission wherever a teacher reads or writes
    a specific student's data.
    """

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN, User.Role.TEACHER)
        )

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
            return True
        if user.role != "teacher":
            return False
        student = self._resolve_student(obj)
        return user.teaches_student(student)

    @staticmethod
    def _resolve_student(obj):
        """Find the student a given object belongs to.

        Handles: a student User itself, models with a .student FK
        (Attendance, ReviewRequest, RecitationGrade, Certificate, ...),
        and models reachable via .enrollment.student (MemorizationProgress).
        """
        from apps.accounts.models import User

        if isinstance(obj, User):
            return obj if obj.role == User.Role.STUDENT else None
        student = getattr(obj, "student", None)
        if student is not None:
            return student
        enrollment = getattr(obj, "enrollment", None)
        if enrollment is not None:
            return getattr(enrollment, "student", None)
        return None
