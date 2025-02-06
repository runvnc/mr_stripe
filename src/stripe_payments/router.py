from fastapi import APIRouter, Request
from .mod import process_payment, create_stripe_session
import os

router = APIRouter()
stripe.api_key = os.getenv("STRIPE_API_KEY")

@router.post("/stripe/webhook")
async def handle_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    event = stripe.Webhook.construct_event(
        payload, 
        sig_header,
        os.getenv("STRIPE_WEBHOOK_SECRET")
    )
    await process_payment(event)

@router.post("/stripe/create-session")
async def handle_create_session(request: Request):
    user = request.state.user
    return {"url": await create_stripe_session(user.id, 10)}
