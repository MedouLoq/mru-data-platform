from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Count, Max, Min, Avg
from django.template.response import TemplateResponse
from .models import Asset, Price
import subprocess
import sys
from datetime import datetime, timedelta


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('code_display', 'name', 'category_badge', 'price_count', 'latest_price', 'last_update')
    list_filter = ('category',)
    search_fields = ('code', 'name')
    list_per_page = 20
    
    def code_display(self, obj):
        return format_html(
            '<strong style="font-size: 14px; color: #006233;">{}</strong>',
            obj.code
        )
    code_display.short_description = 'Code'
    
    def category_badge(self, obj):
        colors = {
            'currency': '#17a2b8',
            'commodity': '#ffc107'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            colors.get(obj.category, '#6c757d'),
            obj.get_category_display()
        )
    category_badge.short_description = 'Category'
    
    def price_count(self, obj):
        count = obj.price_set.count()
        return format_html(
            '<span style="color: #28a745; font-weight: bold;">{}</span> prices',
            count
        )
    price_count.short_description = 'Total Prices'
    
    def latest_price(self, obj):
        latest = obj.price_set.order_by('-date').first()
        if latest:
            formatted_value = '{:,.4f}'.format(latest.value_mru)
            return format_html(
                '<strong>{}</strong> MRU',
                formatted_value
            )
        return format_html('<span style="color: #dc3545;">No data</span>')
    latest_price.short_description = 'Latest Price'
    
    def last_update(self, obj):
        latest = obj.price_set.order_by('-date').first()
        if latest:
            days_ago = (datetime.now().date() - latest.date).days
            if days_ago == 0:
                return format_html('<span style="color: #28a745;">Today</span>')
            elif days_ago == 1:
                return format_html('<span style="color: #ffc107;">Yesterday</span>')
            else:
                return format_html('<span style="color: #6c757d;">{} days ago</span>', days_ago)
        return '-'
    last_update.short_description = 'Last Update'


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ('asset_display', 'date_display', 'value_display', 'variation_display', 'source_display')
    list_filter = ('asset', 'asset__category', 'date')
    date_hierarchy = 'date'
    search_fields = ('asset__code', 'asset__name', 'source')
    list_per_page = 50
    ordering = ('-date', 'asset__code')
    
    # Required: Manual Triggers via admin actions
    actions = ['trigger_manual_scraping', 'trigger_mongodb_sync']
    
    @admin.action(description="🔄 Lancer manuellement le scraping")
    def trigger_manual_scraping(self, request, queryset):
        try:
            subprocess.Popen([sys.executable, "scraper.py"])
            self.message_user(request, "✅ Le scraping a été lancé en arrière-plan.")
        except Exception as e:
            self.message_user(request, f"❌ Erreur lors du lancement : {e}", level='error')
    
    @admin.action(description="💾 Lancer la synchronisation MongoDB")
    def trigger_mongodb_sync(self, request, queryset):
        try:
            subprocess.Popen([sys.executable, "services/sync_mongo/sync.py"])
            self.message_user(request, "✅ La synchronisation MongoDB a été lancée.")
        except Exception as e:
            self.message_user(request, f"❌ Erreur lors du lancement : {e}", level='error')
    
    def asset_display(self, obj):
        colors = {
            'currency': '#17a2b8',
            'commodity': '#ffc107'
        }
        return format_html(
            '<div style="line-height: 1.4;"><strong style="font-size: 13px; color: #006233;">{}</strong><br>'
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 8px; font-size: 10px;">{}</span></div>',
            obj.asset.code,
            colors.get(obj.asset.category, '#6c757d'),
            obj.asset.get_category_display()
        )
    asset_display.short_description = 'Asset'
    
    def date_display(self, obj):
        return format_html(
            '<strong>{}</strong>',
            obj.date.strftime('%d %b %Y')
        )
    date_display.short_description = 'Date'
    date_display.admin_order_field = 'date'
    
    def value_display(self, obj):
        formatted_value = '{:,.4f}'.format(obj.value_mru)
        return format_html(
            '<span style="font-size: 14px; font-weight: bold; color: #006233;">{} MRU</span>',
            formatted_value
        )
    value_display.short_description = 'Price'
    
    def variation_display(self, obj):
        # Get previous price
        previous = Price.objects.filter(
            asset=obj.asset,
            date__lt=obj.date
        ).order_by('-date').first()
        
        if previous and previous.value_mru > 0:
            variation = ((obj.value_mru - previous.value_mru) / previous.value_mru) * 100
            variation_str = '{:.2f}'.format(abs(variation))
            if variation > 0:
                return format_html(
                    '<span style="color: #28a745; font-weight: bold;">▲ {}%</span>',
                    variation_str
                )
            elif variation < 0:
                return format_html(
                    '<span style="color: #dc3545; font-weight: bold;">▼ {}%</span>',
                    variation_str
                )
            else:
                return format_html('<span style="color: #6c757d;">─ 0.00%</span>')
        return format_html('<span style="color: #6c757d;">─</span>')
    variation_display.short_description = 'vs Previous'
    
    def source_display(self, obj):
        if obj.source:
            return format_html(
                '<span style="background-color: #e9ecef; padding: 3px 8px; border-radius: 8px; font-size: 11px;">{}</span>',
                obj.source
            )
        return '-'
    source_display.short_description = 'Source'


# Override the admin site's index view
class CustomAdminSite(admin.AdminSite):
    site_header = '🇲🇷 MRU DataPlatform Administration'
    site_title = 'MRU Admin'
    index_title = 'Financial Data Management'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('operations/', self.admin_view(self.operations_view), name='operations'),
        ]
        return custom_urls + urls
    
    def operations_view(self, request):
        """Custom view for manual operations"""
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'scraping':
                try:
                    subprocess.Popen([sys.executable, "scraper.py"])
                    messages.success(request, '✅ Le scraping a été lancé en arrière-plan.')
                except Exception as e:
                    messages.error(request, f'❌ Erreur lors du lancement : {e}')
            
            elif action == 'mongodb_sync':
                try:
                    subprocess.Popen([sys.executable, "services/sync_mongo/sync.py"])
                    messages.success(request, '✅ La synchronisation MongoDB a été lancée.')
                except Exception as e:
                    messages.error(request, f'❌ Erreur lors du lancement : {e}')
            
            return redirect('admin:operations')
        
        # Get statistics
        total_assets = Asset.objects.count()
        total_prices = Price.objects.count()
        currencies = Asset.objects.filter(category='currency').count()
        commodities = Asset.objects.filter(category='commodity').count()
        
        # Get latest updates
        latest_prices = Price.objects.select_related('asset').order_by('-date')[:10]
        
        # Get date range
        date_stats = Price.objects.aggregate(
            oldest=Min('date'),
            newest=Max('date')
        )
        
        context = {
            **self.each_context(request),
            'title': 'System Operations & Statistics',
            'total_assets': total_assets,
            'total_prices': total_prices,
            'currencies': currencies,
            'commodities': commodities,
            'latest_prices': latest_prices,
            'date_stats': date_stats,
        }
        
        return TemplateResponse(request, 'admin/operations.html', context)
    
    def index(self, request, extra_context=None):
        """Override admin index to add custom dashboard"""
        extra_context = extra_context or {}
        
        # Add statistics
        extra_context['total_assets'] = Asset.objects.count()
        extra_context['total_prices'] = Price.objects.count()
        extra_context['currencies'] = Asset.objects.filter(category='currency').count()
        extra_context['commodities'] = Asset.objects.filter(category='commodity').count()
        
        latest = Price.objects.order_by('-date').first()
        extra_context['latest_update'] = latest
        
        return super().index(request, extra_context)


# Create custom admin site instance
admin_site = CustomAdminSite(name='custom_admin')

# Register models with custom site
admin_site.register(Asset, AssetAdmin)
admin_site.register(Price, PriceAdmin)