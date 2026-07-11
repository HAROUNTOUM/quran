from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Batch, User
from apps.certificates.models import Certificate, CertificateTemplate


class CertificateBatchScopingTests(TestCase):
    """A SUB_ADMIN must only list / view / mutate / issue certificates for
    students in the batches they supervise. MAIN_ADMIN sees all; a student may
    view their own."""

    def setUp(self):
        self.main_admin = User.objects.create_user(
            username="cert_admin@test.com", email="cert_admin@test.com", password="x",
            full_name_ar="مدير", role=User.Role.MAIN_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED, is_staff=True,
        )
        self.batch_own = Batch.objects.create(
            name="دفعتي", number=51, year=2026, created_by=self.main_admin,
        )
        self.batch_foreign = Batch.objects.create(
            name="دفعة أجنبية", number=52, year=2026, created_by=self.main_admin,
        )
        self.sub = User.objects.create_user(
            username="cert_sub@test.com", email="cert_sub@test.com", password="x",
            full_name_ar="مشرف", role=User.Role.SUB_ADMIN,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        self.batch_own.sub_admins.add(self.sub)
        self.student_own = User.objects.create_user(
            username="cert_own@test.com", email="cert_own@test.com", password="x",
            full_name_ar="طالب دفعتي", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=self.batch_own,
        )
        self.student_foreign = User.objects.create_user(
            username="cert_foreign@test.com", email="cert_foreign@test.com", password="x",
            full_name_ar="طالب أجنبي", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED, batch=self.batch_foreign,
        )
        self.template = CertificateTemplate.objects.create(
            name="قالب", category="completion", body_template="{student_name}",
        )
        self.cert_own = Certificate.objects.create(
            student=self.student_own, template=self.template,
            certificate_number="CERT-OWN-1", status="issued",
        )
        self.cert_foreign = Certificate.objects.create(
            student=self.student_foreign, template=self.template,
            certificate_number="CERT-FOREIGN-1", status="issued",
        )

    # ── list ────────────────────────────────────────────────────────────
    def test_list_scoped_for_sub_admin(self):
        self.client.force_login(self.sub)
        r = self.client.get(reverse("certificates:list"))
        self.assertEqual(r.status_code, 200)
        issued_ids = {c.pk for c in r.context["issued_certificates"]}
        self.assertIn(self.cert_own.pk, issued_ids)
        self.assertNotIn(self.cert_foreign.pk, issued_ids)

    def test_list_unscoped_for_main_admin(self):
        self.client.force_login(self.main_admin)
        r = self.client.get(reverse("certificates:list"))
        issued_ids = {c.pk for c in r.context["issued_certificates"]}
        self.assertIn(self.cert_own.pk, issued_ids)
        self.assertIn(self.cert_foreign.pk, issued_ids)

    # ── download / preview object access ────────────────────────────────
    def test_sub_admin_cannot_download_foreign_cert(self):
        self.client.force_login(self.sub)
        r = self.client.get(reverse("certificates:download", args=[self.cert_foreign.pk]))
        self.assertEqual(r.status_code, 403)

    def test_sub_admin_can_reach_own_batch_cert(self):
        self.client.force_login(self.sub)
        r = self.client.get(reverse("certificates:download", args=[self.cert_own.pk]))
        # allowed past the guard → redirects (no pdf uploaded), not 403
        self.assertEqual(r.status_code, 302)

    def test_student_can_preview_own_cert(self):
        self.client.force_login(self.student_own)
        r = self.client.get(reverse("certificates:preview", args=[self.cert_own.pk]))
        self.assertIn(r.status_code, (200, 302))

    def test_student_cannot_preview_others_cert(self):
        self.client.force_login(self.student_own)
        r = self.client.get(reverse("certificates:preview", args=[self.cert_foreign.pk]))
        self.assertEqual(r.status_code, 403)

    # ── mutating object views ───────────────────────────────────────────
    def test_sub_admin_cannot_revoke_foreign_cert(self):
        self.client.force_login(self.sub)
        r = self.client.post(reverse("certificates:revoke", args=[self.cert_foreign.pk]))
        self.assertEqual(r.status_code, 403)
        self.cert_foreign.refresh_from_db()
        self.assertEqual(self.cert_foreign.status, "issued")

    def test_sub_admin_cannot_notify_foreign_cert(self):
        self.client.force_login(self.sub)
        r = self.client.post(reverse("certificates:notify", args=[self.cert_foreign.pk]))
        self.assertEqual(r.status_code, 403)

    # ── generate: server re-scopes a tampered student list ──────────────
    def test_generate_cannot_target_foreign_student(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.sub)
        pdf = SimpleUploadedFile("c.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        self.client.post(reverse("certificates:generate"), {
            "template": str(self.template.pk),
            "students": [str(self.student_foreign.pk)],
            "pdf_file": pdf,
        })
        # No new certificate issued for the out-of-batch student.
        self.assertFalse(
            Certificate.objects.filter(
                student=self.student_foreign, issued_by=self.sub,
            ).exists()
        )
