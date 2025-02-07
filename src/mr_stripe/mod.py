import stripe
from lib.providers import service
from lib.providers.services import service_manager
from lib.logging.logfiles import logger
from typing import Optional, Dict, Any, Union
from decimal import Decimal
from dataclasses import dataclass

@dataclass
class CheckoutUrls:
    success: str
    cancel: str

@service()
async def product_checkout(
    user_id: str,
    amount: Decimal,
    product_name: str,
    currency: str = 'USD',
    quantity: int = 1,
    urls: Optional[CheckoutUrls] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Create Stripe Checkout Session for one-time product purchase"""
    success_url = urls.success if urls else f'/stripe/success?session_id={{CHECKOUT_SESSION_ID}}'
    cancel_url = urls.cancel if urls else '/stripe/cancel'
    
    line_items = [{
        'price_data': {
            'currency': currency.lower(),
            'product_data': {'name': product_name},
            'unit_amount': int(amount * 100)
        },
        'quantity': quantity
    }]
    
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=user_id,
        metadata=metadata or {}
    )
    return session.url

@service()
async def subscription_checkout(
    user_id: str,
    plan_name: str,
    amount: Decimal,
    interval: str,  # 'month' or 'year'
    currency: str = 'USD',
    urls: Optional[CheckoutUrls] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Create Stripe Checkout Session for subscription signup"""
    if interval not in ['month', 'year']:
        raise ValueError("interval must be 'month' or 'year'")
        
    success_url = urls.success if urls else f'/stripe/success?session_id={{CHECKOUT_SESSION_ID}}'
    cancel_url = urls.cancel if urls else '/stripe/cancel'
    
    line_items = [{
        'price_data': {
            'currency': currency.lower(),
            'product_data': {'name': plan_name},
            'unit_amount': int(amount * 100),
            'recurring': {
                'interval': interval
            }
        },
        'quantity': 1
    }]
    
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=line_items,
        mode='subscription',
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=user_id,
        metadata=metadata or {}
    )
    return session.url

async def process_payment(event: dict):
    """Handle completed Stripe payments and subscription events"""
    event_type = event['type']
    session = event['data']['object']

    try:
        if event_type == 'checkout.session.completed':
            if session['mode'] == 'payment':
                # Handle regular product purchase
                await service_manager.process_purchase(
                    user_id=session['client_reference_id'],
                    transaction_id=session['id'],
                    amount=session['amount_total'] / 100,
                    currency=session['currency'],
                    metadata=session['metadata'],
                    source='stripe'
                )
                    
            elif session['mode'] == 'subscription':
                # Handle new subscription
                await service_manager.activate_subscription(
                    user_id=session['client_reference_id'],
                    subscription_id=session['subscription'],
                    plan_id=session['metadata'].get('plan_id'),
                    source='stripe'
                )
                
        elif event_type == 'customer.subscription.deleted':
            # Handle subscription cancellation
            await service_manager.deactivate_subscription(
                user_id=session['client_reference_id'],
                subscription_id=session['id'],
                source='stripe'
            )

    except Exception as e:
        logger.error(f"Payment processing failed: {str(e)}")
        raise
