from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session, SessionStudentNote, SessionRescheduleRequest, SessionLessonToggle, SessionTurn
from apps.certificates.models import Certificate
from apps.attendance.models import Attendance
from apps.memorization.models import MemorizationProgress, RecitationGrade, ReviewRequest, ProgressLog, StudentAchievement, StudyTask
from apps.exams.models import Exam, ExamMark, ExamNotification, ExamApprovalHistory
from apps.references.models import Surah, EvaluationCriterion
from apps.requests.models import SupportRequest, Comment
from apps.announcements.models import Announcement
from apps.notifications.models import Notification


class TeacherSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="full_name_ar", read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "full_name", "avatar_url"]

    def get_avatar_url(self, obj):
        if hasattr(obj, "avatar") and obj.avatar:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.avatar.url)
        return None


class NestedUserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "full_name_ar", "email", "phone", "role", "role_display",
            "gender", "is_approved",
        ]
        read_only_fields = fields


class CircleMinSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.full_name_ar", read_only=True)

    class Meta:
        model = Circle
        fields = ["id", "name", "teacher_name", "status", "gender", "max_students"]


# ─── AUTH ─────────────────────────────────────

class CustomTokenObtainSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        from django.contrib.auth import authenticate
        user = authenticate(
            request=self.context.get("request"),
            email=data["email"],
            password=data["password"],
        )
        if user is None:
            raise DRFValidationError("البريد الإلكتروني أو كلمة المرور غير صحيحة")
        if not user.is_active:
            raise DRFValidationError("الحساب غير نشط")
        if user.is_approved != User.ApprovalStatus.APPROVED:
            raise DRFValidationError("الحساب لم يتم اعتماده بعد")
        data["user"] = user
        return data


class UserProfileSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    status_display = serializers.CharField(source="get_is_approved_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "full_name_ar", "email", "phone", "role", "role_display",
            "gender", "is_approved", "status_display", "is_active",
            "date_joined", "last_login",
        ]
        read_only_fields = ["id", "role", "is_approved", "is_active", "date_joined", "last_login"]


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise DRFValidationError("كلمة المرور القديمة غير صحيحة")
        return value

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise DRFValidationError("كلمة المرور الجديدة وتأكيدها غير متطابقين")
        return data


# ─── USERS ─────────────────────────────────────

class UserListSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    status_display = serializers.CharField(source="get_is_approved_display", read_only=True)
    circles_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "full_name_ar", "email", "phone", "role", "role_display",
            "status_display", "gender", "is_active", "last_login",
            "date_joined", "circles_count",
        ]

    def get_circles_count(self, obj):
        if obj.role == User.Role.TEACHER:
            return obj.teaching_circles.filter(status=Circle.Status.ACTIVE).count()
        return None


class UserDetailSerializer(UserListSerializer):
    active_circles = serializers.SerializerMethodField()

    class Meta(UserListSerializer.Meta):
        fields = UserListSerializer.Meta.fields + ["rejection_reason", "active_circles"]

    def get_active_circles(self, obj):
        if obj.role == User.Role.TEACHER:
            circles = obj.teaching_circles.filter(status=Circle.Status.ACTIVE)
            return CircleMinSerializer(circles, many=True, context=self.context).data
        if obj.role == User.Role.STUDENT:
            enrollments = obj.enrollments.filter(status=CircleEnrollment.Status.ACTIVE)
            circles = [e.circle for e in enrollments.select_related("circle")]
            return CircleMinSerializer(circles, many=True, context=self.context).data
        return []


class UserCreateSerializer(serializers.ModelSerializer):
    circle_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = User
        fields = [
            "full_name_ar", "email", "phone", "role", "gender",
            "password", "circle_ids",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
        }

    def create(self, validated_data):
        circle_ids = validated_data.pop("circle_ids", [])
        password = validated_data.pop("password")
        validated_data["is_approved"] = User.ApprovalStatus.APPROVED
        if validated_data.get("role") in (User.Role.MAIN_ADMIN, User.Role.SUB_ADMIN):
            validated_data["is_approved"] = User.ApprovalStatus.APPROVED
        user = User(**validated_data)
        user.set_password(password)
        user.save()

        if circle_ids and validated_data.get("role") == User.Role.TEACHER:
            Circle.objects.filter(id__in=circle_ids).update(teacher=user)

        return user


# ─── CIRCLES ───────────────────────────────────

class CircleScheduleSerializer(serializers.Serializer):
    day_of_week = serializers.CharField()
    time = serializers.TimeField(required=False, allow_null=True)


class CircleListSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.full_name_ar", read_only=True)
    active_students_count = serializers.IntegerField(read_only=True, default=0)
    sessions_count = serializers.IntegerField(read_only=True, default=0)
    last_session_date = serializers.DateField(read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Circle
        fields = [
            "id", "name", "teacher_name", "gender", "max_students",
            "active_students_count", "sessions_count", "last_session_date",
            "schedule", "status", "status_display", "location",
        ]


class CircleDetailSerializer(CircleListSerializer):
    enrolled_students = serializers.SerializerMethodField()

    class Meta(CircleListSerializer.Meta):
        fields = CircleListSerializer.Meta.fields + ["description", "enrolled_students"]

    def get_enrolled_students(self, obj):
        enrollments = obj.enrollments.filter(status=CircleEnrollment.Status.ACTIVE).select_related("student")
        return [
            {
                "id": e.student_id,
                "full_name_ar": e.student.full_name_ar,
                "enrolled_at": e.enrolled_at,
            }
            for e in enrollments
        ]


class CircleCreateSerializer(serializers.ModelSerializer):
    teacher_id = serializers.UUIDField(write_only=True)
    schedules = serializers.ListField(child=serializers.DictField(), required=False, default=list)

    class Meta:
        model = Circle
        fields = [
            "name", "teacher_id", "description",
            "gender", "max_students", "location", "schedule_days",
            "schedule_time", "schedules",
        ]

    def validate_teacher_id(self, value):
        try:
            return User.objects.get(pk=value, role=User.Role.TEACHER, is_approved=User.ApprovalStatus.APPROVED)
        except User.DoesNotExist:
            raise DRFValidationError("المعلم غير موجود أو غير معتمد")

    def create(self, validated_data):
        validated_data.pop("schedules", [])
        teacher = validated_data.pop("teacher_id")
        return Circle.objects.create(teacher=teacher, **validated_data)


class CircleEnrollSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()

    def validate_student_id(self, value):
        try:
            return User.objects.get(pk=value, role=User.Role.STUDENT, is_approved=User.ApprovalStatus.APPROVED)
        except User.DoesNotExist:
            raise DRFValidationError("الطالب غير موجود أو غير معتمد")

    def validate(self, data):
        circle = self.context["circle"]
        student = data["student_id"]

        # Batch match first — CircleEnrollment.enroll() re-checks it with a
        # Django ValidationError that DRF would surface as a 500.
        try:
            CircleEnrollment._check_batch_match(student, circle)
        except DjangoValidationError as e:
            raise DRFValidationError(e.messages)

        if CircleEnrollment.objects.filter(
            circle=circle, student=student,
            status__in=[CircleEnrollment.Status.ACTIVE, CircleEnrollment.Status.PENDING]
        ).exists():
            raise DRFValidationError("الطالب مسجل بالفعل أو لديه طلب انتظار في هذه الحلقة")

        if CircleEnrollment.objects.filter(
            student=student, status=CircleEnrollment.Status.ACTIVE
        ).exists():
            raise DRFValidationError("الطالب مسجل بالفعل في حلقة نشطة أخرى")

        active_count = circle.enrollments.filter(status=CircleEnrollment.Status.ACTIVE).count()
        if active_count >= circle.max_students:
            raise DRFValidationError("الحلقة ممتلئة، لا يمكن تسجيل المزيد من الطلاب")

        return data

    def save(self, **kwargs):
        circle = self.context["circle"]
        student = self.validated_data["student_id"]
        # Reactivate a previous (dropped/inactive) enrollment row instead of
        # a raw create — the unique_together(circle, student) constraint made
        # re-enrolling a removed student crash with IntegrityError.
        return CircleEnrollment.enroll(student, circle)


class CircleRemoveStudentSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    reason = serializers.CharField(required=False, default="")

    def save(self, **kwargs):
        circle = self.context["circle"]
        enrollment = CircleEnrollment.objects.filter(
            circle=circle,
            student_id=self.validated_data["student_id"],
            status=CircleEnrollment.Status.ACTIVE,
        ).first()
        if enrollment is None:
            raise DRFValidationError("الطالب غير مسجل تسجيلاً نشطاً في هذه الحلقة")
        enrollment.status = CircleEnrollment.Status.INACTIVE
        enrollment.left_at = timezone.now()
        enrollment.save(update_fields=["status", "left_at"])
        return enrollment


class CircleStatsSerializer(serializers.Serializer):
    total_students = serializers.IntegerField()
    total_completed_sessions = serializers.IntegerField()
    present_count = serializers.IntegerField()
    absent_count = serializers.IntegerField()
    attendance_rate = serializers.FloatField()


# ─── SESSIONS ──────────────────────────────────

class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name_ar", read_only=True)
    student_avatar = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id", "student", "student_name", "student_avatar",
            "status", "status_display", "created_at",
        ]

    def get_student_avatar(self, obj):
        return None


class SessionListSerializer(serializers.ModelSerializer):
    circle_name = serializers.CharField(source="circle.name", read_only=True)
    teacher_name = serializers.CharField(source="circle.teacher.full_name_ar", read_only=True)
    present_count = serializers.IntegerField(read_only=True, default=0)
    absent_count = serializers.IntegerField(read_only=True, default=0)
    total_enrolled = serializers.IntegerField(read_only=True, default=0)
    session_type_display = serializers.CharField(source="get_session_type_display", read_only=True)
    meeting_platform_display = serializers.SerializerMethodField()
    is_online = serializers.BooleanField(read_only=True)

    class Meta:
        model = Session
        fields = [
            "id", "circle", "circle_name", "teacher_name",
            "session_date", "session_time", "session_type", "session_type_display",
            "location", "is_online", "meeting_url", "meeting_platform",
            "meeting_platform_display", "meeting_id", "meeting_password",
            "recording_url", "duration_minutes", "notes",
            "present_count", "absent_count",
            "total_enrolled", "created_at",
        ]

    def get_meeting_platform_display(self, obj):
        return obj.get_meeting_platform_display() if obj.meeting_platform else ""


class SessionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = [
            "circle", "session_date", "session_time", "session_type",
            "location", "meeting_url", "meeting_platform", "meeting_id",
            "meeting_password", "recording_url", "duration_minutes", "notes",
        ]

    def validate(self, data):
        if Session.objects.filter(circle=data["circle"], session_date=data["session_date"]).exists():
            raise DRFValidationError("جلسة موجودة بالفعل لهذه الحلقة في هذا التاريخ")
        return data

    def create(self, validated_data):
        from django.utils import timezone as tz
        from datetime import datetime
        session_date = validated_data.get("session_date")
        session_time = validated_data.get("session_time")
        if session_time and session_date:
            validated_data["start_time"] = tz.make_aware(
                datetime.combine(session_date, session_time), tz.get_current_timezone(),
            )
        elif session_date:
            validated_data["start_time"] = tz.make_aware(
                datetime.combine(session_date, datetime.min.time()), tz.get_current_timezone(),
            )
        validated_data["status"] = Session.Status.SCHEDULED
        return super().create(validated_data)


class BatchAttendanceSerializer(serializers.Serializer):
    records = serializers.ListField(child=serializers.DictField())

    def validate_records(self, value):
        valid_statuses = dict(Attendance.Status.choices)
        for i, rec in enumerate(value):
            sid = rec.get("student_id")
            status = rec.get("status")
            if not sid:
                raise DRFValidationError(f"السجل {i+1}: student_id مطلوب")
            if status not in valid_statuses:
                raise DRFValidationError(
                    f"السجل {i+1}: الحالة {status} غير صالحة. الحالات المسموحة: {', '.join(valid_statuses.keys())}"
                )
        return value


# ─── GRADES ────────────────────────────────────

class RecitationGradeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name_ar", read_only=True)
    criterion_name = serializers.CharField(source="criterion.name_ar", read_only=True)
    overall_grade = serializers.SerializerMethodField()

    class Meta:
        model = RecitationGrade
        fields = [
            "id", "session", "student", "student_name",
            "criterion", "criterion_name", "score", "max_score",
            "overall_grade", "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_overall_grade(self, obj):
        return round((obj.score / obj.max_score) * 100, 1) if obj.max_score else 0


class RecitationGradeCreateSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    student_id = serializers.UUIDField()
    criterion_id = serializers.IntegerField()
    score = serializers.FloatField(min_value=0)
    max_score = serializers.FloatField(default=100, min_value=1)

    def validate_session_id(self, value):
        try:
            return Session.objects.get(pk=value)
        except Session.DoesNotExist:
            raise DRFValidationError("الجلسة غير موجودة")

    def validate_student_id(self, value):
        try:
            return User.objects.get(pk=value, role=User.Role.STUDENT)
        except User.DoesNotExist:
            raise DRFValidationError("الطالب غير موجود")

    def validate_criterion_id(self, value):
        try:
            return EvaluationCriterion.objects.get(pk=value, is_active=True)
        except EvaluationCriterion.DoesNotExist:
            raise DRFValidationError("معيار التقييم غير موجود")

    def validate(self, data):
        if data["score"] > data["max_score"]:
            raise DRFValidationError("الدرجة لا يمكن أن تتجاوز الدرجة القصوى")
        att = Attendance.objects.filter(
            session=data["session_id"], student=data["student_id"]
        ).first()
        if att and att.status in (Attendance.Status.ABSENT, Attendance.Status.ABSENT_UNJUSTIFIED):
            raise DRFValidationError("لا يمكن تسجيل درجة لطالب غائب")
        return data

    def create(self, validated_data):
        return RecitationGrade.objects.create(
            session=validated_data["session_id"],
            student=validated_data["student_id"],
            criterion=validated_data["criterion_id"],
            score=validated_data["score"],
            max_score=validated_data["max_score"],
        )


# ─── JUSTIFICATIONS ────────────────────────────

class AbsenceJustificationSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name_ar", read_only=True)
    session_date = serializers.DateField(source="session.session_date", read_only=True)
    circle_name = serializers.CharField(source="session.circle.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name_ar", read_only=True, default=None)

    class Meta:
        model = Attendance
        fields = [
            "id", "student", "student_name", "session", "session_date",
            "circle_name", "status", "status_display",
            "justification", "justification_status", "justification_submitted_at",
            "teacher_comment",
            "reviewed_by", "reviewed_by_name", "reviewed_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["student", "session", "status", "reviewed_by", "reviewed_at"]


# ─── REGISTRATION ──────────────────────────────

class RegistrationRequestSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_is_approved_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "full_name_ar", "email", "phone", "role", "gender",
            "is_approved", "status_display", "rejection_reason",
            "date_joined",
        ]
        read_only_fields = ["id", "is_approved", "date_joined"]


class RegistrationCreateSerializer(serializers.Serializer):
    full_name_ar = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30, required=False, default="")
    role = serializers.ChoiceField(choices=["student", "teacher"])
    gender = serializers.ChoiceField(choices=["male", "female"], required=False, default="male")
    password = serializers.CharField(min_length=8, write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise DRFValidationError("البريد الإلكتروني مستخدم بالفعل")
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise DRFValidationError("كلمة المرور وتأكيدها غير متطابقين")
        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")
        user = User(**validated_data, is_approved=User.ApprovalStatus.PENDING)
        user.set_password(password)
        user.save()
        return user


# ─── REQUESTS ──────────────────────────────────

class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name_ar", read_only=True)
    author_role = serializers.CharField(source="author.get_role_display", read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "author", "author_name", "author_role", "body", "created_at"]
        read_only_fields = ["author", "created_at"]


class SupportRequestSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source="submitted_by.full_name_ar", read_only=True)
    submitted_by_role = serializers.CharField(source="submitted_by.get_role_display", read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    comments = CommentSerializer(many=True, read_only=True)

    class Meta:
        model = SupportRequest
        fields = [
            "id", "submitted_by", "submitted_by_name", "submitted_by_role",
            "title", "body", "type", "type_display", "priority", "priority_display",
            "status", "status_display", "comments", "created_at", "updated_at",
        ]
        read_only_fields = ["submitted_by", "created_at", "updated_at"]


class SupportRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportRequest
        fields = ["title", "body", "type", "priority"]

    def create(self, validated_data):
        return SupportRequest.objects.create(
            submitted_by=self.context["request"].user, **validated_data
        )


class CommentCreateSerializer(serializers.Serializer):
    body = serializers.CharField(min_length=1)

    def create(self, validated_data):
        return Comment.objects.create(
            request=self.context["request_obj"],
            author=self.context["request"].user,
            body=validated_data["body"],
        )


# ─── ANNOUNCEMENTS ─────────────────────────────

class AnnouncementSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name_ar", read_only=True)
    author_role = serializers.CharField(source="author.get_role_display", read_only=True)

    class Meta:
        model = Announcement
        fields = [
            "id", "author", "author_name", "author_role",
            "title", "body", "created_at", "updated_at",
        ]
        read_only_fields = ["author", "created_at", "updated_at"]


class AnnouncementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ["title", "body"]

    def create(self, validated_data):
        return Announcement.objects.create(
            author=self.context["request"].user, **validated_data
        )


# ─── NOTIFICATIONS ─────────────────────────────

class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id", "recipient", "type", "type_display",
            "title", "message", "link", "is_read", "created_at",
        ]
        read_only_fields = ["recipient", "created_at"]


class UnreadCountSerializer(serializers.Serializer):
    unread = serializers.IntegerField()


# ─── REPORTS ───────────────────────────────────

class DashboardStatsSerializer(serializers.Serializer):
    total_circles = serializers.IntegerField()
    total_teachers = serializers.IntegerField()
    total_supervisors = serializers.IntegerField()
    total_students = serializers.IntegerField()


class StudentStatsSerializer(serializers.Serializer):
    total_graduated = serializers.IntegerField()
    total_students = serializers.IntegerField()
    total_withdrawn = serializers.IntegerField()
    total_graduates = serializers.IntegerField()
    levels = serializers.DictField(child=serializers.IntegerField())


class TeacherStatsSerializer(serializers.Serializer):
    total_teachers = serializers.IntegerField()
    total_active_accounts = serializers.IntegerField()
    total_inactive_accounts = serializers.IntegerField()
    total_memorized_parts = serializers.IntegerField()


class UrgentAlertSerializer(serializers.Serializer):
    type = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()
    count = serializers.IntegerField()
    link = serializers.CharField()


# ─── ATTENDANCE CHARTS ─────────────────────────

class AttendanceChartSerializer(serializers.Serializer):
    circle_name = serializers.CharField()
    present_count = serializers.IntegerField()
    absent_count = serializers.IntegerField()


class AttendanceTrendSerializer(serializers.Serializer):
    month = serializers.CharField()
    present = serializers.IntegerField()
    absent = serializers.IntegerField()


# ─── GRADE CHART ───────────────────────────────

class TeacherChartSerializer(serializers.Serializer):
    teacher_name = serializers.CharField()
    memorization_count = serializers.IntegerField()
    review_count = serializers.IntegerField()


# ─── REGISTRATION STATS ────────────────────────

class RegistrationStatsSerializer(serializers.Serializer):
    total_circles = serializers.IntegerField()
    total_teachers = serializers.IntegerField()
    total_students = serializers.IntegerField()
    total_approved = serializers.IntegerField()
    pending_students = serializers.IntegerField()
    pending_teachers = serializers.IntegerField()
    pending_supervisors = serializers.IntegerField()


# ─── EXAMS ─────────────────────────────────────

class ExamListSerializer(serializers.ModelSerializer):
    circle_name = serializers.CharField(source="circle.name", read_only=True, allow_null=True)
    assigned_teacher_name = serializers.CharField(source="assigned_teacher.full_name_ar", read_only=True, allow_null=True)
    created_by_name = serializers.CharField(source="created_by.full_name_ar", read_only=True)
    exam_type_display = serializers.CharField(source="get_exam_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Exam
        fields = [
            "id", "title", "description", "exam_type", "exam_type_display",
            "exam_code", "circle", "circle_name",
            "assigned_teacher", "assigned_teacher_name",
            "created_by", "created_by_name",
            "exam_date", "max_marks", "pass_percentage",
            "status", "status_display", "auto_publish",
            "created_at", "updated_at",
        ]


class ExamCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = [
            "title", "description", "exam_type", "circle",
            "assigned_teacher", "exam_date", "max_marks",
            "pass_percentage", "status", "auto_publish",
        ]

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class ExamMarkSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name_ar", read_only=True)
    entered_by_name = serializers.CharField(source="entered_by.full_name_ar", read_only=True, allow_null=True)
    approved_by_name = serializers.CharField(source="approved_by.full_name_ar", read_only=True, allow_null=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ExamMark
        fields = [
            "id", "exam", "student", "student_name",
            "marks_obtained", "percentage", "grade", "is_passed",
            "teacher_notes", "private_notes",
            "status", "status_display",
            "entered_by", "entered_by_name",
            "approved_by", "approved_by_name",
            "created_at", "updated_at",
        ]


class ExamMarkCreateSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    marks_obtained = serializers.FloatField(min_value=0, max_value=100)
    teacher_notes = serializers.CharField(required=False, default="")
    private_notes = serializers.CharField(required=False, default="")


# ─── REVIEW / RECITATION REQUESTS ───────────────

class ReviewRequestSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name_ar", read_only=True)
    circle_name = serializers.CharField(source="circle.name", read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    surah_name = serializers.CharField(source="surah.name_ar", read_only=True, allow_null=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name_ar", read_only=True, allow_null=True)
    meeting_platform_display = serializers.CharField(source="get_meeting_platform_display", read_only=True, allow_null=True)

    class Meta:
        model = ReviewRequest
        fields = [
            "id", "student", "student_name", "circle", "circle_name",
            "type", "type_display", "surah", "surah_name",
            "ayah_from", "ayah_to", "notes",
            "status", "status_display",
            "reviewed_by", "reviewed_by_name",
            "rejection_reason", "created_at", "updated_at",
            "preferred_days", "preferred_times",
            "scheduled_date", "scheduled_time",
            "meeting_url", "meeting_platform", "meeting_platform_display",
        ]
        read_only_fields = ["student", "status", "reviewed_by", "created_at", "updated_at"]


class ReviewRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewRequest
        fields = ["circle", "type", "surah", "ayah_from", "ayah_to", "notes", "preferred_days", "preferred_times"]

    def create(self, validated_data):
        return ReviewRequest.objects.create(
            student=self.context["request"].user,
            **validated_data,
        )


class ReviewRequestActionSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=False, default="")
    notes = serializers.CharField(required=False, default="")


# ─── SESSION STUDENT NOTES ──────────────────────

class SessionStudentNoteSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name_ar", read_only=True)

    class Meta:
        model = SessionStudentNote
        fields = [
            "id", "session", "student", "student_name",
            "note", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class SessionStudentNoteCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionStudentNote
        fields = ["session", "student", "note"]

    def validate(self, data):
        if SessionStudentNote.objects.filter(
            session=data["session"], student=data["student"]
        ).exists():
            raise DRFValidationError("يوجد ملاحظة مسبقة لهذا الطالب في هذه الحصة. استخدم PUT للتحديث.")
        return data


# ─── MEMORIZATION PROGRESS ──────────────────────

class MemorizationProgressSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="enrollment.student.full_name_ar", read_only=True)
    circle_name = serializers.CharField(source="enrollment.circle.name", read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    surah_name = serializers.CharField(source="surah.name_ar", read_only=True, allow_null=True)

    class Meta:
        model = MemorizationProgress
        fields = [
            "id", "enrollment", "student_name", "circle_name",
            "surah", "surah_name", "ayah_from", "ayah_to",
            "type", "type_display",
            "status", "status_display",
            "revision_count", "notes",
            "last_revised_at", "tested_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


# ─── REFERENCE DATA ─────────────────────────────

class SurahSerializer(serializers.ModelSerializer):
    surah_number = serializers.IntegerField(source="id", read_only=True)
    total_ayahs = serializers.IntegerField(source="ayah_count", read_only=True)

    class Meta:
        model = Surah
        fields = ["id", "surah_number", "name_ar", "name_en", "total_ayahs", "revelation_type"]


class EvaluationCriterionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvaluationCriterion
        fields = ["id", "name_ar", "weight", "is_active"]


# ─── SESSION RESCHEDULE ─────────────────────────

class SessionRescheduleRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source="requested_by.full_name_ar", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = SessionRescheduleRequest
        fields = [
            "id", "session", "requested_by", "requested_by_name",
            "proposed_date", "proposed_time", "reason",
            "status", "status_display",
            "rejection_reason", "created_at", "updated_at",
        ]
        read_only_fields = ["requested_by", "status", "reviewed_by", "created_at", "updated_at"]


class SessionRescheduleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionRescheduleRequest
        fields = ["proposed_date", "proposed_time", "reason"]

    def create(self, validated_data):
        return SessionRescheduleRequest.objects.create(
            session=self.context["session"],
            requested_by=self.context["request"].user,
            **validated_data,
        )


# ─── LESSON TOGGLES ─────────────────────────────

class SessionLessonToggleSerializer(serializers.ModelSerializer):
    surah_name = serializers.CharField(source="surah.name_ar", read_only=True)

    class Meta:
        model = SessionLessonToggle
        fields = ["id", "session", "surah", "surah_name", "ayah_from", "ayah_to", "is_active", "toggled_at"]


class SessionLessonToggleBatchSerializer(serializers.Serializer):
    toggles = serializers.ListField(child=serializers.DictField())

    def validate_toggles(self, value):
        for i, t in enumerate(value):
            if "surah" not in t:
                raise DRFValidationError(f"التسجيل {i+1}: السورة (surah) مطلوبة")
            if "is_active" not in t:
                raise DRFValidationError(f"التسجيل {i+1}: الحالة (is_active) مطلوبة")
        return value


# ─── PROGRESS LOGS (Session Evaluation) ─────────

class ProgressLogListSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name_ar", read_only=True)
    # SerializerMethodField: amount-based entries carry no surah (null FK).
    surah_name = serializers.SerializerMethodField()
    log_category_display = serializers.CharField(source="get_log_category_display", read_only=True)
    evaluation_grade_display = serializers.CharField(source="get_evaluation_grade_display", read_only=True)

    def get_surah_name(self, obj):
        return obj.surah.name_ar if obj.surah_id else None

    class Meta:
        model = ProgressLog
        fields = [
            "id", "session", "student", "student_name",
            "log_category", "log_category_display",
            "surah", "surah_name",
            "start_ayah", "end_ayah",
            "hizb", "thumn", "total_thumns",
            "completed_pages", "evaluation_grade", "evaluation_grade_display",
            "points", "teacher_notes", "created_at",
        ]


class ProgressLogCreateSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    log_category = serializers.ChoiceField(choices=ProgressLog.Category.choices)
    surah_number = serializers.IntegerField(min_value=1, max_value=114)
    start_ayah = serializers.IntegerField(min_value=1)
    end_ayah = serializers.IntegerField(min_value=1)
    completed_pages = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True,
    )
    evaluation_grade = serializers.ChoiceField(
        choices=ProgressLog.Grade.choices, required=False, default="",
    )
    points = serializers.DecimalField(
        max_digits=4, decimal_places=1, required=False, allow_null=True,
        min_value=0, max_value=20,
    )
    teacher_notes = serializers.CharField(required=False, default="")

    def validate_student_id(self, value):
        try:
            return User.objects.get(pk=value, role=User.Role.STUDENT)
        except User.DoesNotExist:
            raise DRFValidationError("الطالب غير موجود")

    def validate_surah_number(self, value):
        from apps.references.models import Surah
        surah = Surah.objects.filter(id=value).first()
        if not surah:
            raise DRFValidationError(f"رقم السورة {value} غير صالح")
        return surah

    def validate(self, data):
        from apps.memorization.validators import validate_ayah_range
        surah = data["surah_number"]
        start = data["start_ayah"]
        end = data["end_ayah"]
        validate_ayah_range(surah.id, start, end)

        session = self.context["session"]
        student = data["student_id"]

        enrolled = CircleEnrollment.objects.filter(
            circle=session.circle, student=student, status=CircleEnrollment.Status.ACTIVE
        ).exists()
        if not enrolled:
            raise DRFValidationError("الطالب غير مسجل في هذه الحلقة")

        return data

    def create(self, validated_data):
        from apps.memorization.engine import create_progress_log

        session = self.context["session"]
        student = validated_data.pop("student_id")
        surah = validated_data.pop("surah_number")
        log_category = validated_data.pop("log_category")
        start_ayah = validated_data.pop("start_ayah")
        end_ayah = validated_data.pop("end_ayah")
        completed_pages = validated_data.pop("completed_pages", None)
        evaluation_grade = validated_data.pop("evaluation_grade", "")
        points = validated_data.pop("points", None)
        teacher_notes = validated_data.pop("teacher_notes", "")

        log = create_progress_log(
            session=session,
            student=student,
            log_category=log_category,
            surah=surah,
            start_ayah=start_ayah,
            end_ayah=end_ayah,
            evaluation_grade=evaluation_grade,
            teacher_notes=teacher_notes,
            completed_pages=completed_pages,
            points=points,
        )
        return log


class ProgressLogUpdateSerializer(serializers.Serializer):
    """Correction payload — a subset of the create fields; student/session
    are immutable (delete + re-create to move an entry)."""
    log_category = serializers.ChoiceField(choices=ProgressLog.Category.choices, required=False)
    surah_number = serializers.IntegerField(min_value=1, max_value=114, required=False)
    start_ayah = serializers.IntegerField(min_value=1, required=False)
    end_ayah = serializers.IntegerField(min_value=1, required=False)
    completed_pages = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True,
    )
    evaluation_grade = serializers.ChoiceField(
        choices=ProgressLog.Grade.choices, required=False, allow_blank=True,
    )
    points = serializers.DecimalField(
        max_digits=4, decimal_places=1, required=False, allow_null=True,
        min_value=0, max_value=20,
    )
    teacher_notes = serializers.CharField(required=False, allow_blank=True)


# ─── STUDY TASKS (Todos) ────────────────────────

class StudyTaskSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name_ar", read_only=True)
    assigned_by_name = serializers.CharField(source="assigned_by.full_name_ar", read_only=True, default=None)
    circle_name = serializers.CharField(source="circle.name", read_only=True, default=None)
    session_date = serializers.DateField(source="session.session_date", read_only=True, default=None)
    surah_name = serializers.CharField(source="surah.name_ar", read_only=True)
    task_type_display = serializers.CharField(source="get_task_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = StudyTask
        fields = [
            "id", "student", "student_name", "assigned_by", "assigned_by_name",
            "circle", "circle_name", "session", "session_date",
            "task_type", "task_type_display",
            "surah", "surah_name", "ayah_from", "ayah_to",
            "due_date", "is_overdue", "status", "status_display",
            "rejection_reason", "notes",
            "created_at", "completed_at", "validated_at",
        ]


class StudyTaskWriteSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    task_type = serializers.ChoiceField(choices=StudyTask.TaskType.choices)
    surah = serializers.IntegerField(min_value=1, max_value=114)
    ayah_from = serializers.IntegerField(min_value=1)
    ayah_to = serializers.IntegerField(min_value=1)
    circle = serializers.IntegerField(required=False, allow_null=True)
    session = serializers.IntegerField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_student_id(self, value):
        try:
            return User.objects.get(pk=value, role=User.Role.STUDENT)
        except User.DoesNotExist:
            raise DRFValidationError("الطالب غير موجود")

    def validate(self, data):
        from apps.references.utils import validate_ayah_range
        try:
            validate_ayah_range(data["surah"], data["ayah_from"], data["ayah_to"])
        except DjangoValidationError as e:
            raise DRFValidationError(e.messages)
        if data.get("circle"):
            data["circle"] = Circle.objects.filter(pk=data["circle"]).first()
        else:
            data["circle"] = None
        if data.get("session"):
            data["session"] = Session.objects.filter(pk=data["session"]).first()
            if data["session"] is None:
                raise DRFValidationError("الحصة غير موجودة")
        else:
            data["session"] = None
        return data


# ─── SESSION TURNS ──────────────────────────────


class SessionTurnSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name_ar", read_only=True)

    class Meta:
        model = SessionTurn
        fields = ["id", "session", "student", "student_name", "turn_number", "created_at"]
        read_only_fields = ["id", "turn_number", "created_at"]


# ─── CERTIFICATES ───────────────────────────────


class CertificateSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)
    category = serializers.CharField(source="template.category", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            "id", "certificate_number", "template", "template_name",
            "category", "issue_date", "status", "status_display",
            "details", "pdf_url", "created_at",
        ]
        read_only_fields = fields

    def get_pdf_url(self, obj):
        if obj.pdf_file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.pdf_file.url)
        return None
