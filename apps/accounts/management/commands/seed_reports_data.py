from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
import random

from apps.accounts.models import User
from apps.circles.models import Circle, CircleEnrollment, Session
from apps.attendance.models import Attendance
from apps.references.models import Surah, EvaluationCriterion, Juz
from apps.references.utils import seed_juz_data
from apps.memorization.models import MemorizationProgress, RecitationGrade


SURAH_DATA = [
    (1, "الفاتحة", "Al-Fatiha", 7, "makki"),
    (2, "البقرة", "Al-Baqarah", 286, "madani"),
    (3, "آل عمران", "Aal-e-Imran", 200, "madani"),
    (4, "النساء", "An-Nisa'", 176, "madani"),
    (5, "المائدة", "Al-Ma'idah", 120, "madani"),
    (6, "الأنعام", "Al-An'am", 165, "makki"),
    (7, "الأعراف", "Al-A'raf", 206, "makki"),
    (8, "الأنفال", "Al-Anfal", 75, "madani"),
    (9, "التوبة", "At-Tawbah", 129, "madani"),
    (10, "يونس", "Yunus", 109, "makki"),
    (11, "هود", "Hud", 123, "makki"),
    (12, "يوسف", "Yusuf", 111, "makki"),
    (13, "الرعد", "Ar-Ra'd", 43, "madani"),
    (14, "إبراهيم", "Ibrahim", 52, "makki"),
    (15, "الحجر", "Al-Hijr", 99, "makki"),
    (16, "النحل", "An-Nahl", 128, "makki"),
    (17, "الإسراء", "Al-Isra'", 111, "makki"),
    (18, "الكهف", "Al-Kahf", 110, "makki"),
    (19, "مريم", "Maryam", 98, "makki"),
    (20, "طه", "Ta-Ha", 135, "makki"),
    (21, "الأنبياء", "Al-Anbiya'", 112, "makki"),
    (22, "الحج", "Al-Hajj", 78, "madani"),
    (23, "المؤمنون", "Al-Mu'minun", 118, "makki"),
    (24, "النور", "An-Nur", 64, "madani"),
    (25, "الفرقان", "Al-Furqan", 77, "makki"),
    (26, "الشعراء", "Ash-Shu'ara'", 227, "makki"),
    (27, "النمل", "An-Naml", 93, "makki"),
    (28, "القصص", "Al-Qasas", 88, "makki"),
    (29, "العنكبوت", "Al-Ankabut", 69, "makki"),
    (30, "الروم", "Ar-Rum", 60, "makki"),
    (31, "لقمان", "Luqman", 34, "makki"),
    (32, "السجدة", "As-Sajdah", 30, "makki"),
    (33, "الأحزاب", "Al-Ahzab", 73, "madani"),
    (34, "سبأ", "Saba'", 54, "makki"),
    (35, "فاطر", "Fatir", 45, "makki"),
    (36, "يس", "Ya-Sin", 83, "makki"),
    (37, "الصافات", "As-Saffat", 182, "makki"),
    (38, "ص", "Sad", 88, "makki"),
    (39, "الزمر", "Az-Zumar", 75, "makki"),
    (40, "غافر", "Ghafir", 85, "makki"),
    (41, "فصلت", "Fussilat", 54, "makki"),
    (42, "الشورى", "Ash-Shura", 53, "makki"),
    (43, "الزخرف", "Az-Zukhruf", 89, "makki"),
    (44, "الدخان", "Ad-Dukhan", 59, "makki"),
    (45, "الجاثية", "Al-Jathiyah", 37, "makki"),
    (46, "الأحقاف", "Al-Ahqaf", 35, "makki"),
    (47, "محمد", "Muhammad", 38, "madani"),
    (48, "الفتح", "Al-Fath", 29, "madani"),
    (49, "الحجرات", "Al-Hujurat", 18, "madani"),
    (50, "ق", "Qaf", 45, "makki"),
    (51, "الذاريات", "Adh-Dhariyat", 60, "makki"),
    (52, "الطور", "At-Tur", 49, "makki"),
    (53, "النجم", "An-Najm", 62, "makki"),
    (54, "القمر", "Al-Qamar", 55, "makki"),
    (55, "الرحمن", "Ar-Rahman", 78, "madani"),
    (56, "الواقعة", "Al-Waqi'ah", 96, "makki"),
    (57, "الحديد", "Al-Hadid", 29, "madani"),
    (58, "المجادلة", "Al-Mujadilah", 22, "madani"),
    (59, "الحشر", "Al-Hashr", 24, "madani"),
    (60, "الممتحنة", "Al-Mumtahanah", 13, "madani"),
    (61, "الصف", "As-Saff", 14, "madani"),
    (62, "الجمعة", "Al-Jumu'ah", 11, "madani"),
    (63, "المنافقون", "Al-Munafiqun", 11, "madani"),
    (64, "التغابن", "At-Taghabun", 18, "madani"),
    (65, "الطلاق", "At-Talaq", 12, "madani"),
    (66, "التحريم", "At-Tahrim", 12, "madani"),
    (67, "الملك", "Al-Mulk", 30, "makki"),
    (68, "القلم", "Al-Qalam", 52, "makki"),
    (69, "الحاقة", "Al-Haqqah", 52, "makki"),
    (70, "المعارج", "Al-Ma'arij", 44, "makki"),
    (71, "نوح", "Nuh", 28, "makki"),
    (72, "الجن", "Al-Jinn", 28, "makki"),
    (73, "المزمل", "Al-Muzzammil", 20, "makki"),
    (74, "المدثر", "Al-Muddaththir", 56, "makki"),
    (75, "القيامة", "Al-Qiyamah", 40, "makki"),
    (76, "الإنسان", "Al-Insan", 31, "madani"),
    (77, "المرسلات", "Al-Mursalat", 50, "makki"),
    (78, "النبأ", "An-Naba'", 40, "makki"),
    (79, "النازعات", "An-Nazi'at", 46, "makki"),
    (80, "عبس", "Abasa", 42, "makki"),
    (81, "التكوير", "At-Takwir", 29, "makki"),
    (82, "الإنفطار", "Al-Infitar", 19, "makki"),
    (83, "المطففين", "Al-Mutaffifin", 36, "makki"),
    (84, "الإنشقاق", "Al-Inshiqaq", 25, "makki"),
    (85, "البروج", "Al-Buruj", 22, "makki"),
    (86, "الطارق", "At-Tariq", 17, "makki"),
    (87, "الأعلى", "Al-A'la", 19, "makki"),
    (88, "الغاشية", "Al-Ghashiyah", 26, "makki"),
    (89, "الفجر", "Al-Fajr", 30, "makki"),
    (90, "البلد", "Al-Balad", 20, "makki"),
    (91, "الشمس", "Ash-Shams", 15, "makki"),
    (92, "الليل", "Al-Layl", 21, "makki"),
    (93, "الضحى", "Ad-Duha", 11, "makki"),
    (94, "الشرح", "Ash-Sharh", 8, "makki"),
    (95, "التين", "At-Tin", 8, "makki"),
    (96, "العلق", "Al-Alaq", 19, "makki"),
    (97, "القدر", "Al-Qadr", 5, "makki"),
    (98, "البينة", "Al-Bayyinah", 8, "madani"),
    (99, "الزلزلة", "Az-Zalzalah", 8, "madani"),
    (100, "العاديات", "Al-Adiyat", 11, "makki"),
    (101, "القارعة", "Al-Qari'ah", 11, "makki"),
    (102, "التكاثر", "At-Takathur", 8, "makki"),
    (103, "العصر", "Al-Asr", 3, "makki"),
    (104, "الهمزة", "Al-Humazah", 9, "makki"),
    (105, "الفيل", "Al-Fil", 5, "makki"),
    (106, "قريش", "Quraysh", 4, "makki"),
    (107, "الماعون", "Al-Ma'un", 7, "makki"),
    (108, "الكوثر", "Al-Kawthar", 3, "makki"),
    (109, "الكافرون", "Al-Kafirun", 6, "makki"),
    (110, "النصر", "An-Nasr", 3, "madani"),
    (111, "المسد", "Al-Masad", 5, "makki"),
    (112, "الإخلاص", "Al-Ikhlas", 4, "makki"),
    (113, "الفلق", "Al-Falaq", 5, "makki"),
    (114, "الناس", "An-Nas", 6, "makki"),
]


class Command(BaseCommand):
    help = "Seed reports reference data (Surahs, EvaluationCriteria) and demo hifz/murajaa/grades"

    def handle(self, *args, **options):
        self.stdout.write("Seeding reports data...")

        # ── Juz (Hizb) ─────────────────────────────────────
        seed_juz_data()
        self.stdout.write(f"  ✓ {Juz.objects.count()} Juz (Hizb) records")

        # ── Surahs ──────────────────────────────────────────
        for sid, name_ar, name_en, ayah_count, rev_type in SURAH_DATA:
            Surah.objects.get_or_create(
                id=sid,
                defaults=dict(
                    name_ar=name_ar,
                    name_en=name_en,
                    ayah_count=ayah_count,
                    revelation_type=rev_type,
                ),
            )
        self.stdout.write(f"  ✓ {Surah.objects.count()} Surahs")

        # ── Evaluation Criteria ─────────────────────────────
        criteria = [
            ("النطق والتجويد", 1.0),
            ("الطلاقة", 1.0),
            ("الخشوع", 1.0),
            ("الحفظ والضبط", 1.0),
        ]
        for name, weight in criteria:
            EvaluationCriterion.objects.get_or_create(
                name_ar=name, defaults=dict(weight=weight, is_active=True)
            )
        self.stdout.write(f"  ✓ {EvaluationCriterion.objects.count()} Evaluation Criteria")

        # ── Enrollments ─────────────────────────────────────
        active_enrollments = CircleEnrollment.objects.filter(status="active")
        if not active_enrollments.exists():
            circles = Circle.objects.all()
            students = User.objects.filter(role=User.Role.STUDENT, is_approved="approved")[:12]
            for i, student in enumerate(students):
                circle = circles[i % len(circles)]
                active_enrollments = list(CircleEnrollment.objects.filter(status="active"))
                if not active_enrollments:
                    en, _ = CircleEnrollment.objects.get_or_create(
                        circle=circle, student=student,
                        defaults=dict(status="active")
                    )
                    active_enrollments = CircleEnrollment.objects.filter(status="active")
        self.stdout.write(f"  ✓ {active_enrollments.count()} active enrollments")

        # Set current_surah on enrollments
        surahs = list(Surah.objects.all())
        for en in active_enrollments.select_related("current_surah"):
            if not en.current_surah:
                en.current_surah = random.choice(surahs[:30])
                en.save(update_fields=["current_surah"])

        # ── Hifz Progress ──────────────────────────────────
        surahs_1_20 = Surah.objects.filter(id__lte=20)
        hifz_statuses = ["mastered", "mastered", "mastered", "tested", "reviewed", "memorizing"]
        hifz_created = 0
        for en in active_enrollments:
            for surah in surahs_1_20:
                if random.random() > 0.4:
                    continue
                ayah_from = random.randint(1, max(1, surah.ayah_count - 10))
                ayah_to = min(ayah_from + random.randint(3, 15), surah.ayah_count)
                status = random.choice(hifz_statuses)
                obj, created = MemorizationProgress.objects.get_or_create(
                    enrollment=en,
                    type="hifz",
                    surah=surah,
                    ayah_from=ayah_from,
                    ayah_to=ayah_to,
                    defaults=dict(
                        status=status,
                        tested_at=timezone.now() if status == "tested" else None,
                        tested_by=User.objects.filter(role=User.Role.TEACHER).first(),
                    ),
                )
                if created:
                    hifz_created += 1
        self.stdout.write(f"  ✓ {hifz_created} Hifz progress records created")

        # ── Murajaa Progress ────────────────────────────────
        murajaa_created = 0
        for en in active_enrollments:
            for _ in range(random.randint(1, 5)):
                surah = random.choice(surahs_1_20)
                ayah_from = random.randint(1, max(1, surah.ayah_count - 5))
                ayah_to = min(ayah_from + random.randint(3, 10), surah.ayah_count)
                status = random.choice(["mastered", "mastered", "mastered", "reviewed", "weak", "tested"])
                last_rev = timezone.now() - timedelta(days=random.randint(0, 14))
                obj, created = MemorizationProgress.objects.get_or_create(
                    enrollment=en,
                    type="murajaa",
                    surah=surah,
                    ayah_from=ayah_from,
                    ayah_to=ayah_to,
                    defaults=dict(
                        status=status,
                        revision_count=random.randint(1, 15),
                        last_revised_at=last_rev,
                        tested_at=last_rev if status == "tested" else None,
                        tested_by=User.objects.filter(role=User.Role.TEACHER).first(),
                    ),
                )
                if created:
                    murajaa_created += 1
        self.stdout.write(f"  ✓ {murajaa_created} Murajaa progress records created")

        # ── Recitation Grades ───────────────────────────────
        criteria_list = list(EvaluationCriterion.objects.filter(is_active=True))
        sessions = Session.objects.all()[:20]
        grade_created = 0
        for session in sessions:
            circle_enrollments = CircleEnrollment.objects.filter(circle=session.circle, status="active")
            for en in circle_enrollments:
                for criterion in criteria_list:
                    score = random.randint(50, 100)
                    obj, created = RecitationGrade.objects.get_or_create(
                        session=session,
                        student=en.student,
                        criterion=criterion,
                        defaults=dict(score=score, max_score=100),
                    )
                    if created:
                        grade_created += 1
        self.stdout.write(f"  ✓ {grade_created} Recitation grades created")

        self.stdout.write(self.style.SUCCESS("Done! Reports reference data seeded."))
