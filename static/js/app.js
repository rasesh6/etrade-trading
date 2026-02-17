/**
 * E*TRADE Trading UI - Application JavaScript
 */

// State
let currentSide = 'BUY';
let currentPriceSource = 'manual';
let currentAccountIdKey = null;
let quoteData = null;

// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', () => {
    checkAuthStatus();
    setupEventListeners();
    updateOrderSummary();
    handleCallbackParams();
});

function setupEventListeners() {
    // Order form inputs
    document.getElementById('order-symbol').addEventListener('input', updateOrderSummary);
    document.getElementById('order-quantity').addEventListener('input', updateOrderSummary);
    document.getElementById('limit-price').addEventListener('input', updateOrderSummary);

    // Quote symbol - auto-fill order symbol
    document.getElementById('quote-symbol').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            fetchQuote();
        }
    });

    // Copy quote symbol to order symbol
    document.getElementById('quote-symbol').addEventListener('input', function() {
        document.getElementById('order-symbol').value = this.value.toUpperCase();
        updateOrderSummary();
    });
}

function handleCallbackParams() {
    // Check for callback result in URL params
    const urlParams = new URLSearchParams(window.location.search);

    if (urlParams.get('auth_success') === 'true') {
        // Clear the URL param and show success
        window.history.replaceState({}, document.title, '/');
        // Auth status will be checked below
    }

    if (urlParams.get('auth_error')) {
        const error = urlParams.get('auth_error');
        window.history.replaceState({}, document.title, '/');
        alert('Authentication failed: ' + error);
    }
}

// ==================== AUTHENTICATION ====================

async function checkAuthStatus() {
    try {
        const response = await fetch('/api/auth/status');
        const data = await response.json();

        updateAuthUI(data);

        if (data.authenticated) {
            loadAccounts();
        }
    } catch (error) {
        console.error('Auth status check failed:', error);
    }
}

function updateAuthUI(data) {
    const badge = document.getElementById('auth-badge');
    const notAuth = document.getElementById('auth-not-authenticated');
    const authFlow = document.getElementById('auth-flow');
    const authed = document.getElementById('auth-authenticated');

    if (data.authenticated) {
        badge.textContent = 'Connected';
        badge.classList.add('authenticated');
        notAuth.style.display = 'none';
        authFlow.style.display = 'none';
        authed.style.display = 'block';
        document.getElementById('token-expires').textContent = data.expires_at || '-';
    } else {
        badge.textContent = 'Not Connected';
        badge.classList.remove('authenticated');
        notAuth.style.display = 'block';
        authFlow.style.display = 'none';
        authed.style.display = 'none';
    }
}

async function startLogin() {
    try {
        const btn = event.target;
        btn.disabled = true;
        btn.textContent = 'Starting...';

        const response = await fetch('/api/auth/login', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            const authUrl = data.authorize_url;

            // Show the auth flow section with link
            document.getElementById('auth-url').href = authUrl;
            document.getElementById('auth-not-authenticated').style.display = 'none';
            document.getElementById('auth-flow').style.display = 'block';

            // Open E*TRADE authorization in a new window
            const authWindow = window.open(authUrl, 'etrade-auth', 'width=800,height=600');

            // Start polling for auth status
            pollAuthStatus();
        } else {
            alert('Failed to start login: ' + data.error);
        }

        btn.disabled = false;
        btn.textContent = 'Connect to E*TRADE';

    } catch (error) {
        console.error('Start login failed:', error);
        alert('Failed to start login: ' + error.message);
    }
}

function pollAuthStatus() {
    // Poll every 2 seconds for up to 5 minutes
    let attempts = 0;
    const maxAttempts = 150; // 5 minutes at 2 second intervals

    const poll = async () => {
        attempts++;

        try {
            const response = await fetch('/api/auth/status');
            const data = await response.json();

            if (data.authenticated) {
                // Auth successful - update UI
                updateAuthUI(data);
                loadAccounts();
                return;
            }
        } catch (error) {
            console.error('Poll auth status failed:', error);
        }

        // Continue polling if not authenticated and haven't exceeded max attempts
        if (attempts < maxAttempts) {
            setTimeout(poll, 2000);
        }
    };

    setTimeout(poll, 2000);
}

async function verifyCode() {
    const code = document.getElementById('verifier-code').value.trim();
    const flowId = document.getElementById('flow-id').value;

    if (!code) {
        alert('Please enter the verification code');
        return;
    }

    try {
        const btn = event.target;
        btn.disabled = true;
        btn.textContent = 'Verifying...';

        const response = await fetch('/api/auth/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                verifier_code: code,
                flow_id: flowId
            })
        });

        const data = await response.json();

        if (data.success) {
            checkAuthStatus();
            alert('Authentication successful!');
        } else {
            alert('Verification failed: ' + data.error);
        }

        btn.disabled = false;
        btn.textContent = 'Verify';

    } catch (error) {
        console.error('Verify failed:', error);
        alert('Verification failed: ' + error.message);
    }
}

async function logout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });

        currentAccountIdKey = null;
        document.getElementById('account-select').innerHTML = '<option value="">Select an account...</option>';
        document.getElementById('account-balance').style.display = 'none';
        document.getElementById('positions-list').innerHTML = '<p class="placeholder-text">Select an account to view positions</p>';
        document.getElementById('orders-list').innerHTML = '<p class="placeholder-text">No open orders</p>';

        checkAuthStatus();

    } catch (error) {
        console.error('Logout failed:', error);
    }
}

// ==================== ACCOUNTS ====================

async function loadAccounts() {
    try {
        const response = await fetch('/api/accounts');
        const data = await response.json();

        if (data.success && data.accounts.length > 0) {
            const select = document.getElementById('account-select');
            select.innerHTML = '<option value="">Select an account...</option>';

            data.accounts.forEach(acc => {
                const option = document.createElement('option');
                option.value = acc.account_id_key;
                option.textContent = `${acc.account_id} - ${acc.description || acc.type}`;
                select.appendChild(option);
            });

            // Auto-select first account
            if (data.accounts.length === 1) {
                select.value = data.accounts[0].account_id_key;
                loadAccountInfo();
            }
        }
    } catch (error) {
        console.error('Load accounts failed:', error);
    }
}

async function loadAccountInfo() {
    const accountSelect = document.getElementById('account-select');
    currentAccountIdKey = accountSelect.value;

    if (!currentAccountIdKey) {
        document.getElementById('account-balance').style.display = 'none';
        document.getElementById('positions-list').innerHTML = '<p class="placeholder-text">Select an account to view positions</p>';
        return;
    }

    // Load balance
    loadBalance(currentAccountIdKey);

    // Load positions
    loadPositions(currentAccountIdKey);

    // Load open orders
    loadOrders(currentAccountIdKey);
}

async function loadBalance(accountIdKey) {
    try {
        const response = await fetch(`/api/accounts/${accountIdKey}/balance`);
        const data = await response.json();

        if (data.success) {
            const balance = data.balance;
            document.getElementById('net-value').textContent = formatCurrency(balance.net_account_value);
            document.getElementById('cash-available').textContent = formatCurrency(balance.cash_available);
            document.getElementById('buying-power').textContent = formatCurrency(balance.margin_buying_power);
            document.getElementById('account-balance').style.display = 'block';
        }
    } catch (error) {
        console.error('Load balance failed:', error);
    }
}

async function loadPositions(accountIdKey) {
    try {
        const response = await fetch(`/api/accounts/${accountIdKey}/portfolio`);
        const data = await response.json();

        const container = document.getElementById('positions-list');

        if (data.success && data.positions.length > 0) {
            container.innerHTML = data.positions.map(pos => `
                <div class="position-item">
                    <div>
                        <span class="position-symbol">${pos.symbol || 'N/A'}</span>
                        <span class="position-qty"> x ${pos.quantity || 0}</span>
                    </div>
                    <div class="position-gain ${pos.total_gain >= 0 ? 'positive' : 'negative'}">
                        ${formatCurrency(pos.total_gain)}
                    </div>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<p class="placeholder-text">No positions</p>';
        }
    } catch (error) {
        console.error('Load positions failed:', error);
    }
}

async function loadOrders(accountIdKey) {
    try {
        const response = await fetch(`/api/accounts/${accountIdKey}/orders?status=OPEN`);
        const data = await response.json();

        const container = document.getElementById('orders-list');

        if (data.success && data.orders.length > 0) {
            container.innerHTML = data.orders.map(order => `
                <div class="order-item">
                    <div>
                        <span class="order-symbol">${order.symbol || 'N/A'}</span>
                        <span>${order.action || ''} ${order.quantity || 0}</span>
                        <span>@ ${order.limit_price || 'MKT'}</span>
                    </div>
                    <div class="order-actions">
                        <button class="btn btn-small btn-danger" onclick="cancelOrder('${accountIdKey}', '${order.order_id}')">
                            Cancel
                        </button>
                    </div>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<p class="placeholder-text">No open orders</p>';
        }
    } catch (error) {
        console.error('Load orders failed:', error);
    }
}

async function cancelOrder(accountIdKey, orderId) {
    if (!confirm('Are you sure you want to cancel this order?')) {
        return;
    }

    try {
        const response = await fetch(`/api/orders/${accountIdKey}/${orderId}/cancel`, {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            loadOrders(accountIdKey);
            showResponse('success', 'Order Cancelled', { message: data.message });
        } else {
            alert('Failed to cancel order: ' + data.error);
        }
    } catch (error) {
        console.error('Cancel order failed:', error);
    }
}

// ==================== QUOTES ====================

async function fetchQuote() {
    const symbol = document.getElementById('quote-symbol').value.trim().toUpperCase();

    if (!symbol) {
        alert('Please enter a symbol');
        return;
    }

    try {
        const response = await fetch(`/api/quote/${symbol}`);
        const data = await response.json();

        if (data.success) {
            quoteData = data.quote;
            displayQuote(data.quote);

            // Auto-fill order symbol
            document.getElementById('order-symbol').value = symbol;
            updateOrderSummary();
        } else {
            alert('Failed to get quote: ' + data.error);
        }
    } catch (error) {
        console.error('Fetch quote failed:', error);
        alert('Failed to fetch quote: ' + error.message);
    }
}

function displayQuote(quote) {
    document.getElementById('q-symbol').textContent = quote.symbol;
    document.getElementById('q-last').textContent = formatCurrency(quote.last_price);

    // Change
    const change = quote.change || 0;
    const changePercent = quote.change_percent || 0;
    const changeEl = document.getElementById('q-change');
    changeEl.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)} (${changePercent}%)`;
    changeEl.className = 'quote-change ' + (change >= 0 ? 'positive' : 'negative');

    // Bid/Ask
    document.getElementById('q-bid').textContent = formatCurrency(quote.bid);
    document.getElementById('q-bid-size').textContent = `x${quote.bid_size || ''}`;
    document.getElementById('q-ask').textContent = formatCurrency(quote.ask);
    document.getElementById('q-ask-size').textContent = `x${quote.ask_size || ''}`;

    // Volume & Range
    document.getElementById('q-volume').textContent = formatNumber(quote.volume);
    document.getElementById('q-range').textContent = `${quote.low || '-'} - ${quote.high || '-'}`;

    document.getElementById('quote-display').style.display = 'block';
}

// ==================== ORDER ENTRY ====================

function toggleLimitPrice() {
    const orderType = document.getElementById('order-type').value;
    const limitSection = document.getElementById('limit-price-section');

    if (orderType === 'LIMIT') {
        limitSection.style.display = 'block';
    } else {
        limitSection.style.display = 'none';
    }

    updateOrderSummary();
}

function setPriceSource(source) {
    currentPriceSource = source;

    // Update button states
    document.querySelectorAll('.price-source-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`.price-source-btn[data-source="${source}"]`).classList.add('active');

    // Show/hide appropriate input
    const manualInput = document.getElementById('manual-price-input');
    const marketDisplay = document.getElementById('market-price-display');
    const label = document.getElementById('price-source-label');

    if (source === 'manual') {
        manualInput.style.display = 'block';
        marketDisplay.style.display = 'none';
    } else {
        manualInput.style.display = 'none';
        marketDisplay.style.display = 'block';
        label.textContent = source.toUpperCase();

        // Update with current quote if available
        if (quoteData) {
            const price = source === 'bid' ? quoteData.bid : quoteData.ask;
            if (price) {
                label.textContent = `${source.toUpperCase()} (${formatCurrency(price)})`;
            }
        }
    }

    updateOrderSummary();
}

function setSide(side) {
    currentSide = side;

    // Update button states
    document.querySelectorAll('.side-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`.side-btn.${side.toLowerCase()}`).classList.add('active');

    // Update order button
    const orderBtn = document.getElementById('place-order-btn');
    orderBtn.className = `btn btn-${side.toLowerCase()}`;
    orderBtn.textContent = `Place ${side} Order`;

    updateOrderSummary();
}

function updateOrderSummary() {
    const symbol = document.getElementById('order-symbol').value.toUpperCase() || '-';
    const quantity = parseInt(document.getElementById('order-quantity').value) || 0;
    const orderType = document.getElementById('order-type').value;
    let limitPrice = parseFloat(document.getElementById('limit-price').value) || 0;

    // Update action
    const actionEl = document.getElementById('sum-action');
    actionEl.textContent = currentSide;
    actionEl.className = currentSide === 'BUY' ? 'buy-text' : 'sell-text';

    // Update symbol, quantity, type
    document.getElementById('sum-symbol').textContent = symbol;
    document.getElementById('sum-quantity').textContent = quantity;
    document.getElementById('sum-type').textContent = orderType === 'MARKET' ? 'Market' : 'Limit';

    // Limit price
    const priceRow = document.getElementById('sum-price-row');
    const estRow = document.getElementById('sum-est-row');

    if (orderType === 'LIMIT') {
        priceRow.style.display = 'flex';

        let priceDisplay = '-';
        if (currentPriceSource === 'manual' && limitPrice > 0) {
            priceDisplay = formatCurrency(limitPrice);
        } else if (currentPriceSource === 'bid') {
            priceDisplay = quoteData?.bid ? `${formatCurrency(quoteData.bid)} (BID)` : 'BID Price';
            limitPrice = quoteData?.bid || 0;
        } else if (currentPriceSource === 'ask') {
            priceDisplay = quoteData?.ask ? `${formatCurrency(quoteData.ask)} (ASK)` : 'ASK Price';
            limitPrice = quoteData?.ask || 0;
        }
        document.getElementById('sum-price').textContent = priceDisplay;

        // Estimated total
        if (limitPrice > 0 && quantity > 0) {
            estRow.style.display = 'flex';
            document.getElementById('sum-est').textContent = formatCurrency(limitPrice * quantity);
        } else {
            estRow.style.display = 'none';
        }
    } else {
        priceRow.style.display = 'none';
        estRow.style.display = 'none';
    }
}

async function placeOrder() {
    if (!currentAccountIdKey) {
        alert('Please select an account first');
        return;
    }

    const symbol = document.getElementById('order-symbol').value.trim().toUpperCase();
    const quantity = parseInt(document.getElementById('order-quantity').value) || 0;
    const orderType = document.getElementById('order-type').value;
    let limitPrice = null;

    // Validation
    if (!symbol) {
        alert('Please enter a symbol');
        return;
    }

    if (quantity <= 0) {
        alert('Please enter a valid quantity');
        return;
    }

    if (orderType === 'LIMIT') {
        if (currentPriceSource === 'manual') {
            limitPrice = parseFloat(document.getElementById('limit-price').value) || 0;
            if (limitPrice <= 0) {
                alert('Please enter a valid limit price');
                return;
            }
        }
        // For bid/ask, server will fetch the price
    }

    const btn = document.getElementById('place-order-btn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span> Placing Order...';

    try {
        const response = await fetch('/api/orders/place', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                account_id_key: currentAccountIdKey,
                symbol: symbol,
                quantity: quantity,
                side: currentSide,
                priceType: orderType,
                limitPrice: limitPrice,
                limitPriceSource: orderType === 'LIMIT' ? currentPriceSource : null
            })
        });

        const data = await response.json();

        if (data.success) {
            showResponse('success', 'Order Placed', data.order);
            loadOrders(currentAccountIdKey);  // Refresh orders list
        } else {
            showResponse('error', 'Order Failed', { error: data.error });
        }

    } catch (error) {
        console.error('Place order failed:', error);
        showResponse('error', 'Order Failed', { error: error.message });
    }

    btn.disabled = false;
    btn.textContent = originalText;
}

// ==================== RESPONSE DISPLAY ====================

function showResponse(type, title, data) {
    const area = document.getElementById('response-area');
    const content = document.getElementById('response-content');

    area.className = 'response-area ' + type;
    area.style.display = 'block';

    let html = `<div class="response-order">`;
    html += `<h4>${type === 'success' ? '✅' : '❌'} ${title}</h4>`;

    if (data.error) {
        html += `<p class="error-text">${data.error}</p>`;
    } else {
        html += `<div class="response-row"><span>Order ID:</span><span>${data.order_id || '-'}</span></div>`;
        html += `<div class="response-row"><span>Symbol:</span><span>${data.symbol}</span></div>`;
        html += `<div class="response-row"><span>Action:</span><span>${data.side}</span></div>`;
        html += `<div class="response-row"><span>Quantity:</span><span>${data.quantity}</span></div>`;
        html += `<div class="response-row"><span>Type:</span><span>${data.price_type}</span></div>`;
        if (data.limit_price) {
            html += `<div class="response-row"><span>Limit Price:</span><span>${formatCurrency(data.limit_price)}</span></div>`;
        }
        if (data.estimated_commission) {
            html += `<div class="response-row"><span>Commission:</span><span>${formatCurrency(data.estimated_commission)}</span></div>`;
        }
        if (data.estimated_total) {
            html += `<div class="response-row"><span>Est. Total:</span><span>${formatCurrency(data.estimated_total)}</span></div>`;
        }
        html += `<div class="response-row"><span>Message:</span><span>${data.message || 'Success'}</span></div>`;
    }

    html += `</div>`;
    content.innerHTML = html;
}

function clearResponse() {
    document.getElementById('response-area').style.display = 'none';
}

// ==================== UTILITIES ====================

function formatCurrency(value) {
    if (value === null || value === undefined) return '-';
    return '$' + parseFloat(value).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatNumber(value) {
    if (value === null || value === undefined) return '-';
    return parseInt(value).toLocaleString('en-US');
}
