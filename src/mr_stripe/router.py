from fastapi import APIRouter, Request, HTTPException
from .mod import process_payment, product_checkout, subscription_checkout, normalize_subscription_event
import stripe
import os
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel
from lib.providers.services import service_manager
from loguru import logger

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
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

@router.post("/stripe/webhook")
async def handle_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        # Verify and parse the webhook
        event = stripe.Webhook.construct_event(
            payload, 
            sig_header,
            os.getenv("STRIPE_WEBHOOK_SECRET")
        )
        
        event_type = event['type']
        logger.info(f"Processing Stripe webhook event: {event_type}")
        
        # Process regular payment events
        await process_payment(event)
        
        # For subscription-related events, normalize and forward to subscription plugin
        if event_type in ['checkout.session.completed', 'invoice.paid', 
                         'customer.subscription.updated', 'customer.subscription.deleted']:
            
            # Normalize the event to subscription format
            normalized_event = await normalize_subscription_event(event)
            
            # Forward to subscription plugin's event handler
            try:
                result = await service_manager.process_subscription_event({
                    'provider': 'stripe',
                    'normalized_event': normalized_event,
                    'original_event': event
                })
                logger.info(f"Subscription event processed: {result}")
            except Exception as e:
                logger.error(f"Error forwarding to subscription plugin: {e}")
                # Continue processing - don't fail the webhook
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        # Always return 200 to Stripe even on error
        return {"status": "error", "message": str(e)}

@router.post("/stripe/checkout/product")
async def handle_product_checkout(request: Request, checkout_data: ProductCheckoutRequest):
    user = request.state.user
    try:
        url = await product_checkout(
            user_id=user.username,
            amount=checkout_data.amount,
            product_name=checkout_data.product_name,
            currency=checkout_data.currency,
            quantity=checkout_data.quantity,
            metadata=checkout_data.metadata
        )
        return {"url": url}
    except Exception as e:
        logger.error(f"Error creating product checkout: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/stripe/checkout/subscription")
async def handle_subscription_checkout(request: Request, checkout_data: SubscriptionCheckoutRequest):
    user = request.state.user
    try:
        url = await subscription_checkout(
            user_id=user.username,
            plan_name=checkout_data.plan_name,
            amount=checkout_data.amount,
            interval=checkout_data.interval,
            currency=checkout_data.currency,
            metadata=checkout_data.metadata
        )
        return {"url": url}
    except Exception as e:
        logger.error(f"Error creating subscription checkout: {e}")
        raise HTTPException(status_code=400, detail=str(e))
