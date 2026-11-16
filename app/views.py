import json
import os

import joblib
import numpy as np
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render

from .models import Asset, Price


def _days(request, default, maximum=3650):
    """?days=N, clamped to 1..maximum; invalid values fall back to the default."""
    try:
        return max(1, min(int(request.GET.get('days', default)), maximum))
    except (TypeError, ValueError):
        return default


@login_required 
def dashboard(request):
    """Enhanced dashboard with better data organization"""
    assets = Asset.objects.all()
    data_list = []

    for asset in assets:
        prices = Price.objects.filter(asset=asset).order_by('-date')[:30]

        if not prices:
            continue

        latest_price = prices[0]
        previous_price = prices[1] if len(prices) > 1 else None

        # Calculate daily variation
        variation = 0
        abs_variation = 0
        if previous_price and previous_price.value_mru > 0:
            variation = ((latest_price.value_mru - previous_price.value_mru) / previous_price.value_mru) * 100
            abs_variation = abs(variation)

        # Calculate weekly variation (7 days)
        weekly_variation = 0
        week_price = prices[7] if len(prices) > 7 else None
        if week_price and week_price.value_mru > 0:
            weekly_variation = ((latest_price.value_mru - week_price.value_mru) / week_price.value_mru) * 100

        # Calculate monthly variation (30 days)
        monthly_variation = 0
        month_price = prices[29] if len(prices) > 29 else None
        if month_price and month_price.value_mru > 0:
            monthly_variation = ((latest_price.value_mru - month_price.value_mru) / month_price.value_mru) * 100

        data_list.append({
            'asset': asset,
            'latest': latest_price,
            'variation': variation,
            'abs_variation': abs_variation,
            'weekly_variation': weekly_variation,
            'monthly_variation': monthly_variation,
        })

    # Separate by category
    currencies = [d for d in data_list if d['asset'].category == 'currency']
    commodities = [d for d in data_list if d['asset'].category == 'commodity']

    context = {
        'data': data_list,
        'currencies': currencies,
        'commodities': commodities,
        'total_assets': len(data_list),
    }

    return render(request, 'dashboard.html', context)

@login_required 
def asset_detail(request, code):
    """Detailed view for a specific asset with historical data"""
    asset = get_object_or_404(Asset, code=code)

    # Get time range from request (default 2 years)
    days = _days(request, 730)

    # Get historical prices
    prices = Price.objects.filter(asset=asset).order_by('-date')[:days]

    if not prices:
        context = {'asset': asset, 'error': 'No price data available'}
        return render(request, 'asset_detail.html', context)

    latest_price = prices[0]

    # Calculate statistics
    price_values = [float(p.value_mru) for p in prices]
    stats = {
        'current': float(latest_price.value_mru),
        'max': max(price_values),
        'min': min(price_values),
        'avg': sum(price_values) / len(price_values),
        'count': len(prices)
    }

    # Prepare chart data (reverse for chronological order)
    chart_data = {
        'dates': [p.date.strftime('%Y-%m-%d') for p in reversed(prices)],
        'values': [float(p.value_mru) for p in reversed(prices)]
    }

    # Calculate variations
    variations = {}
    periods = {'daily': 1, 'weekly': 7, 'monthly': 30, 'yearly': 365}

    for period_name, days_back in periods.items():
        if len(prices) > days_back:
            old_price = prices[days_back]
            if old_price.value_mru > 0:
                change = ((latest_price.value_mru - old_price.value_mru) / old_price.value_mru) * 100
                variations[period_name] = {
                    'percentage': float(change),
                    'absolute': float(latest_price.value_mru - old_price.value_mru)
                }

    context = {
        'asset': asset,
        'latest_price': latest_price,
        'stats': stats,
        'variations': variations,
        'chart_data': json.dumps(chart_data),
        'days': days,
    }

    return render(request, 'asset_detail.html', context)

@login_required 
def comparison(request):
    """Compare multiple assets side by side"""
    # Get selected assets from query params
    selected_codes = request.GET.getlist('assets')
    days = _days(request, 365)

    assets = Asset.objects.all()
    comparison_data = []
    chart_data = {'dates': [], 'series': []}

    if selected_codes:
        for code in selected_codes:
            try:
                asset = Asset.objects.get(code=code)
                prices = Price.objects.filter(asset=asset).order_by('-date')[:days]

                if prices:
                    latest = prices[0]
                    oldest = prices[len(prices)-1]

                    # Calculate overall change
                    if oldest.value_mru > 0:
                        total_change = ((latest.value_mru - oldest.value_mru) / oldest.value_mru) * 100
                    else:
                        total_change = 0

                    comparison_data.append({
                        'asset': asset,
                        'latest': latest,
                        'oldest': oldest,
                        'total_change': total_change,
                        'days': len(prices)
                    })

                    # Add to chart data
                    chart_data['series'].append({
                        'name': asset.code,
                        'data': [float(p.value_mru) for p in reversed(prices)]
                    })

                    if not chart_data['dates']:
                        chart_data['dates'] = [p.date.strftime('%Y-%m-%d') for p in reversed(prices)]
            except Asset.DoesNotExist:
                pass

    context = {
        'all_assets': assets,
        'selected_codes': selected_codes,
        'comparison_data': comparison_data,
        'chart_data': json.dumps(chart_data),
        'days': days,
    }

    return render(request, 'comparison.html', context)

@login_required 
def statistics(request):
    """Show overall market statistics"""
    assets = Asset.objects.all()

    stats_data = []
    for asset in assets:
        prices = Price.objects.filter(asset=asset).order_by('-date')[:365]

        if not prices:
            continue

        price_values = [float(p.value_mru) for p in prices]

        # Calculate volatility (standard deviation)
        mean = sum(price_values) / len(price_values)
        variance = sum((x - mean) ** 2 for x in price_values) / len(price_values)
        volatility = variance ** 0.5

        stats_data.append({
            'asset': asset,
            'current': price_values[0],
            'max_year': max(price_values),
            'min_year': min(price_values),
            'avg_year': mean,
            'volatility': volatility,
            'data_points': len(prices)
        })

    context = {
        'stats_data': stats_data,
    }

    return render(request, 'statistics.html', context)


# --- NOUVELLE VUE DE LOGIN ---
class CustomLoginView(LoginView):
    template_name = 'login.html'  # On réutilise votre joli template
    redirect_authenticated_user = True  # Redirige si déjà connecté
    
    def get_success_url(self):
        # Redirige vers le tableau de bord public au lieu de l'admin
        return '/' 

def logout_view(request):
    if request.method == 'POST':  # POST only, so a link or image tag cannot log users out
        logout(request)
    return redirect('/login/')


@login_required
def calculator(request):
    """Advanced asset converter with categories and smart suggestions"""
    assets = Asset.objects.all()
    
    # Organize assets by category with latest prices
    currencies = []
    commodities = []
    
    for asset in assets:
        latest = Price.objects.filter(asset=asset).order_by('-date').first()
        if latest:
            asset_data = {
                'code': asset.code,
                'name': asset.name,
                'price': float(latest.value_mru),
                'category': asset.category,
                'date': latest.date,
                'formatted_price': f'{latest.value_mru:,.4f}'
            }
            
            if asset.category == 'currency':
                currencies.append(asset_data)
            else:
                commodities.append(asset_data)
    
    # Create popular conversion suggestions
    suggestions = []
    
    # If we have both currencies and commodities, create some suggestions
    if currencies and commodities:
        # Example: "How much Gold can you buy with 50,000 MRU?"
        if any(c['code'] == 'GOLD' for c in commodities):
            suggestions.append({
                'title': 'Gold Purchase Power',
                'description': 'See how much gold you can buy',
                'from_type': 'MRU',
                'to_type': 'GOLD',
                'amount': 50000
            })
        
        # Example: "Convert USD to local commodities"
        if any(c['code'] == 'USD' for c in currencies):
            suggestions.append({
                'title': 'Dollar Commodity Value',
                'description': 'Check USD purchasing power',
                'from_type': 'USD',
                'to_type': 'commodity',
                'amount': 1000
            })
    
    context = {
        'currencies': currencies,
        'commodities': commodities,
        'all_assets': currencies + commodities,
        'suggestions': suggestions,
        'total_assets': len(currencies) + len(commodities),
    }
    
    return render(request, 'calculator.html', context)


def sanitize_metadata(metadata):
    """Convert all NumPy types to native Python types for safe JSON/template use"""
    sanitized = {}
    for k, v in metadata.items():
        if isinstance(v, (np.integer,)):
            sanitized[k] = int(v)
        elif isinstance(v, (np.floating,)):
            sanitized[k] = float(v)
        elif isinstance(v, np.ndarray):
            sanitized[k] = v.tolist()
        elif isinstance(v, dict):
            sanitized[k] = {dk: float(dv) if isinstance(dv, (np.floating,)) else dv for dk, dv in v.items()}
        else:
            sanitized[k] = v
    return sanitized


@login_required
def predictions(request):
    """Load saved models, generate predictions, and build chart data"""
    assets = Asset.objects.all()
    predictions_data = []
    all_chart_data = {}  # keyed by asset code for JS switching

    for asset in assets:
        models_dir = os.getenv('MODELS_DIR', 'models')
        meta_path = os.path.join(models_dir, f'{asset.code}_metadata.joblib')
        model_path = os.path.join(models_dir, f'{asset.code}_model.joblib')

        if not os.path.exists(meta_path) or not os.path.exists(model_path):
            continue

        metadata = sanitize_metadata(joblib.load(meta_path))
        if metadata.get('model_version', 1) < 2:
            continue  # v1 level models: retrain with `python manage.py train_models`

        # Get actual historical prices (last 365 days max)
        actual_prices = Price.objects.filter(asset=asset).order_by('-date')[:365]

        actual_dates = [p.date.strftime('%Y-%m-%d') for p in reversed(actual_prices)]
        actual_values = [float(p.value_mru) for p in reversed(actual_prices)]

        latest_price = actual_prices[0] if actual_prices else None

        # Generate predictions for 1, 2 weeks, 1 month
        pred_7, pred_14, pred_30 = [], [], []
        try:
            from services.ml_service.train import predict_future
            df_30 = predict_future(asset.code, days_ahead=30)
            if df_30 is not None:
                records = df_30.to_dict('records')
                if latest_price:
                    current = float(latest_price.value_mru)
                    for r in records:
                        r['change'] = r['predicted_price'] - current
                        r['change_pct'] = 100 * r['change'] / current if current else 0.0
                pred_7 = records[:7]
                pred_14 = records[:14]
                pred_30 = records[:30]
        except Exception as e:
            print(f"Prediction error for {asset.code}: {e}")

        pred_dates_30 = [p['date'] for p in pred_30]
        pred_values_30 = [p['predicted_price'] for p in pred_30]

        # Build chart data object for JS
        all_chart_data[asset.code] = {
            'actual_dates': actual_dates,
            'actual_values': actual_values,
            'pred_dates': pred_dates_30,
            'pred_values': pred_values_30,
        }

        # Top 5 feature importances sorted
        feat_imp = metadata.get('feature_importances', {})
        top_features = sorted(feat_imp.items(), key=lambda x: x[1], reverse=True)[:5]

        predictions_data.append({
            'asset': asset,
            'metadata': metadata,
            'latest_price': latest_price,
            'pred_7': pred_7,
            'pred_14': pred_14,
            'pred_30': pred_30,
            'top_features': top_features,
            'skill_pct': 100 * metadata.get('skill', 0),
            'direction_pct': 100 * metadata.get('direction_accuracy', 0),
        })

    context = {
        'predictions_data': predictions_data,
        'total_models': len(predictions_data),
        'all_chart_data': json.dumps(all_chart_data),
        # Pass first asset code as default selected
        'default_asset': predictions_data[0]['asset'].code if predictions_data else '',
    }

    return render(request, 'predictions.html', context)