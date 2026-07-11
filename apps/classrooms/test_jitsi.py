import jwt
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.classrooms.services import is_moderator, jitsi_auth_enabled, mint_jitsi_jwt

SECRET = "test-secret-key-with-at-least-32-bytes"


class JitsiJWTTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user(
            username="jt@test.com", email="jt@test.com", password="x",
            full_name_ar="المعلم", role=User.Role.TEACHER,
            is_approved=User.ApprovalStatus.APPROVED,
        )
        cls.student = User.objects.create_user(
            username="js@test.com", email="js@test.com", password="x",
            full_name_ar="الطالب", role=User.Role.STUDENT,
            is_approved=User.ApprovalStatus.APPROVED,
        )

    def test_no_token_when_secret_unset(self):
        with override_settings(JITSI_APP_SECRET=""):
            self.assertFalse(jitsi_auth_enabled())
            self.assertIsNone(mint_jitsi_jwt(self.teacher, "room1", moderator=True))

    @override_settings(JITSI_APP_SECRET=SECRET, JITSI_APP_ID="hafez",
                       JITSI_DOMAIN="meet.example.dz", JITSI_JWT_TTL=3600)
    def test_token_claims_and_moderator_flag(self):
        token = mint_jitsi_jwt(self.teacher, "hafezroom-abc", moderator=True)
        self.assertIsNotNone(token)
        decoded = jwt.decode(token, SECRET, algorithms=["HS256"], audience="jitsi")
        self.assertEqual(decoded["room"], "hafezroom-abc")
        self.assertEqual(decoded["aud"], "jitsi")
        self.assertEqual(decoded["iss"], "hafez")
        self.assertEqual(decoded["context"]["user"]["name"], "المعلم")
        self.assertEqual(decoded["context"]["user"]["moderator"], "true")

    @override_settings(JITSI_APP_SECRET=SECRET)
    def test_student_is_not_moderator(self):
        token = mint_jitsi_jwt(self.student, "room", moderator=False)
        decoded = jwt.decode(token, SECRET, algorithms=["HS256"], audience="jitsi")
        self.assertEqual(decoded["context"]["user"]["moderator"], "false")

    @override_settings(JITSI_APP_SECRET=SECRET)
    def test_token_is_scoped_to_room(self):
        token = mint_jitsi_jwt(self.teacher, "only-this-room", moderator=True)
        decoded = jwt.decode(token, SECRET, algorithms=["HS256"], audience="jitsi")
        self.assertEqual(decoded["room"], "only-this-room")

    def test_role_moderator_mapping(self):
        self.assertTrue(is_moderator(self.teacher))
        self.assertFalse(is_moderator(self.student))
