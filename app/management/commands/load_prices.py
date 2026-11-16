"""Load prices from a CSV export: code,name,category,date,value_mru,source

    python manage.py load_prices prices.csv
"""
import csv
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from app.models import Asset, Price


class Command(BaseCommand):
    help = "Load (upsert) asset prices from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_path")

    @transaction.atomic
    def handle(self, csv_path, **opts):
        assets, n = {}, 0
        with open(csv_path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                code = row["code"]
                if code not in assets:
                    assets[code], _ = Asset.objects.update_or_create(
                        code=code, defaults={"name": row["name"], "category": row["category"]})
                Price.objects.update_or_create(
                    asset=assets[code], date=row["date"],
                    defaults={"value_mru": Decimal(row["value_mru"]), "source": row.get("source") or "BCM"})
                n += 1
        self.stdout.write(self.style.SUCCESS(f"Loaded {n} prices for {len(assets)} assets"))
