import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from app.models import Asset, Price

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["/", "/asset/USD/", "/comparison/?assets=USD&assets=EUR", "/statistics/", "/calculator/", "/predictions/"]


@pytest.fixture
def data(db, tmp_path):
    csv = tmp_path / "prices.csv"
    lines = ["code,name,category,date,value_mru,source"]
    start = date(2025, 1, 1)
    for i in range(200):
        d = start + timedelta(days=i)
        lines.append(f"USD,US Dollar,currency,{d},{39.5 + 0.002 * i:.4f},BCM")
        lines.append(f"EUR,Euro,currency,{d},{43 + 0.01 * (i % 17):.4f},Yahoo Finance")
    csv.write_text("\n".join(lines))
    call_command("load_prices", str(csv))
    return csv


@pytest.mark.parametrize("url", PAGES)
def test_every_page_requires_login(client, data, url):
    resp = client.get(url)
    assert resp.status_code == 302 and resp["Location"].startswith("/login/")


@pytest.mark.parametrize("url", PAGES)
def test_pages_render_for_logged_in_user(client, data, url, tmp_path, monkeypatch):
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    User.objects.create_user("analyst", password="pw-for-tests-123")
    client.login(username="analyst", password="pw-for-tests-123")
    assert client.get(url).status_code == 200


def test_bad_days_parameter_does_not_crash(client, data):
    User.objects.create_user("analyst", password="pw-for-tests-123")
    client.login(username="analyst", password="pw-for-tests-123")
    assert client.get("/asset/USD/?days=abc").status_code == 200
    assert client.get("/comparison/?assets=USD&days=-5").status_code == 200


def test_load_prices_upserts(data):
    assert Asset.objects.count() == 2 and Price.objects.count() == 400
    call_command("load_prices", str(data))                     # idempotent
    assert Price.objects.count() == 400


def test_train_models_and_predictions_page(client, data, tmp_path, monkeypatch):
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    call_command("train_models")
    assert (tmp_path / "models" / "USD_model.joblib").exists()
    User.objects.create_user("analyst", password="pw-for-tests-123")
    client.login(username="analyst", password="pw-for-tests-123")
    html = client.get("/predictions/").content.decode()
    assert "Skill vs naive" in html and "Naive error" in html


def test_logout_requires_post(client, data):
    User.objects.create_user("analyst", password="pw-for-tests-123")
    client.login(username="analyst", password="pw-for-tests-123")
    client.get("/logout/")
    assert client.get("/").status_code == 200                 # GET does not log out
    client.post("/logout/")
    assert client.get("/").status_code == 302


def test_production_refuses_to_start_without_secret_key(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "DEBUG": "False", "SECRET_KEY": ""}
    proc = subprocess.run([sys.executable, "-c", "import django,os;os.environ['DJANGO_SETTINGS_MODULE']='mru_dataplatform.settings';"
                           "from django.conf import settings;settings.SECRET_KEY"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode != 0 and "SECRET_KEY" in proc.stderr
