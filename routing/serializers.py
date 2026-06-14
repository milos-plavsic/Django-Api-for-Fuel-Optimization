from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.JSONField()
    finish = serializers.JSONField()

    def validate(self, attrs):
        if attrs["start"] == attrs["finish"]:
            raise serializers.ValidationError("Start and finish must be different.")
        return attrs
