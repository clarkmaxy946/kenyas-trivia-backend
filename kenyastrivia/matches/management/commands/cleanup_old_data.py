from django.core.management.base import BaseCommand

from matches.cleanup import run_cleanup


class Command(BaseCommand):
    help = "Deletes old guest matches, stale matches, expired guest sessions and old generation jobs."

    def handle(self, *args, **options):
        counts = run_cleanup()
        for name, number in counts.items():
            self.stdout.write(f"{name}: {number}")