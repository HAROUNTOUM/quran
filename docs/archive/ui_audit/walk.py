import urllib.request, urllib.parse, http.cookiejar, json, sys, re

BASE = "http://127.0.0.1:8080"

def login(cj, username, password):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    # GET login page for csrf
    r = opener.open(f"{BASE}/login/")
    body = r.read().decode()
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', body)
    csrf = m.group(1) if m else ""
    data = urllib.parse.urlencode({"username": username, "password": password, "csrfmiddlewaretoken": csrf}).encode()
    r = opener.open(f"{BASE}/login/", data)
    return opener

def walk_role(opener, name, pages):
    print(f"\n=== {name} ===")
    for url, label in pages:
        try:
            r = opener.open(f"{BASE}{url}")
            body = r.read().decode()
            status = r.status
            errors = []
            if "خطأ" in body:
                # Find error messages in Arabic
                for m in re.finditer(r'(?:رسالة خطأ|alert-danger|is-invalid)[^<]*', body):
                    errors.append(m.group())
            if "Traceback" in body:
                errors.append("DJANGO TRACEBACK IN HTML")
            if status >= 400:
                errors.append(f"HTTP {status}")
            marker = " ❌ " if errors else " ✅ "
            print(f"  {marker} {label} ({url}) [{status}]")
            if errors:
                for e in errors[:3]:
                    print(f"       {e}")
        except Exception as e:
            print(f"  ❌ {label} ({url}) — {e}")

ADMIN_PAGES = [
    ("/dashboard/", "Home"),
    ("/dashboard/users/table/", "Users Table"),
    ("/dashboard/students/", "Students"),
    ("/dashboard/students/create/", "Student Create"),
    ("/dashboard/teachers/", "Teachers"),
    ("/dashboard/teachers/create/", "Teacher Create"),
    ("/dashboard/supervisors/", "Supervisors"),
    ("/dashboard/supervisors/create/", "Supervisor Create"),
    ("/dashboard/circles/", "Circles"),
    ("/dashboard/circles/create/", "Circle Create"),
    ("/dashboard/circles/1/", "Circle Detail (pk=1)"),
    ("/dashboard/requests/", "Requests"),
    ("/dashboard/announcements/", "Announcements"),
    ("/dashboard/announcements/create/", "Announcement Create"),
    ("/dashboard/reports/", "Reports"),
    ("/dashboard/exams/", "Exams"),
    ("/dashboard/exams/create/", "Exam Create"),
    ("/dashboard/absences/", "Absences"),
    ("/dashboard/absences/active/", "Active Substitutions"),
    ("/dashboard/admin/notifications/", "Notifications"),
    ("/dashboard/admin/notifications/create/", "Notif Create"),
]

TEACHER_PAGES = [
    ("/dashboard/teacher/", "Home"),
    ("/dashboard/teacher/circles/7/", "Circle Detail (pk=7)"),
    ("/dashboard/teacher/students/", "Students"),
    ("/dashboard/teacher/sessions/manage/", "Session Manage"),
    ("/dashboard/teacher/absences/", "Absences"),
    ("/dashboard/teacher/absences/create/", "Absence Create"),
    ("/dashboard/teacher/announcements/", "Announcements"),
    ("/dashboard/teacher/requests/", "Requests"),
    ("/dashboard/teacher/requests/create/", "Request Create"),
    ("/dashboard/teacher/notifications/", "Notifications"),
    ("/dashboard/teacher/exams/", "Exams"),
    ("/dashboard/teacher/review-requests/", "Review Requests"),
    ("/dashboard/teacher/reschedule-requests/", "Reschedule Requests"),
    ("/dashboard/teacher/absence-justifications/", "Absence Justifications"),
]

STUDENT_PAGES = [
    ("/dashboard/student/", "Home"),
    ("/dashboard/student/circles/", "Circles"),
    ("/dashboard/student/circles/7/", "Circle Detail (pk=7)"),
    ("/dashboard/student/memorization/", "Memorization"),
    ("/dashboard/student/attendance/", "Attendance"),
    ("/dashboard/student/sessions/", "Sessions"),
    ("/dashboard/student/review-requests/", "Review Requests"),
    ("/dashboard/student/review-requests/create/", "Review Request Create"),
    ("/dashboard/student/requests/", "Requests"),
    ("/dashboard/student/requests/create/", "Request Create"),
    ("/dashboard/student/announcements/", "Announcements"),
    ("/dashboard/student/notifications/", "Notifications"),
    ("/dashboard/student/exams/", "Exams"),
    ("/dashboard/student/achievements/", "Achievements"),
    ("/dashboard/student/justifications/", "Justifications"),
]

CERT_PAGES = [
    ("/dashboard/certificates/", "List (admin/supervisor)"),
    ("/dashboard/certificates/generate/", "Generate"),
    ("/dashboard/certificates/own/", "Own (student)"),
    ("/dashboard/certificates/teacher/", "Teacher List"),
    ("/dashboard/certificates/teacher/create/", "Teacher Create"),
]

# Admin walk
jar = http.cookiejar.CookieJar()
opener = login(jar, "admin_test@test.com", "test1234")
walk_role(opener, "ADMIN", ADMIN_PAGES)
walk_role(opener, "ADMIN — certs", CERT_PAGES)

# Teacher walk
jar2 = http.cookiejar.CookieJar()
opener2 = login(jar2, "teacher1@hafez.com", "test1234")
walk_role(opener2, "TEACHER", TEACHER_PAGES)

# Student walk
jar3 = http.cookiejar.CookieJar()
opener3 = login(jar3, "student1@hafez.com", "test1234")
walk_role(opener3, "STUDENT", STUDENT_PAGES)
walk_role(opener3, "STUDENT — certs", [("/dashboard/certificates/own/", "Own certs")])
