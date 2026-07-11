from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.memorization import review_engine as engine
from apps.memorization.models import (
    MemorizationRecord, ProgressLog, ReviewHistory, ReviewRequest, StudyTask,
)
from apps.notifications.models import Notification
from apps.references.models import Rub, Surah


class SRSEngineTest(TestCase):
    def test_first_memorize_interval(self):
        self.assertEqual(engine.first_interval_days(), 1)

    def test_growth_multipliers(self):
        self.assertEqual(engine.calculate_next_interval(10, "جيد"), 15)
        self.assertEqual(engine.calculate_next_interval(10, "جيد جداً"), 20)
        self.assertEqual(engine.calculate_next_interval(10, "ممتاز"), 25)

    def test_acceptable_holds(self):
        self.assertEqual(engine.calculate_next_interval(30, "مقبول"), 30)

    def test_weak_and_failed_reset(self):
        self.assertEqual(engine.calculate_next_interval(120, "ضعيف"), 1)
        self.assertEqual(engine.calculate_next_interval(120, "راسب"), 1)

    def test_cap(self):
        self.assertEqual(engine.calculate_next_interval(300, "ممتاز"), 365)

    def test_invalid_evaluation_treated_as_reset(self):
        # unknown evaluations map to None multiplier -> reset
        self.assertEqual(engine.calculate_next_interval(50, "غير معروف"), 1)


class MemorizationRecordTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_quran")
        cls.teacher = User.objects.create_user(
            username="t@test.com", email="t@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.other_teacher = User.objects.create_user(
            username="t2@test.com", email="t2@test.com", password="x",
            full_name_ar="معلم آخر", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.student = User.objects.create_user(
            username="s@test.com", email="s@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.circle = Circle.objects.create(name="حلقة", teacher=cls.teacher,
                                           status=Circle.Status.ACTIVE)
        CircleEnrollment.objects.create(circle=cls.circle, student=cls.student,
                                        status=CircleEnrollment.Status.ACTIVE)
        cls.rub = Rub.objects.get(number=1)

    def test_record_for_is_idempotent(self):
        r1 = MemorizationRecord.record_for(self.student, self.rub)
        r2 = MemorizationRecord.record_for(self.student, 1)
        self.assertEqual(r1.pk, r2.pk)
        self.assertEqual(MemorizationRecord.objects.count(), 1)

    def test_mark_memorized_schedules_review(self):
        rec = MemorizationRecord.record_for(self.student, self.rub)
        rec.mark_memorized()
        rec.refresh_from_db()
        self.assertEqual(rec.status, MemorizationRecord.Status.MEMORIZED)
        self.assertIsNotNone(rec.next_review_date)
        self.assertEqual(rec.review_interval_days, 1)

    def test_evaluate_appends_history_and_reschedules(self):
        rec = MemorizationRecord.record_for(self.student, self.rub)
        rec.mark_memorized()
        rec.evaluate(self.teacher, "جيد جداً", mistakes_count=1, notes="جيد")
        rec.refresh_from_db()
        self.assertEqual(rec.review_count, 1)
        self.assertEqual(rec.review_interval_days, 2)  # 1 * 2.0
        self.assertEqual(ReviewHistory.objects.filter(record=rec).count(), 1)
        h = ReviewHistory.objects.get(record=rec)
        self.assertEqual(h.previous_interval, 1)
        self.assertEqual(h.new_interval, 2)

    def test_evaluate_weak_sets_weak_status_and_resets(self):
        rec = MemorizationRecord.record_for(self.student, self.rub)
        rec.mark_memorized()
        rec.review_interval_days = 60
        rec.save(update_fields=["review_interval_days"])
        rec.evaluate(self.teacher, "ضعيف", mistakes_count=8)
        rec.refresh_from_db()
        self.assertEqual(rec.status, MemorizationRecord.Status.WEAK)
        self.assertEqual(rec.review_interval_days, 1)

    def test_evaluate_rejects_unrelated_teacher(self):
        rec = MemorizationRecord.record_for(self.student, self.rub)
        rec.mark_memorized()
        with self.assertRaises(ValidationError):
            rec.evaluate(self.other_teacher, "جيد")

    def test_evaluate_rejects_invalid_evaluation(self):
        rec = MemorizationRecord.record_for(self.student, self.rub)
        with self.assertRaises(ValidationError):
            rec.evaluate(self.teacher, "xyz")

    def test_due_queryset_is_daily_plan(self):
        rec = MemorizationRecord.record_for(self.student, self.rub)
        rec.mark_memorized()
        # push due date into the past
        rec.next_review_date = timezone.localdate() - timedelta(days=1)
        rec.save(update_fields=["next_review_date"])
        due = MemorizationRecord.objects.due(self.student)
        self.assertIn(rec, list(due))

    def test_not_memorized_excluded_from_due(self):
        rec = MemorizationRecord.record_for(self.student, self.rub)
        rec.next_review_date = timezone.localdate()
        rec.save(update_fields=["next_review_date"])
        self.assertNotIn(rec, list(MemorizationRecord.objects.due(self.student)))

    def test_weak_sections(self):
        rec = MemorizationRecord.record_for(self.student, self.rub)
        rec.mark_memorized()
        rec.evaluate(self.teacher, "راسب")
        weak = engine.get_weak_sections(self.student)
        self.assertIn(rec, list(weak))


class StudyTaskTest(TestCase):
    """HAF-03/07/21 + HAF-04: model-level validation, permission, state guards,
    the MemorizationRecord bridge, and notification dispatch."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_quran")
        cls.teacher = User.objects.create_user(
            username="t@test.com", email="t@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.other_teacher = User.objects.create_user(
            username="t2@test.com", email="t2@test.com", password="x",
            full_name_ar="معلم آخر", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.student = User.objects.create_user(
            username="s@test.com", email="s@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.circle = Circle.objects.create(name="حلقة", teacher=cls.teacher,
                                           status=Circle.Status.ACTIVE)
        CircleEnrollment.objects.create(circle=cls.circle, student=cls.student,
                                        status=CircleEnrollment.Status.ACTIVE)
        cls.ikhlas = Surah.objects.get(pk=112)  # 4 ayahs
        cls.baqarah = Surah.objects.get(pk=2)   # 286 ayahs

    def _assign(self, ayah_from=1, ayah_to=4, surah=None, task_type=StudyTask.TaskType.HIFZ):
        return StudyTask.assign(
            student=self.student, assigned_by=self.teacher, task_type=task_type,
            surah=surah or self.ikhlas, ayah_from=ayah_from, ayah_to=ayah_to,
            circle=self.circle,
        )

    def test_assign_rejects_impossible_ayah_range(self):
        # HAF-03: al-Ikhlas has 4 ayahs — asking for ayah 500 must fail.
        with self.assertRaises(ValidationError):
            self._assign(ayah_from=1, ayah_to=500)

    def test_save_enforces_range_at_model_level(self):
        # Even a raw create (bypassing assign) is guarded by save().
        with self.assertRaises(ValidationError):
            StudyTask.objects.create(
                student=self.student, assigned_by=self.teacher,
                task_type=StudyTask.TaskType.HIFZ, surah=self.ikhlas,
                ayah_from=1, ayah_to=99,
            )

    def test_assign_rejects_unrelated_teacher(self):
        with self.assertRaises(ValidationError):
            StudyTask.assign(
                student=self.student, assigned_by=self.other_teacher,
                task_type=StudyTask.TaskType.HIFZ, surah=self.ikhlas,
                ayah_from=1, ayah_to=4,
            )

    def test_assign_notifies_student(self):
        self._assign()
        self.assertTrue(Notification.objects.filter(
            recipient=self.student, type=Notification.Type.TASK_ASSIGNED,
        ).exists())

    def test_validate_requires_done_state(self):
        task = self._assign()
        with self.assertRaises(ValidationError):
            task.validate(by=self.teacher)  # still PENDING

    def test_validate_rejects_unrelated_teacher(self):
        task = self._assign()
        task.mark_done(by=self.student)
        with self.assertRaises(ValidationError):
            task.validate(by=self.other_teacher)

    def test_validate_records_validator_and_bridges_to_records(self):
        task = self._assign()
        task.mark_done(by=self.student)
        task.validate(by=self.teacher)
        task.refresh_from_db()
        self.assertEqual(task.status, StudyTask.Status.VALIDATED)
        self.assertEqual(task.validated_by, self.teacher)
        # HAF-21: a validated hifz task advances the canonical record.
        self.assertTrue(MemorizationRecord.objects.filter(
            student=self.student,
        ).exclude(status=MemorizationRecord.Status.NOT_MEMORIZED).exists())

    def test_reject_sets_reason_and_no_bridge(self):
        task = self._assign()
        task.mark_done(by=self.student)
        task.validate(by=self.teacher, rejection_reason="أعد الحفظ")
        task.refresh_from_db()
        self.assertEqual(task.status, StudyTask.Status.REJECTED)
        self.assertEqual(task.rejection_reason, "أعد الحفظ")
        self.assertFalse(MemorizationRecord.objects.filter(
            student=self.student,
        ).exclude(status=MemorizationRecord.Status.NOT_MEMORIZED).exists())


class ReviewRequestQuestionTest(TestCase):
    """Ask-the-teacher (سؤال للمعلم): a question ticket the teacher resolves with
    a written answer rather than a scheduled session."""

    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user(
            username="qt@test.com", email="qt@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.other_teacher = User.objects.create_user(
            username="qt2@test.com", email="qt2@test.com", password="x",
            full_name_ar="معلم آخر", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.student = User.objects.create_user(
            username="qs@test.com", email="qs@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.circle = Circle.objects.create(name="حلقة", teacher=cls.teacher,
                                           status=Circle.Status.ACTIVE)
        CircleEnrollment.objects.create(circle=cls.circle, student=cls.student,
                                        status=CircleEnrollment.Status.ACTIVE)

    def _question(self):
        return self.student.submit_review_request(
            circle=self.circle, type=ReviewRequest.Type.QUESTION,
            notes="ما حكم المد المتصل؟",
        )

    def test_question_needs_no_surah_or_ayah(self):
        req = self._question()
        self.assertEqual(req.type, ReviewRequest.Type.QUESTION)
        self.assertIsNone(req.surah_id)
        self.assertEqual(req.status, ReviewRequest.Status.PENDING)

    def test_answer_resolves_and_stores_response(self):
        req = self._question()
        req.answer(by=self.teacher, response_text="المد المتصل واجب بمقدار أربع حركات")
        req.refresh_from_db()
        self.assertEqual(req.status, ReviewRequest.Status.APPROVED)
        self.assertEqual(req.reviewed_by, self.teacher)
        self.assertIn("واجب", req.response)
        # student is notified of the answer
        self.assertTrue(Notification.objects.filter(
            recipient=self.student, title="تم الرد على سؤالك",
        ).exists())

    def test_answer_requires_text(self):
        req = self._question()
        with self.assertRaises(ValidationError):
            req.answer(by=self.teacher, response_text="   ")

    def test_answer_rejects_unrelated_teacher(self):
        req = self._question()
        with self.assertRaises(ValidationError):
            req.answer(by=self.other_teacher, response_text="رد")

    def test_answer_only_for_question_type(self):
        recitation = self.student.submit_review_request(
            circle=self.circle, type=ReviewRequest.Type.RECITATION,
        )
        with self.assertRaises(ValidationError):
            recitation.answer(by=self.teacher, response_text="رد")


class PrivateSessionTest(TestCase):
    """Approving a تسميع request spawns a private 1-on-1 session with a link,
    time, reminder and teacher results marking."""

    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user(
            username="pt@test.com", email="pt@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.other_teacher = User.objects.create_user(
            username="pt2@test.com", email="pt2@test.com", password="x",
            full_name_ar="معلم آخر", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.student = User.objects.create_user(
            username="ps@test.com", email="ps@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.circle = Circle.objects.create(name="حلقة", teacher=cls.teacher,
                                           status=Circle.Status.ACTIVE)
        CircleEnrollment.objects.create(circle=cls.circle, student=cls.student,
                                        status=CircleEnrollment.Status.ACTIVE)

    def _approved_recitation(self):
        req = self.student.submit_review_request(
            circle=self.circle, type=ReviewRequest.Type.RECITATION,
            notes="حفظ جديد — سورة الملك",
        )
        req.approve(
            by=self.teacher, scheduled_date=timezone.localdate() + timedelta(days=1),
            scheduled_time="10:00", meeting_url="https://meet.example/abc",
        )
        return req

    def test_approval_creates_private_session(self):
        from apps.memorization.models import PrivateSession
        req = self._approved_recitation()
        ps = PrivateSession.objects.get(source_request=req)
        self.assertEqual(ps.teacher, self.teacher)
        self.assertEqual(ps.student, self.student)
        self.assertEqual(ps.status, PrivateSession.Status.SCHEDULED)
        self.assertEqual(ps.meeting_url, "https://meet.example/abc")
        self.assertIn("حفظ جديد", ps.student_notes)
        # the student is notified with the scheduled details
        self.assertTrue(Notification.objects.filter(
            recipient=self.student, title="تم تحديد جلسة تسميع خاصة",
        ).exists())

    def test_question_approval_does_not_create_session(self):
        from apps.memorization.models import PrivateSession
        req = self.student.submit_review_request(
            circle=self.circle, type=ReviewRequest.Type.QUESTION, notes="سؤال",
        )
        req.answer(by=self.teacher, response_text="جواب")
        self.assertFalse(PrivateSession.objects.filter(source_request=req).exists())

    def test_mark_result_completes_and_notifies(self):
        from apps.memorization.models import PrivateSession
        ps = PrivateSession.objects.get(source_request=self._approved_recitation())
        ps.mark_result(by=self.teacher, result_mark="ممتاز", result_notes="أداء جيد")
        ps.refresh_from_db()
        self.assertEqual(ps.status, PrivateSession.Status.COMPLETED)
        self.assertEqual(ps.result_mark, "ممتاز")
        self.assertTrue(Notification.objects.filter(
            recipient=self.student, title="تم تقييم جلستك الخاصة",
        ).exists())

    def test_mark_result_rejects_unrelated_teacher(self):
        from apps.memorization.models import PrivateSession
        ps = PrivateSession.objects.get(source_request=self._approved_recitation())
        with self.assertRaises(ValidationError):
            ps.mark_result(by=self.other_teacher, result_mark="جيد")

    def test_reminder_command_notifies_once(self):
        from django.core.management import call_command
        from apps.memorization.models import PrivateSession
        ps = PrivateSession.objects.get(source_request=self._approved_recitation())
        call_command("send_session_reminders")
        ps.refresh_from_db()
        self.assertIsNotNone(ps.reminder_sent_at)
        self.assertTrue(Notification.objects.filter(
            recipient=self.student, title="تذكير: جلسة تسميع خاصة",
        ).exists())
        # idempotent — a second run doesn't re-remind
        before = Notification.objects.filter(recipient=self.student).count()
        call_command("send_session_reminders")
        self.assertEqual(Notification.objects.filter(recipient=self.student).count(), before)

    def test_effective_meeting_url_uses_explicit_link(self):
        from apps.memorization.models import PrivateSession
        ps = PrivateSession.objects.get(source_request=self._approved_recitation())
        self.assertEqual(ps.effective_meeting_url(), "https://meet.example/abc")

    def test_effective_meeting_url_falls_back_to_classroom_room(self):
        from django.urls import reverse
        from apps.classrooms.models import TeacherRoom
        from apps.memorization.models import PrivateSession
        # Every teacher auto-gets a permanent room via signal.
        room = TeacherRoom.objects.get(teacher=self.teacher)
        ps = PrivateSession.objects.create(teacher=self.teacher, student=self.student)
        self.assertEqual(
            ps.effective_meeting_url(),
            reverse("classrooms:join", kwargs={"slug": room.slug}),
        )

    def test_effective_meeting_url_blank_without_link_or_room(self):
        from apps.classrooms.models import TeacherRoom
        from apps.memorization.models import PrivateSession
        # Teachers auto-get a room via signal; drop it to exercise the no-room path.
        TeacherRoom.objects.filter(teacher=self.other_teacher).delete()
        ps = PrivateSession.objects.create(teacher=self.other_teacher, student=self.student)
        self.assertEqual(ps.effective_meeting_url(), "")





class StudyTaskTodoWorkflowTest(TestCase):
    """The Todo requirements: due date, linked session, overdue detection,
    recitation type, and the REST API workflow with role scoping."""

    @classmethod
    def setUpTestData(cls):
        from datetime import date, timedelta
        call_command("seed_quran")
        cls.teacher = User.objects.create_user(
            username="tt@test.com", email="tt@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.student = User.objects.create_user(
            username="ss@test.com", email="ss@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.outsider = User.objects.create_user(
            username="out@test.com", email="out@test.com", password="x",
            full_name_ar="طالب آخر", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.circle = Circle.objects.create(name="حلقة", teacher=cls.teacher,
                                           status=Circle.Status.ACTIVE)
        CircleEnrollment.objects.create(circle=cls.circle, student=cls.student,
                                        status=CircleEnrollment.Status.ACTIVE)
        cls.session = Session.objects.create(
            circle=cls.circle, session_date=date.today(),
        )
        cls.ikhlas = Surah.objects.get(pk=112)

    def test_assign_with_due_date_and_session(self):
        from datetime import date, timedelta
        due = date.today() + timedelta(days=3)
        task = StudyTask.assign(
            student=self.student, assigned_by=self.teacher,
            task_type=StudyTask.TaskType.HIFZ, surah=self.ikhlas,
            ayah_from=1, ayah_to=4, circle=self.circle,
            due_date=due, session=self.session,
        )
        task.refresh_from_db()
        self.assertEqual(task.due_date, due)
        self.assertEqual(task.session_id, self.session.id)
        self.assertFalse(task.is_overdue)

    def test_overdue_detection_and_queryset(self):
        from datetime import date, timedelta
        task = StudyTask.assign(
            student=self.student, assigned_by=self.teacher,
            task_type=StudyTask.TaskType.MURAJAA, surah=self.ikhlas,
            ayah_from=1, ayah_to=4, due_date=date.today() - timedelta(days=1),
        )
        self.assertTrue(task.is_overdue)
        self.assertIn(task, StudyTask.objects.overdue())
        task.mark_done(by=self.student)
        self.assertFalse(task.is_overdue)
        self.assertNotIn(task, StudyTask.objects.overdue())

    def test_recitation_task_type_does_not_touch_memorization(self):
        task = StudyTask.assign(
            student=self.student, assigned_by=self.teacher,
            task_type=StudyTask.TaskType.RECITATION, surah=self.ikhlas,
            ayah_from=1, ayah_to=4,
        )
        task.mark_done(by=self.student)
        task.validate(by=self.teacher)
        self.assertEqual(task.status, StudyTask.Status.VALIDATED)
        self.assertFalse(
            MemorizationRecord.objects.filter(student=self.student).exists()
        )

    # ── REST API ────────────────────────────────────────────────────────
    def test_api_full_todo_lifecycle(self):
        from datetime import date, timedelta
        self.client.force_login(self.teacher)
        resp = self.client.post("/api/v1/tasks/", {
            "student_id": str(self.student.id),
            "task_type": "hifz", "surah": 112,
            "ayah_from": 1, "ayah_to": 4,
            "due_date": (date.today() + timedelta(days=2)).isoformat(),
            "session": self.session.id,
            "notes": "مهمة اختبار",
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 201, resp.content)
        task_id = resp.json()["data"]["id"]

        # student sees it and marks it done
        self.client.force_login(self.student)
        resp = self.client.get("/api/v1/tasks/")
        payload = resp.json()
        items = payload.get("data") or payload.get("results")
        self.assertEqual(len(items), 1)
        resp = self.client.post(f"/api/v1/tasks/{task_id}/done/")
        self.assertEqual(resp.status_code, 200, resp.content)

        # teacher validates
        self.client.force_login(self.teacher)
        resp = self.client.post(f"/api/v1/tasks/{task_id}/validate/")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(StudyTask.objects.get(pk=task_id).status,
                         StudyTask.Status.VALIDATED)

    def test_api_student_cannot_create_or_delete(self):
        task = StudyTask.assign(
            student=self.student, assigned_by=self.teacher,
            task_type=StudyTask.TaskType.HIFZ, surah=self.ikhlas,
            ayah_from=1, ayah_to=4,
        )
        self.client.force_login(self.student)
        resp = self.client.post("/api/v1/tasks/", {
            "student_id": str(self.student.id), "task_type": "hifz",
            "surah": 112, "ayah_from": 1, "ayah_to": 4,
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 403)
        resp = self.client.delete(f"/api/v1/tasks/{task.id}/")
        self.assertEqual(resp.status_code, 403)

    def test_api_other_student_cannot_see_task(self):
        task = StudyTask.assign(
            student=self.student, assigned_by=self.teacher,
            task_type=StudyTask.TaskType.HIFZ, surah=self.ikhlas,
            ayah_from=1, ayah_to=4,
        )
        self.client.force_login(self.outsider)
        resp = self.client.get(f"/api/v1/tasks/{task.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_api_rejects_invalid_range(self):
        self.client.force_login(self.teacher)
        resp = self.client.post("/api/v1/tasks/", {
            "student_id": str(self.student.id), "task_type": "hifz",
            "surah": 112, "ayah_from": 1, "ayah_to": 500,
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 400)


class ProgressLogRecitationTest(TestCase):
    """Session marking must support the recitation type end to end."""

    @classmethod
    def setUpTestData(cls):
        from datetime import date
        call_command("seed_quran")
        cls.teacher = User.objects.create_user(
            username="tr@test.com", email="tr@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.student = User.objects.create_user(
            username="sr@test.com", email="sr@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.circle = Circle.objects.create(name="حلقة", teacher=cls.teacher,
                                           status=Circle.Status.ACTIVE)
        CircleEnrollment.objects.create(circle=cls.circle, student=cls.student,
                                        status=CircleEnrollment.Status.ACTIVE)
        cls.session = Session.objects.create(circle=cls.circle, session_date=date.today())

    def test_api_records_recitation_log(self):
        self.client.force_login(self.teacher)
        resp = self.client.post(f"/api/v1/sessions/{self.session.id}/logs/", {
            "student_id": str(self.student.id),
            "log_category": "RECITATION",
            "surah_number": 1, "start_ayah": 1, "end_ayah": 7,
            "evaluation_grade": "A",
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 201, resp.content)
        log = ProgressLog.objects.get(student=self.student)
        self.assertEqual(log.log_category, ProgressLog.Category.RECITATION)
        self.assertEqual(log.get_log_category_display(), "تلاوة")

    def test_recitation_filterable(self):
        from apps.memorization.engine import create_progress_log
        create_progress_log(
            session=self.session, student=self.student,
            log_category=ProgressLog.Category.RECITATION,
            surah=Surah.objects.get(pk=1), start_ayah=1, end_ayah=7,
        )
        self.client.force_login(self.teacher)
        resp = self.client.get("/api/v1/progress-logs/?log_category=RECITATION")
        payload = resp.json()
        items = payload.get("data") or payload.get("results")
        self.assertEqual(len(items), 1)


class SessionReportTest(TestCase):
    """After-session report: recorded entries carry surah/ayah range, thumn
    amount, mark /20 and remark; todos assigned in the session appear too."""

    @classmethod
    def setUpTestData(cls):
        from datetime import date
        call_command("seed_quran")
        call_command("seed_thumns")
        cls.teacher = User.objects.create_user(
            username="rep_t@test.com", email="rep_t@test.com", password="x",
            full_name_ar="معلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.student = User.objects.create_user(
            username="rep_s@test.com", email="rep_s@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.circle = Circle.objects.create(name="حلقة", teacher=cls.teacher,
                                           status=Circle.Status.ACTIVE)
        CircleEnrollment.objects.create(circle=cls.circle, student=cls.student,
                                        status=CircleEnrollment.Status.ACTIVE)
        cls.session = Session.objects.create(circle=cls.circle, session_date=date.today())

    def test_points_stored_via_api_and_report_contents(self):
        from apps.memorization.engine import session_report_data
        self.client.force_login(self.teacher)
        resp = self.client.post(f"/api/v1/sessions/{self.session.id}/logs/", {
            "student_id": str(self.student.id), "log_category": "HIFDH",
            "surah_number": 2, "start_ayah": 1, "end_ayah": 141,
            "points": "17.5", "teacher_notes": "أداء متقن",
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(str(ProgressLog.objects.get().points), "17.5")

        StudyTask.assign(
            student=self.student, assigned_by=self.teacher,
            task_type=StudyTask.TaskType.MURAJAA, surah=2,
            ayah_from=1, ayah_to=141, session=self.session, notes="راجع جيداً",
        )
        report_rows, todo_rows = session_report_data(self.session)
        self.assertEqual(len(report_rows), 1)
        row = report_rows[0]
        self.assertEqual(row["surah"], "البقرة")
        self.assertEqual((row["ayah_from"], row["ayah_to"]), (1, 141))
        self.assertEqual(str(row["points"]), "17.5")
        self.assertEqual(row["remark"], "أداء متقن")
        self.assertIn("حزب", row["thumn_units"])  # ~2 hizb worth of thumns
        self.assertEqual(len(todo_rows), 1)
        self.assertEqual(todo_rows[0]["surah"], "البقرة")
        self.assertIn("حزب", todo_rows[0]["thumn_units"])
        self.assertEqual(todo_rows[0]["remark"], "راجع جيداً")

    def test_points_out_of_range_rejected(self):
        self.client.force_login(self.teacher)
        resp = self.client.post(f"/api/v1/sessions/{self.session.id}/logs/", {
            "student_id": str(self.student.id), "log_category": "HIFDH",
            "surah_number": 1, "start_ayah": 1, "end_ayah": 7, "points": "25",
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 422)

    def test_teacher_and_student_session_pages_show_report(self):
        from apps.memorization.engine import create_progress_log
        from apps.references.models import Surah
        create_progress_log(
            session=self.session, student=self.student,
            log_category=ProgressLog.Category.RECITATION,
            surah=Surah.objects.get(pk=1), start_ayah=1, end_ayah=7,
            points=18, teacher_notes="تلاوة حسنة",
        )
        self.client.force_login(self.teacher)
        r = self.client.get(f"/dashboard/teacher/sessions/{self.session.id}/")
        self.assertContains(r, "تقرير الحصة")
        self.assertContains(r, "18")
        self.assertContains(r, "تلاوة حسنة")
        self.client.force_login(self.student)
        r = self.client.get(f"/dashboard/student/sessions/{self.session.id}/")
        self.assertContains(r, "تقريري في هذه الحصة")
        self.assertContains(r, "تلاوة حسنة")

    def test_task_assign_api_400_for_unrelated_student(self):
        """Regression: NameError made this 500 in production."""
        outsider = User.objects.create_user(
            username="rep_o@test.com", email="rep_o@test.com", password="x",
            full_name_ar="طالب خارجي", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.client.force_login(self.teacher)
        resp = self.client.post("/api/v1/tasks/", {
            "student_id": str(outsider.id), "task_type": "hifz",
            "surah": 1, "ayah_from": 1, "ayah_to": 7,
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_review_request_api_400_for_non_enrolled(self):
        """Regression: integrity-signal ValidationError leaked as 500."""
        outsider = User.objects.create_user(
            username="rep_o2@test.com", email="rep_o2@test.com", password="x",
            full_name_ar="طالب خارجي", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.client.force_login(outsider)
        resp = self.client.post("/api/v1/review-requests/", {
            "circle": self.circle.id, "type": "question", "notes": "سؤال",
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 400, resp.content)


class CircleRemoveStudentApiTest(TestCase):
    """Regression: removing a non-enrolled student returned 500 (bare .get())."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_quran")
        cls.admin = User.objects.create_user(
            username="rm_a@test.com", email="rm_a@test.com", password="x",
            full_name_ar="مدير", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        cls.student = User.objects.create_user(
            username="rm_s@test.com", email="rm_s@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.circle = Circle.objects.create(name="حلقة", status=Circle.Status.ACTIVE)

    def test_remove_non_enrolled_student_returns_400(self):
        self.client.force_login(self.admin)
        resp = self.client.post(f"/api/v1/circles/{self.circle.id}/remove_student/", {
            "student_id": str(self.student.id),
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_remove_enrolled_student_succeeds(self):
        CircleEnrollment.objects.create(
            circle=self.circle, student=self.student,
            status=CircleEnrollment.Status.ACTIVE,
        )
        self.client.force_login(self.admin)
        resp = self.client.post(f"/api/v1/circles/{self.circle.id}/remove_student/", {
            "student_id": str(self.student.id),
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content)
        enr = CircleEnrollment.objects.get(circle=self.circle, student=self.student)
        self.assertEqual(enr.status, CircleEnrollment.Status.INACTIVE)


class CircleReEnrollApiTest(TestCase):
    """Regression: re-enrolling a previously removed student raised
    IntegrityError (unique_together) → 500. Enrollment must reactivate."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_quran")
        cls.admin = User.objects.create_user(
            username="re_a@test.com", email="re_a@test.com", password="x",
            full_name_ar="مدير", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        cls.student = User.objects.create_user(
            username="re_s@test.com", email="re_s@test.com", password="x",
            full_name_ar="طالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.circle = Circle.objects.create(name="حلقة", status=Circle.Status.ACTIVE)

    def test_remove_then_reenroll_reactivates(self):
        self.client.force_login(self.admin)
        r = self.client.post(f"/api/v1/circles/{self.circle.id}/enroll/",
                             {"student_id": str(self.student.id)},
                             content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.client.post(f"/api/v1/circles/{self.circle.id}/remove_student/",
                             {"student_id": str(self.student.id)},
                             content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.client.post(f"/api/v1/circles/{self.circle.id}/enroll/",
                             {"student_id": str(self.student.id)},
                             content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(
            CircleEnrollment.objects.filter(circle=self.circle, student=self.student).count(), 1)
        self.assertEqual(
            CircleEnrollment.objects.get(circle=self.circle, student=self.student).status,
            CircleEnrollment.Status.ACTIVE)
