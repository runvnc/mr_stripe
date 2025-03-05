import stripe
from lib.providers.services import service, service_manager
from lib.logging.logfiles import logger
from typing import Optional, Dict, Any, Union
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime

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

@service()
async def cancel_stripe_subscription(
    provider_subscription_id: str,
    at_period_end: bool = True
) -> bool:
    """Cancel a Stripe subscription
    
    Args:
        provider_subscription_id: Stripe subscription ID
        at_period_end: Whether to cancel at period end or immediately
        
    Returns:
        bool: Success status
    """
    try:
        # Cancel subscription
        stripe.Subscription.modify(
            provider_subscription_id,
            cancel_at_period_end=at_period_end
        )
        
        logger.info(f"Cancelled Stripe subscription {provider_subscription_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to cancel Stripe subscription: {str(e)}")
        raise

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
                # For subscriptions, we'll handle this in the webhook handler
                # to forward to the subscriptions plugin
                pass
                
        elif event_type == 'customer.subscription.deleted':
            # For subscriptions, we'll handle this in the webhook handler
            # to forward to the subscriptions plugin
            pass

    except Exception as e:
        logger.error(f"Payment processing failed: {str(e)}")
        raise

async def normalize_subscription_event(event: dict) -> dict:
    """Convert Stripe event to normalized subscription event format"""
    event_type = event['type']
    normalized = {
        'original_type': event_type,
        'provider': 'stripe',
        'timestamp': datetime.now().isoformat()
    }
    
    if event_type == 'checkout.session.completed':
        session = event['data']['object']
        if session.get('mode') == 'subscription':
            normalized.update({
                'event_type': 'subscription_created',
                'username': session.get('client_reference_id'),
                'subscription_id': session.get('subscription'),
                'metadata': session.get('metadata', {})
            })
    
    elif event_type == 'invoice.paid':
        invoice = event['data']['object']
        subscription_id = invoice.get('subscription')
        normalized.update({
            'event_type': 'subscription_renewed',
            'subscription_id': subscription_id,
            'invoice_id': invoice.get('id')
        })
        
        # Get additional subscription details from Stripe
        try:
            stripe_subscription = stripe.Subscription.retrieve(subscription_id)
            normalized.update({
                'period_start': datetime.fromtimestamp(stripe_subscription.current_period_start).isoformat(),
                'period_end': datetime.fromtimestamp(stripe_subscription.current_period_end).isoformat()
            })
        except Exception as e:
            logger.error(f"Error getting subscription details: {e}")
    
    elif event_type == 'customer.subscription.updated':
        subscription = event['data']['object']
        normalized.update({
            'event_type': 'subscription_updated',
            'subscription_id': subscription.get('id'),
            'status': subscription.get('status'),
            'cancel_at_period_end': subscription.get('cancel_at_period_end', False),
            'current_period_end': datetime.fromtimestamp(subscription.get('current_period_end')).isoformat()
        })
    
    elif event_type == 'customer.subscription.deleted':
        subscription = event['data']['object']
        normalized.update({
            'event_type': 'subscription_canceled',
            'subscription_id': subscription.get('id')
        })
    
    return normalized
