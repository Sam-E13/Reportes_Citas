from django.urls import path
from .views import *

urlpatterns = [
    path('api/estadisticas-citas/', EstadisticasCitasView.as_view(), name='estadisticas-citas'),
    path('api/filtros-citas/', FiltrosCitasView.as_view(), name='filtros-citas'),
    path('api/generar-reporte-pdf/', GenerarReportePDFView.as_view(), name='generar-reporte-pdf'),
]