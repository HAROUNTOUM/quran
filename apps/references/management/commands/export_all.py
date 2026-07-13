"""Export all Quran reference and memorization data to JSON files in /home/abdelalim/projects/scrap/."""
import json
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db.models import Prefetch

from apps.references.models import Ayah, Hizb, Juz, Rub, Surah
from apps.memorization.models import (
    MemorizationRecord,
    MemorizationProgress,
    ProgressLog,
    ReviewHistory,
    ReviewRequest,
    StudyTask,
    StudentAchievement,
)
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.accounts.models import User


def serialize(obj):
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

OUT = Path("/home/abdelalim/projects/scrap")


class Command(BaseCommand):
    help = "Export all Quran data to JSON files"

    def handle(self, *args, **opts):
        OUT.mkdir(parents=True, exist_ok=True)

        self._export_surahs()
        self._export_juz()
        self._export_hizb()
        self._export_rub()
        self._export_ayahs()
        self._export_memorization()
        self._export_progress_logs()
        self._export_review_history()
        self._export_study_tasks()
        self._export_review_requests()
        self._export_achievements()
        self._export_circles()
        self._export_users()
        self._export_summary()

    def _export_surahs(self):
        data = []
        for s in Surah.objects.all():
            data.append({
                "id": s.id,
                "name_ar": s.name_ar,
                "name_en": s.name_en,
                "ayah_count": s.ayah_count,
                "revelation_type": s.revelation_type,
            })
        (OUT / "surahs.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  surahs.json — {len(data)} surahs")

    def _export_juz(self):
        data = []
        for j in Juz.objects.all():
            rubs = Rub.objects.filter(hizb__juz=j)
            first_ayah = Ayah.objects.filter(rub__in=rubs).order_by("surah_id", "number_in_surah").first()
            last_ayah = Ayah.objects.filter(rub__in=rubs).order_by("-surah_id", "-number_in_surah").first()
            surahs = Surah.objects.filter(ayahs__rub__in=rubs).distinct()
            data.append({
                "number": j.number,
                "ayah_count": j.ayah_count,
                "first_ayah": f"{first_ayah.surah.name_ar} {first_ayah.number_in_surah}" if first_ayah else None,
                "last_ayah": f"{last_ayah.surah.name_ar} {last_ayah.number_in_surah}" if last_ayah else None,
                "surahs": [{"id": s.id, "name_ar": s.name_ar} for s in surahs],
            })
        (OUT / "juz.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  juz.json — {len(data)} juz")

    def _export_hizb(self):
        data = []
        for h in Hizb.objects.select_related("juz").all():
            data.append({
                "number": h.number,
                "number_in_juz": h.number_in_juz,
                "juz_number": h.juz.number,
                "rub_count": h.rubs.count(),
            })
        (OUT / "hizb.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  hizb.json — {len(data)} hizb")

    def _export_rub(self):
        data = []
        for r in Rub.objects.select_related("hizb__juz").prefetch_related("ayahs__surah").all():
            ayahs = list(r.ayahs.order_by("surah_id", "number_in_surah").select_related("surah"))
            first = ayahs[0] if ayahs else None
            last = ayahs[-1] if ayahs else None
            surahs_in_rub = sorted(set(
                (a.surah_id, a.surah.name_ar, a.surah.name_en) for a in ayahs
            ), key=lambda x: x[0])
            data.append({
                "number": r.number,
                "number_in_hizb": r.number_in_hizb,
                "hizb_number": r.hizb.number,
                "juz_number": r.hizb.juz.number,
                "ayah_count": len(ayahs),
                "page_start": first.page if first else None,
                "page_end": last.page if last else None,
                "start": {
                    "surah_id": first.surah_id,
                    "surah_name_ar": first.surah.name_ar,
                    "surah_name_en": first.surah.name_en,
                    "ayah": first.number_in_surah,
                    "verse_key": first.verse_key,
                    "text_uthmani": first.text_uthmani,
                } if first else None,
                "end": {
                    "surah_id": last.surah_id,
                    "surah_name_ar": last.surah.name_ar,
                    "surah_name_en": last.surah.name_en,
                    "ayah": last.number_in_surah,
                    "verse_key": last.verse_key,
                    "text_uthmani": last.text_uthmani,
                } if last else None,
                "surahs": [
                    {"id": s[0], "name_ar": s[1], "name_en": s[2]} for s in surahs_in_rub
                ],
                "label": r.label(),
            })
        (OUT / "rub.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  rub.json — {len(data)} rub (1/8 divisions)")

    def _export_ayahs(self):
        # Export in batches by rub for manageable files
        rubs = Rub.objects.all()
        all_ayahs = []
        for rub in rubs:
            for ayah in rub.ayahs.select_related("surah").order_by("surah_id", "number_in_surah"):
                all_ayahs.append({
                    "surah_id": ayah.surah_id,
                    "surah_name_ar": ayah.surah.name_ar,
                    "surah_name_en": ayah.surah.name_en,
                    "number_in_surah": ayah.number_in_surah,
                    "verse_key": ayah.verse_key,
                    "juz": rub.hizb.juz.number,
                    "hizb": rub.hizb.number,
                    "rub": rub.number,
                    "page": ayah.page,
                    "sajdah": ayah.sajdah,
                    "text_uthmani": ayah.text_uthmani,
                    "text_normalized": ayah.text_normalized,
                })

        (OUT / "ayahs.json").write_text(
            json.dumps(all_ayahs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.stdout.write(f"  ayahs.json — {len(all_ayahs)} ayahs")

    def _export_memorization(self):
        data = []
        for rec in MemorizationRecord.objects.select_related(
            "student", "rub__hizb__juz", "circle"
        ).all():
            data.append({
                "student_name": rec.student.full_name_ar,
                "student_id": rec.student_id,
                "rub_number": rec.rub.number,
                "rub_label": rec.rub.label(),
                "juz_number": rec.rub.hizb.juz.number,
                "circle_name": rec.circle.name if rec.circle else None,
                "status": rec.status,
                "memorized_at": rec.memorized_at.isoformat() if rec.memorized_at else None,
                "last_reviewed_at": rec.last_reviewed_at.isoformat() if rec.last_reviewed_at else None,
                "next_review_date": rec.next_review_date.isoformat() if rec.next_review_date else None,
                "review_interval_days": rec.review_interval_days,
                "review_count": rec.review_count,
            })
        (OUT / "memorization_records.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  memorization_records.json — {len(data)} records")

    def _export_progress_logs(self):
        data = []
        for log in ProgressLog.objects.select_related("student", "surah", "session__circle").all():
            data.append({
                "student_name": log.student.full_name_ar,
                "session_date": log.session.date.isoformat() if log.session else None,
                "circle_name": log.session.circle.name if log.session and log.session.circle else None,
                "category": log.log_category,
                "surah_name_ar": log.surah.name_ar if log.surah_id else None,
                "hizb": log.hizb, "thumn": log.thumn, "total_thumns": log.total_thumns,
                "start_ayah": log.start_ayah,
                "end_ayah": log.end_ayah,
                "completed_pages": str(log.completed_pages) if log.completed_pages else None,
                "grade": log.evaluation_grade,
                "teacher_notes": log.teacher_notes,
                "created_at": log.created_at.isoformat(),
            })
        (OUT / "progress_logs.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  progress_logs.json — {len(data)} logs")

    def _export_review_history(self):
        data = []
        for h in ReviewHistory.objects.select_related(
            "record__student", "reviewer"
        ).all():
            data.append({
                "student_name": h.record.student.full_name_ar,
                "rub_number": h.record.rub.number,
                "reviewer_name": h.reviewer.full_name_ar if h.reviewer else None,
                "evaluation": h.evaluation,
                "mistakes_count": h.mistakes_count,
                "teacher_notes": h.teacher_notes,
                "previous_interval": h.previous_interval,
                "new_interval": h.new_interval,
                "previous_status": h.previous_status,
                "new_status": h.new_status,
                "created_at": h.created_at.isoformat(),
            })
        (OUT / "review_history.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  review_history.json — {len(data)} reviews")

    def _export_study_tasks(self):
        data = []
        for t in StudyTask.objects.select_related("student", "assigned_by", "surah", "circle").all():
            data.append({
                "student_name": t.student.full_name_ar,
                "assigned_by_name": t.assigned_by.full_name_ar if t.assigned_by else None,
                "circle_name": t.circle.name if t.circle else None,
                "task_type": t.task_type,
                "surah_name_ar": t.surah.name_ar,
                "ayah_from": t.ayah_from,
                "ayah_to": t.ayah_to,
                "status": t.status,
                "notes": t.notes,
                "rejection_reason": t.rejection_reason,
                "created_at": t.created_at.isoformat(),
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "validated_at": t.validated_at.isoformat() if t.validated_at else None,
            })
        (OUT / "study_tasks.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  study_tasks.json — {len(data)} tasks")

    def _export_review_requests(self):
        data = []
        for r in ReviewRequest.objects.select_related(
            "student", "circle", "surah", "reviewed_by"
        ).all():
            data.append({
                "student_name": r.student.full_name_ar,
                "circle_name": r.circle.name if r.circle else None,
                "type": r.type,
                "surah_name_ar": r.surah.name_ar if r.surah else None,
                "ayah_from": r.ayah_from,
                "ayah_to": r.ayah_to,
                "status": r.status,
                "reviewed_by_name": r.reviewed_by.full_name_ar if r.reviewed_by else None,
                "scheduled_date": r.scheduled_date.isoformat() if r.scheduled_date else None,
                "created_at": r.created_at.isoformat(),
            })
        (OUT / "review_requests.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  review_requests.json — {len(data)} requests")

    def _export_achievements(self):
        data = []
        for a in StudentAchievement.objects.select_related("student").all():
            data.append({
                "student_name": a.student.full_name_ar,
                "total_hifdh_ayahs": a.total_hifdh_ayahs,
                "total_murajaah_ayahs": a.total_murajaah_ayahs,
                "total_hifdh_pages": str(a.total_hifdh_pages),
                "total_murajaah_pages": str(a.total_murajaah_pages),
                "completed_juz": a.completed_juz,
                "current_juz": a.current_juz,
            })
        (OUT / "achievements.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  achievements.json — {len(data)} achievements")

    def _export_circles(self):
        data = []
        for c in Circle.objects.select_related("teacher").all():
            enrollments = []
            for e in CircleEnrollment.objects.filter(circle=c).select_related("student"):
                enrollments.append({
                    "student_name": e.student.full_name_ar,
                    "status": e.status,
                    "enrolled_at": e.enrolled_at.isoformat(),
                })
            data.append({
                "name": c.name,
                "teacher_name": c.teacher.full_name_ar if c.teacher else None,
                "student_count": c.enrollments.count(),
                "students": enrollments,
            })
        (OUT / "circles.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  circles.json — {len(data)} circles")

    def _export_users(self):
        data = []
        for u in User.objects.all():
            data.append({
                "id": u.id,
                "full_name": getattr(u, "full_name_ar", getattr(u, "full_name", str(u))),
                "email": getattr(u, "email", ""),
                "role": getattr(u, "role", ""),
                "phone": getattr(u, "phone", ""),
                "is_active": getattr(u, "is_active", True),
            })
        (OUT / "users.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  users.json — {len(data)} users")

    def _export_summary(self):
        data = {
            "surahs": Surah.objects.count(),
            "juz": Juz.objects.count(),
            "hizb": Hizb.objects.count(),
            "rub": Rub.objects.count(),
            "ayahs": Ayah.objects.count(),
            "memorization_records": MemorizationRecord.objects.count(),
            "progress_logs": ProgressLog.objects.count(),
            "review_history": ReviewHistory.objects.count(),
            "study_tasks": StudyTask.objects.count(),
            "review_requests": ReviewRequest.objects.count(),
            "achievements": StudentAchievement.objects.count(),
            "users": User.objects.count(),
            "circles": Circle.objects.count(),
            "circle_enrollments": CircleEnrollment.objects.count(),
        }
        (OUT / "summary.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=serialize), encoding="utf-8"
        )
        self.stdout.write(f"  summary.json — {len(data)} stats")
