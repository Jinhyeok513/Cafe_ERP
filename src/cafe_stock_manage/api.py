"""FastAPI application for cafe inventory operations."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from .repository import InventoryRepository


class HealthResponse(BaseModel):
    status: str
    database_connected: bool
    scenario: str | None
    dataset_sha256: str | None
    imported_at: datetime | None


class InventoryItem(BaseModel):
    product_id: str
    product_name: str
    category: str
    inventory_unit: str
    current_quantity: Decimal
    reorder_point_inventory_qty: Decimal | None
    stock_status: str


class MovementItem(BaseModel):
    movement_id: int
    movement_source_key: str | None
    product_id: str
    product_name: str
    inventory_unit: str
    movement_datetime: datetime
    movement_type: str
    quantity_change: Decimal
    running_quantity: Decimal
    source_type: str
    source_id: str
    reason_code: str | None
    recorded_by: str


class DiscrepancyItem(BaseModel):
    receipt_source_key: str | None
    received_datetime: datetime
    supplier_id: str
    receipt_item_source_key: str | None
    product_id: str
    product_name: str
    order_unit: str
    invoice_quantity: Decimal
    received_quantity: Decimal
    damaged_quantity: Decimal
    accepted_quantity: Decimal
    wrong_item_flag: bool
    discrepancy_reason: str


class StocktakeAccuracyItem(BaseModel):
    stocktake_id: int
    source_key: str | None
    stocktake_date: date
    products_counted: int
    products_matched: int
    products_with_variance: int
    inventory_accuracy_percent: Decimal
    absolute_variance_quantity: Decimal


class KpiResponse(BaseModel):
    active_products: int
    reorder_due_products: int
    negative_stock_products: int
    receipt_lines: int
    discrepancy_lines: int
    receiving_accuracy_percent: float | None
    waste_events: int
    movement_count: int
    latest_inventory_accuracy_percent: Decimal | None
    data_quality_issue_count: int


class ReorderRecommendationItem(BaseModel):
    product_id: str
    product_name: str
    category: str
    supplier_id: str
    supplier_name: str
    inventory_unit: str
    order_unit: str
    pack_size: Decimal
    current_quantity: Decimal
    on_order_quantity: Decimal
    average_daily_usage: Decimal
    lead_time_days: int
    safety_stock_inventory_qty: Decimal
    reorder_point_inventory_qty: Decimal | None
    projected_on_delivery: Decimal
    target_inventory_quantity: Decimal
    recommended_order_quantity: Decimal
    expected_delivery_date: date
    urgency: str


class DraftPurchaseOrderItemRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=80)
    ordered_quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=4)


class DraftPurchaseOrderRequest(BaseModel):
    supplier_id: str = Field(min_length=1, max_length=80)
    expected_delivery_date: date
    ordered_by: str = Field(min_length=1, max_length=120)
    items: list[DraftPurchaseOrderItemRequest] = Field(min_length=1, max_length=100)


class DraftPurchaseOrderItemResponse(BaseModel):
    po_item_id: int
    product_id: str
    ordered_quantity: Decimal
    order_unit: str


class DraftPurchaseOrderResponse(BaseModel):
    po_id: int
    source_key: str
    supplier_id: str
    order_datetime: datetime
    expected_delivery_date: date
    order_status: str
    ordered_by: str
    items: list[DraftPurchaseOrderItemResponse]


class PosDayItem(BaseModel):
    sale_date: date
    menu_lines: int
    items_sold: int
    gross_revenue: Decimal
    posted_lines: int
    pending_lines: int
    missing_recipe_lines: int


class PosUsageItem(BaseModel):
    sale_date: date
    product_id: str
    product_name: str
    category: str
    inventory_unit: str
    usage_quantity: Decimal
    contributing_menu_items: int


class MenuItemResponse(BaseModel):
    menu_item_id: str
    menu_item_name: str
    menu_category: str
    selling_price: Decimal
    recipe_ingredient_count: int


class PosImportRow(BaseModel):
    sale_date: date
    menu_item_id: str = Field(min_length=1, max_length=80)
    quantity_sold: int = Field(gt=0, le=100000)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class PosImportRequest(BaseModel):
    recorded_by: str = Field(min_length=1, max_length=120)
    rows: list[PosImportRow] = Field(min_length=1, max_length=5000)


class ImportedPosSale(BaseModel):
    pos_sale_id: int
    source_key: str
    sale_date: date
    menu_item_id: str
    quantity_sold: int
    unit_price: Decimal
    gross_revenue: Decimal


class PosImportResponse(BaseModel):
    received_rows: int
    inserted_rows: int
    skipped_rows: int
    movement_count: int
    sales: list[ImportedPosSale]


class SalesForecastItem(BaseModel):
    forecast_date: date
    weekday_name: str
    forecast_items_sold: int
    forecast_revenue: Decimal
    revenue_lower_bound: Decimal
    revenue_upper_bound: Decimal
    trend_factor: Decimal
    forecast_method: str


class InventoryForecastItem(BaseModel):
    product_id: str
    product_name: str
    category: str
    inventory_unit: str
    supplier_id: str
    supplier_name: str
    lead_time_days: int
    current_quantity: Decimal
    on_order_quantity: Decimal
    average_daily_depletion: Decimal
    days_of_cover: Decimal | None
    projected_quantity_7_days: Decimal
    projected_quantity_14_days: Decimal
    expected_stockout_date: date | None
    risk_status: str


def get_repository(request: Request) -> InventoryRepository:
    return request.app.state.repository


RepositoryDependency = Annotated[InventoryRepository, Depends(get_repository)]


def create_app(repository: InventoryRepository | Any | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if repository is not None:
            app.state.repository = repository
            yield
            return

        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required to start the API")
        pool = ConnectionPool(
            database_url,
            min_size=1,
            max_size=int(os.environ.get("DATABASE_POOL_MAX_SIZE", "5")),
            open=False,
        )
        pool.open(wait=True)
        app.state.repository = InventoryRepository(pool)
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(
        title="Cafe Stock Manage API",
        version="0.1.0",
        description="Inventory, receiving, stocktake and replenishment operations API.",
        lifespan=lifespan,
    )

    @app.exception_handler(psycopg.Error)
    async def database_error_handler(
        request: Request,
        error: psycopg.Error,
    ) -> JSONResponse:
        del request, error
        return JSONResponse(
            status_code=503,
            content={"detail": "Inventory database is temporarily unavailable."},
        )

    @app.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health(repo: RepositoryDependency) -> dict[str, Any]:
        return {"status": "ok", **repo.health()}

    @app.get("/api/kpis", response_model=KpiResponse, tags=["dashboard"])
    def kpis(repo: RepositoryDependency) -> dict[str, Any]:
        return repo.kpis()

    @app.get(
        "/api/reorder/recommendations",
        response_model=list[ReorderRecommendationItem],
        tags=["reorder"],
    )
    def reorder_recommendations(
        repo: RepositoryDependency,
        urgency: Literal["CRITICAL", "ORDER_NOW", "REVIEW", "PLANNED"]
        | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        return repo.reorder_recommendations(urgency)

    @app.post(
        "/api/purchase-orders/drafts",
        response_model=DraftPurchaseOrderResponse,
        status_code=201,
        tags=["reorder"],
    )
    def create_draft_purchase_order(
        request: DraftPurchaseOrderRequest,
        repo: RepositoryDependency,
    ) -> dict[str, Any]:
        try:
            return repo.create_draft_purchase_order(
                request.supplier_id,
                request.expected_delivery_date,
                request.ordered_by,
                [item.model_dump() for item in request.items],
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get(
        "/api/pos/days",
        response_model=list[PosDayItem],
        tags=["pos-usage"],
    )
    def pos_days(
        repo: RepositoryDependency,
        limit: int = Query(default=30, ge=1, le=366),
    ) -> list[dict[str, Any]]:
        return repo.pos_days(limit)

    @app.get(
        "/api/pos/usage",
        response_model=list[PosUsageItem],
        tags=["pos-usage"],
    )
    def pos_usage(
        repo: RepositoryDependency,
        sale_date: date | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        return repo.pos_usage(sale_date)

    @app.get(
        "/api/pos/menu-items",
        response_model=list[MenuItemResponse],
        tags=["pos-usage"],
    )
    def menu_items(repo: RepositoryDependency) -> list[dict[str, Any]]:
        return repo.menu_items()

    @app.post(
        "/api/pos/import",
        response_model=PosImportResponse,
        status_code=201,
        tags=["pos-usage"],
    )
    def import_pos_sales(
        request: PosImportRequest,
        repo: RepositoryDependency,
    ) -> dict[str, Any]:
        try:
            return repo.import_pos_sales(
                [row.model_dump() for row in request.rows],
                request.recorded_by,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get(
        "/api/forecast/sales",
        response_model=list[SalesForecastItem],
        tags=["forecast"],
    )
    def sales_forecast(
        repo: RepositoryDependency,
        days: int = Query(default=14, ge=1, le=30),
    ) -> list[dict[str, Any]]:
        return repo.sales_forecast(days)

    @app.get(
        "/api/forecast/inventory",
        response_model=list[InventoryForecastItem],
        tags=["forecast"],
    )
    def inventory_forecast(repo: RepositoryDependency) -> list[dict[str, Any]]:
        return repo.inventory_forecast()

    @app.get("/api/inventory", response_model=list[InventoryItem], tags=["inventory"])
    def inventory(
        repo: RepositoryDependency,
        status: Literal[
            "NEGATIVE_STOCK", "REORDER_DUE", "IN_STOCK", "NO_REORDER_POINT"
        ]
        | None = Query(default=None),
        search: str | None = Query(default=None, min_length=1, max_length=80),
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        return repo.inventory(status, search, limit, offset)

    @app.get(
        "/api/inventory/{product_id}/movements",
        response_model=list[MovementItem],
        tags=["inventory"],
    )
    def movements(
        product_id: str,
        repo: RepositoryDependency,
        movement_type: Literal["RECEIVE", "USE", "WASTE", "ADJUSTMENT"]
        | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        if repo.inventory_product(product_id) is None:
            raise HTTPException(status_code=404, detail="Product not found")
        return repo.movements(product_id, movement_type, limit)

    @app.get(
        "/api/discrepancies",
        response_model=list[DiscrepancyItem],
        tags=["receiving"],
    )
    def discrepancies(
        repo: RepositoryDependency,
        reason: Literal[
            "SHORT_DELIVERY", "MISSING_ITEM", "WRONG_PRODUCT", "DAMAGED", "OTHER"
        ]
        | None = Query(default=None),
        supplier_id: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        return repo.discrepancies(reason, supplier_id, limit, offset)

    @app.get(
        "/api/stocktakes/accuracy",
        response_model=list[StocktakeAccuracyItem],
        tags=["stocktakes"],
    )
    def stocktake_accuracy(
        repo: RepositoryDependency,
        date_from: date | None = Query(default=None),
        date_to: date | None = Query(default=None),
        limit: int = Query(default=90, ge=1, le=366),
    ) -> list[dict[str, Any]]:
        if date_from and date_to and date_from > date_to:
            raise HTTPException(
                status_code=422,
                detail="date_from must be on or before date_to",
            )
        return repo.stocktake_accuracy(date_from, date_to, limit)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "cafe_stock_manage.api:app",
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
        reload=False,
    )
