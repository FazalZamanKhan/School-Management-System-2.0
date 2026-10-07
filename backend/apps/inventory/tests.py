from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, StaffProfile
from apps.accounts.test_access import make_request, make_user
from apps.inventory import stock
from apps.inventory.models import Asset, StockLevel, StockMovement
from apps.inventory.views import AssetListView
from apps.schools.models import Campus, School


class AssetCampusIsolationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Inventory School")
        self.campus_a = Campus.objects.create(school=self.school, name="Campus A")
        self.campus_b = Campus.objects.create(school=self.school, name="Campus B")
        self.user = make_user("inventory-admin", Role.CAMPUS_ADMIN, self.school, campus=self.campus_a)
        StaffProfile.objects.create(
            user=self.user,
            employee_number="INV-001",
            first_name="Inventory",
            last_name="Admin",
            gender="male",
            primary_campus=self.campus_a,
        )

    def test_asset_list_includes_own_and_school_wide_assets_only(self):
        own = Asset.objects.create(name="Campus A asset", campus=self.campus_a)
        campus_b_asset = Asset.objects.create(name="Campus B asset", campus=self.campus_b)
        school_wide = Asset.objects.create(name="Shared asset")

        request = make_request(self.user)
        request.institution = self.school
        view = AssetListView()
        view.request = request

        qs = view.get_queryset()
        self.assertIn(own, qs)
        self.assertIn(school_wide, qs)
        self.assertNotIn(campus_b_asset, qs)


class StockEngineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Stock School")
        self.campus_a = Campus.objects.create(school=self.school, name="Campus A")
        self.campus_b = Campus.objects.create(school=self.school, name="Campus B")
        self.asset = Asset.objects.create(
            name="Ink",
            institution=self.school,
            unit="box",
            unit_cost=Decimal("10.00"),
        )

    def _move(self, **overrides):
        params = dict(
            asset=self.asset,
            campus=self.campus_a,
            institution=self.school,
        )
        params.update(overrides)
        return stock.apply_movement(**params)

    def test_receive_increases_quantity_and_syncs_asset(self):
        self._move(movement_type="receive", quantity=5, unit_cost=Decimal("20.00"))
        level = StockLevel.objects.get(campus=self.campus_a, asset=self.asset)
        self.assertEqual(level.quantity, 5)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.quantity, 5)

    def test_receive_updates_moving_average_cost(self):
        self._move(movement_type="receive", quantity=2, unit_cost=Decimal("10.00"))
        self._move(movement_type="receive", quantity=2, unit_cost=Decimal("30.00"))
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.unit_cost, Decimal("20.00"))

    def test_issue_reduces_quantity(self):
        self._move(movement_type="receive", quantity=5)
        self._move(movement_type="issue", quantity=3)
        level = StockLevel.objects.get(campus=self.campus_a, asset=self.asset)
        self.assertEqual(level.quantity, 2)
        self.assertEqual(
            StockMovement.objects.filter(movement_type="issue").count(),
            1,
        )

    def test_issue_insufficient_stock_rejected(self):
        self._move(movement_type="receive", quantity=2)
        with self.assertRaises(stock.StockError):
            self._move(movement_type="issue", quantity=5)
        level = StockLevel.objects.get(campus=self.campus_a, asset=self.asset)
        self.assertEqual(level.quantity, 2)

    def test_transfer_creates_symmetric_inbound(self):
        self._move(movement_type="receive", quantity=5)
        self._move(
            movement_type="transfer_out",
            quantity=3,
            destination_campus=self.campus_b,
        )
        level_a = StockLevel.objects.get(campus=self.campus_a, asset=self.asset)
        level_b = StockLevel.objects.get(campus=self.campus_b, asset=self.asset)
        self.assertEqual(level_a.quantity, 2)
        self.assertEqual(level_b.quantity, 3)
        self.assertEqual(
            StockMovement.objects.filter(movement_type="transfer_out").count(),
            1,
        )
        self.assertEqual(
            StockMovement.objects.filter(movement_type="transfer_in").count(),
            1,
        )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.quantity, 5)

    def test_transfer_requires_destination(self):
        with self.assertRaises(stock.StockError):
            self._move(movement_type="transfer_out", quantity=1)

    def test_transfer_same_campus_rejected(self):
        with self.assertRaises(stock.StockError):
            self._move(
                movement_type="transfer_out",
                quantity=1,
                destination_campus=self.campus_a,
            )

    def test_adjust_sets_absolute_quantity(self):
        self._move(movement_type="receive", quantity=5)
        self._move(movement_type="adjust", quantity=2)
        level = StockLevel.objects.get(campus=self.campus_a, asset=self.asset)
        self.assertEqual(level.quantity, 2)

    def test_zero_quantity_rejected(self):
        with self.assertRaises(stock.StockError):
            self._move(movement_type="receive", quantity=0)

    def test_low_and_out_flags(self):
        self._move(movement_type="receive", quantity=5)
        level = StockLevel.objects.get(campus=self.campus_a, asset=self.asset)
        level.minimum_stock = 5
        level.save()
        self.assertTrue(level.is_low)
        self.assertFalse(level.is_out)
        self._move(movement_type="adjust", quantity=0)
        level.refresh_from_db()
        self.assertTrue(level.is_out)


class StockLevelAPITests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Stock API School")
        self.campus_a = Campus.objects.create(school=self.school, name="Campus A")
        self.campus_b = Campus.objects.create(school=self.school, name="Campus B")
        self.user = make_user("stock-acc", Role.ACCOUNTANT, self.school)
        StaffProfile.objects.create(
            user=self.user,
            employee_number="ACC-001",
            first_name="Stock",
            last_name="Accountant",
            gender="female",
            primary_campus=self.campus_a,
        )
        self.asset = Asset.objects.create(
            name="Paper",
            institution=self.school,
            unit="ream",
            unit_cost=Decimal("5.00"),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_stock_level_sets_institution(self):
        response = self.client.post(
            "/api/inventory/stock/levels/",
            {
                "campus": self.campus_a.pk,
                "asset": self.asset.pk,
                "minimum_stock": 3,
                "location": "Store Room",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        level = StockLevel.objects.get(campus=self.campus_a, asset=self.asset)
        self.assertEqual(level.quantity, 0)
        self.assertEqual(level.institution, self.school)
        self.assertEqual(level.minimum_stock, 3)

    def test_list_stock_levels_is_campus_scoped(self):
        StockLevel.objects.create(
            campus=self.campus_b,
            asset=self.asset,
            quantity=9,
        )
        response = self.client.get("/api/inventory/stock/levels/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_quantity_is_read_only_on_update(self):
        stock.apply_movement(
            asset=self.asset,
            campus=self.campus_a,
            movement_type="receive",
            quantity=4,
            institution=self.school,
        )
        level = StockLevel.objects.get(campus=self.campus_a, asset=self.asset)
        response = self.client.patch(
            f"/api/inventory/stock/levels/{level.pk}/",
            {"quantity": 999, "minimum_stock": 2},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        level.refresh_from_db()
        self.assertEqual(level.quantity, 4)
        self.assertEqual(level.minimum_stock, 2)


class StockMovementAPITests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Movement API School")
        self.campus_a = Campus.objects.create(school=self.school, name="Campus A")
        self.user = make_user("move-acc", Role.ACCOUNTANT, self.school)
        StaffProfile.objects.create(
            user=self.user,
            employee_number="ACC-002",
            first_name="Move",
            last_name="Accountant",
            gender="male",
            primary_campus=self.campus_a,
        )
        self.asset = Asset.objects.create(
            name="Chalk",
            institution=self.school,
            unit="box",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_receive_via_api(self):
        response = self.client.post(
            "/api/inventory/stock/movements/",
            {
                "asset": self.asset.pk,
                "campus": self.campus_a.pk,
                "movement_type": "receive",
                "quantity": 10,
                "unit_cost": "6.50",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["movement_type"], "receive")
        self.assertEqual(response.data["created_by"], self.user.pk)
        level = StockLevel.objects.get(campus=self.campus_a, asset=self.asset)
        self.assertEqual(level.quantity, 10)

    def test_insufficient_stock_returns_400(self):
        response = self.client.post(
            "/api/inventory/stock/movements/",
            {
                "asset": self.asset.pk,
                "campus": self.campus_a.pk,
                "movement_type": "issue",
                "quantity": 3,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zero_quantity_returns_400(self):
        response = self.client.post(
            "/api/inventory/stock/movements/",
            {
                "asset": self.asset.pk,
                "campus": self.campus_a.pk,
                "movement_type": "receive",
                "quantity": 0,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_transfer_via_api(self):
        campus_b = Campus.objects.create(school=self.school, name="Campus B")
        stock.apply_movement(
            asset=self.asset,
            campus=self.campus_a,
            movement_type="receive",
            quantity=5,
            institution=self.school,
        )
        response = self.client.post(
            "/api/inventory/stock/movements/",
            {
                "asset": self.asset.pk,
                "campus": self.campus_a.pk,
                "destination_campus": campus_b.pk,
                "movement_type": "transfer_out",
                "quantity": 2,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            StockMovement.objects.filter(movement_type="transfer_in").count(),
            1,
        )

    def test_non_accountant_forbidden(self):
        teacher = make_user("teach", Role.TEACHER, self.school)
        StaffProfile.objects.create(
            user=teacher,
            employee_number="TCH-001",
            first_name="Tea",
            last_name="Cher",
            gender="female",
            primary_campus=self.campus_a,
        )
        self.client.force_authenticate(teacher)
        response = self.client.get("/api/inventory/stock/movements/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class StockSummaryAPITests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Summary API School")
        self.campus_a = Campus.objects.create(school=self.school, name="Campus A")
        self.user = make_user("sum-acc", Role.ACCOUNTANT, self.school)
        StaffProfile.objects.create(
            user=self.user,
            employee_number="ACC-003",
            first_name="Sum",
            last_name="Accountant",
            gender="male",
            primary_campus=self.campus_a,
        )
        self.asset_a = Asset.objects.create(
            name="Glue",
            institution=self.school,
            unit_cost=Decimal("2.00"),
        )
        self.asset_b = Asset.objects.create(
            name="Ink",
            institution=self.school,
            unit_cost=Decimal("10.00"),
        )
        stock.apply_movement(
            asset=self.asset_a,
            campus=self.campus_a,
            movement_type="receive",
            quantity=10,
            unit_cost=Decimal("2.00"),
            institution=self.school,
        )
        stock.apply_movement(
            asset=self.asset_b,
            campus=self.campus_a,
            movement_type="receive",
            quantity=2,
            unit_cost=Decimal("10.00"),
            institution=self.school,
        )
        StockLevel.objects.filter(asset=self.asset_a, campus=self.campus_a).update(
            minimum_stock=15
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_summary_counts_and_value(self):
        response = self.client.get("/api/inventory/stock/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data["stock_levels"], 2)
        self.assertEqual(data["total_quantity"], 12)
        self.assertEqual(data["total_value"], 40)
        self.assertEqual(data["low_stock"], 1)
        self.assertEqual(data["out_of_stock"], 0)
