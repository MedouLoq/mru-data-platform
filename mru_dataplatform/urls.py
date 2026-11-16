"""
URL configuration for mru_dataplatform project.
"""
from django.contrib import admin
from django.urls import path
from app import views
from app.admin import admin_site

urlpatterns = [
    # Route pour l'administration (inclut /admin/login/)
    path('admin/', admin_site.urls),
    
    # AJOUT : Route directe pour le login
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('', views.dashboard, name='dashboard'),
    path('asset/<str:code>/', views.asset_detail, name='asset_detail'),
    path('comparison/', views.comparison, name='comparison'),
    path('statistics/', views.statistics, name='statistics'),
    path('calculator/', views.calculator, name='calculator'),
    path('predictions/', views.predictions, name='predictions'),
]
