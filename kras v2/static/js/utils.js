function updateCartCount() {
    const cart = JSON.parse(localStorage.getItem('cart')) || [];
    const cartCount = cart.length;
    const cartCountElement = document.getElementById('cart-count');
    if (cartCountElement) {
        cartCountElement.textContent = cartCount;
    }
}

async function checkSeatAvailability(matchId, sectorName, row, seat) {
    try {
        const response = await fetch(`/check_seat/${matchId}/${sectorName}/${row}/${seat}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });
        if (response.ok) {
            const data = await response.json();
            return data.available;
        }
        return false;
    } catch (error) {
        console.error('Error checking seat availability:', error);
        return false;
    }
}

function updateCart(cart) {
    localStorage.setItem('cart', JSON.stringify(cart));
    updateCartCount();
}