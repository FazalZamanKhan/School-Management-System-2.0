from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import (
    apply_campus_scope,
    assert_campus_allowed,
    get_institution,
)
from apps.accounts.permissions import IsAccountantRole
from apps.schools.models import Campus

from . import stock
from .models import (
    Asset,
    AssetAssignment,
    AssetCategory,
    MaintenanceRecord,
    StockLevel,
    StockMovement,
    Supplier,
)
from .serializers import (
    AssetAssignmentSerializer,
    AssetCategorySerializer,
    AssetSerializer,
    MaintenanceRecordSerializer,
    StockLevelCreateSerializer,
    StockLevelSerializer,
    StockMovementSerializer,
    SupplierSerializer,
)


def _active_institution(request):
    """Active institution from the middleware or the user's primary one."""
    institution = get_institution(request)
    if institution is not None:
        return institution
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return getattr(user, "primary_institution", None)
    return None


def _assert_campus_allowed(user, campus):
    """Campus access assertion that accepts either an id or a model instance."""
    if campus is None:
        return
    assert_campus_allowed(user, getattr(campus, "pk", campus))


class AssetCategoryListView(generics.ListCreateAPIView):
    serializer_class = AssetCategorySerializer
    permission_classes = [IsAccountantRole]

    def get_queryset(self):
        # School-wide reference data: institution-scoped only, no campus split.
        return apply_campus_scope(AssetCategory.objects.all(), self.request, None)

    def perform_create(self, serializer):
        serializer.save(institution=_active_institution(self.request))


class AssetCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AssetCategorySerializer
    permission_classes = [IsAccountantRole]

    def get_queryset(self):
        return apply_campus_scope(AssetCategory.objects.all(), self.request, None)


class SupplierListView(generics.ListCreateAPIView):
    serializer_class = SupplierSerializer
    permission_classes = [IsAccountantRole]

    def get_queryset(self):
        return apply_campus_scope(Supplier.objects.all(), self.request, None)

    def perform_create(self, serializer):
        serializer.save(institution=_active_institution(self.request))


class SupplierDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SupplierSerializer
    permission_classes = [IsAccountantRole]

    def get_queryset(self):
        return apply_campus_scope(Supplier.objects.all(), self.request, None)


class AssetListView(generics.ListCreateAPIView):
    serializer_class = AssetSerializer
    permission_classes = [IsAccountantRole]

    def get_queryset(self):
        queryset = apply_campus_scope(
            Asset.objects.select_related("campus", "category", "supplier").prefetch_related("stock_levels"),
            self.request,
            "campus_id",
        )

        search = self.request.query_params.get("q")

        if search:
            queryset = queryset.filter(name__icontains=search)

        category = self.request.query_params.get("category")

        if category:
            queryset = queryset.filter(category_id=category)

        status_filter = self.request.query_params.get("status")

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    def perform_create(self, serializer):
        _assert_campus_allowed(self.request.user, serializer.validated_data.get("campus"))
        serializer.save(institution=_active_institution(self.request))


class AssetDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AssetSerializer
    permission_classes = [IsAccountantRole]
    def get_queryset(self):
        return apply_campus_scope(
            Asset.objects.prefetch_related("stock_levels"),
            self.request,
            "campus_id",
        )

    def perform_update(self, serializer):
        _assert_campus_allowed(self.request.user, serializer.validated_data.get("campus", serializer.instance.campus))
        serializer.save()


class AssetAssignmentListView(generics.ListCreateAPIView):
    serializer_class = AssetAssignmentSerializer
    permission_classes = [IsAccountantRole]
    def get_queryset(self):
        return apply_campus_scope(
            AssetAssignment.objects.select_related("asset"),
            self.request,
            "asset__campus_id",
        )

    def perform_create(self, serializer):
        asset = serializer.validated_data["asset"]
        if not self.get_queryset().filter(asset=asset).exists():
            raise PermissionDenied("The asset is outside your campus scope.")
        serializer.save()


class AssetAssignmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AssetAssignmentSerializer
    permission_classes = [IsAccountantRole]
    def get_queryset(self):
        return apply_campus_scope(
            AssetAssignment.objects.all(),
            self.request,
            "asset__campus_id",
        )

    def perform_update(self, serializer):
        if not self.get_queryset().filter(
            asset=serializer.validated_data.get("asset", serializer.instance.asset),
        ).exists():
            raise PermissionDenied("The asset is outside your campus scope.")
        serializer.save()


class MaintenanceRecordListView(generics.ListCreateAPIView):
    serializer_class = MaintenanceRecordSerializer
    permission_classes = [IsAccountantRole]
    def get_queryset(self):
        return apply_campus_scope(
            MaintenanceRecord.objects.select_related("asset"),
            self.request,
            "asset__campus_id",
        )

    def perform_create(self, serializer):
        asset = serializer.validated_data["asset"]
        if not self.get_queryset().filter(asset=asset).exists():
            raise PermissionDenied("The asset is outside your campus scope.")
        serializer.save()


class MaintenanceRecordDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MaintenanceRecordSerializer
    permission_classes = [IsAccountantRole]
    def get_queryset(self):
        return apply_campus_scope(
            MaintenanceRecord.objects.all(),
            self.request,
            "asset__campus_id",
        )

    def perform_update(self, serializer):
        if not self.get_queryset().filter(
            asset=serializer.validated_data.get("asset", serializer.instance.asset),
        ).exists():
            raise PermissionDenied("The asset is outside your campus scope.")
        serializer.save()


class StockLevelListView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return StockLevelCreateSerializer
        return StockLevelSerializer

    def get_queryset(self):
        return apply_campus_scope(
            StockLevel.objects.select_related("asset", "campus"),
            self.request,
            "campus_id",
        )

    def perform_create(self, serializer):
        _assert_campus_allowed(self.request.user, serializer.validated_data.get("campus"))
        serializer.save(institution=_active_institution(self.request))


class StockLevelDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = StockLevelSerializer
    permission_classes = [IsAccountantRole]

    def get_queryset(self):
        return apply_campus_scope(
            StockLevel.objects.select_related("asset", "campus"),
            self.request,
            "campus_id",
        )

    def perform_update(self, serializer):
        assert_campus_allowed(self.request.user, serializer.instance.campus_id)
        # Quantity is append-only via the movement ledger — never edited here.
        serializer.validated_data.pop("quantity", None)
        serializer.save()


class StockMovementListView(generics.ListCreateAPIView):
    serializer_class = StockMovementSerializer
    permission_classes = [IsAccountantRole]

    def get_queryset(self):
        return apply_campus_scope(
            StockMovement.objects.select_related(
                "asset", "campus", "destination_campus", "created_by"
            ),
            self.request,
            "campus_id",
        )

    def create(self, request, *args, **kwargs):
        data = request.data

        asset = get_object_or_404(
            apply_campus_scope(Asset.objects.all(), self.request, "campus_id"),
            pk=data.get("asset"),
        )
        campus = get_object_or_404(Campus, pk=data.get("campus"))
        assert_campus_allowed(self.request.user, campus.pk)

        destination = None
        if data.get("destination_campus"):
            destination = get_object_or_404(Campus, pk=data.get("destination_campus"))

        try:
            movement = stock.apply_movement(
                asset=asset,
                campus=campus,
                movement_type=data.get("movement_type", ""),
                quantity=data.get("quantity", 0),
                institution=_active_institution(request),
                unit_cost=data.get("unit_cost"),
                destination_campus=destination,
                reference=data.get("reference", ""),
                notes=data.get("notes", ""),
                created_by=request.user,
            )
        except stock.StockError as exc:
            raise ValidationError(str(exc))

        serializer = self.get_serializer(movement)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class StockSummaryView(APIView):
    permission_classes = [IsAccountantRole]

    def get(self, request):
        levels = apply_campus_scope(
            StockLevel.objects.select_related("asset", "campus", "asset__category"),
            request,
            "campus_id",
        )

        movements = apply_campus_scope(
            StockMovement.objects.select_related("asset", "campus"),
            request,
            "campus_id",
        ).order_by("-created_at")[:10]

        total_value = 0
        total_quantity = 0
        low_stock = 0
        out_of_stock = 0

        for level in levels:
            total_quantity += level.quantity
            total_value += level.quantity * (level.asset.unit_cost or 0)
            if level.is_out:
                out_of_stock += 1
            elif level.is_low:
                low_stock += 1

        return Response(
            {
                "stock_levels": len(list(levels)),
                "total_quantity": total_quantity,
                "total_value": total_value,
                "low_stock": low_stock,
                "out_of_stock": out_of_stock,
                "recent_movements": StockMovementSerializer(movements, many=True).data,
            }
        )
