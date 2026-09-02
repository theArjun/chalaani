from django.core.management.base import BaseCommand, CommandError

from chalani.models import Chalani
from extraction.tasks import run_extraction


class Command(BaseCommand):
    help = "Run AI extraction for one chalani synchronously (no qcluster needed)."

    def add_arguments(self, parser):
        parser.add_argument("chalani_id", type=int)

    def handle(self, *args, **options):
        chalani_id = options["chalani_id"]
        if not Chalani.objects.filter(pk=chalani_id).exists():
            raise CommandError(f"चलानी #{chalani_id} भेटिएन")
        result = run_extraction(chalani_id)
        chalani = Chalani.objects.get(pk=chalani_id)
        self.stdout.write(f"result: {result}")
        if chalani.extraction_error:
            self.stdout.write(self.style.ERROR(chalani.extraction_error))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{chalani.chalani_no or '(no no.)'} · {chalani.vendor or '(vendor unmatched)'} "
                    f"· {chalani.items.count()} lines"
                )
            )
