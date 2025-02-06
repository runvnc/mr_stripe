import stripe
from lib.providers import command
from lib.providers.services import service_manager
from lib.logging.logfiles import logger

@command()
async def create_stripe_session(user_id: str, amount: int, currency: str = "usd"):
    """Create Stripe Checkout Session for credit purchase"""
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': currency,
                'product_data': {'name': f'{amount} Credits'},
                'unit_amount': amount * 100
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=f'/stripe/success?session_id={{CHECKOUT_SESSION_ID}}',
        cancel_url='/stripe/cancel',
        client_reference_id=user_id
    )
    return session.url

async def process_payment(event: dict):
    """Handle completed Stripe payments"""
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        try:
            await service_manager.allocate_credits(
                user_id=session['client_reference_id'],
                amount=session['amount_total'] / 100,
                source='stripe',
                transaction_id=session['id'],
                metadata={
                    'payment_intent': session['payment_intent'],
                    'currency': session['currency']
                }
            )
        except Exception as e:
            logger.error(f"Credit allocation failed: {str(e)}")
            raise

