from rest_framework import serializers

class CitaSerializer(serializers.Serializer):
    estado = serializers.CharField()
    creado_el = serializers.DateTimeField()
    # Agrega otros campos que necesites