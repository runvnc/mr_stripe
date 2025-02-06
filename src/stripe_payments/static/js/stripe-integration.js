async function initStripeCheckout() {
    try {
        const response = await fetch('/stripe/create-session', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        
        const {url} = await response.json();
        window.location.href = url;
    } catch (error) {
        console.error('Stripe checkout failed:', error);
    }
}
