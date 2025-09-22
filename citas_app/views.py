import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import datetime
from django.conf import settings
from django.http import HttpResponse
import io
from io import BytesIO
import tempfile
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
import logging

logger = logging.getLogger(__name__)
class EstadisticasCitasView(APIView):
    def parse_date(self, date_string):
        """
        Helper para parsear diferentes formatos de fecha
        """
        if not date_string:
            return None
            
        # Lista de formatos posibles
        formats = [
            '%Y-%m-%dT%H:%M:%S.%f%z',     # Con zona horaria: 2025-08-13T16:52:14.298714-06:00
            '%Y-%m-%dT%H:%M:%S%z',        # Sin microsegundos, con zona: 2025-08-13T16:52:14-06:00
            '%Y-%m-%dT%H:%M:%S.%fZ',      # Con Z: 2025-08-13T16:52:14.298714Z
            '%Y-%m-%dT%H:%M:%SZ',         # Sin microsegundos, con Z: 2025-08-13T16:52:14Z
            '%Y-%m-%dT%H:%M:%S.%f',       # Sin zona horaria: 2025-08-13T16:52:14.298714
            '%Y-%m-%dT%H:%M:%S'           # Básico: 2025-08-13T16:52:14
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_string, fmt)
            except ValueError:
                continue
        
        # Si ningún formato funciona, intentar con fromisoformat
        try:
            return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        except ValueError:
            logger.warning(f"No se pudo parsear la fecha: {date_string}")
            return None

    def get(self, request):
        try:
            # URLs usando configuración del settings.py
            API_CITAS = settings.API_CITAS
            API_PROFESIONALES = settings.API_PROFESIONALES
            API_ATLETAS = settings.API_ATLETAS
            API_AREAS = settings.API_AREAS
            
            # 1. Obtener todas las citas
            logger.info(f"Consultando citas en: {API_CITAS}")
            citas_response = requests.get(API_CITAS, timeout=10)
            citas_response.raise_for_status()
            todas_citas = citas_response.json()
            
            # 2. Filtrar citas del mes actual
            mes_actual = datetime.now().month
            año_actual = datetime.now().year
            
            # 3. Calcular estadísticas básicas
            citas_mes_actual = []
            for c in todas_citas:
                fecha_str = c.get('fecha', c.get('creado_el', ''))
                fecha_parsed = self.parse_date(fecha_str)
                
                if fecha_parsed and fecha_parsed.month == mes_actual and fecha_parsed.year == año_actual:
                    citas_mes_actual.append(c)
            
            total_citas = len(citas_mes_actual)
            
            # 4. Obtener todos los profesionales
            profesionales_response = requests.get(API_PROFESIONALES, timeout=10)
            profesionales_response.raise_for_status()
            todos_profesionales = profesionales_response.json()
            
            # 5. Obtener todos los atletas
            atletas_response = requests.get(API_ATLETAS, timeout=10)
            atletas_response.raise_for_status()
            todos_atletas = atletas_response.json()
            
            # 6. Obtener todas las áreas
            areas_response = requests.get(API_AREAS, timeout=10)
            areas_response.raise_for_status()
            todas_areas = areas_response.json()
            
            # 7. Datos mensuales por profesional (últimos 12 meses)
            monthly_data_by_profesional = []
            meses_mostrar = 12  # Mostrar datos de los últimos 12 meses
            
            for i in range(meses_mostrar):
                # Calcular mes y año para el período actual
                mes_offset = meses_mostrar - i - 1
                month = (mes_actual - mes_offset - 1) % 12 + 1
                year = año_actual - (1 if mes_actual - mes_offset - 1 < 0 else 0)
                
                # Filtrar citas para este mes
                citas_mes = []
                for c in todas_citas:
                    fecha_str = c.get('fecha', c.get('creado_el', ''))
                    fecha_parsed = self.parse_date(fecha_str)
                    
                    if fecha_parsed and fecha_parsed.month == month and fecha_parsed.year == year:
                        citas_mes.append(c)
                
                # Contar citas por profesional para este mes
                profesionales_data_mes = []
                for profesional in todos_profesionales:
                    profesional_id = str(profesional['id'])
                    count = sum(1 for c in citas_mes if str(c.get('profesional_salud_id', '')) == profesional_id)
                    
                    profesionales_data_mes.append({
                        'profesional_id': profesional['id'],
                        'profesional_name': f"{profesional.get('nombre', '')} {profesional.get('apPaterno', '')}",
                        'count': count
                    })
                
                monthly_data_by_profesional.append({
                    'mes': datetime(year, month, 1).strftime('%b'),
                    'mes_numero': month,
                    'ano': year,
                    'profesionales': profesionales_data_mes,
                    'total': len(citas_mes)
                })
            
            # 8. Datos totales por profesional (para el gráfico simple)
            profesionales_data = []
            for profesional in todos_profesionales:
                profesional_id = str(profesional['id'])
                total_citas_prof = sum(
                    1 for c in citas_mes_actual 
                    if str(c.get('profesional_salud_id', '')) == profesional_id
                )
                
                profesionales_data.append({
                    'nombre': f"{profesional.get('nombre', '')} {profesional.get('apPaterno', '')}",
                    'id': profesional_id,
                    'total': total_citas_prof,
                    'especialidad': profesional.get('especialidad', 'Sin especialidad')
                })
            
            # 9. Datos por atleta (top 10 con más citas)
            atletas_data = []
            for atleta in todos_atletas:
                atleta_id = str(atleta['id'])
                total_citas_atleta = sum(
                    1 for c in todas_citas 
                    if str(c.get('atleta_id', '')) == atleta_id
                )
                
                atletas_data.append({
                    'nombre': f"{atleta.get('nombre', '')} {atleta.get('apPaterno', '')}",
                    'id': atleta_id,
                    'total': total_citas_atleta
                })
            
            # Ordenar y tomar top 10
            top_atletas = sorted(atletas_data, key=lambda x: x['total'], reverse=True)[:10]
            
            # 10. Datos por área
            areas_data = []
            for area in todas_areas:
                area_id = str(area['id'])
                total_citas_area = sum(
                    1 for c in citas_mes_actual 
                    if str(c.get('area_id', '')) == area_id
                )
                
                areas_data.append({
                    'nombre': area.get('nombre', 'Sin nombre'),
                    'id': area_id,
                    'total': total_citas_area,
                    'pendiente': sum(
                        1 for c in citas_mes_actual 
                        if str(c.get('area_id', '')) == area_id and c.get('estado', '').lower() == 'pendiente'
                    ),
                    'confirmada': sum(
                        1 for c in citas_mes_actual 
                        if str(c.get('area_id', '')) == area_id and c.get('estado', '').lower() == 'confirmada'
                    ),
                    'completada': sum(
                        1 for c in citas_mes_actual 
                        if str(c.get('area_id', '')) == area_id and c.get('estado', '').lower() == 'completada'
                    ),
                    'cancelada': sum(
                        1 for c in citas_mes_actual 
                        if str(c.get('area_id', '')) == area_id and c.get('estado', '').lower() == 'cancelada'
                    )
                })
            
           # 11. Datos mensuales por área (últimos 12 meses)
            monthly_data_by_area = []

            for i in range(meses_mostrar):
                # Calcular mes y año para el período actual
                mes_offset = meses_mostrar - i - 1
                month = (mes_actual - mes_offset - 1) % 12 + 1
                year = año_actual - (1 if mes_actual - mes_offset - 1 < 0 else 0)
                
                # Filtrar citas para este mes
                citas_mes = []
                for c in todas_citas:
                    fecha_str = c.get('fecha', c.get('creado_el', ''))
                    fecha_parsed = self.parse_date(fecha_str)
                    
                    if fecha_parsed and fecha_parsed.month == month and fecha_parsed.year == year:
                        citas_mes.append(c)
                
                # Contar citas por área para este mes
                areas_data_mes = []
                for area in todas_areas:
                    area_id = str(area['id'])
                    
                    # Verificar diferentes campos posibles para el área
                    count = 0
                    for c in citas_mes:
                        # Verificar diferentes campos posibles para el ID del área
                        cita_area_id = None
                        if 'area_id' in c and c['area_id'] is not None:
                            cita_area_id = str(c['area_id'])
                        elif 'area' in c and c['area'] is not None:
                            if isinstance(c['area'], dict) and 'id' in c['area']:
                                cita_area_id = str(c['area']['id'])
                            else:
                                cita_area_id = str(c['area'])
                                
                        if cita_area_id == area_id:
                            count += 1
                    
                    areas_data_mes.append({
                        'area_id': area['id'],
                        'area_name': area.get('nombre', 'Sin nombre'),
                        'count': count
                    })
                
                # Verificar si la suma de los conteos coincide con el total
                sum_counts = sum(a['count'] for a in areas_data_mes)
                total_citas_mes = len(citas_mes)
                
                # Si hay una discrepancia, distribuir las citas no asignadas
                if sum_counts < total_citas_mes and areas_data_mes:
                    # Distribuir las citas no asignadas a la primera área
                    # (o podrías crear una categoría "Sin asignar")
                    if areas_data_mes:
                        areas_data_mes[0]['count'] += (total_citas_mes - sum_counts)
                
                monthly_data_by_area.append({
                    'mes': datetime(year, month, 1).strftime('%b'),
                    'mes_numero': month,
                    'ano': year,
                    'areas': areas_data_mes,
                    'total': total_citas_mes
                })
                    
            # 12. Calcular distribución por estado
            estado_distribucion = {
                'Pendiente': sum(1 for c in citas_mes_actual if c.get('estado', '').lower() == 'pendiente'),
                'Confirmada': sum(1 for c in citas_mes_actual if c.get('estado', '').lower() == 'confirmada'),
                'Completada': sum(1 for c in citas_mes_actual if c.get('estado', '').lower() == 'completada'),
                'Cancelada': sum(1 for c in citas_mes_actual if c.get('estado', '').lower() == 'cancelada')
            }
            
            # 13. Calcular porcentaje de citas completadas
            citas_completadas = estado_distribucion['Completada']
            porcentaje_completadas = round((citas_completadas / total_citas) * 100) if total_citas > 0 else 0
            
            # Respuesta final
            return Response({
                'total_citas': total_citas,
                'citas_mes_actual': len(citas_mes_actual),
                'citas_completadas': citas_completadas,
                'porcentaje_completadas': porcentaje_completadas,
                'estado_distribucion': estado_distribucion,
                'profesionales_data': profesionales_data,
                'monthly_data_by_profesional': monthly_data_by_profesional,
                'monthly_data': [{'mes': m['mes'], 'total': m['total']} for m in monthly_data_by_profesional],
                'top_atletas': top_atletas,
                'areas_data': areas_data,
                'monthly_data_by_area': monthly_data_by_area
            })
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de conexión: {str(e)}")
            return Response({
                'error': 'Error al conectar con los servicios externos',
                'detalles': str(e)
            }, status=503)
            
        except Exception as e:
            logger.exception("Error interno del servidor")
            return Response({
                'error': 'Error interno del servidor',
                'detalles': str(e)
            }, status=500)

class FiltrosCitasView(APIView):
    def get(self, request):
        # Usar configuración del settings.py
        API_URL_BASE = f'{settings.BACKEND_PROTOCOL}://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}/Catalogos/'
        
        try:
            # Obtener datos de atletas
            atletas_response = requests.get(f"{API_URL_BASE}Atletas/", timeout=5)
            atletas_response.raise_for_status()
            
            # Usar un diccionario para eliminar duplicados por ID
            atletas_dict = {}
            for a in atletas_response.json():
                if a["id"] not in atletas_dict:
                    atletas_dict[a["id"]] = {"id": a["id"], "nombre": f"{a.get('nombre', '')} {a.get('apPaterno', '')} {a.get('apMaterno', '')}"}
            
            atletas = list(atletas_dict.values())
            
            # Obtener datos de áreas
            areas_response = requests.get(f"{API_URL_BASE}Areas/", timeout=5)
            areas_response.raise_for_status()
            
            # Usar un diccionario para eliminar duplicados por ID
            areas_dict = {}
            for a in areas_response.json():
                if a["id"] not in areas_dict:
                    areas_dict[a["id"]] = {"id": a["id"], "nombre": a["nombre"]}
            
            areas = list(areas_dict.values())
            
            # Obtener datos de consultorios
            consultorios_response = requests.get(f"{API_URL_BASE}Consultorios/", timeout=5)
            consultorios_response.raise_for_status()
            
            # Usar un diccionario para eliminar duplicados por ID
            consultorios_dict = {}
            for c in consultorios_response.json():
                if c["id"] not in consultorios_dict:
                    consultorios_dict[c["id"]] = {"id": c["id"], "nombre": c["nombre"]}
            
            consultorios = list(consultorios_dict.values())
            
            # Obtener datos de profesionales de salud
            profesionales_response = requests.get(f"{API_URL_BASE}Profesionales-Salud/", timeout=5)
            profesionales_response.raise_for_status()
            
            # Usar un diccionario para eliminar duplicados por ID
            profesionales_dict = {}
            for p in profesionales_response.json():
                if p["id"] not in profesionales_dict:
                    profesionales_dict[p["id"]] = {
                        "id": p["id"], 
                        "nombre": f"{p.get('nombre', '')} {p.get('apPaterno', '')} {p.get('apMaterno', '')} - {p.get('especialidad', '')}"
                    }
            
            profesionales = list(profesionales_dict.values())
            
            return Response({
                'atletas': atletas,
                'areas': areas,
                'consultorios': consultorios,
                'Profesionales-Salud': profesionales
            })
            
        except requests.exceptions.RequestException as e:
            return Response({
                'error': 'Error al conectar con el servicio de datos',
                'detalles': str(e)
            }, status=503)
        
        except Exception as e:
            return Response({
                'error': 'Error interno del servidor',
                'detalles': str(e)
            }, status=500)


logger = logging.getLogger(__name__)

class GenerarReportePDFView(APIView):
    """
    Vista que genera reportes PDF de citas obteniendo datos de servicios externos
    y enriqueciéndolos con información de catálogos relacionados.
    """

    def __init__(self):
        super().__init__()
        # Usar configuración del settings.py
        self.CITAS_API_URL = settings.API_CITAS
        self.CATALOGOS_API_URL = f'{settings.BACKEND_PROTOCOL}://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}/Catalogos/'
        self.TIMEOUT = 10  # segundos

    def post(self, request):
        """
        Genera un reporte PDF de citas médicas con filtros aplicables.
        
        Parámetros esperados en request.data:
        - fecha_inicio (requerido): Fecha de inicio (YYYY-MM-DD)
        - fecha_fin (requerido): Fecha de fin (YYYY-MM-DD)
        - atleta_id (opcional): ID del atleta para filtrar
        - area_id (opcional): ID del área para filtrar
        - consultorio_id (opcional): ID del consultorio para filtrar
        - profesional_id (opcional): ID del profesional para filtrar
        """
        try:
            logger.info("Iniciando generación de reporte PDF con filtros: %s", request.data)
            
            # 1. Validación de parámetros requeridos
            if not all(k in request.data for k in ['fecha_inicio', 'fecha_fin']):
                error_msg = "Las fechas de inicio y fin son requeridas"
                logger.error(error_msg)
                return Response(
                    {'error': error_msg}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 2. Obtener todas las citas del servicio externo
            try:
                response = requests.get(
                    self.CITAS_API_URL,
                    timeout=self.TIMEOUT
                )
                response.raise_for_status()
                todas_citas = response.json()
                logger.info("Total de citas obtenidas del servicio: %d", len(todas_citas))
            except requests.exceptions.RequestException as e:
                logger.error("Error al obtener citas: %s", str(e))
                return Response(
                    {'error': 'No se pudieron obtener las citas del servicio'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            # 3. Obtener catálogos necesarios
            catalogos = self._obtener_catalogos()
            if isinstance(catalogos, Response):
                return catalogos  # Retorna el error si hubo problema

            # 4. Filtrar citas según parámetros
            citas_filtradas = self._filtrar_citas(
                todas_citas, 
                request.data,
                catalogos
            )
            logger.info("Citas después de filtrar: %d", len(citas_filtradas))

            # 5. Enriquecer citas con datos completos
            citas_enriquecidas = self._enriquecer_citas(
                citas_filtradas,
                catalogos
            )

            # 6. Generar PDF
            pdf_buffer = self._generar_pdf(
                citas_enriquecidas,
                request.data
            )

            # 7. Preparar respuesta
            fecha_inicio = request.data['fecha_inicio']
            fecha_fin = request.data['fecha_fin']
            response = HttpResponse(
                pdf_buffer.getvalue(), 
                content_type='application/pdf'
            )
            filename = f"reporte_citas_{fecha_inicio}_{fecha_fin}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            logger.info("Reporte PDF generado exitosamente")
            return response
            
        except Exception as e:
            logger.error("Error inesperado al generar reporte: %s", str(e), exc_info=True)
            return Response(
                {
                    'error': 'Error interno al generar el reporte',
                    'detalles': str(e)
                }, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _obtener_catalogos(self):
        """
        Obtiene todos los catálogos necesarios desde los servicios externos.
        
        Returns:
            dict: Diccionario con los catálogos o Response con error
        """
        catalogos = {
            'atletas': {},
            'areas': {},
            'consultorios': {},
            'profesionales': {}
        }
        
        try:
            # Obtener atletas
            response = requests.get(
                f"{self.CATALOGOS_API_URL}Atletas/",
                timeout=self.TIMEOUT
            )
            response.raise_for_status()
            for atleta in response.json():
                catalogos['atletas'][str(atleta['id'])] = atleta
            
            # Obtener áreas
            response = requests.get(
                f"{self.CATALOGOS_API_URL}Areas/",
                timeout=self.TIMEOUT
            )
            response.raise_for_status()
            for area in response.json():
                catalogos['areas'][str(area['id'])] = area
            
            # Obtener consultorios
            response = requests.get(
                f"{self.CATALOGOS_API_URL}Consultorios/",
                timeout=self.TIMEOUT
            )
            response.raise_for_status()
            for consultorio in response.json():
                catalogos['consultorios'][str(consultorio['id'])] = consultorio
            
            # Obtener profesionales
            response = requests.get(
                f"{self.CATALOGOS_API_URL}Profesionales-Salud/",
                timeout=self.TIMEOUT
            )
            response.raise_for_status()
            for profesional in response.json():
                catalogos['profesionales'][str(profesional['id'])] = profesional
                
            return catalogos
            
        except requests.exceptions.RequestException as e:
            logger.error("Error al obtener catálogos: %s", str(e))
            return Response(
                {
                    'error': 'No se pudieron obtener los catálogos necesarios',
                    'detalles': str(e)
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

    def _filtrar_citas(self, citas, filtros, catalogos):
        """
        Filtra las citas según los parámetros recibidos.
        
        Args:
            citas (list): Lista de citas a filtrar
            filtros (dict): Parámetros de filtrado
            catalogos (dict): Catálogos para validar IDs
            
        Returns:
            list: Lista de citas filtradas
        """
        fecha_inicio = datetime.strptime(filtros['fecha_inicio'], '%Y-%m-%d')
        fecha_fin = datetime.strptime(filtros['fecha_fin'], '%Y-%m-%d').replace(
            hour=23, minute=59, second=59
        )
        
        citas_filtradas = []
        
        for cita in citas:
            try:
                # 1. Filtrar por fecha
                fecha_cita = datetime.strptime(
                    cita['creado_el'], 
                    '%Y-%m-%dT%H:%M:%S.%fZ'
                )
                if not (fecha_inicio <= fecha_cita <= fecha_fin):
                    continue
                
                # 2. Filtrar por atleta si se especificó
                if 'atleta_id' in filtros and filtros['atleta_id'] not in [None, "todos", ""]:
                    # Obtener el ID del atleta de la cita en diferentes formatos posibles
                    atleta_id_cita = None
                    for campo in ['atleta_id', 'atleta', 'id_atleta', 'paciente_id', 'paciente']:
                        if campo in cita:
                            valor = cita[campo]
                            # Manejar si el valor es un diccionario o un ID directo
                            if isinstance(valor, dict) and 'id' in valor:
                                atleta_id_cita = str(valor['id'])
                                break
                            elif valor is not None:
                                atleta_id_cita = str(valor)
                                break
                    
                    if not atleta_id_cita or str(atleta_id_cita) != str(filtros['atleta_id']):
                        continue
                
                # 3. Filtrar por área si se especificó
                if 'area_id' in filtros and filtros['area_id'] not in [None, "todos", ""]:
                    # Obtener el ID del área de la cita en diferentes formatos posibles
                    area_id_cita = None
                    for campo in ['area_id', 'area', 'id_area']:
                        if campo in cita:
                            valor = cita[campo]
                            # Manejar si el valor es un diccionario o un ID directo
                            if isinstance(valor, dict) and 'id' in valor:
                                area_id_cita = str(valor['id'])
                                break
                            elif valor is not None:
                                area_id_cita = str(valor)
                                break
                    
                    if not area_id_cita or str(area_id_cita) != str(filtros['area_id']):
                        continue
                
                # 4. Filtrar por consultorio si se especificó
                if 'consultorio_id' in filtros and filtros['consultorio_id'] not in [None, "todos", ""]:
                    # Obtener el ID del consultorio de la cita en diferentes formatos posibles
                    consultorio_id_cita = None
                    for campo in ['consultorio_id', 'consultorio', 'id_consultorio']:
                        if campo in cita:
                            valor = cita[campo]
                            # Manejar si el valor es un diccionario o un ID directo
                            if isinstance(valor, dict) and 'id' in valor:
                                consultorio_id_cita = str(valor['id'])
                                break
                            elif valor is not None:
                                consultorio_id_cita = str(valor)
                                break
                    
                    if not consultorio_id_cita or str(consultorio_id_cita) != str(filtros['consultorio_id']):
                        continue
                
                # 5. Filtrar por profesional si se especificó
                if 'profesional_id' in filtros and filtros['profesional_id'] not in [None, "todos", ""]:
                    # Obtener el ID del profesional de la cita en diferentes formatos posibles
                    profesional_id_cita = None
                    for campo in ['profesional_id', 'profesional_salud', 'profesional_salud_id', 'profesional', 'id_profesional']:
                        if campo in cita:
                            valor = cita[campo]
                            # Manejar si el valor es un diccionario o un ID directo
                            if isinstance(valor, dict) and 'id' in valor:
                                profesional_id_cita = str(valor['id'])
                                break
                            elif valor is not None:
                                profesional_id_cita = str(valor)
                                break
                    
                    if not profesional_id_cita or str(profesional_id_cita) != str(filtros['profesional_id']):
                        continue
                
                # Si pasó todos los filtros, agregar a las citas filtradas
                citas_filtradas.append(cita)
                
            except Exception as e:
                logger.warning(
                    "Error al procesar cita ID %s: %s", 
                    cita.get('id'), str(e)
                )
                continue
                
        return citas_filtradas

    def _enriquecer_citas(self, citas, catalogos):
        """
        Enriquece las citas con información completa de los catálogos.
        
        Args:
            citas (list): Lista de citas a enriquecer
            catalogos (dict): Diccionario con los catálogos
            
        Returns:
            list: Lista de citas enriquecidas
        """
        citas_enriquecidas = []
        
        for cita in citas:
            try:
                cita_enriquecida = cita.copy()
                
                # Imprimir la estructura de la cita para depuración
                logger.debug(f"Estructura de cita: {json.dumps(cita, indent=2)}")
                
                # Imprimir todos los campos de la cita para depuración
                logger.debug(f"Campos disponibles en la cita: {list(cita.keys())}")
                
                # Enriquecer con datos del atleta - buscar en diferentes formatos posibles
                atleta_id = None
                for campo in ['atleta_id', 'atleta', 'id_atleta', 'paciente_id', 'paciente']:
                    if campo in cita:
                        valor = cita[campo]
                        # Manejar si el valor es un diccionario o un ID directo
                        if isinstance(valor, dict) and 'id' in valor:
                            atleta_id = str(valor['id'])
                        elif valor is not None:
                            atleta_id = str(valor)
                        break
                
                if atleta_id and atleta_id in catalogos['atletas']:
                    atleta = catalogos['atletas'][atleta_id]
                    cita_enriquecida['atleta_nombre'] = f"{atleta.get('nombre', '')} {atleta.get('apPaterno', '')} {atleta.get('apMaterno', '')}".strip()
                else:
                    cita_enriquecida['atleta_nombre'] = "No especificado"
                    logger.warning(f"No se encontró atleta con ID {atleta_id}")
                
                # Enriquecer con datos del área - buscar en diferentes formatos posibles
                area_id = None
                for campo in ['area_id', 'area', 'id_area']:
                    if campo in cita:
                        valor = cita[campo]
                        # Manejar si el valor es un diccionario o un ID directo
                        if isinstance(valor, dict) and 'id' in valor:
                            area_id = str(valor['id'])
                        elif valor is not None:
                            area_id = str(valor)
                        break
                
                if area_id and area_id in catalogos['areas']:
                    cita_enriquecida['area_nombre'] = catalogos['areas'][area_id]['nombre']
                else:
                    cita_enriquecida['area_nombre'] = "No especificada"
                    logger.warning(f"No se encontró área con ID {area_id}")
                
                # Enriquecer con datos del consultorio - buscar en diferentes formatos posibles
                consultorio_id = None
                for campo in ['consultorio_id', 'consultorio', 'id_consultorio']:
                    if campo in cita:
                        valor = cita[campo]
                        # Manejar si el valor es un diccionario o un ID directo
                        if isinstance(valor, dict) and 'id' in valor:
                            consultorio_id = str(valor['id'])
                        elif valor is not None:
                            consultorio_id = str(valor)
                        break
                
                if consultorio_id and consultorio_id in catalogos['consultorios']:
                    cita_enriquecida['consultorio_nombre'] = catalogos['consultorios'][consultorio_id]['nombre']
                else:
                    cita_enriquecida['consultorio_nombre'] = "No especificado"
                    logger.warning(f"No se encontró consultorio con ID {consultorio_id}")
                
                # Enriquecer con datos del profesional - buscar en diferentes formatos posibles
                profesional_id = None
                
                # Buscar el ID del profesional en diferentes campos posibles
                for campo in ['profesional_salud', 'profesional_salud_id']:
                    if campo in cita:
                        valor = cita[campo]
                        # Manejar si el valor es un diccionario o un ID directo
                        if isinstance(valor, dict) and 'id' in valor:
                            profesional_id = str(valor['id'])
                            logger.debug(f"Encontrado profesional_id en diccionario {campo}: {profesional_id}")
                        elif valor is not None:
                            profesional_id = str(valor)
                            logger.debug(f"Encontrado profesional_id directo en {campo}: {profesional_id}")
                        break
                
                # Si no se encontró en los campos anteriores, intentar con otros nombres posibles
                if profesional_id and profesional_id in catalogos['profesionales']:
                    profesional = catalogos['profesionales'][profesional_id]
                    nombre = profesional.get('nombre', '')
                    apellido = profesional.get('apellido', '')
                    cita_enriquecida['profesional_nombre'] = f"{nombre} {apellido}".strip()
                    cita_enriquecida['profesional_especialidad'] = profesional.get('especialidad', 'No especificada')
                    logger.debug(f"Profesional encontrado: {cita_enriquecida['profesional_nombre']}")
                else:
                    cita_enriquecida['profesional_nombre'] = "No especificado"
                    cita_enriquecida['profesional_especialidad'] = "No especificada"
                    logger.warning(f"No se encontró profesional con ID {profesional_id}")
                
                # Verificar si el ID existe en el catálogo
                if profesional_id:
                    logger.debug(f"Buscando profesional con ID: {profesional_id}")
                    logger.debug(f"IDs disponibles en catálogo: {list(catalogos['profesionales'].keys())}")
                    
                    # Intentar diferentes formatos del ID
                    profesional_encontrado = False
                    for formato_id in [profesional_id, profesional_id.strip('"\''), int(profesional_id) if profesional_id.isdigit() else profesional_id]:
                        formato_id_str = str(formato_id)
                        if formato_id_str in catalogos['profesionales']:
                            profesional = catalogos['profesionales'][formato_id_str]
                            nombre = profesional.get('nombre', '')
                            apellido = profesional.get('apellido', '')
                            especialidad = profesional.get('especialidad', 'No especificada')
                            
                            cita_enriquecida['profesional_nombre'] = f"{nombre} {apellido}".strip()
                            cita_enriquecida['profesional_especialidad'] = especialidad
                            logger.debug(f"Profesional encontrado con formato ID {formato_id_str}: {cita_enriquecida['profesional_nombre']}")
                            profesional_encontrado = True
                            break
                    
                    if not profesional_encontrado:
                        cita_enriquecida['profesional_nombre'] = "No especificado"
                        cita_enriquecida['profesional_especialidad'] = "No especificada"
                        logger.warning(f"No se encontró profesional con ID {profesional_id} en ningún formato")
                else:
                    cita_enriquecida['profesional_nombre'] = "No especificado"
                    cita_enriquecida['profesional_especialidad'] = "No especificada"
                    logger.warning("No se encontró campo de profesional en la cita")
                
                # Formatear fecha y hora
                try:
                    fecha_hora = datetime.strptime(cita['creado_el'], '%Y-%m-%dT%H:%M:%S.%fZ')
                    cita_enriquecida['fecha_formateada'] = fecha_hora.strftime('%d/%m/%Y')
                    cita_enriquecida['hora_formateada'] = fecha_hora.strftime('%H:%M')
                except (KeyError, ValueError) as e:
                    logger.warning(f"Error al formatear fecha/hora: {str(e)}")
                    cita_enriquecida['fecha_formateada'] = "No especificada"
                    cita_enriquecida['hora_formateada'] = "No especificada"
                
                citas_enriquecidas.append(cita_enriquecida)
                
            except Exception as e:
                logger.error(f"Error al enriquecer cita: {str(e)}", exc_info=True)
                # Añadir la cita sin enriquecer para no perder datos
                cita_enriquecida = cita.copy()
                cita_enriquecida['atleta_nombre'] = "Error al procesar"
                cita_enriquecida['area_nombre'] = "Error al procesar"
                cita_enriquecida['consultorio_nombre'] = "Error al procesar"
                cita_enriquecida['profesional_nombre'] = "Error al procesar"
                cita_enriquecida['profesional_especialidad'] = "Error al procesar"
                cita_enriquecida['fecha_formateada'] = "Error al procesar"
                cita_enriquecida['hora_formateada'] = "Error al procesar"
                citas_enriquecidas.append(cita_enriquecida)
        
        return citas_enriquecidas

    def _generar_pdf(self, citas, filtros):
        """
        Genera el PDF con el reporte de citas.
        
        Args:
            citas (list): Lista de citas enriquecidas
            filtros (dict): Parámetros de filtrado
            
        Returns:
            io.BytesIO: Buffer con el PDF generado
        """
        buffer = io.BytesIO()
        
        # Configuración del documento
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=30
        )
        
        # Estilos
        styles = getSampleStyleSheet()
        title_style = styles['Heading1']
        subtitle_style = styles['Heading2']
        normal_style = styles['Normal']
        small_style = styles['BodyText']
        
        # Elementos del documento
        elements = []
        
        # 1. Encabezado
        elements.append(Paragraph("Reporte de Citas Médicas", title_style))
        elements.append(Paragraph(
            f"Generado el: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 
            small_style
        ))
        elements.append(Spacer(1, 0.25*inch))
        
        # 2. Filtros aplicados
        elements.append(Paragraph("Filtros Aplicados:", subtitle_style))
        elements.append(Spacer(1, 0.1*inch))
        
        # Fechas
        fecha_inicio = datetime.strptime(filtros['fecha_inicio'], '%Y-%m-%d').strftime('%d/%m/%Y')
        fecha_fin = datetime.strptime(filtros['fecha_fin'], '%Y-%m-%d').strftime('%d/%m/%Y')
        elements.append(Paragraph(f"Período: {fecha_inicio} - {fecha_fin}", normal_style))
        
        # Filtros específicos
        if 'atleta_id' in filtros and filtros['atleta_id'] not in [None, "todos", ""]:
            for cita in citas:
                if str(cita.get('atleta_id')) == str(filtros['atleta_id']):
                    elements.append(Paragraph(
                        f"Atleta: {cita['atleta_nombre']}", 
                        normal_style
                    ))
                    break
        
        if 'area_id' in filtros and filtros['area_id'] not in [None, "todos", ""]:
            for cita in citas:
                if str(cita.get('area_id')) == str(filtros['area_id']):
                    elements.append(Paragraph(
                        f"Área: {cita['area_nombre']}", 
                        normal_style
                    ))
                    break
        
        if 'consultorio_id' in filtros and filtros['consultorio_id'] not in [None, "todos", ""]:
            for cita in citas:
                if str(cita.get('consultorio_id')) == str(filtros['consultorio_id']):
                    elements.append(Paragraph(
                        f"Consultorio: {cita['consultorio_nombre']}", 
                        normal_style
                    ))
                    break
        
        if 'profesional_id' in filtros and filtros['profesional_id'] not in [None, "todos", ""]:
            for cita in citas:
                if str(cita.get('profesional_salud_id')) == str(filtros['profesional_id']):
                    elements.append(Paragraph(
                        f"Profesional: {cita['profesional_nombre']} ({cita['profesional_especialidad']})", 
                        normal_style
                    ))
                    break
        
        elements.append(Spacer(1, 0.25*inch))
        
        # 3. Estadísticas resumidas
        elements.append(Paragraph("Resumen Estadístico:", subtitle_style))
        elements.append(Spacer(1, 0.1*inch))
        
        # Calcular estadísticas
        total = len(citas)
        estados = {
            'Completada': 0,
            'Pendiente': 0,
            'Cancelada': 0,
            'Confirmada': 0,
            'Desconocido': 0
        }
        
        for cita in citas:
            estado = cita.get('estado', 'Desconocido')
            estados[estado] += 1
        
        # Tabla de estadísticas
        stats_data = [
            ["Total", "Completadas", "Pendientes", "Canceladas", "Confirmadas"],
            [
                str(total),
                str(estados['Completada']),
                str(estados['Pendiente']),
                str(estados['Cancelada']),
                str(estados['Confirmada'])
            ]
        ]
        
        stats_table = Table(
            stats_data, 
            colWidths=[1.0*inch, 1.0*inch, 1.0*inch, 1.0*inch, 1.0*inch]
        )
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#EFF6FF')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#BFDBFE')),
        ]))
        
        elements.append(stats_table)
        elements.append(Spacer(1, 0.25*inch))
        
        # 4. Detalle de citas
        if citas:
            elements.append(Paragraph("Detalle de Citas:", subtitle_style))
            elements.append(Spacer(1, 0.1*inch))
            
            # Encabezados de tabla
            detail_headers = [
                "Fecha", "Hora", "Atleta", "Profesional", "Consultorio", "Estado"
            ]
            
            # Datos de la tabla
            detail_data = [detail_headers]
            
            for cita in citas:
                # Usar la estructura plana de las citas enriquecidas
                detail_data.append([
                    cita.get('fecha_formateada', 'No especificada'),
                    cita.get('hora_formateada', 'No especificada'),
                    cita.get('atleta_nombre', 'No especificado'),
                    cita.get('profesional_nombre', 'No especificado'),
                    cita.get('consultorio_nombre', 'No especificado'),
                    cita.get('estado', 'Desconocido')
                ])
            
            # Crear tabla
            detail_table = Table(
                detail_data, 
                colWidths=[0.8*inch, 0.7*inch, 1.5*inch, 1.5*inch, 1.2*inch, 0.9*inch],
                repeatRows=1
            )
            
            # Estilo de la tabla
            detail_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(detail_table)
        else:
            elements.append(Paragraph(
                "No se encontraron citas que cumplan con los criterios de filtrado.", 
                normal_style
            ))
            elements.append(Spacer(1, 0.5*inch))
        
        # 5. Pie de página
        elements.append(Spacer(1, 0.25*inch))
        elements.append(Paragraph(
            "Este reporte fue generado automáticamente por el Sistema de Gestión de Citas Médicas.",
            small_style
        ))
        
        # Construir el documento
        doc.build(elements)
        buffer.seek(0)
        
        return buffer