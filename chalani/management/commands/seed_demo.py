"""Populate a demo firm with realistic Nepali suppliers, items and chalani."""

from __future__ import annotations

import random
from decimal import Decimal

import nepali_datetime as ndt
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from chalani.models import Chalani, ChalaniItem, Item, Vendor
from orgs.models import Membership, Organization

VENDORS = [
    ("Shree Ganesh Hardware Suppliers", "श्री गणेश हार्डवेयर सप्लायर्स", "301472856", "9851024478", "बल्खु, काठमाडौँ", "काठमाडौँ"),
    ("Himal Cement Udyog", "हिमाल सिमेन्ट उद्योग", "600238914", "9841127763", "हेटौँडा-११", "मकवानपुर"),
    ("Everest Steel Traders", "एभरेष्ट स्टिल ट्रेडर्स", "302915647", "9802345612", "बालाजु, काठमाडौँ", "काठमाडौँ"),
    ("Gorkha Bricks Udyog", "गोर्खा इँटा उद्योग", "500176239", "9856021144", "भक्तपुर-७", "भक्तपुर"),
    ("Nepal Paints & Chemicals", "नेपाल पेन्ट्स एण्ड केमिकल्स", "304558712", "01-4478123", "टेकु, काठमाडौँ", "काठमाडौँ"),
]

ITEMS = [
    ("Cement OPC 50kg", "सिमेन्ट ओ.पि.सि. ५० के.जी.", "bag", "870"),
    ("TMT Rod 12mm", "टि.एम.टि. डन्डी १२ एम.एम.", "kg", "128"),
    ("TMT Rod 16mm", "टि.एम.टि. डन्डी १६ एम.एम.", "kg", "126"),
    ("Red Brick (Chimney)", "रातो इँटा (चिम्नी)", "pcs", "22"),
    ("River Sand", "बालुवा", "cft", "58"),
    ("Aggregate 20mm", "गिट्टी २० एम.एम.", "cft", "62"),
    ("Binding Wire", "बाँध्ने तार", "kg", "142"),
    ("Emulsion Paint 20L", "इमल्सन पेन्ट २० लिटर", "packet", "6400"),
    ("PVC Pipe 4 inch", "पि.भि.सि. पाइप ४ इन्च", "pcs", "1180"),
    ("Plywood 8x4", "प्लाइउड ८x४", "sheet", "2350"),
]


class Command(BaseCommand):
    help = "Create a demo organization with sample chalani (username: demo / demo12345)."

    def add_arguments(self, parser):
        parser.add_argument("--chalani", type=int, default=24, help="how many chalani to create")
        parser.add_argument("--reset", action="store_true", help="wipe the demo firm first")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(2082)
        User = get_user_model()

        if options["reset"]:
            Organization.objects.filter(slug="demo-nirman-sewa").delete()

        organization, _ = Organization.objects.get_or_create(
            slug="demo-nirman-sewa",
            defaults={
                "name": "Demo Nirman Sewa",
                "name_np": "डेमो निर्माण सेवा",
                "pan_no": "609123456",
                "phone": "9851000000",
                "address": "नयाँ बानेश्वर",
                "district": "काठमाडौँ",
            },
        )
        user, created = User.objects.get_or_create(
            username="demo",
            defaults={"full_name_np": "रमेश श्रेष्ठ", "email": "demo@example.com"},
        )
        if created:
            user.set_password("demo12345")
        user.active_organization = organization
        user.save()
        Membership.objects.get_or_create(
            organization=organization, user=user, defaults={"role": Membership.Role.OWNER}
        )

        vendors = [
            Vendor.objects.get_or_create(
                organization=organization,
                name=name,
                defaults={
                    "name_np": name_np,
                    "pan_no": pan,
                    "phone": phone,
                    "address": address,
                    "district": district,
                },
            )[0]
            for name, name_np, pan, phone, address, district in VENDORS
        ]
        items = [
            Item.objects.get_or_create(
                organization=organization,
                name=name,
                defaults={"name_np": name_np, "unit": unit, "default_rate": Decimal(rate)},
            )[0]
            for name, name_np, unit, rate in ITEMS
        ]

        today = ndt.date.today()
        fy_start_year = today.year if today.month >= 4 else today.year - 1
        created_count = 0
        for n in range(options["chalani"]):
            month = 4 + (n % 9)
            year = fy_start_year + (1 if month > 12 else 0)
            month = month if month <= 12 else month - 12
            day = random.randint(1, 28)
            vendor = random.choice(vendors)
            status = random.choices(
                [Chalani.Status.DRAFT, Chalani.Status.VERIFIED, Chalani.Status.BILLED],
                weights=[3, 5, 2],
            )[0]
            chalani, made = Chalani.objects.get_or_create(
                organization=organization,
                vendor=vendor,
                chalani_no=f"C/{fy_start_year % 100}-{1200 + n}",
                defaults={
                    "date_bs": f"{year}-{month:02d}-{day:02d}",
                    "vehicle_no": random.choice(["बा १२ ख ३४५६", "ना ५ च ८८२१", "प्रदेश ३-०१-००४ च ०४३४", "बा २ ज ११९०"]),
                    "received_by": random.choice(["रमेश श्रेष्ठ", "सुनिता तामाङ", "हरि बहादुर", "बिनोद गुरुङ"]),
                    "status": status,
                    "created_by": user,
                    "extracted_by_ai": random.random() < 0.6,
                },
            )
            if not made:
                continue
            created_count += 1
            for line_no, item in enumerate(random.sample(items, random.randint(1, 4)), start=1):
                ChalaniItem.objects.create(
                    chalani=chalani,
                    item=item if random.random() < 0.85 else None,
                    description=item.name_np,
                    qty=Decimal(random.randint(5, 400)),
                    unit=item.unit,
                    rate=item.default_rate,
                    line_no=line_no,
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"{organization} तयार — {created_count} नयाँ चलानी, "
                f"{len(vendors)} आपूर्तिकर्ता, {len(items)} सामान.\n"
                "लगइन: demo / demo12345"
            )
        )
