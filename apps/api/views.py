from datetime import date, timedelta

from django.db.models import Count, Q, Sum, F, Max
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import status, viewsets, generics, permissions
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session, SessionStudentNote, SessionRescheduleRequest, SessionLessonToggle
from apps.attendance.models import Attendance, SessionAttendanceIntent
from apps.memorization.models import MemorizationProgress, RecitationGrade, ReviewRequest, ProgressLog, StudentAchievement
from apps.exams.models import Exam, ExamMark, ExamNotification, ExamApprovalHistory
from apps.exams.services import notify_published, submit_for_approval, approve_all_marks, reject_marks, save_mark
from apps.references.models import EvaluationCriterion, Surah
from apps.requests.models import SupportRequest, Comment
from apps.announcements.models import Announcement
from apps.notifications.models import Notification

from .serializers import (
    UserProfileSerializer,
    ChangePasswordSerializer,
    UserListSerializer,
    UserDetailSerializer,
    UserCreateSerializer,
    CircleListSerializer,
    CircleDetailSerializer,
    CircleCreateSerializer,
    CircleEnrollSerializer,
    CircleRemoveStudentSerializer,
    CircleStatsSerializer,
    SessionListSerializer,
    SessionCreateSerializer,
    AttendanceRecordSerializer,
    BatchAttendanceSerializer,
    RecitationGradeSerializer,
    RecitationGradeCreateSerializer,
    AbsenceJustificationSerializer,
    RegistrationCreateSerializer,
    RegistrationRequestSerializer,
    SupportRequestSerializer,
    SupportRequestCreateSerializer,
    CommentSerializer,
    CommentCreateSerializer,
    AnnouncementSerializer,
    AnnouncementCreateSerializer,
    NotificationSerializer,
    AttendanceChartSerializer,
    AttendanceTrendSerializer,
    TeacherChartSerializer,
    DashboardStatsSerializer,
    StudentStatsSerializer,
    TeacherStatsSerializer,
    UrgentAlertSerializer,
    RegistrationStatsSerializer,
    CircleMinSerializer,
    ExamListSerializer,
    ExamCreateSerializer,
    ExamMarkSerializer,
    ExamMarkCreateSerializer,
    ReviewRequestSerializer,
    ReviewRequestCreateSerializer,
    ReviewRequestActionSerializer,
    SessionStudentNoteSerializer,
    SessionStudentNoteCreateSerializer,
    MemorizationProgressSerializer,
    MemorizationProgressCreateSerializer,
    SurahSerializer,
    EvaluationCriterionSerializer,
    SessionRescheduleRequestSerializer,
    SessionRescheduleCreateSerializer,
    SessionLessonToggleSerializer,
    SessionLessonToggleBatchSerializer,
    ProgressLogListSerializer,
    ProgressLogCreateSerializer,
)
from .permissions import IsSupervisorOrAdmin, IsTeacherOrAbove, IsStudent, IsOwnerOrAdmin
from apps.references.utils import ayahs_to_juz_quarters
from .utils import api_response


# ─── AUTH VIEWS ─────────────────────────────────

class CustomTokenObtainView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from django.contrib.auth import authenticate
        email = request.data.get("email", "")
        password = request.data.get("password", "")
        user = authenticate(request=request, username=email, password=password)
        if user is None:
            return api_response(
                message="البريد الإلكتروني أو كلمة المرور غير صحيحة",
                status=status.HTTP_401_UNAUTHORIZED,
                success=False,
            )
        if not user.is_active:
            return api_response(
                message="الحساب غير نشط",
                status=status.HTTP_401_UNAUTHORIZED,
                success=False,
            )
        if user.is_approved != User.ApprovalStatus.APPROVED:
            return api_response(
                message="الحساب لم يتم اعتماده بعد",
                status=status.HTTP_401_UNAUTHORIZED,
                success=False,
            )

        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role
        refresh["full_name"] = user.full_name_ar
        refresh["email"] = user.email

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        return api_response(data={
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserProfileSerializer(user, context={"request": request}).data,
        }, message="تم تسجيل الدخول بنجاح")


class LogoutView(APIView):
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return api_response(message="تم تسجيل الخروج بنجاح")
        except Exception:
            return api_response(message="تم تسجيل الخروج بنجاح")


class MeView(APIView):
    def get(self, request):
        return api_response(
            data=UserProfileSerializer(request.user, context={"request": request}).data
        )

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        serializer.save()
        return api_response(
            data=UserProfileSerializer(request.user, context={"request": request}).data,
            message="تم تحديث الملف الشخصي",
        )


class ChangePasswordView(APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return api_response(message="تم تغيير كلمة المرور بنجاح")


# ─── USERS VIEWSET ─────────────────────────────

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    search_fields = ["full_name_ar", "email", "phone"]
    filterset_fields = ["role", "is_approved", "gender"]
    ordering_fields = ["full_name_ar", "email", "date_joined", "last_login"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action == "retrieve":
            return UserDetailSerializer
        return UserListSerializer

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsSupervisorOrAdmin()]
        if self.action in ("list", "destroy"):
            return [permissions.IsAuthenticated(), IsSupervisorOrAdmin()]
        if self.action == "stats":
            return [permissions.IsAuthenticated(), IsSupervisorOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = User.objects.all()
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        status_f = self.request.query_params.get("status")
        if status_f == "pending":
            qs = qs.filter(is_approved=User.ApprovalStatus.PENDING)
        elif status_f == "approved":
            qs = qs.filter(is_approved=User.ApprovalStatus.APPROVED)
        elif status_f == "rejected":
            qs = qs.filter(is_approved=User.ApprovalStatus.REJECTED)
        return qs.order_by("-date_joined")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if request.user.role != "admin" and instance != request.user:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)

    def list(self, request, *args, **kwargs):
        if request.user.role not in ("admin", "supervisor"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        user = serializer.save()
        return api_response(
            data=UserDetailSerializer(user, context={"request": request}).data,
            message="تم إنشاء المستخدم بنجاح",
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if request.user.role != "admin" and instance != request.user:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        serializer = UserProfileSerializer(instance, data=request.data, partial=True, context={"request": request})
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        serializer.save()
        return api_response(
            data=UserDetailSerializer(instance, context={"request": request}).data,
            message="تم تحديث المستخدم",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        return api_response(message="تم تعطيل المستخدم بنجاح")

    @action(detail=False, methods=["get"])
    def stats(self, request):
        return api_response(data={
            "total_admins": User.objects.filter(role=User.Role.ADMIN).count(),
            "total_supervisors": User.objects.filter(role=User.Role.SUPERVISOR).count(),
            "total_teachers": User.objects.filter(role=User.Role.TEACHER).count(),
            "total_students": User.objects.filter(role=User.Role.STUDENT).count(),
            "pending_count": User.objects.filter(is_approved=User.ApprovalStatus.PENDING).count(),
            "approved_count": User.objects.filter(is_approved=User.ApprovalStatus.APPROVED).count(),
            "rejected_count": User.objects.filter(is_approved=User.ApprovalStatus.REJECTED).count(),
        })


# ─── REGISTRATION VIEWSET ──────────────────────

class RegistrationViewSet(viewsets.GenericViewSet):
    queryset = User.objects.filter(is_approved=User.ApprovalStatus.PENDING)
    serializer_class = RegistrationRequestSerializer
    search_fields = ["full_name_ar", "email", "phone"]
    filterset_fields = ["role", "is_approved"]

    def get_permissions(self):
        if self.action == "create":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsSupervisorOrAdmin()]

    def list(self, request):
        if request.user.role not in ("admin", "supervisor"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        qs = User.objects.filter(is_approved=User.ApprovalStatus.PENDING)
        role = request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        search = request.query_params.get("search", "")
        if search:
            qs = qs.filter(
                Q(full_name_ar__icontains=search) | Q(email__icontains=search)
            )
        qs = qs.order_by("-date_joined")
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return api_response(data=serializer.data)

    def retrieve(self, request, pk=None):
        instance = get_object_or_404(User, pk=pk)
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)

    def create(self, request):
        serializer = RegistrationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        user = serializer.save()
        return api_response(
            data=RegistrationRequestSerializer(user).data,
            message="تم تقديم طلب التسجيل بنجاح",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        user = get_object_or_404(User, pk=pk)
        if user.is_approved != User.ApprovalStatus.PENDING:
            return api_response(
                message="لا يمكن اعتماد طلب تمت معالجته مسبقاً",
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
            )
        user.is_approved = User.ApprovalStatus.APPROVED
        user.save(update_fields=["is_approved"])
        return api_response(data=RegistrationRequestSerializer(user).data, message="تم اعتماد الطلب")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        user = get_object_or_404(User, pk=pk)
        if user.is_approved != User.ApprovalStatus.PENDING:
            return api_response(
                message="لا يمكن رفض طلب تمت معالجته مسبقاً",
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
            )
        user.is_approved = User.ApprovalStatus.REJECTED
        user.rejection_reason = request.data.get("reason", "")
        user.save(update_fields=["is_approved", "rejection_reason"])
        return api_response(data=RegistrationRequestSerializer(user).data, message="تم رفض الطلب")

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        ids = request.data.get("ids", [])
        action_type = request.data.get("action", "approve")
        if not ids:
            return api_response(message="يرجى تقديم قائمة ids", status=status.HTTP_400_BAD_REQUEST, success=False)

        users = User.objects.filter(id__in=ids, is_approved=User.ApprovalStatus.PENDING)
        if action_type == "approve":
            users.update(is_approved=User.ApprovalStatus.APPROVED)
            msg = f"تم اعتماد {users.count()} طلب"
        else:
            users.update(is_approved=User.ApprovalStatus.REJECTED)
            msg = f"تم رفض {users.count()} طلب"
        return api_response(message=msg)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        return api_response(data={
            "total_circles": Circle.objects.count(),
            "total_teachers": User.objects.filter(role=User.Role.TEACHER).count(),
            "total_students": User.objects.filter(role=User.Role.STUDENT).count(),
            "total_approved": User.objects.filter(is_approved=User.ApprovalStatus.APPROVED).count(),
            "pending_students": User.objects.filter(role=User.Role.STUDENT, is_approved=User.ApprovalStatus.PENDING).count(),
            "pending_teachers": User.objects.filter(role=User.Role.TEACHER, is_approved=User.ApprovalStatus.PENDING).count(),
            "pending_supervisors": User.objects.filter(role=User.Role.SUPERVISOR, is_approved=User.ApprovalStatus.PENDING).count(),
        })


# ─── CIRCLES VIEWSET ───────────────────────────

class CircleViewSet(viewsets.ModelViewSet):
    queryset = Circle.objects.all()
    search_fields = ["name", "teacher__full_name_ar"]
    filterset_fields = ["status", "gender"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CircleDetailSerializer
        if self.action == "create":
            return CircleCreateSerializer
        return CircleListSerializer

    def get_permissions(self):
        if self.action in ("create", "destroy", "enroll", "remove_student"):
            return [permissions.IsAuthenticated(), IsSupervisorOrAdmin()]
        return [permissions.IsAuthenticated(), IsTeacherOrAbove()]

    def get_queryset(self):
        qs = Circle.objects.select_related("teacher").annotate(
            active_students_count=Count(
                "enrollments", filter=Q(enrollments__status=CircleEnrollment.Status.ACTIVE)
            ),
            sessions_count=Count("sessions"),
            last_session_date=Max("sessions__session_date"),
        )
        if self.request.user.role == User.Role.TEACHER:
            qs = qs.filter(teacher=self.request.user)
        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        circle = serializer.save()
        return api_response(
            data=CircleDetailSerializer(circle, context={"request": request}).data,
            message="تم إنشاء الحلقة بنجاح",
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = CircleCreateSerializer(instance, data=request.data, partial=True)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        serializer.save()
        return api_response(
            data=CircleDetailSerializer(instance, context={"request": request}).data,
            message="تم تحديث الحلقة",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.status = Circle.Status.INACTIVE
        instance.save(update_fields=["status"])
        return api_response(message="تم أرشفة الحلقة بنجاح")

    @action(detail=True, methods=["get"])
    def students(self, request, pk=None):
        circle = self.get_object()
        enrollments = circle.enrollments.filter(
            status=CircleEnrollment.Status.ACTIVE
        ).select_related("student")
        data = [
            {"id": e.student_id, "full_name_ar": e.student.full_name_ar, "enrolled_at": e.enrolled_at}
            for e in enrollments
        ]
        return api_response(data=data)

    @action(detail=True, methods=["post"])
    def enroll(self, request, pk=None):
        circle = self.get_object()
        serializer = CircleEnrollSerializer(data=request.data, context={"circle": circle})
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        enrollment = serializer.save()
        return api_response(
            data={"id": enrollment.id, "student_id": enrollment.student_id, "circle_id": enrollment.circle_id},
            message="تم تسجيل الطالب في الحلقة",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def remove_student(self, request, pk=None):
        circle = self.get_object()
        serializer = CircleRemoveStudentSerializer(data=request.data, context={"circle": circle})
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        enrollment = serializer.save()
        return api_response(message="تم إزالة الطالب من الحلقة")

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        circle = self.get_object()
        total_students = circle.enrollments.filter(status=CircleEnrollment.Status.ACTIVE).count()
        total_sessions = circle.sessions.count()
        present_count = Attendance.objects.filter(
            session__circle=circle, status__in=["present", "late"]
        ).count()
        absent_count = Attendance.objects.filter(
            session__circle=circle, status="absent"
        ).count()
        total_att = present_count + absent_count
        rate = round(present_count / total_att * 100, 1) if total_att else 0
        return api_response(data={
            "total_students": total_students,
            "total_completed_sessions": total_sessions,
            "present_count": present_count,
            "absent_count": absent_count,
            "attendance_rate": rate,
        })


# ─── SESSIONS VIEWSET ──────────────────────────

class SessionViewSet(viewsets.ModelViewSet):
    queryset = Session.objects.select_related("circle__teacher").all()
    filterset_fields = ["circle", "session_date"]

    def get_serializer_class(self):
        if self.action == "create":
            return SessionCreateSerializer
        return SessionListSerializer

    def get_permissions(self):
        if self.action == "attendance_intent":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsTeacherOrAbove()]

    def get_queryset(self):
        qs = Session.objects.select_related("circle__teacher").annotate(
            present_count=Count(
                "attendance_records",
                filter=Q(attendance_records__status__in=["present", "late"]),
            ),
            absent_count=Count(
                "attendance_records",
                filter=Q(attendance_records__status="absent"),
            ),
            total_enrolled=Count(
                "circle__enrollments",
                filter=Q(circle__enrollments__status=CircleEnrollment.Status.ACTIVE),
            ),
        )
        if self.request.user.role == User.Role.TEACHER:
            qs = qs.filter(circle__teacher=self.request.user)
        return qs.order_by("-session_date")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        circle_id = request.query_params.get("circle")
        if circle_id:
            queryset = queryset.filter(circle_id=circle_id)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        session = serializer.save()
        return api_response(
            data=SessionListSerializer(session, context={"request": request}).data,
            message="تم إنشاء الجلسة",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def submit_attendance(self, request, pk=None):
        session = self.get_object()
        serializer = BatchAttendanceSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)

        records_data = serializer.validated_data["records"]
        enrolled = CircleEnrollment.objects.filter(
            circle=session.circle, status=CircleEnrollment.Status.ACTIVE
        ).values_list("student_id", flat=True)

        submitted_ids = set()
        for rec in records_data:
            sid = rec["student_id"]
            Attendance.objects.update_or_create(
                session=session, student_id=sid,
                defaults={"status": rec["status"]},
            )
            submitted_ids.add(sid)

        for sid in enrolled:
            if sid not in submitted_ids:
                Attendance.objects.update_or_create(
                    session=session, student_id=sid,
                    defaults={"status": Attendance.Status.ABSENT},
                )

        return api_response(message="تم تسجيل الحضور بنجاح")

    @action(detail=True, methods=["get"])
    def attendance(self, request, pk=None):
        session = self.get_object()
        records = Attendance.objects.filter(session=session).select_related("student")
        serializer = AttendanceRecordSerializer(records, many=True)
        return api_response(data=serializer.data)

    @action(detail=True, methods=["get"], url_path="join-link")
    def join_link(self, request, pk=None):
        session = self.get_object()
        if not session.is_unlocked:
            return api_response(
                message="لا يمكن الدخول الآن. الحصة ستفتح قبل موعدها بـ 15 دقيقة",
                success=False,
                status=status.HTTP_403_FORBIDDEN,
            )
        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken()
        token["session_id"] = str(session.id)
        token["circle_id"] = str(session.circle_id)
        token["teacher_id"] = str(session.circle.teacher_id)
        token["purpose"] = "session_join"
        return api_response(data={
            "access_token": str(token),
            "meeting_url": session.meeting_url or "",
            "meeting_platform": session.meeting_platform or "",
            "meeting_id": session.meeting_id or "",
            "meeting_password": session.meeting_password or "",
            "session_type": session.session_type,
            "is_online": session.is_online,
        })

    @action(detail=True, methods=["get", "post"], url_path="attendance-intent", permission_classes=[permissions.IsAuthenticated])
    def attendance_intent(self, request, pk=None):
        session = self.get_object()
        if request.user.role != User.Role.STUDENT:
            return api_response(message="للطلاب فقط", status=status.HTTP_403_FORBIDDEN, success=False)
        if request.method == "GET":
            intent, _ = SessionAttendanceIntent.objects.get_or_create(
                session=session, student=request.user,
            )
            return api_response(data={
                "intent": intent.intent,
                "reason": intent.reason,
            })
        intent, _ = SessionAttendanceIntent.objects.get_or_create(
            session=session, student=request.user,
        )
        intent.intent = request.data.get("intent", SessionAttendanceIntent.Intent.UNDECIDED)
        intent.reason = request.data.get("reason", "")
        intent.save()
        return api_response(
            message="تم تسجيل حالتك بنجاح",
            data={"intent": intent.intent, "reason": intent.reason},
        )

    @action(detail=True, methods=["post"], url_path="reschedule")
    def reschedule(self, request, pk=None):
        session = self.get_object()
        if request.user.role == User.Role.TEACHER and session.circle.teacher != request.user:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)

        proposed_date_str = request.data.get("proposed_date", "")
        proposed_time_str = request.data.get("proposed_time", "")
        reason = request.data.get("reason", "")

        if not proposed_date_str:
            return api_response(message="التاريخ المقترح مطلوب", status=status.HTTP_400_BAD_REQUEST, success=False)

        from datetime import datetime
        proposed_date = datetime.strptime(proposed_date_str, "%Y-%m-%d").date()
        proposed_time = None
        if proposed_time_str:
            try:
                proposed_time = datetime.strptime(proposed_time_str, "%H:%M").time()
            except ValueError:
                pass

        old_date = session.session_date
        old_time = session.session_time

        session.session_date = proposed_date
        if proposed_time:
            session.session_time = proposed_time
        session.save(update_fields=["session_date", "session_time"])

        SessionRescheduleRequest.objects.create(
            session=session,
            requested_by=request.user,
            proposed_date=proposed_date,
            proposed_time=proposed_time,
            reason=reason,
            status=SessionRescheduleRequest.Status.APPROVED,
        )

        from apps.notifications.models import Notification
        admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
        from datetime import date as ddate
        for admin in admins:
            Notification.objects.create(
                recipient=admin,
                type=Notification.Type.RESCHEDULE_REQUEST,
                title="تعديل موعد حصة من قبل معلم",
                message=f"قام {request.user.full_name_ar} بتعديل موعد حصة {session.circle.name} من {old_date}" +
                        (f" {old_time.strftime('%H:%M')}" if old_time else "") +
                        f" إلى {proposed_date}" +
                        (f" {proposed_time.strftime('%H:%M')}" if proposed_time else "") +
                        (f". السبب: {reason}" if reason else ""),
                link=f"/dashboard/teacher/sessions/manage/",
            )

        return api_response(
            message="تم تعديل موعد الحصة بنجاح",
            data={
                "session_date": str(proposed_date),
                "session_time": str(proposed_time) if proposed_time else None,
            },
        )


# ─── ATTENDANCE VIEWSET ────────────────────────

class AttendanceViewSet(viewsets.GenericViewSet):
    queryset = Attendance.objects.all()
    serializer_class = AttendanceRecordSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), IsTeacherOrAbove()]

    def partial_update(self, request, pk=None):
        record = self.get_object()
        if request.user.role == User.Role.TEACHER and record.session.circle.teacher != request.user:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)

        new_status = request.data.get("status")
        if new_status not in dict(Attendance.Status.choices):
            return api_response(message="حالة غير صالحة", status=status.HTTP_400_BAD_REQUEST, success=False)

        record.status = new_status
        record.save(update_fields=["status"])
        return api_response(
            data=AttendanceRecordSerializer(record).data,
            message="تم تحديث حالة الحضور",
        )


class AttendanceChartView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAdmin]

    def get(self, request):
        circles = Circle.objects.filter(status=Circle.Status.ACTIVE)[:8]
        data = []
        for c in circles:
            present = Attendance.objects.filter(
                session__circle=c, status__in=["present", "late"]
            ).count()
            absent = Attendance.objects.filter(
                session__circle=c, status="absent"
            ).count()
            data.append({"circle_name": c.name, "present_count": present, "absent_count": absent})
        serializer = AttendanceChartSerializer(data, many=True)
        return api_response(data=serializer.data)


class AttendanceTrendView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAdmin]

    def get(self, request):
        months_data = []
        now = timezone.now()
        for i in range(6, -1, -1):
            month_start = now.replace(day=1) - timedelta(days=30 * i)
            month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            present = Attendance.objects.filter(
                session__session_date__gte=month_start.date(),
                session__session_date__lte=month_end.date(),
                status__in=["present", "late"],
            ).count()
            absent = Attendance.objects.filter(
                session__session_date__gte=month_start.date(),
                session__session_date__lte=month_end.date(),
                status="absent",
            ).count()
            months_data.append({
                "month": month_start.strftime("%Y-%m"),
                "present": present,
                "absent": absent,
            })
        serializer = AttendanceTrendSerializer(months_data, many=True)
        return api_response(data=serializer.data)


# ─── GRADES VIEWSET ────────────────────────────

class RecitationGradeViewSet(viewsets.ModelViewSet):
    queryset = RecitationGrade.objects.select_related("session__circle", "student", "criterion").all()
    serializer_class = RecitationGradeSerializer
    filterset_fields = ["session", "student", "criterion"]
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAbove]

    def get_queryset(self):
        qs = RecitationGrade.objects.select_related("session__circle", "student", "criterion")
        if self.request.user.role == User.Role.TEACHER:
            qs = qs.filter(session__circle__teacher=self.request.user)
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = RecitationGradeCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        grade = serializer.save()
        return api_response(
            data=RecitationGradeSerializer(grade).data,
            message="تم تسجيل الدرجة",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"])
    def teacher_chart(self, request):
        teachers = User.objects.filter(role=User.Role.TEACHER, is_approved=User.ApprovalStatus.APPROVED)
        data = []
        for t in teachers:
            m_count = MemorizationProgress.objects.filter(
                enrollment__circle__teacher=t, type="hifz"
            ).count()
            r_count = MemorizationProgress.objects.filter(
                enrollment__circle__teacher=t, type="murajaa"
            ).count()
            data.append({
                "teacher_name": t.full_name_ar,
                "memorization_count": m_count,
                "review_count": r_count,
            })
        serializer = TeacherChartSerializer(data, many=True)
        return api_response(data=serializer.data)


# ─── JUSTIFICATIONS VIEWSET ────────────────────

class AbsenceJustificationViewSet(viewsets.GenericViewSet):
    queryset = Attendance.objects.all()
    serializer_class = AbsenceJustificationSerializer
    filterset_fields = ["student", "status"]

    def get_permissions(self):
        if self.action in ("approve", "reject"):
            return [permissions.IsAuthenticated(), IsTeacherOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = Attendance.objects.select_related("student", "session__circle")
        user = self.request.user
        if user.role == User.Role.STUDENT:
            qs = qs.filter(student=user)
        elif user.role == User.Role.TEACHER:
            qs = qs.filter(session__circle__teacher=user)
        return qs

    def list(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request):
        session_id = request.data.get("session_id")
        reason = request.data.get("reason", "")
        if not session_id:
            return api_response(message="session_id مطلوب", status=status.HTTP_400_BAD_REQUEST, success=False)
        try:
            session = Session.objects.get(pk=session_id)
        except Session.DoesNotExist:
            return api_response(message="الجلسة غير موجودة", status=status.HTTP_404_NOT_FOUND, success=False)

        if request.user.role == User.Role.STUDENT:
            att, created = Attendance.objects.get_or_create(
                session=session, student=request.user,
                defaults={
                    "status": Attendance.Status.PENDING_JUSTIFICATION,
                    "justification": reason,
                },
            )
            if not created:
                if att.status in (Attendance.Status.ABSENT, Attendance.Status.PENDING_JUSTIFICATION):
                    att.status = Attendance.Status.PENDING_JUSTIFICATION
                    att.justification = reason or att.justification
                    att.save(update_fields=["status", "justification"])
            return api_response(
                data=AbsenceJustificationSerializer(att).data,
                message="تم تقديم طلب التبرير",
                status=status.HTTP_201_CREATED,
            )
        return api_response(message="غير مصرح", status=status.HTTP_403_FORBIDDEN, success=False)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        record = self.get_object()
        from django.utils import timezone
        record.status = Attendance.Status.EXCUSED
        record.teacher_remark = request.data.get("teacher_remark", record.teacher_remark)
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.save(update_fields=["status", "teacher_remark", "reviewed_by", "reviewed_at"])
        return api_response(
            data=AbsenceJustificationSerializer(record).data,
            message="تم قبول التبرير",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        record = self.get_object()
        from django.utils import timezone
        record.status = Attendance.Status.ABSENT
        record.teacher_remark = request.data.get("teacher_remark", record.teacher_remark)
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.save(update_fields=["status", "teacher_remark", "reviewed_by", "reviewed_at"])
        return api_response(
            data=AbsenceJustificationSerializer(record).data,
            message="تم رفض التبرير",
        )


# ─── REQUESTS VIEWSET ──────────────────────────

class RequestViewSet(viewsets.ModelViewSet):
    queryset = SupportRequest.objects.select_related("submitted_by").prefetch_related("comments__author").all()
    search_fields = ["title", "body", "submitted_by__full_name_ar"]
    filterset_fields = ["type", "status", "priority"]

    def get_serializer_class(self):
        if self.action == "create":
            return SupportRequestCreateSerializer
        return SupportRequestSerializer

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = SupportRequest.objects.select_related("submitted_by").prefetch_related("comments__author")
        if self.request.user.role not in ("admin", "supervisor"):
            qs = qs.filter(submitted_by=self.request.user)
        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if request.user.role not in ("admin", "supervisor") and instance.submitted_by != request.user:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        req = serializer.save()
        return api_response(
            data=SupportRequestSerializer(req).data,
            message="تم تقديم الطلب",
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        if request.user.role not in ("admin", "supervisor"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def comments(self, request, pk=None):
        req = self.get_object()
        if request.user.role not in ("admin", "supervisor") and req.submitted_by != request.user:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        serializer = CommentCreateSerializer(
            data=request.data,
            context={"request": request, "request_obj": req},
        )
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        comment = serializer.save()
        return api_response(
            data=CommentSerializer(comment).data,
            message="تم إضافة التعليق",
            status=status.HTTP_201_CREATED,
        )


# ─── ANNOUNCEMENTS VIEWSET ─────────────────────

class AnnouncementViewSet(viewsets.ModelViewSet):
    queryset = Announcement.objects.select_related("author").all()
    serializer_class = AnnouncementSerializer
    search_fields = ["title", "body"]
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return AnnouncementCreateSerializer
        return AnnouncementSerializer

    def get_queryset(self):
        return Announcement.objects.select_related("author").order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def create(self, request, *args, **kwargs):
        if request.user.role not in ("admin", "supervisor"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        serializer = self.get_serializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        ann = serializer.save()
        return api_response(
            data=AnnouncementSerializer(ann).data,
            message="تم إنشاء الإعلان",
            status=status.HTTP_201_CREATED,
        )


# ─── NOTIFICATIONS VIEWSET ─────────────────────

class NotificationViewSet(viewsets.GenericViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    filterset_fields = ["is_read", "type"]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by("-created_at")

    def list(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    @action(detail=True, methods=["patch"])
    def read(self, request, pk=None):
        notif = self.get_object()
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        return api_response(data=NotificationSerializer(notif).data, message="تم تحديد الإشعار كمقروء")

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return api_response(message="تم تحديد الكل كمقروء")

    @action(detail=False, methods=["get"])
    def count(self, request):
        unread = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return api_response(data={"unread": unread})


# ─── REPORTS VIEWS ─────────────────────────────

class DashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAdmin]

    def get(self, request):
        total_hifz_ayahs = MemorizationProgress.objects.filter(type='hifz').aggregate(
            t=Sum(F('ayah_to') - F('ayah_from') + 1)
        )['t'] or 0
        total_murajaa_ayahs = MemorizationProgress.objects.filter(type='murajaa').aggregate(
            t=Sum(F('ayah_to') - F('ayah_from') + 1)
        )['t'] or 0
        h_juz, h_qua = ayahs_to_juz_quarters(total_hifz_ayahs)
        m_juz, m_qua = ayahs_to_juz_quarters(total_murajaa_ayahs)
        return api_response(data={
            "total_circles": Circle.objects.filter(status=Circle.Status.ACTIVE).count(),
            "total_teachers": User.objects.filter(role=User.Role.TEACHER).count(),
            "total_supervisors": User.objects.filter(role=User.Role.SUPERVISOR).count(),
            "total_students": User.objects.filter(role=User.Role.STUDENT).count(),
            "total_hifz_juz": h_juz, "total_hifz_quarters": h_qua,
            "total_hifz_ayahs": total_hifz_ayahs,
            "total_murajaa_juz": m_juz, "total_murajaa_quarters": m_qua,
            "total_murajaa_ayahs": total_murajaa_ayahs,
        })


class StudentStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAdmin]

    def get(self, request):
        from apps.circles.models import CircleEnrollment
        from apps.memorization.models import MemorizationProgress, RecitationGrade
        from django.db.models import Avg

        UserModel = User
        total_students = UserModel.objects.filter(role=User.Role.STUDENT).count()

        enrolled_ids = CircleEnrollment.objects.filter(
            status=CircleEnrollment.Status.ACTIVE
        ).values_list("student_id", flat=True).distinct()
        total_enrolled = len(enrolled_ids)

        withdrawn_ids = CircleEnrollment.objects.filter(
            status=CircleEnrollment.Status.INACTIVE
        ).values_list("student_id", flat=True).distinct()
        total_withdrawn = len(withdrawn_ids)

        student_avgs = list(
            RecitationGrade.objects.filter(
                student__enrollments__status=CircleEnrollment.Status.ACTIVE
            ).values("student").annotate(
                avg_score=Avg("score")
            ).values_list("student", "avg_score")
        )

        excellent = 0
        good = 0
        weak = 0
        for sid, avg in student_avgs:
            if avg and avg >= 85:
                excellent += 1
            elif avg and avg >= 60:
                good += 1
            else:
                weak += 1

        total_graduates = UserModel.objects.filter(
            role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED
        ).count()

        return api_response(data={
            "total_graduated": 0,
            "total_students": total_students,
            "total_withdrawn": total_withdrawn,
            "total_graduates": total_graduates,
            "levels": {
                "excellent": excellent,
                "good": good,
                "weak": weak,
            },
        })


class TeacherStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAdmin]

    def get(self, request):
        total = User.objects.filter(role=User.Role.TEACHER).count()
        active = User.objects.filter(role=User.Role.TEACHER, is_active=True).count()
        inactive = total - active
        memorized_ayahs = MemorizationProgress.objects.filter(
            type="hifz", status="mastered"
        ).aggregate(
            t=Sum(F("ayah_to") - F("ayah_from") + 1)
        )["t"] or 0
        m_juz, m_qua = ayahs_to_juz_quarters(memorized_ayahs)
        return api_response(data={
            "total_teachers": total,
            "total_active_accounts": active,
            "total_inactive_accounts": inactive,
            "total_memorized_ayahs": memorized_ayahs,
            "total_memorized_juz": m_juz,
            "total_memorized_quarters": m_qua,
        })


class UrgentAlertsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAdmin]

    def get(self, request):
        alerts = []

        pending_count = User.objects.filter(is_approved=User.ApprovalStatus.PENDING).count()
        if pending_count > 0:
            alerts.append({
                "type": "registration",
                "title": "طلبات تسجيل جديدة",
                "body": f"{pending_count} طلب بانتظار المراجعة",
                "count": pending_count,
                "link": "/registration",
            })

        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        repeated = (
            Attendance.objects.filter(
                status="absent",
                session__session_date__gte=thirty_days_ago.date(),
            )
            .values("student")
            .annotate(count=Count("id"))
            .filter(count__gt=3)
        )
        if repeated.count() > 0:
            alerts.append({
                "type": "absence",
                "title": "طلاب متغيبون بشكل متكرر",
                "body": f"{repeated.count()} طالب تغيبوا أكثر من 3 مرات هذا الشهر",
                "count": repeated.count(),
                "link": "/attendance",
            })

        three_weeks_ago = now - timedelta(days=21)
        inactive = Circle.objects.filter(
            status=Circle.Status.ACTIVE
        ).annotate(
            last_session=Max("sessions__session_date")
        ).filter(
            Q(last_session__lt=three_weeks_ago.date()) | Q(last_session__isnull=True)
        )
        icount = inactive.count()
        if icount > 0:
            alerts.append({
                "type": "inactive_circle",
                "title": "حلقات متوقفة",
                "body": f"{icount} حلقة لم تُعقد منذ 3 أسابيع",
                "count": icount,
                "link": "/circles",
            })

        urgent_requests = SupportRequest.objects.filter(
            priority__in=["urgent", "high"],
            status__in=["submitted", "under_review"],
        ).count()
        if urgent_requests > 0:
            alerts.append({
                "type": "urgent_request",
                "title": "طلبات عاجلة",
                "body": f"{urgent_requests} طلب بانتظار المراجعة",
                "count": urgent_requests,
                "link": "/requests",
            })

        return api_response(data=alerts)


# ─── EXAMS API ─────────────────────────────────

class ExamViewSet(viewsets.ModelViewSet):
    queryset = Exam.objects.select_related("circle", "created_by", "assigned_teacher").all()
    filterset_fields = ["status", "circle", "exam_type"]
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return ExamCreateSerializer
        return ExamListSerializer

    def get_queryset(self):
        qs = Exam.objects.select_related("circle", "created_by", "assigned_teacher").all()
        user = self.request.user
        if user.role == User.Role.TEACHER:
            my_circles = Circle.objects.filter(teacher=user, status=Circle.Status.ACTIVE)
            qs = qs.filter(
                Q(assigned_teacher=user) | Q(circle__in=my_circles),
                status__in=[Exam.Status.PUBLISHED, Exam.Status.GRADING],
            )
        elif user.role == User.Role.STUDENT:
            qs = qs.filter(status=Exam.Status.PUBLISHED)
        return qs.order_by("-exam_date")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        if request.user.role not in ("admin", "supervisor"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        serializer = self.get_serializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        exam = serializer.save()
        return api_response(
            data=ExamListSerializer(exam, context={"request": request}).data,
            message="تم إنشاء الامتحان",
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ExamListSerializer(instance, context={"request": request})
        return api_response(data=serializer.data)

    def partial_update(self, request, *args, **kwargs):
        if request.user.role not in ("admin", "supervisor"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        instance = self.get_object()
        serializer = ExamCreateSerializer(instance, data=request.data, partial=True, context={"request": request})
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        serializer.save()
        return api_response(data=ExamListSerializer(instance).data, message="تم تحديث الامتحان")

    def destroy(self, request, *args, **kwargs):
        if request.user.role not in ("admin", "supervisor"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        instance = self.get_object()
        instance.delete()
        return api_response(message="تم حذف الامتحان")

    @action(detail=True, methods=["get"])
    def marks(self, request, pk=None):
        exam = self.get_object()
        marks_qs = ExamMark.objects.filter(exam=exam).select_related("student", "entered_by", "approved_by")
        serializer = ExamMarkSerializer(marks_qs, many=True)
        return api_response(data=serializer.data)

    @action(detail=True, methods=["post"])
    def grade(self, request, pk=None):
        if request.user.role not in ("admin", "supervisor", "teacher"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        exam = self.get_object()
        serializer = ExamMarkCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)

        mark = save_mark(
            exam=exam,
            student_id=serializer.validated_data["student_id"],
            marks_obtained=serializer.validated_data["marks_obtained"],
            entered_by=request.user,
            teacher_notes=serializer.validated_data.get("teacher_notes", ""),
            private_notes=serializer.validated_data.get("private_notes", ""),
        )
        return api_response(
            data=ExamMarkSerializer(mark).data,
            message="تم تسجيل الدرجة",
        )

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        if request.user.role not in ("admin", "supervisor"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        exam = self.get_object()
        exam.status = Exam.Status.PUBLISHED
        exam.save(update_fields=["status"])
        notify_published(exam, request.user)
        return api_response(message="تم نشر الامتحان")

    @action(detail=True, methods=["post"])
    def submit_approval(self, request, pk=None):
        if request.user.role not in ("admin", "supervisor", "teacher"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        exam = self.get_object()
        success, error = submit_for_approval(exam, request.user)
        return api_response(
            message=error if error else "تم تقديم الامتحان للاعتماد",
            success=success,
            status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        if request.user.role not in ("admin", "supervisor"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        exam = self.get_object()
        approve_all_marks(exam, request.user)
        return api_response(message="تم اعتماد جميع النتائج")

    @action(detail=True, methods=["post"])
    def reject_marks(self, request, pk=None):
        if request.user.role not in ("admin", "supervisor"):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        exam = self.get_object()
        mark_ids = request.data.get("mark_ids", [])
        reason = request.data.get("reason", "")
        if not mark_ids:
            return api_response(message="لم يتم تحديد درجات للرفض", success=False, status=status.HTTP_400_BAD_REQUEST)
        reject_marks(exam, mark_ids, request.user, reason)
        return api_response(message="تم رفض الدرجات المحددة")


# ─── REVIEW / RECITATION REQUESTS API ───────────

class ReviewRequestViewSet(viewsets.ModelViewSet):
    queryset = ReviewRequest.objects.select_related(
        "student", "circle", "surah", "reviewed_by"
    ).all()
    filterset_fields = ["circle", "type", "status", "student"]
    search_fields = ["student__full_name_ar", "notes"]

    def get_serializer_class(self):
        if self.action == "create":
            return ReviewRequestCreateSerializer
        if self.action in ("approve", "reject"):
            return ReviewRequestActionSerializer
        return ReviewRequestSerializer

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated()]
        if self.action in ("approve", "reject"):
            return [permissions.IsAuthenticated(), IsTeacherOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = ReviewRequest.objects.select_related("student", "circle", "surah", "reviewed_by")
        user = self.request.user
        if user.role == User.Role.STUDENT:
            qs = qs.filter(student=user)
        elif user.role == User.Role.TEACHER:
            qs = qs.filter(circle__teacher=user)
        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        if request.user.role != User.Role.STUDENT:
            return api_response(message="فقط الطلاب يمكنهم تقديم الطلبات", status=status.HTTP_403_FORBIDDEN, success=False)
        serializer = self.get_serializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        req = serializer.save()
        return api_response(
            data=ReviewRequestSerializer(req, context={"request": request}).data,
            message="تم تقديم الطلب",
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        req = self.get_object()
        if req.status != ReviewRequest.Status.PENDING:
            return api_response(message="تمت معالجة الطلب مسبقاً", success=False, status=status.HTTP_400_BAD_REQUEST)
        req.status = ReviewRequest.Status.APPROVED
        req.reviewed_by = request.user
        req.save(update_fields=["status", "reviewed_by"])
        return api_response(
            data=ReviewRequestSerializer(req, context={"request": request}).data,
            message="تم قبول الطلب",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        req = self.get_object()
        if req.status != ReviewRequest.Status.PENDING:
            return api_response(message="تمت معالجة الطلب مسبقاً", success=False, status=status.HTTP_400_BAD_REQUEST)
        req.status = ReviewRequest.Status.REJECTED
        req.reviewed_by = request.user
        req.rejection_reason = request.data.get("rejection_reason", "")
        req.save(update_fields=["status", "reviewed_by", "rejection_reason"])
        return api_response(
            data=ReviewRequestSerializer(req, context={"request": request}).data,
            message="تم رفض الطلب",
        )


# ─── SESSION STUDENT NOTES API ──────────────────

class SessionStudentNoteViewSet(viewsets.ModelViewSet):
    queryset = SessionStudentNote.objects.select_related("session", "student").all()
    filterset_fields = ["session", "student"]

    def get_serializer_class(self):
        if self.action == "create":
            return SessionStudentNoteCreateSerializer
        return SessionStudentNoteSerializer

    def get_permissions(self):
        return [permissions.IsAuthenticated(), IsTeacherOrAbove()]

    def get_queryset(self):
        qs = SessionStudentNote.objects.select_related("session__circle", "student")
        if self.request.user.role == User.Role.TEACHER:
            qs = qs.filter(session__circle__teacher=self.request.user)
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        note = serializer.save()
        return api_response(
            data=SessionStudentNoteSerializer(note, context={"request": request}).data,
            message="تم إضافة الملاحظة",
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        serializer.save()
        return api_response(
            data=self.get_serializer(instance).data,
            message="تم تحديث الملاحظة",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return api_response(message="تم حذف الملاحظة")


# ─── MEMORIZATION PROGRESS API ──────────────────

class MemorizationProgressViewSet(viewsets.ModelViewSet):
    queryset = MemorizationProgress.objects.select_related(
        "enrollment__circle", "surah"
    ).all()
    filterset_fields = ["enrollment", "type", "status", "surah"]

    def get_serializer_class(self):
        if self.action == "create":
            return MemorizationProgressCreateSerializer
        return MemorizationProgressSerializer

    def get_permissions(self):
        if self.action in ("create", "destroy", "partial_update"):
            return [permissions.IsAuthenticated(), IsTeacherOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = MemorizationProgress.objects.select_related(
            "enrollment__circle__teacher", "surah"
        )
        user = self.request.user
        if user.role == User.Role.STUDENT:
            qs = qs.filter(enrollment__student=user)
        elif user.role == User.Role.TEACHER:
            qs = qs.filter(enrollment__circle__teacher=user)
        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        progress = serializer.save()
        return api_response(
            data=MemorizationProgressSerializer(progress, context={"request": request}).data,
            message="تم تسجيل التقدم",
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        serializer.save()
        return api_response(
            data=MemorizationProgressSerializer(instance, context={"request": request}).data,
            message="تم تحديث التقدم",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return api_response(message="تم حذف التقدم")


# ─── REFERENCE DATA API ─────────────────────────

class SurahViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Surah.objects.all()
    serializer_class = SurahSerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ["name_ar", "name_en"]
    ordering = ["id"]


class EvaluationCriterionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EvaluationCriterion.objects.filter(is_active=True)
    serializer_class = EvaluationCriterionSerializer
    permission_classes = [permissions.IsAuthenticated]


# ─── LESSON TOGGLES API ─────────────────────────

class SessionLessonToggleViewSet(viewsets.ModelViewSet):
    queryset = SessionLessonToggle.objects.select_related("session__circle", "surah").all()
    serializer_class = SessionLessonToggleSerializer
    filterset_fields = ["session", "surah", "is_active"]
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAbove]

    def get_queryset(self):
        qs = SessionLessonToggle.objects.select_related("session__circle", "surah")
        if self.request.user.role == User.Role.TEACHER:
            qs = qs.filter(session__circle__teacher=self.request.user)
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        toggle = serializer.save()
        return api_response(
            data=self.get_serializer(toggle).data,
            message="تم إضافة التبديل",
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        serializer.save()
        return api_response(
            data=self.get_serializer(instance).data,
            message="تم تحديث التبديل",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return api_response(message="تم حذف التبديل")


# ─── PROGRESS LOGS API ─────────────────────────

class ProgressLogViewSet(viewsets.GenericViewSet):
    queryset = ProgressLog.objects.select_related("student", "surah", "session__circle").all()
    filterset_fields = ["session", "student", "log_category", "surah"]
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return ProgressLogCreateSerializer
        return ProgressLogListSerializer

    def get_queryset(self):
        qs = ProgressLog.objects.select_related("student", "surah", "session__circle")
        user = self.request.user
        if user.role == User.Role.STUDENT:
            qs = qs.filter(student=user)
        elif user.role == User.Role.TEACHER:
            qs = qs.filter(session__circle__teacher=user)
        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        session_id = kwargs.get("session_id") or request.data.get("session_id")
        if not session_id:
            return api_response(message="session_id مطلوب", status=status.HTTP_400_BAD_REQUEST, success=False)
        try:
            session = Session.objects.get(pk=session_id)
        except Session.DoesNotExist:
            return api_response(message="الجلسة غير موجودة", status=status.HTTP_404_NOT_FOUND, success=False)

        if request.user.role == User.Role.TEACHER and session.circle.teacher_id != request.user.id:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)

        serializer = ProgressLogCreateSerializer(
            data=request.data,
            context={"request": request, "session": session},
        )
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_422_UNPROCESSABLE_ENTITY, success=False)
        log = serializer.save()
        return api_response(
            data=ProgressLogListSerializer(log, context={"request": request}).data,
            message="تم تسجيل التقييم بنجاح",
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)


# ─── SESSION RESCHEDULE REQUESTS API ───────────

class SessionRescheduleViewSet(viewsets.ModelViewSet):
    queryset = SessionRescheduleRequest.objects.select_related(
        "session__circle", "requested_by"
    ).all()
    filterset_fields = ["session", "status"]

    def get_serializer_class(self):
        if self.action == "create":
            return SessionRescheduleCreateSerializer
        return SessionRescheduleRequestSerializer

    def get_permissions(self):
        if self.action in ("approve", "reject"):
            return [permissions.IsAuthenticated(), IsSupervisorOrAdmin()]
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsTeacherOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = SessionRescheduleRequest.objects.select_related("session__circle", "requested_by")
        user = self.request.user
        if user.role == User.Role.TEACHER:
            qs = qs.filter(session__circle__teacher=user)
        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return api_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        session_id = request.data.get("session")
        if not session_id:
            return api_response(message="session مطلوب", status=status.HTTP_400_BAD_REQUEST, success=False)
        try:
            session = Session.objects.get(pk=session_id)
        except Session.DoesNotExist:
            return api_response(message="الجلسة غير موجودة", status=status.HTTP_404_NOT_FOUND, success=False)
        serializer = SessionRescheduleCreateSerializer(
            data=request.data,
            context={"request": request, "session": session},
        )
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        req = serializer.save()
        return api_response(
            data=SessionRescheduleRequestSerializer(req, context={"request": request}).data,
            message="تم تقديم طلب تعديل الموعد",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        req = self.get_object()
        if req.status != SessionRescheduleRequest.Status.PENDING:
            return api_response(message="تمت معالجة الطلب مسبقاً", success=False, status=status.HTTP_400_BAD_REQUEST)
        req.status = SessionRescheduleRequest.Status.APPROVED
        req.reviewed_by = request.user
        session = req.session
        session.session_date = req.proposed_date
        session.save(update_fields=["session_date"])
        req.save(update_fields=["status", "reviewed_by"])
        return api_response(
            data=SessionRescheduleRequestSerializer(req).data,
            message="تم قبول طلب تعديل الموعد",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        req = self.get_object()
        if req.status != SessionRescheduleRequest.Status.PENDING:
            return api_response(message="تمت معالجة الطلب مسبقاً", success=False, status=status.HTTP_400_BAD_REQUEST)
        req.status = SessionRescheduleRequest.Status.REJECTED
        req.reviewed_by = request.user
        req.rejection_reason = request.data.get("reason", "")
        req.save(update_fields=["status", "reviewed_by", "rejection_reason"])
        return api_response(
            data=SessionRescheduleRequestSerializer(req).data,
            message="تم رفض طلب تعديل الموعد",
        )
