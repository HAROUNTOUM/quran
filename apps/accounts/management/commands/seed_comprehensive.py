from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, datetime, timedelta, time as dtime
import random

from apps.accounts.models import User, Batch
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.attendance.models import Attendance
from apps.requests.models import SupportRequest
from apps.announcements.models import Announcement
from apps.memorization.models import PrivateSession
from apps.webinars.models import Webinar
from apps.chat.models import Conversation, Message
from apps.classrooms.models import TeacherRoom
from apps.exams.models import Exam, ExamMark
from apps.certificates.models import Certificate, CertificateTemplate
from apps.certificates.services import issue_certificate


class Command(BaseCommand):
    help = "Comprehensive DB seed: sessions, private sessions, requests, webinars, chat, etc."

    def handle(self, *args, **options):
        now = timezone.localtime()
        today = now.date()

        users = {u.email: u for u in User.objects.all()}
        admin = users.get("admin@hafez.com")
        supervisor = users.get("supervisor@hafez.com")
        teacher1 = users.get("teacher1@hafez.com")
        teacher2 = users.get("teacher2@hafez.com")
        student1 = users.get("student1@hafez.com")
        student2 = users.get("student2@hafez.com")
        student3 = users.get("student3@hafez.com")
        student4 = users.get("student4@hafez.com")
        student5 = users.get("student5@hafez.com")
        student6 = users.get("student6@hafez.com")

        if not all([admin, teacher1, student1]):
            self.stdout.write(self.style.ERROR("Run seed_data first"))
            return

        circles = {c.name: c for c in Circle.objects.all()}

        # ── 1. Fix batch assignments ──────────────────────────
        batch, _ = Batch.objects.get_or_create(
            name="الدفعة الأولى 1446",
            defaults=dict(
                number=1, year=1446,
                description="الدفعة الأولى للعام 1446 هـ",
                created_by=admin,
            ),
        )

        approved_students = User.objects.filter(
            role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        for s in approved_students:
            if not s.batch:
                s.batch = batch
                s.save()

        active_circles = Circle.objects.filter(status=Circle.Status.ACTIVE)
        for c in active_circles:
            if not c.batch:
                c.batch = batch
                c.save()

        self.stdout.write("  ✓ Batch assignments fixed")

        # ── 2. Session in 10 minutes ──────────────────────────
        session_time_10 = (now + timedelta(minutes=10)).time()
        session_time_10 = dtime(session_time_10.hour, session_time_10.minute)

        target_circle = active_circles.filter(teacher=teacher1).first()
        if target_circle:
            session_obj, created = Session.objects.update_or_create(
                circle=target_circle,
                session_date=today,
                defaults=dict(
                    session_time=session_time_10,
                    session_type=Session.Type.ONLINE,
                    location=target_circle.location or "غرفة الاختبار",
                    meeting_url="https://meet.google.com/abc-defg-hij",
                    notes=f"حصة اختبار بعد 10 دقائق - {now.strftime('%H:%M')}",
                ),
            )
            self.stdout.write(f"  {'Created' if created else 'Updated'} session in 10 min: {target_circle.name} @ {session_time_10}")
            self.stdout.write(f"  ✓ Session in 10 min: {target_circle.name} @ {session_time_10}")

        # ── 3. Private Sessions for student1 ──────────────────
        for i, (status, days_offset) in enumerate([
            ("scheduled", 0),
            ("scheduled", 1),
            ("completed", -3),
            ("completed", -7),
            ("cancelled", -2),
        ]):
            ps_date = today + timedelta(days=days_offset)
            ps_time = dtime(10 + i, 0)
            PrivateSession.objects.get_or_create(
                teacher=teacher1,
                student=student1,
                scheduled_date=ps_date,
                scheduled_time=ps_time,
                defaults=dict(
                    circle=target_circle,
                    status=status,
                    meeting_url=f"https://meet.google.com/private-{i+1}",
                    meeting_platform="google_meet",
                    student_notes="احتاج مساعدة في سورة البقرة" if i == 0 else "",
                    result_mark="جيد جداً" if status == "completed" else "",
                    result_notes="تم التركيز على أحكام التجويد" if status == "completed" else "",
                ),
            )
        self.stdout.write(f"  ✓ 5 Private sessions for {student1.full_name_ar}")

        # Also some for other students
        for student in [student2, student3, student4]:
            PrivateSession.objects.get_or_create(
                teacher=teacher1,
                student=student,
                scheduled_date=today + timedelta(days=2),
                scheduled_time=dtime(9, 0),
                defaults=dict(
                    circle=target_circle,
                    status="scheduled",
                    meeting_url="https://meet.google.com/private-session",
                    meeting_platform="google_meet",
                    student_notes="مراجعة عامة",
                ),
            )
        self.stdout.write(f"  ✓ Private sessions for 3 more students")

        # ── 4. Support Requests (all types/statuses) ─────────
        sr_data = [
            ("مشكلة في تسجيل الدخول", student1, "technical", "urgent", "submitted",
             "لا أستطيع تسجيل الدخول إلى حسابي منذ يومين"),
            ("طلب شهادة بدل فاقد", student2, "administrative", "high", "under_review",
             "فقدت شهادتي السابقة وأحتاج بدلاً لها"),
            ("استفسار عن منهج الحفظ", student3, "academic", "normal", "approved",
             "هل يمكن البدء بحفظ جزء عم بدلاً من جزء تبارك؟"),
            ("طلب تغيير الحلقة", student4, "administrative", "normal", "submitted",
             "أرغب في الانتقال إلى حلقة الفجر"),
            ("مشكلة في البث المباشر", student5, "technical", "urgent", "under_review",
             "البث المباشر لا يعمل عندي في حلقة العصر"),
            ("طلب اختبار شفوي", student6, "academic", "high", "submitted",
             "أحتاج اختبار شفوي للأجزاء التي حفظتها"),
            ("مشكلة في تطبيق الجوال", student1, "technical", "low", "resolved",
             "التطبيق يغلق فجأة عند فتح صفحة الاختبارات"),
            ("استفسار عن الرسوم", student2, "administrative", "normal", "resolved",
             "متى موعد سداد الرسوم الفصلية؟"),
            ("طلب إجازة", student3, "academic", "low", "rejected",
             "طلب إجازة لمدة أسبوع"),
            ("مشكلة في الكاميرا", student4, "technical", "high", "submitted",
             "الكاميرا لا تعمل أثناء الحصة"),
        ]
        for title, submitter, rtype, priority, status, body in sr_data:
            SupportRequest.objects.get_or_create(
                title=title,
                submitted_by=submitter,
                defaults=dict(
                    body=body,
                    type=rtype,
                    priority=priority,
                    status=status,
                ),
            )
        self.stdout.write(f"  ✓ {len(sr_data)} Support requests")

        # ── 5. Webinars ───────────────────────────────────────
        webinar_data = [
            ("كيف تحفظ القرآن في سنة", admin, now + timedelta(hours=2), "scheduled"),
            ("أحكام التجويد للمبتدئين", teacher1, now + timedelta(days=3), "scheduled"),
            ("المراجعة الفعالة للحفظ", teacher2, timezone.make_aware(datetime.combine(today - timedelta(days=2), dtime(10, 0))), "replay"),
            ("لقاء مفتوح مع المشرفين", supervisor, timezone.make_aware(datetime.combine(today - timedelta(days=5), dtime(15, 0))), "ended"),
            ("تفسير سورة الكهف", teacher1, timezone.make_aware(datetime.combine(today - timedelta(days=14), dtime(14, 0))), "ended"),
        ]
        for title, creator, sched, status in webinar_data:
            ended_at = sched + timedelta(hours=1) if status == "ended" else None
            Webinar.objects.get_or_create(
                title=title,
                scheduled_at=sched,
                defaults=dict(
                    description=f"ندوة حول: {title}",
                    created_by=creator,
                    status=status,
                    stream_url=f"https://youtube.com/watch?v=webinar-{random.randint(1000,9999)}",
                    speaker_room_name=f"room-{random.randint(1000,9999)}",
                    is_active=status not in ("ended",),
                    started_at=sched if status == "ended" else None,
                    ended_at=ended_at,
                ),
            )
        self.stdout.write(f"  ✓ {len(webinar_data)} Webinars")

        # ── 6. Chat conversations ─────────────────────────────
        conv, _ = Conversation.objects.get_or_create(
            id=1,
            defaults=dict(last_message_at=now - timedelta(minutes=30)),
        )
        conv.participants.add(teacher1, student1)

        for msg_body, mins_ago in [
            ("السلام عليكم يا أستاذ، عندي سؤال", 30),
            ("وعليكم السلام ورحمة الله، تفضل", 28),
            ("في سورة البقرة آية 255، كيف نطقها صحيح؟", 25),
            ("هذه آية الكرسي، تقرأ بالمد الطبيعي في (الله) ثم تقف", 22),
            ("جزاك الله خيراً يا أستاذ، فهمت", 20),
            ("وفقك الله يا بني", 18),
        ]:
            sender = teacher1 if "أستاذ" not in msg_body and "وفقك" not in msg_body else teacher1
            if msg_body in ["السلام عليكم يا أستاذ، عندي سؤال", "في سورة البقرة آية 255، كيف نطقها صحيح؟", "جزاك الله خيراً يا أستاذ، فهمت"]:
                sender = student1
            Message.objects.get_or_create(
                conversation=conv,
                sender=sender,
                body=msg_body,
                created_at=now - timedelta(minutes=mins_ago),
            )
        self.stdout.write("  ✓ Chat conversation (teacher1 ↔ student1)")

        # Second conversation
        conv2, _ = Conversation.objects.get_or_create(
            id=2,
            defaults=dict(last_message_at=now - timedelta(hours=1)),
        )
        conv2.participants.add(supervisor, student2)

        Message.objects.get_or_create(
            conversation=conv2, sender=student2,
            body="السلام عليكم، هل يمكنني الحصول على شهادة؟",
            created_at=now - timedelta(hours=1),
        )
        Message.objects.get_or_create(
            conversation=conv2, sender=supervisor,
            body="وعليكم السلام، نعم يمكنك التقديم عبر صفحة الشهادات",
            created_at=now - timedelta(minutes=55),
        )
        self.stdout.write("  ✓ Chat conversation (supervisor ↔ student2)")

        # ── 7. Teacher Rooms ──────────────────────────────────
        for teacher in [teacher1, teacher2]:
            TeacherRoom.objects.get_or_create(
                teacher=teacher,
                defaults=dict(
                    room_name=f"غرفة {teacher.full_name_ar}",
                    slug=f"room-{teacher.id}",
                    is_active=True,
                ),
            )
        self.stdout.write("  ✓ Teacher rooms")

        # ── 8. More exams and marks ──────────────────────────
        for i in range(2):
            exam_date = today - timedelta(days=random.randint(15, 45))
            exam, _ = Exam.objects.get_or_create(
                title=f"الاختبار الشهري - {i+1}",
                defaults=dict(
                    exam_type="monthly",
                    circle=target_circle or active_circles.first(),
                    created_by=admin,
                    exam_date=exam_date,
                    max_marks=100,
                    pass_percentage=50,
                    status=Exam.Status.COMPLETED,
                ),
            )
            for s in approved_students[:10]:
                marks = random.uniform(40, 100)
                ExamMark.objects.get_or_create(
                    exam=exam, student=s,
                    defaults=dict(
                        marks_obtained=marks,
                        is_passed=marks >= 50,
                        status=ExamMark.Status.APPROVED,
                        entered_by=teacher1,
                        approved_by=admin,
                    ),
                )
        self.stdout.write("  ✓ 2 More exams with marks")

        # ── 9. More certificates ─────────────────────────────
        templates = list(CertificateTemplate.objects.filter(is_active=True))
        if templates:
            for idx, s in enumerate(approved_students[:3]):
                template = templates[idx % len(templates)]
                existing = Certificate.objects.filter(student=s).count()
                if existing < 2:
                    try:
                        issue_certificate(
                            student=s,
                            template=template,
                            issued_by=admin,
                            details=f"جزء {random.randint(1, 10)}",
                            metadata={"circle_name": target_circle.name if target_circle else ""},
                        )
                    except Exception:
                        pass
        self.stdout.write("  ✓ Certificates")

        # ── 10. More sessions with attendance for recent days ─
        for circle in active_circles:
            for days_ago in range(5, 0, -1):
                session_date = today - timedelta(days=days_ago)
                if session_date.weekday() >= 5:
                    continue
                session, _ = Session.objects.update_or_create(
                    circle=circle,
                    session_date=session_date,
                    defaults=dict(
                        session_type=random.choice([Session.Type.IN_PERSON, Session.Type.ONLINE]),
                        location=circle.location or "المسجد",
                    ),
                )
                active = circle.enrollments.filter(status=CircleEnrollment.Status.ACTIVE)
                for enr in active:
                    Attendance.objects.get_or_create(
                        session=session,
                        student=enr.student,
                        defaults=dict(
                            status=random.choices(
                                [Attendance.Status.PRESENT, Attendance.Status.LATE,
                                 Attendance.Status.ABSENT, Attendance.Status.EXCUSED],
                                weights=[65, 15, 12, 8], k=1
                            )[0],
                        ),
                    )
        self.stdout.write("  ✓ Recent sessions + attendance")

        # ── Summary ──────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("\n═══ COMPREHENSIVE SEED SUMMARY ═══"))
        self.stdout.write(f"  Users:            {User.objects.count()}")
        self.stdout.write(f"  Batches:          {Batch.objects.count()}")
        self.stdout.write(f"  Circles:          {Circle.objects.count()}")
        self.stdout.write(f"  Enrollments:      {CircleEnrollment.objects.filter(status='active').count()}")
        self.stdout.write(f"  Sessions:         {Session.objects.count()}")
        self.stdout.write(f"  PrivateSessions:  {PrivateSession.objects.count()}")
        self.stdout.write(f"  Attendance:       {Attendance.objects.count()}")
        self.stdout.write(f"  SupportRequests:  {SupportRequest.objects.count()}")
        self.stdout.write(f"  Announcements:    {Announcement.objects.count()}")
        self.stdout.write(f"  Webinars:         {Webinar.objects.count()}")
        self.stdout.write(f"  Conversations:    {Conversation.objects.count()}")
        self.stdout.write(f"  Messages:         {Message.objects.count()}")
        self.stdout.write(f"  Exams:            {Exam.objects.count()}")
        self.stdout.write(f"  ExamMarks:        {ExamMark.objects.count()}")
        self.stdout.write(f"  Certificates:     {Certificate.objects.count()}")
        self.stdout.write(f"  TeacherRooms:     {TeacherRoom.objects.count()}")
        self.stdout.write(f"\n  student1@hafez.com / test1234 — ready to test all features")
