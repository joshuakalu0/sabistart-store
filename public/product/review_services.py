from __future__ import annotations

from decimal import Decimal

from django.db.models import Avg, Count, Q
from django.utils import timezone

from public.cart.models import Order, OrderItem
from public.product.models import Product, ProductReview


APPROVED_STATUSES = {
    Order.OrderStatus.CONFIRMED,
    Order.OrderStatus.PROCESSING,
    Order.OrderStatus.COMPLETED,
    Order.OrderStatus.PARTIALLY_RETURNED,
    Order.OrderStatus.RETURNED,
}


def refresh_product_review_stats(product: Product) -> Product:
    aggregates = product.reviews.filter(status=ProductReview.Status.APPROVED).aggregate(
        average=Avg("rating"),
        review_count=Count("id"),
    )
    average = Decimal(str(aggregates.get("average") or 0)).quantize(Decimal("0.01"))
    review_count = int(aggregates.get("review_count") or 0)
    rating_count = review_count
    Product.objects.filter(pk=product.pk).update(
        average_rating=average,
        review_count=review_count,
        rating_count=rating_count,
    )
    product.average_rating = average
    product.review_count = review_count
    product.rating_count = rating_count
    return product


def get_verified_purchase_order_item(product: Product, customer):
    if customer is None:
        return None
    return (
        OrderItem.objects.select_related("order", "variant")
        .filter(
            order__customer=customer,
            order__status__in=APPROVED_STATUSES,
        )
        .filter(
            Q(product_id_snapshot=product.id)
            | Q(variant__product=product)
        )
        .order_by("-order__placed_at", "-created_at")
        .first()
    )


def serialize_product_review(review: ProductReview) -> dict:
    display_name = "Anonymous"
    if review.user_id and getattr(review.user, "get_full_name", None):
        display_name = review.user.get_full_name() or review.user.email or "Verified customer"
    elif review.customer_id and getattr(review.customer, "display_name", None):
        display_name = review.customer.display_name
    submitted_at = review.published_at or review.approved_at or review.created_at
    return {
        "id": str(review.id),
        "title": review.title,
        "body": review.body,
        "rating": int(review.rating or 0),
        "status": review.status,
        "status_label": review.get_status_display(),
        "verified_purchase": bool(review.is_verified_purchase),
        "display_name": display_name,
        "submitted_at": submitted_at,
        "submitted_at_iso": submitted_at.isoformat() if submitted_at else "",
        "helpful_count": int(review.helpful_votes or 0),
        "unhelpful_count": int(review.unhelpful_votes or 0),
        "merchant_response": review.response_body,
        "merchant_response_at": review.responded_at,
        "merchant_response_title": review.response_title,
        "order_number": review.order_number,
    }


def get_product_review_payload(product: Product, *, customer=None) -> dict:
    approved_reviews = list(
        product.reviews.select_related("user", "customer")
        .filter(status=ProductReview.Status.APPROVED)
        .order_by("-published_at", "-approved_at", "-created_at")
    )
    existing_review = None
    if customer is not None:
        existing_review = (
            product.reviews.select_related("user", "customer")
            .filter(customer=customer)
            .exclude(status=ProductReview.Status.REJECTED)
            .order_by("-created_at")
            .first()
        )
    verified_item = get_verified_purchase_order_item(product, customer)
    return {
        "average_rating": Decimal(str(product.average_rating or 0)).quantize(Decimal("0.01")),
        "review_count": int(product.review_count or 0),
        "approved_reviews": [serialize_product_review(review) for review in approved_reviews],
        "existing_review": serialize_product_review(existing_review) if existing_review else None,
        "can_submit": bool(product.enable_reviews),
        "is_verified_purchaser": verified_item is not None,
        "verified_order_number": getattr(getattr(verified_item, "order", None), "order_number", ""),
    }


def submit_product_review(*, product: Product, customer, user, title: str, body: str, rating: int) -> ProductReview:
    verified_item = get_verified_purchase_order_item(product, customer)
    status = ProductReview.Status.PENDING
    review = (
        product.reviews.filter(customer=customer)
        .exclude(status=ProductReview.Status.REJECTED)
        .order_by("-created_at")
        .first()
    )
    if review is None:
        review = ProductReview(product=product, customer=customer, user=user)
    review.title = (title or "").strip()
    review.body = (body or "").strip()
    review.rating = int(rating)
    review.status = status
    review.is_verified_purchase = verified_item is not None
    review.order_id = getattr(getattr(verified_item, "order", None), "id", None)
    review.order_number = getattr(getattr(verified_item, "order", None), "order_number", "")
    review.order_item_id = getattr(verified_item, "id", None)
    review.metadata = dict(review.metadata or {})
    review.metadata["submitted_at"] = timezone.now().isoformat()
    review.published_at = None
    review.approved_at = None
    review.rejected_at = None
    review.save()
    return review
