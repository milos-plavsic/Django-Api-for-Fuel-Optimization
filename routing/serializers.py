from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.JSONField()
    finish = serializers.JSONField()
    route_count = serializers.IntegerField(min_value=1, max_value=5, required=False)

    def validate(self, attrs):
        if attrs["start"] == attrs["finish"]:
            raise serializers.ValidationError("Start and finish must be different.")
        return attrs
