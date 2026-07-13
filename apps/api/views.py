from datetime import date, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q, Sum, F, Max
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import status, viewsets, generics, permissions
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session, SessionStudentNote, SessionRescheduleRequest, SessionLessonToggle, SessionTurn
from apps.certificates.models import Certificate
from apps.attendance.models import Attendance, SessionAttendanceIntent
from apps.memorization.models import MemorizationProgress, RecitationGrade, ReviewRequest, ProgressLog, StudentAchievement, StudyTask
from apps.exams.models import Exam, ExamMark, ExamNotification, ExamApprovalHistory
from apps.exams.services import notify_published, submit_for_approval, approve_all_marks, reject_marks, save_mark
from apps.references.models import EvaluationCriterion, Surah
from apps.requests.models import SupportRequest, Comment
from apps.announcements.models import Announcement
from apps.notifications.models import Notification

from .serializers import (
    StudyTaskSerializer,
    StudyTaskWriteSerializer,
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
    SurahSerializer,
    EvaluationCriterionSerializer,
    SessionRescheduleRequestSerializer,
    SessionRescheduleCreateSerializer,
    SessionLessonToggleSerializer,
    SessionLessonToggleBatchSerializer,
    ProgressLogListSerializer,
    ProgressLogCreateSerializer,
    ProgressLogUpdateSerializer,
    SessionTurnSerializer,
    CertificateSerializer,
)
from .permissions import IsSupervisorOrAdmin, IsTeacherOrAbove, IsStudent, IsOwnerOrAdmin
from apps.references.utils import count_thumns, format_hizb_thumn
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
        if request.user.role != User.Role.MAIN_ADMIN and instance != request.user:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)

    def list(self, request, *args, **kwargs):
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
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
        if request.user.role != User.Role.MAIN_ADMIN and instance != request.user:
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
            "total_admins": User.objects.filter(role=User.Role.MAIN_ADMIN).count(),
            "total_supervisors": User.objects.filter(role=User.Role.SUB_ADMIN).count(),
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
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
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
            "pending_supervisors": User.objects.filter(role=User.Role.SUB_ADMIN, is_approved=User.ApprovalStatus.PENDING).count(),
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
        qs = Circle.objects.select_related(User.Role.TEACHER).annotate(
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
        if session.status != Session.Status.LIVE:
            return api_response(
                message="لا يمكن تسجيل الحضور إلا أثناء الحصة",
                success=False,
                status=status.HTTP_403_FORBIDDEN,
            )
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
                    defaults={"status": Attendance.Status.ABSENT_UNJUSTIFIED},
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
        if session.status not in (Session.Status.CONFIRMATION_OPEN, Session.Status.TURN_TAKING_OPEN, Session.Status.LIVE):
            return api_response(
                message="لا يمكن الدخول الآن. الحصة غير متاحة",
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
        if not CircleEnrollment.objects.filter(
            student=request.user, circle=session.circle,
            status=CircleEnrollment.Status.ACTIVE,
        ).exists():
            return api_response(message="غير مسجل في هذه الحلقة", status=status.HTTP_403_FORBIDDEN, success=False)
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
        admins = User.objects.filter(role=User.Role.MAIN_ADMIN, is_active=True)
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
    queryset = RecitationGrade.objects.select_related("session__circle", "student", "criterion").order_by(
        "-created_at", "-id"
    )
    serializer_class = RecitationGradeSerializer
    filterset_fields = ["session", "student", "criterion"]
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAbove]

    def get_queryset(self):
        qs = RecitationGrade.objects.select_related("session__circle", "student", "criterion")
        if self.request.user.role == User.Role.TEACHER:
            qs = qs.filter(session__circle__teacher=self.request.user)
        return qs.order_by("-created_at", "-id")

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
    queryset = Attendance.objects.select_related("student", "session__circle").order_by("-created_at", "-id")
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
        return qs.order_by("-created_at", "-id")

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
            from django.utils import timezone
            att, created = Attendance.objects.get_or_create(
                session=session, student=request.user,
                defaults={
                    "status": Attendance.Status.ABSENT_UNJUSTIFIED,
                    "justification": reason,
                    "justification_status": Attendance.JustificationStatus.PENDING,
                    "justification_submitted_at": timezone.now(),
                    "submitted_before_session": session.start_time and timezone.now() < session.start_time,
                },
            )
            if not created:
                if att.justification_status == Attendance.JustificationStatus.PENDING:
                    return api_response(
                        message="لديك طلب تبرير قيد المراجعة بالفعل",
                        success=False,
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if att.status == Attendance.Status.CONFIRMED:
                    att.status = Attendance.Status.NOT_RESPONDED
                att.justification = reason or att.justification
                att.justification_status = Attendance.JustificationStatus.PENDING
                att.justification_submitted_at = timezone.now()
                att.submitted_before_session = session.start_time and timezone.now() < session.start_time
                att.save(update_fields=[
                    "justification", "justification_status",
                    "justification_submitted_at", "submitted_before_session", "status",
                ])

            teacher = session.circle.teacher
            if teacher:
                Notification.objects.create(
                    recipient=teacher,
                    type=Notification.Type.ABSENCE_REVIEW,
                    title="تبرير غياب جديد",
                    message=f"قام الطالب {request.user.full_name_ar} بتقديم تبرير غياب لحصة {session.circle.name}",
                    link=f"/dashboard/teacher/absence-justifications/?justification_status=pending",
                )

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
        record.status = Attendance.Status.ABSENT_JUSTIFIED
        record.justification_status = Attendance.JustificationStatus.ACCEPTED
        record.teacher_comment = request.data.get("teacher_comment", record.teacher_comment)
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.save(update_fields=["status", "justification_status", "teacher_comment", "reviewed_by", "reviewed_at"])
        return api_response(
            data=AbsenceJustificationSerializer(record).data,
            message="تم قبول التبرير",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        record = self.get_object()
        from django.utils import timezone
        record.status = Attendance.Status.ABSENT_UNJUSTIFIED
        record.justification_status = Attendance.JustificationStatus.REFUSED
        record.teacher_comment = request.data.get("teacher_comment", record.teacher_comment)
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.save(update_fields=["status", "justification_status", "teacher_comment", "reviewed_by", "reviewed_at"])
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
        if self.request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
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
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN) and instance.submitted_by != request.user:
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
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def comments(self, request, pk=None):
        req = self.get_object()
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN) and req.submitted_by != request.user:
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
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
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
        total_hifz_thumns = count_thumns(
            MemorizationProgress.objects.filter(type='hifz')
            .values_list('surah_id', 'ayah_from', 'ayah_to')
        )
        total_murajaa_thumns = count_thumns(
            MemorizationProgress.objects.filter(type='murajaa')
            .values_list('surah_id', 'ayah_from', 'ayah_to')
        )
        return api_response(data={
            "total_circles": Circle.objects.filter(status=Circle.Status.ACTIVE).count(),
            "total_teachers": User.objects.filter(role=User.Role.TEACHER).count(),
            "total_supervisors": User.objects.filter(role=User.Role.SUB_ADMIN).count(),
            "total_students": User.objects.filter(role=User.Role.STUDENT).count(),
            "total_hifz_thumns": total_hifz_thumns,
            "total_hifz_units": format_hizb_thumn(total_hifz_thumns),
            "total_murajaa_thumns": total_murajaa_thumns,
            "total_murajaa_units": format_hizb_thumn(total_murajaa_thumns),
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
        memorized_thumns = count_thumns(
            MemorizationProgress.objects.filter(
                type="hifz", status="mastered"
            ).values_list("surah_id", "ayah_from", "ayah_to")
        )
        return api_response(data={
            "total_teachers": total,
            "total_active_accounts": active,
            "total_inactive_accounts": inactive,
            "total_memorized_thumns": memorized_thumns,
            "total_memorized_units": format_hizb_thumn(memorized_thumns),
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
            enrolled_circles = CircleEnrollment.objects.filter(
                student=user, status=CircleEnrollment.Status.ACTIVE
            ).values_list("circle_id", flat=True)
            qs = qs.filter(circle_id__in=enrolled_circles, status=Exam.Status.PUBLISHED)
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
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
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
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        instance = self.get_object()
        serializer = ExamCreateSerializer(instance, data=request.data, partial=True, context={"request": request})
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        serializer.save()
        return api_response(data=ExamListSerializer(instance).data, message="تم تحديث الامتحان")

    def destroy(self, request, *args, **kwargs):
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
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
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN, User.Role.TEACHER):
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
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        exam = self.get_object()
        exam.status = Exam.Status.PUBLISHED
        exam.save(update_fields=["status"])
        notify_published(exam, request.user)
        return api_response(message="تم نشر الامتحان")

    @action(detail=True, methods=["post"])
    def submit_approval(self, request, pk=None):
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN, User.Role.TEACHER):
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
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        exam = self.get_object()
        approve_all_marks(exam, request.user)
        return api_response(message="تم اعتماد جميع النتائج")

    @action(detail=True, methods=["post"])
    def reject_marks(self, request, pk=None):
        if request.user.role not in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
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
        try:
            # The pre_save integrity signal rejects requests from students who
            # are not actively enrolled in the target circle.
            req = serializer.save()
        except DjangoValidationError as e:
            return api_response(errors=e.messages, status=status.HTTP_400_BAD_REQUEST, success=False)
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
        from django.core.exceptions import ValidationError as DjangoValidationError
        req = self.get_object()
        try:
            req.approve(
                by=request.user,
                scheduled_date=request.data.get("scheduled_date") or None,
                scheduled_time=request.data.get("scheduled_time") or None,
                meeting_url=request.data.get("meeting_url", ""),
                meeting_platform=request.data.get("meeting_platform", ""),
            )
        except DjangoValidationError as e:
            return api_response(message=" ".join(e.messages), success=False, status=status.HTTP_400_BAD_REQUEST)
        return api_response(
            data=ReviewRequestSerializer(req, context={"request": request}).data,
            message="تم قبول الطلب وجدولته",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        from django.core.exceptions import ValidationError as DjangoValidationError
        req = self.get_object()
        try:
            req.reject(by=request.user, reason=request.data.get("rejection_reason", ""))
        except DjangoValidationError as e:
            return api_response(message=" ".join(e.messages), success=False, status=status.HTTP_400_BAD_REQUEST)
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

class MemorizationProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only. MemorizationProgress is the deprecated legacy tracker kept
    for historical data; all new progress is written through the session
    marking flow (ProgressLog) and study-task validation (MemorizationRecord).
    The former create/partial_update/destroy actions (and the web
    teacher_toggle_lesson status toggle) were removed so nothing bypasses
    what the teacher actually records."""
    queryset = MemorizationProgress.objects.select_related(
        "enrollment__circle", "surah"
    ).all()
    filterset_fields = ["enrollment", "type", "status", "surah"]
    serializer_class = MemorizationProgressSerializer
    permission_classes = [permissions.IsAuthenticated]

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

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)


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

    # ── Corrections: only the session's own teacher (or main admin) may fix
    # or remove a recorded entry; achievement totals are rebuilt (engine) ──
    def partial_update(self, request, *args, **kwargs):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from apps.memorization.engine import update_progress_log, can_modify_progress_log

        log = self.get_object()
        if not can_modify_progress_log(request.user, log):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        serializer = ProgressLogUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_422_UNPROCESSABLE_ENTITY, success=False)
        d = serializer.validated_data
        try:
            log = update_progress_log(
                log, request.user,
                log_category=d.get("log_category", log.log_category),
                surah=d.get("surah_number", log.surah_id),
                start_ayah=d.get("start_ayah", log.start_ayah),
                end_ayah=d.get("end_ayah", log.end_ayah),
                points=d.get("points", log.points),
                evaluation_grade=d.get("evaluation_grade", log.evaluation_grade),
                teacher_notes=d.get("teacher_notes", log.teacher_notes),
                completed_pages=d.get("completed_pages"),
            )
        except DjangoValidationError as e:
            # PermissionDenied is NOT caught: it propagates to DRF's handler
            # and surfaces as a proper 403 (can_modify is checked above, so
            # that path is a defense-in-depth backstop only).
            return api_response(
                message=getattr(e, "message", None) or "قيم غير صالحة",
                status=status.HTTP_422_UNPROCESSABLE_ENTITY, success=False,
            )
        return api_response(
            data=ProgressLogListSerializer(log, context={"request": request}).data,
            message="تم تعديل التسجيل",
        )

    def destroy(self, request, *args, **kwargs):
        from apps.memorization.engine import delete_progress_log, can_modify_progress_log

        log = self.get_object()
        if not can_modify_progress_log(request.user, log):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        delete_progress_log(log, request.user)
        return api_response(message="تم حذف التسجيل", status=status.HTTP_200_OK)


# ─── STUDY TASKS (Todos) API ───────────────────

class StudyTaskViewSet(viewsets.GenericViewSet):
    """Todo workflow: teachers assign/edit/validate/delete tasks for their
    students; students list their own tasks and mark them done."""
    queryset = StudyTask.objects.select_related(
        "student", "assigned_by", "circle", "session", "surah"
    ).all()
    filterset_fields = ["status", "task_type", "student", "circle", "session"]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudyTaskSerializer

    def get_queryset(self):
        qs = StudyTask.objects.select_related(
            "student", "assigned_by", "circle", "session", "surah"
        )
        user = self.request.user
        if user.role == User.Role.STUDENT:
            qs = qs.filter(student=user)
        elif user.role == User.Role.TEACHER:
            qs = qs.filter(
                student__enrollments__circle__teacher=user,
                student__enrollments__status=CircleEnrollment.Status.ACTIVE,
            ).distinct()
        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        overdue = request.query_params.get("overdue")
        if overdue in ("1", "true"):
            queryset = queryset.filter(
                status=StudyTask.Status.PENDING,
                due_date__isnull=False,
                due_date__lt=timezone.localdate(),
            )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return api_response(data=self.get_serializer(queryset, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return api_response(data=self.get_serializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        if request.user.role not in (User.Role.TEACHER, User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        serializer = StudyTaskWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        d = serializer.validated_data
        try:
            task = StudyTask.assign(
                student=d["student_id"], assigned_by=request.user,
                task_type=d["task_type"], surah=d["surah"],
                ayah_from=d["ayah_from"], ayah_to=d["ayah_to"],
                circle=d["circle"], notes=d.get("notes", ""),
                due_date=d.get("due_date"), session=d["session"],
            )
        except DjangoValidationError as e:
            return api_response(errors=e.messages, status=status.HTTP_400_BAD_REQUEST, success=False)
        return api_response(
            data=StudyTaskSerializer(task).data,
            message="تم إسناد المهمة", status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        task = self.get_object()
        if request.user.role not in (User.Role.TEACHER, User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        data = {  # merge current values with the patch
            "student_id": str(task.student_id),
            "task_type": request.data.get("task_type", task.task_type),
            "surah": request.data.get("surah", task.surah_id),
            "ayah_from": request.data.get("ayah_from", task.ayah_from),
            "ayah_to": request.data.get("ayah_to", task.ayah_to),
            "circle": request.data.get("circle", task.circle_id),
            "session": request.data.get("session", task.session_id),
            "due_date": request.data.get("due_date", task.due_date),
            "notes": request.data.get("notes", task.notes),
        }
        serializer = StudyTaskWriteSerializer(data=data)
        if not serializer.is_valid():
            return api_response(errors=serializer.errors, status=status.HTTP_400_BAD_REQUEST, success=False)
        d = serializer.validated_data
        try:
            task.update_details(
                by=request.user, task_type=d["task_type"], surah=d["surah"],
                ayah_from=d["ayah_from"], ayah_to=d["ayah_to"],
                circle=d["circle"], notes=d.get("notes", ""),
                due_date=d.get("due_date"), session=d["session"],
            )
        except DjangoValidationError as e:
            return api_response(errors=e.messages, status=status.HTTP_400_BAD_REQUEST, success=False)
        return api_response(data=StudyTaskSerializer(task).data, message="تم تحديث المهمة")

    def destroy(self, request, *args, **kwargs):
        task = self.get_object()
        user = request.user
        if user.role == User.Role.TEACHER and not user.teaches_student(task.student):
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        if user.role == User.Role.STUDENT:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        task.delete()
        return api_response(message="تم حذف المهمة")

    @action(detail=True, methods=["post"])
    def done(self, request, pk=None):
        task = self.get_object()
        if request.user.role == User.Role.STUDENT and task.student_id != request.user.id:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        try:
            task.mark_done(by=request.user)
        except DjangoValidationError as e:
            return api_response(errors=e.messages, status=status.HTTP_400_BAD_REQUEST, success=False)
        return api_response(data=StudyTaskSerializer(task).data, message="تم تأكيد الإنجاز")

    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        task = self.get_object()
        if request.user.role == User.Role.STUDENT:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        try:
            task.validate(by=request.user, rejection_reason=request.data.get("rejection_reason", ""))
        except DjangoValidationError as e:
            return api_response(errors=e.messages, status=status.HTTP_400_BAD_REQUEST, success=False)
        return api_response(data=StudyTaskSerializer(task).data, message="تمت معالجة المهمة")


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


# ─── SESSION TURNS API ──────────────────────────

class SessionTurnViewSet(viewsets.GenericViewSet):
    queryset = SessionTurn.objects.select_related("session__circle", "student").all()
    serializer_class = SessionTurnSerializer

    def get_permissions(self):
        if self.action in ("reorder", "remove"):
            return [permissions.IsAuthenticated(), IsTeacherOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = SessionTurn.objects.select_related("session__circle", "student")
        user = self.request.user
        if user.role == User.Role.STUDENT:
            circles = CircleEnrollment.objects.filter(
                student=user, status=CircleEnrollment.Status.ACTIVE
            ).values_list("circle_id", flat=True)
            qs = qs.filter(session__circle_id__in=circles)
        elif user.role == User.Role.TEACHER:
            qs = qs.filter(session__circle__teacher=user)
        return qs

    def list(self, request, *args, **kwargs):
        session_id = request.query_params.get("session")
        if not session_id:
            return api_response(
                message="معرف الجلسة (session) مطلوب",
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
            )
        try:
            session = Session.objects.get(pk=session_id)
        except Session.DoesNotExist:
            return api_response(message="الجلسة غير موجودة", status=status.HTTP_404_NOT_FOUND, success=False)

        if request.user.role == User.Role.STUDENT:
            enrolled = CircleEnrollment.objects.filter(
                student=request.user, circle=session.circle,
                status=CircleEnrollment.Status.ACTIVE,
            ).exists()
            if not enrolled:
                return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)

        qs = self.get_queryset().filter(session=session).order_by("turn_number")
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return api_response(data=serializer.data)

    @action(detail=False, methods=["post"])
    def claim(self, request):
        if request.user.role != User.Role.STUDENT:
            return api_response(message="للطلاب فقط", status=status.HTTP_403_FORBIDDEN, success=False)

        session_id = request.data.get("session")
        if not session_id:
            return api_response(message="معرف الجلسة مطلوب", status=status.HTTP_400_BAD_REQUEST, success=False)

        try:
            session = Session.objects.select_related("circle").get(pk=session_id)
        except Session.DoesNotExist:
            return api_response(message="الجلسة غير موجودة", status=status.HTTP_404_NOT_FOUND, success=False)

        if not CircleEnrollment.objects.filter(
            student=request.user, circle=session.circle, status=CircleEnrollment.Status.ACTIVE
        ).exists():
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)

        if session.status not in (Session.Status.TURN_TAKING_OPEN, Session.Status.LIVE):
            return api_response(message="التسجيل في الأدوار غير متاح حالياً", status=status.HTTP_403_FORBIDDEN, success=False)

        attendance = Attendance.objects.filter(session=session, student=request.user).first()
        if not attendance or attendance.status not in (Attendance.Status.NOT_RESPONDED, Attendance.Status.CONFIRMED):
            return api_response(message="يجب تأكيد الحضور أولاً", status=status.HTTP_403_FORBIDDEN, success=False)
        if attendance.status == Attendance.Status.NOT_RESPONDED:
            attendance.status = Attendance.Status.CONFIRMED
            attendance.save(update_fields=["status"])

        if SessionTurn.objects.filter(session=session, student=request.user).exists():
            return api_response(message="لديك دور بالفعل", status=status.HTTP_400_BAD_REQUEST, success=False)

        from django.db import IntegrityError, transaction
        try:
            with transaction.atomic():
                locked = SessionTurn.objects.select_for_update().filter(session=session)
                taken = set(locked.values_list("turn_number", flat=True))
                n = 1
                while n in taken:
                    n += 1
                SessionTurn.objects.create(session=session, student=request.user, turn_number=n)
        except IntegrityError:
            return api_response(
                message="تم أخذ هذا الدور للتو، حاول مرة أخرى",
                status=status.HTTP_409_CONFLICT,
                success=False,
            )

        return api_response(
            data=SessionTurnSerializer(
                SessionTurn.objects.get(session=session, student=request.user),
                context={"request": request},
            ).data,
            message=f"تم حجز الدور رقم {n}",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def release(self, request):
        if request.user.role != User.Role.STUDENT:
            return api_response(message="للطلاب فقط", status=status.HTTP_403_FORBIDDEN, success=False)

        session_id = request.data.get("session")
        if not session_id:
            return api_response(message="معرف الجلسة مطلوب", status=status.HTTP_400_BAD_REQUEST, success=False)

        try:
            session = Session.objects.get(pk=session_id)
        except Session.DoesNotExist:
            return api_response(message="الجلسة غير موجودة", status=status.HTTP_404_NOT_FOUND, success=False)

        deleted, _ = SessionTurn.objects.filter(session=session, student=request.user).delete()
        if not deleted:
            return api_response(message="ليس لديك دور", status=status.HTTP_400_BAD_REQUEST, success=False)

        return api_response(message="تم إلغاء دورك")

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        session_id = request.data.get("session")
        order = request.data.get("order", [])
        if not session_id:
            return api_response(message="معرف الجلسة مطلوب", status=status.HTTP_400_BAD_REQUEST, success=False)

        try:
            session = Session.objects.select_related("circle__teacher").get(pk=session_id)
        except Session.DoesNotExist:
            return api_response(message="الجلسة غير موجودة", status=status.HTTP_404_NOT_FOUND, success=False)

        if request.user.role == User.Role.TEACHER and session.circle.teacher != request.user:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)

        existing_ids = set(
            str(sid) for sid in SessionTurn.objects.filter(session=session).values_list("student_id", flat=True)
        )
        invalid = [sid for sid in order if sid not in existing_ids]
        if invalid:
            return api_response(
                message="بعض الطلاب ليس لديهم دور",
                errors={"invalid_ids": invalid},
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
            )

        from django.db import transaction
        with transaction.atomic():
            turns = SessionTurn.objects.select_for_update().filter(session=session)
            offset = 10000
            turn_map = {str(t.student_id): t for t in turns}
            for i, student_id in enumerate(order, start=1):
                turn_map[student_id].turn_number = offset + i
            SessionTurn.objects.bulk_update(turn_map.values(), ["turn_number"])
            for t in turn_map.values():
                t.turn_number = t.turn_number - offset
            SessionTurn.objects.bulk_update(turn_map.values(), ["turn_number"])

        return api_response(message="تم إعادة ترتيب الأدوار")

    @action(detail=False, methods=["post"])
    def remove(self, request):
        session_id = request.data.get("session")
        student_id = request.data.get("student")
        if not session_id or not student_id:
            return api_response(
                message="session و student مطلوبان",
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
            )

        try:
            session = Session.objects.select_related("circle__teacher").get(pk=session_id)
        except Session.DoesNotExist:
            return api_response(message="الجلسة غير موجودة", status=status.HTTP_404_NOT_FOUND, success=False)

        if request.user.role == User.Role.TEACHER and session.circle.teacher != request.user:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)

        deleted, _ = SessionTurn.objects.filter(session=session, student_id=student_id).delete()
        if not deleted:
            return api_response(message="لا يوجد دور لهذا الطالب", status=status.HTTP_400_BAD_REQUEST, success=False)

        return api_response(message="تم حذف الدور")


# ─── CERTIFICATES API ───────────────────────────

class CertificateViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CertificateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Certificate.objects.select_related("template")
        user = self.request.user
        if not user or user.is_anonymous:
            return qs.none()
        if user.role == User.Role.STUDENT:
            qs = qs.filter(student=user)
        return qs.order_by("-issue_date")

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
        if request.user.role == User.Role.STUDENT and instance.student != request.user:
            return api_response(message="ليس لديك صلاحية", status=status.HTTP_403_FORBIDDEN, success=False)
        serializer = self.get_serializer(instance)
        return api_response(data=serializer.data)


# ─── STUDENT HOME / DASHBOARD ───────────────────

class StudentHomeView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsStudent]

    def get(self, request):
        student = request.user
        now = timezone.now()

        # Active circles
        active_enrollments = CircleEnrollment.objects.filter(
            student=student, status=CircleEnrollment.Status.ACTIVE
        ).select_related("circle__teacher")

        circles_data = []
        for e in active_enrollments:
            c = e.circle
            circles_data.append({
                "id": c.id,
                "name": c.name,
                "teacher_name": c.teacher.full_name_ar if c.teacher else "",
                "schedule_days": c.schedule_days,
                "schedule_time": str(c.schedule_time) if c.schedule_time else None,
            })

        # Today's session(s)
        today = now.date()
        today_sessions = Session.objects.filter(
            circle__in=[e.circle_id for e in active_enrollments],
            session_date=today,
        ).select_related("circle")

        sessions_data = []
        for s in today_sessions:
            has_turn = SessionTurn.objects.filter(session=s, student=student).exists()
            turn_info = None
            if has_turn:
                turn = SessionTurn.objects.get(session=s, student=student)
                turn_info = {
                    "turn_number": turn.turn_number,
                    "id": turn.id,
                }
            sessions_data.append({
                "id": s.id,
                "circle_id": s.circle_id,
                "circle_name": s.circle.name,
                "session_date": str(s.session_date),
                "session_time": str(s.session_time) if s.session_time else None,
                "session_type": s.session_type,
                "is_online": s.is_online,
                "is_unlocked": s.is_unlocked,
                "meeting_url": s.meeting_url or "",
                "location": s.location,
                "has_turn": has_turn,
                "turn": turn_info,
            })

        # Unread notifications
        unread_count = Notification.objects.filter(recipient=student, is_read=False).count()

        # Most recent recitation grade
        latest_grade = RecitationGrade.objects.filter(student=student).select_related("criterion", "session").order_by("-created_at").first()
        grade_data = None
        if latest_grade:
            grade_data = {
                "score": latest_grade.score,
                "max_score": latest_grade.max_score,
                "percentage": round((latest_grade.score / latest_grade.max_score) * 100, 1) if latest_grade.max_score else 0,
                "criterion": latest_grade.criterion.name_ar if latest_grade.criterion else "",
                "session_date": str(latest_grade.session.session_date) if latest_grade.session else None,
            }

        # Pending requests / justifications
        pending_requests_count = SupportRequest.objects.filter(
            submitted_by=student, status__in=["submitted", "under_review"]
        ).count()
        pending_justifications_count = Attendance.objects.filter(
            student=student, justification_status=Attendance.JustificationStatus.PENDING
        ).count()

        # Certificates count
        cert_count = Certificate.objects.filter(student=student).count()

        return api_response(data={
            "active_circles": circles_data,
            "today_sessions": sessions_data,
            "unread_notifications": unread_count,
            "latest_grade": grade_data,
            "pending_requests_count": pending_requests_count,
            "pending_justifications_count": pending_justifications_count,
            "certificates_count": cert_count,
        })
