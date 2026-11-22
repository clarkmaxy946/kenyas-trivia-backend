import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from generations.jobs import claim_next_job, reset_stuck_jobs, run_job
from generations.models import JobStatus


class Command(BaseCommand):
    help = "Runs card-generation jobs from the queue."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run the waiting jobs, then stop.")

    def handle(self, *args, **options):
        reset_stuck_jobs()
        self.stdout.write("Generation worker started. Press Ctrl+C to stop.")
        try:
            while True:
                job = claim_next_job()
                if job is None:
                    if options["once"]:
                        break
                    time.sleep(1)
                    continue
                try:
                    run_job(job)
                except Exception as exc:  # a bug must not kill the worker
                    job.status = JobStatus.FAILED
                    job.finished_at = timezone.now()
                    job.save()
                    self.stderr.write(f"Job {job.id} crashed: {exc!r}")
                self.stdout.write(f"Job {job.id}: {job.status}")
        except KeyboardInterrupt:
            self.stdout.write("Worker stopped.")