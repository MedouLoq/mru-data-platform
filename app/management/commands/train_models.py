"""Train one forecasting model per asset and report it against the naive baseline.

    python manage.py train_models [--asset BTC]
"""
from django.core.management.base import BaseCommand

from app.models import Asset
from services.ml_service.train import train_asset_model


class Command(BaseCommand):
    help = "Train price models (next-day log-return) and benchmark them against 'tomorrow = today'"

    def add_arguments(self, parser):
        parser.add_argument("--asset", action="append", help="asset code (repeatable); default: all")

    def handle(self, *args, asset=None, **opts):
        codes = asset or list(Asset.objects.values_list("code", flat=True).order_by("code"))
        self.stdout.write(f"{'asset':7} {'rows':>5} {'MAE model':>10} {'MAE naive':>10} {'skill':>7} {'direction':>9}")
        for code in codes:
            m = train_asset_model(code)
            if not m:
                self.stdout.write(f"{code:7} not enough data")
                continue
            self.stdout.write(f"{code:7} {m['n_samples']:5d} {m['mape']:9.2f}% {m['mape_naive']:9.2f}% "
                              f"{100 * m['skill']:+6.1f}% {100 * m['direction_accuracy']:8.0f}%")
