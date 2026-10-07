from rest_framework import serializers

from .models import (
    Asset,
    AssetAssignment,
    AssetCategory,
    MaintenanceRecord,
    StockLevel,
    StockMovement,
    Supplier,
)


class AssetCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetCategory
        fields = ["id", "name", "description"]


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "contact_person",
            "phone",
            "email",
            "address",
        ]


class StockLevelSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(
        source="asset.name",
        read_only=True,
    )
    asset_code = serializers.CharField(
        source="asset.code",
        read_only=True,
    )
    unit = serializers.CharField(
        source="asset.unit",
        read_only=True,
    )
    is_low = serializers.BooleanField(read_only=True)
    is_out = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockLevel
        fields = [
            "id",
            "institution",
            "campus",
            "asset",
            "asset_name",
            "asset_code",
            "unit",
            "quantity",
            "minimum_stock",
            "location",
            "is_low",
            "is_out",
            "updated_at",
        ]
        read_only_fields = ["institution", "quantity", "updated_at"]


class StockLevelCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockLevel
        fields = [
            "id",
            "campus",
            "asset",
            "minimum_stock",
            "location",
        ]


class StockMovementSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(
        source="asset.name",
        read_only=True,
    )
    asset_code = serializers.CharField(
        source="asset.code",
        read_only=True,
    )
    movement_type_display = serializers.CharField(
        source="get_movement_type_display",
        read_only=True,
    )
    destination_campus_name = serializers.CharField(
        source="destination_campus.name",
        read_only=True,
        default="",
    )
    created_by_name = serializers.CharField(
        source="created_by.get_full_name",
        read_only=True,
        default="",
    )

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "institution",
            "campus",
            "asset",
            "asset_name",
            "asset_code",
            "movement_type",
            "movement_type_display",
            "quantity",
            "unit_cost",
            "destination_campus",
            "destination_campus_name",
            "reference",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = ["institution", "created_by", "created_at"]


class AssetSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(
        source="campus.name",
        read_only=True,
        default="",
    )
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
        default="",
    )
    supplier_name = serializers.CharField(
        source="supplier.name",
        read_only=True,
        default="",
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    total_value = serializers.DecimalField(
        read_only=True,
        max_digits=12,
        decimal_places=2,
    )
    stock_levels = StockLevelSerializer(many=True, read_only=True)

    class Meta:
        model = Asset
        fields = [
            "id",
            "name",
            "campus",
            "campus_name",
            "code",
            "category",
            "category_name",
            "supplier",
            "supplier_name",
            "quantity",
            "unit",
            "unit_cost",
            "total_value",
            "stock_levels",
            "purchase_date",
            "location",
            "status",
            "status_display",
            "notes",
        ]

    def validate_unit_cost(self, value):
        if value < 0:
            raise serializers.ValidationError("Unit cost must be zero or greater.")
        return value


class AssetAssignmentSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(
        source="asset.name",
        read_only=True,
    )
    assignee_type_display = serializers.CharField(
        source="get_assignee_type_display",
        read_only=True,
    )

    class Meta:
        model = AssetAssignment
        fields = [
            "id",
            "asset",
            "asset_name",
            "assignee_type",
            "assignee_type_display",
            "assignee_name",
            "assigned_to",
            "quantity",
            "assigned_date",
            "return_date",
            "notes",
        ]


class MaintenanceRecordSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(
        source="asset.name",
        read_only=True,
    )

    class Meta:
        model = MaintenanceRecord
        fields = [
            "id",
            "asset",
            "asset_name",
            "date",
            "cost",
            "description",
            "performed_by",
            "status",
        ]
