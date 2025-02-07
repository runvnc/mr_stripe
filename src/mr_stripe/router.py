from fastapi import APIRouter, Request, HTTPException
from .mod import process_payment, product_checkout, subscription_checkout
import stripe
import os
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

class ProductCheckoutRequest(BaseModel):
    amount: Decimal
    product_name: str
    currency: str = 'USD'
    quantity: int = 1
    metadata: Optional[dict] = None

class SubscriptionCheckoutRequest(BaseModel):
    plan_name: str
    amount: Decimal
    interval: str  # 'month' or 'year'
    currency: str = 'USD'
    metadata: Optional[dict] = None

router = APIRouter()
stripe.api_key = os.getenv("STRIPE_API_KEY")

@router.post("/stripe/webhook")
async def handle_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, 
            sig_header,
            os.getenv("STRIPE_WEBHOOK_SECRET")
        )
        await process_payment(event)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/stripe/checkout/product")
async def handle_product_checkout(request: Request, checkout_data: ProductCheckoutRequest):
    user = request.state.user
    try:
        url = await product_checkout(
            user_id=user.id,
            amount=checkout_data.amount,
            product_name=checkout_data.product_name,
            currency=checkout_data.currency,
            quantity=checkout_data.quantity,
            metadata=checkout_data.metadata
        )
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/stripe/checkout/subscription")
async def handle_subscription_checkout(request: Request, checkout_data: SubscriptionCheckoutRequest):
    user = request.state.user
    try:
        url = await subscription_checkout(
            user_id=user.id,
            plan_name=checkout_data.plan_name,
            amount=checkout_data.amount,
            interval=checkout_data.interval,
            currency=checkout_data.currency,
            metadata=checkout_data.metadata
        )
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
