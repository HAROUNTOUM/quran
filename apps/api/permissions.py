from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "admin"
        )


class IsSupervisorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ("admin", "supervisor")
        )


class IsTeacherOrAbove(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ("admin", "supervisor", "teacher")
        )


class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == "admin":
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
