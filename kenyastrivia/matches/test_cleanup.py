from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from users.models import GuestSession, User

from .cleanup import run_cleanup
from .models import Match
from .models import MatchStatus as S


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class CleanupTests(TestCase):
    def setUp(self):
        self.guest = GuestSession.objects.create()
        self.now = timezone.now()

    def test_old_finished_guest_match_goes_but_a_fresh_one_stays(self):
        old = Match.objects.create(
            guest=self.guest, status=S.FINISHED, finished_at=self.now - timedelta(minutes=11)
        )
        fresh = Match.objects.create(
            guest=self.guest, status=S.FINISHED, finished_at=self.now - timedelta(minutes=2)
        )
        counts = run_cleanup(self.now)
        self.assertEqual(counts["finished_guest_matches"], 1)
        self.assertFalse(Match.objects.filter(pk=old.pk).exists())
        self.assertTrue(Match.objects.filter(pk=fresh.pk).exists())

    def test_unfinished_matches_nobody_can_resume_are_deleted(self):
        stale = Match.objects.create(guest=self.guest, status=S.IN_PROGRESS)
        recent = Match.objects.create(guest=self.guest, status=S.IN_PROGRESS)
        Match.objects.filter(pk=stale.pk).update(updated_at=self.now - timedelta(hours=4))
        run_cleanup(self.now)
        self.assertFalse(Match.objects.filter(pk=stale.pk).exists())
        self.assertTrue(Match.objects.filter(pk=recent.pk).exists())

    def test_finished_account_matches_are_never_deleted(self):
        user = User.objects.create_user(
            username="clark_k", email="clark@example.com", password="S3cure-pass-123"
        )
        match = Match.objects.create(
            user=user, status=S.FINISHED, finished_at=self.now - timedelta(days=60)
        )
        run_cleanup(self.now)
        self.assertTrue(Match.objects.filter(pk=match.pk).exists())

    def test_expired_guest_sessions_go_with_their_matches(self):
        match = Match.objects.create(guest=self.guest, status=S.IN_PROGRESS)
        GuestSession.objects.filter(pk=self.guest.pk).update(expires_at=self.now - timedelta(hours=1))
        counts = run_cleanup(self.now)
        self.assertEqual(counts["expired_guest_sessions"], 1)
        self.assertFalse(GuestSession.objects.filter(pk=self.guest.pk).exists())
        self.assertFalse(Match.objects.filter(pk=match.pk).exists())