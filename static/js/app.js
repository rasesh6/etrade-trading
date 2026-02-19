/**
 * E*TRADE Trading UI - Application JavaScript
 */

// State
let currentSide = 'BUY';
let currentPriceSource = 'manual';
let currentAccountIdKey = null;
let quoteData = null;
let fillCheckInterval = null;

// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', () => {
    checkAuthStatus();
    setupEventListeners();
    updateOrderSummary();
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
            document.getElementById('auth-url').href = data.authorize_url;
            document.getElementById('flow-id').value = data.flow_id;

            document.getElementById('auth-not-authenticated').style.display = 'none';
            document.getElementById('auth-flow').style.display = 'block';
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

    // Load balance and positions in parallel
    loadBalance(currentAccountIdKey);
    loadPositions(currentAccountIdKey);
    loadOrders(currentAccountIdKey);
}

async function loadBalance(accountIdKey) {
    try {
        const response = await fetch(`/api/accounts/${accountIdKey}/balance`);
        const data = await response.json();

        if (data.success) {
            const balance = data.balance;
            document.getElementById('balance-total').textContent = formatCurrency(balance.net_account_value);
            document.getElementById('balance-cash').textContent = formatCurrency(balance.cash_available);
            document.getElementById('balance-buying-power').textContent = formatCurrency(balance.buying_power);
            document.getElementById('account-balance').style.display = 'block';
        }
    } catch (error) {
        console.error('Load balance failed:', error);
    }
}

async function loadPositions(accountIdKey) {
    try {
        const response = await fetch(`/api/accounts/${accountIdKey}/positions`);
        const data = await response.json();

        const container = document.getElementById('positions-list');

        if (data.success && data.positions.length > 0) {
            let html = '<table class="data-table"><thead><tr><th>Symbol</th><th>Qty</th><th>Value</th><th>P&L</th></tr></thead><tbody>';

            data.positions.forEach(pos => {
                const pnlClass = pos.total_gain_loss >= 0 ? 'positive' : 'negative';
                html += `<tr>
                    <td><strong>${pos.symbol}</strong></td>
                    <td>${pos.quantity}</td>
                    <td>${formatCurrency(pos.market_value)}</td>
                    <td class="${pnlClass}">${formatCurrency(pos.total_gain_loss)}</td>
                </tr>`;
            });

            html += '</tbody></table>';
            container.innerHTML = html;
        } else {
            container.innerHTML = '<p class="placeholder-text">No positions</p>';
        }
    } catch (error) {
        console.error('Load positions failed:', error);
    }
}

async function loadOrders(accountIdKey) {
    try {
        const response = await fetch(`/api/accounts/${accountIdKey}/orders`);
        const data = await response.json();

        const container = document.getElementById('orders-list');

        if (data.success && data.orders.length > 0) {
            let html = '<table class="data-table"><thead><tr><th>Symbol</th><th>Action</th><th>Qty</th><th>Price</th><th>Status</th></tr></thead><tbody>';

            data.orders.forEach(order => {
                html += `<tr>
                    <td><strong>${order.symbol}</strong></td>
                    <td>${order.action}</td>
                    <td>${order.quantity}</td>
                    <td>${formatPrice(order.price)}</td>
                    <td>${order.status}</td>
                </tr>`;
            });

            html += '</tbody></table>';
            container.innerHTML = html;
        } else {
            container.innerHTML = '<p class="placeholder-text">No open orders</p>';
        }
    } catch (error) {
        console.error('Load orders failed:', error);
    }
}

// ==================== QUOTES ====================

async function fetchQuote() {
    const symbol = document.getElementById('quote-symbol').value.toUpperCase().trim();

    if (!symbol) {
        alert('Please enter a symbol');
        return;
    }

    try {
        const btn = event.target;
        const originalText = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Loading...';

        const response = await fetch(`/api/quote/${symbol}`);
        const data = await response.json();

        if (data.success) {
            quoteData = data.quote;
            displayQuote(quoteData);
        } else {
            alert('Failed to get quote: ' + data.error);
        }

        btn.disabled = false;
        btn.textContent = originalText;

    } catch (error) {
        console.error('Quote fetch failed:', error);
        alert('Failed to get quote: ' + error.message);
    }
}

function displayQuote(quote) {
    const container = document.getElementById('quote-display');
    const changeClass = quote.change >= 0 ? 'positive' : 'negative';
    const changeSign = quote.change >= 0 ? '+' : '';

    container.innerHTML = `
        <div class="quote-header">
            <span class="quote-symbol">${quote.symbol}</span>
            <span class="quote-price">${formatPrice(quote.last_price)}</span>
        </div>
        <div class="quote-details">
            <span class="quote-change ${changeClass}">${changeSign}${formatPrice(quote.change)} (${changeSign}${quote.change_percent.toFixed(2)}%)</span>
        </div>
        <div class="quote-bidask">
            <span>Bid: ${formatPrice(quote.bid)}</span>
            <span>Ask: ${formatPrice(quote.ask)}</span>
            <span>Vol: ${quote.volume.toLocaleString()}</span>
        </div>
    `;
    container.style.display = 'block';
}

// ==================== ORDER ENTRY ====================

function setSide(side) {
    currentSide = side;

    // Update button states
    document.getElementById('btn-buy').classList.toggle('active', side === 'BUY');
    document.getElementById('btn-sell').classList.toggle('active', side === 'SELL');

    updateOrderSummary();
}

function setPriceSource(source) {
    currentPriceSource = source;

    // Update button states
    document.getElementById('btn-market').classList.toggle('active', source === 'market');
    document.getElementById('btn-limit').classList.toggle('active', source === 'limit');

    // Show/hide limit price input
    document.getElementById('limit-price-container').style.display = source === 'limit' ? 'block' : 'none';

    updateOrderSummary();
}

function updateOrderSummary() {
    const symbol = document.getElementById('order-symbol').value.toUpperCase().trim();
    const quantity = parseInt(document.getElementById('order-quantity').value) || 0;
    const limitPrice = parseFloat(document.getElementById('limit-price').value) || 0;

    const summary = document.getElementById('order-summary');
    const action = currentSide === 'BUY' ? 'Buy' : 'Sell';
    const orderType = currentPriceSource === 'market' ? 'Market' : `Limit @ ${formatPrice(limitPrice)}`;

    summary.innerHTML = `<strong>${action}</strong> ${quantity || 0} shares of <strong>${symbol || '---'}</strong> @ <strong>${orderType}</strong>`;

    // Update profit target info
    const profitEnabled = document.getElementById('profit-enabled').checked;
    const profitInfo = document.getElementById('profit-info');
    if (profitEnabled) {
        const offsetType = document.getElementById('profit-offset-type').value;
        const offsetValue = parseFloat(document.getElementById('profit-offset-value').value) || 0;
        profitInfo.textContent = `Profit target: +${offsetValue}${offsetType === 'percent' ? '%' : '$'} from fill price`;
    } else {
        profitInfo.textContent = '';
    }
}

function toggleProfitOptions() {
    const enabled = document.getElementById('profit-enabled').checked;
    document.getElementById('profit-options').style.display = enabled ? 'block' : 'none';
    updateOrderSummary();
}

// ==================== ORDER PLACEMENT ====================

async function placeOrder() {
    if (!currentAccountIdKey) {
        alert('Please select an account first');
        return;
    }

    const symbol = document.getElementById('order-symbol').value.toUpperCase().trim();
    const quantity = parseInt(document.getElementById('order-quantity').value) || 0;
    const orderType = currentPriceSource === 'market' ? 'MARKET' : 'LIMIT';
    const limitPrice = parseFloat(document.getElementById('limit-price').value) || null;

    // Validation
    if (!symbol) {
        alert('Please enter a symbol');
        return;
    }
    if (quantity <= 0) {
        alert('Please enter a valid quantity');
        return;
    }
    if (orderType === 'LIMIT' && (!limitPrice || limitPrice <= 0)) {
        alert('Please enter a valid limit price');
        return;
    }

    // Profit target options
    const profitEnabled = document.getElementById('profit-enabled').checked;
    const profitOffsetType = document.getElementById('profit-offset-type').value;
    const profitOffsetValue = parseFloat(document.getElementById('profit-offset-value').value) || 0;
    const fillTimeout = parseInt(document.getElementById('fill-timeout').value) || 15;

    const orderData = {
        account_id_key: currentAccountIdKey,
        symbol: symbol,
        quantity: quantity,
        order_action: currentSide,
        order_type: orderType,
        limit_price: limitPrice,
        profit_target: profitEnabled ? {
            offset_type: profitOffsetType,
            offset_value: profitOffsetValue,
            timeout_seconds: fillTimeout
        } : null
    };

    try {
        const btn = event.target;
        btn.disabled = true;
        btn.textContent = 'Placing Order...';

        const response = await fetch('/api/orders/place', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderData)
        });

        const data = await response.json();

        if (data.success) {
            const result = data.result;

            // Show order status card
            document.getElementById('order-status-card').style.display = 'block';
            document.getElementById('order-status-symbol').textContent = symbol;
            document.getElementById('order-status-action').textContent = currentSide;
            document.getElementById('order-status-qty').textContent = quantity;
            document.getElementById('order-status-id').textContent = result.order_id || 'Pending';

            if (result.preview_only) {
                document.getElementById('order-status-status').textContent = 'Preview Only';
                document.getElementById('order-status-status').className = 'status-pending';
            } else {
                document.getElementById('order-status-status').textContent = 'Placed';
                document.getElementById('order-status-status').className = 'status-pending';
            }

            // Start fill checking if profit target enabled
            if (profitEnabled && result.order_id) {
                startFillChecking(result.order_id, currentAccountIdKey, {
                    symbol: symbol,
                    quantity: quantity,
                    action: currentSide === 'BUY' ? 'SELL' : 'BUY',
                    offset_type: profitOffsetType,
                    offset_value: profitOffsetValue
                }, fillTimeout * 1000);
            }

            // Refresh orders list
            loadOrders(currentAccountIdKey);

            alert(`Order placed successfully!\n\nOrder ID: ${result.order_id || 'N/A'}\nPreview ID: ${result.preview_id || 'N/A'}`);
        } else {
            alert('Failed to place order: ' + data.error);
        }

        btn.disabled = false;
        btn.textContent = 'Place Order';

    } catch (error) {
        console.error('Order placement failed:', error);
        alert('Failed to place order: ' + error.message);
    }
}

// ==================== FILL CHECKING ====================

function startFillChecking(orderId, accountIdKey, profitOrder, timeoutMs) {
    const startTime = Date.now();
    const pollInterval = 500; // Check every 500ms
    let elapsed = 0;

    const statusEl = document.getElementById('order-status-status');
    const elapsedEl = document.getElementById('order-status-elapsed');

    document.getElementById('order-status-fill-price').textContent = 'Waiting...';
    document.getElementById('order-status-profit-order').style.display = 'none';

    const checkFill = async () => {
        elapsed = (Date.now() - startTime) / 1000;
        elapsedEl.textContent = `${elapsed.toFixed(1)}s / ${(timeoutMs / 1000).toFixed(0)}s`;

        if (elapsed * 1000 >= timeoutMs) {
            // Timeout - cancel order
            statusEl.textContent = 'Timeout - Cancelling...';
            statusEl.className = 'status-cancelled';

            try {
                await fetch(`/api/orders/${accountIdKey}/${orderId}`, { method: 'DELETE' });
                statusEl.textContent = 'Cancelled (No Fill)';
            } catch (e) {
                console.error('Cancel failed:', e);
            }

            fillCheckInterval = null;
            return;
        }

        try {
            const response = await fetch(`/api/orders/${accountIdKey}/${orderId}/fill`);
            const data = await response.json();

            if (data.filled) {
                // Order filled!
                statusEl.textContent = 'FILLED';
                statusEl.className = 'status-filled';
                document.getElementById('order-status-fill-price').textContent = formatPrice(data.fill_price);

                // Place profit order
                if (profitOrder) {
                    const profitPrice = calculateProfitPrice(data.fill_price, profitOrder.offset_type, profitOrder.offset_value);
                    await placeProfitOrder(accountIdKey, profitOrder, profitPrice, data.fill_price);
                }

                fillCheckInterval = null;
                loadOrders(accountIdKey);
                return;
            }

            // Continue polling
            fillCheckInterval = setTimeout(checkFill, pollInterval);

        } catch (error) {
            console.error('Fill check failed:', error);
            fillCheckInterval = setTimeout(checkFill, pollInterval);
        }
    };

    // Start polling
    fillCheckInterval = setTimeout(checkFill, pollInterval);
}

function calculateProfitPrice(fillPrice, offsetType, offsetValue) {
    if (offsetType === 'percent') {
        return fillPrice * (1 + offsetValue / 100);
    } else {
        return fillPrice + offsetValue;
    }
}

async function placeProfitOrder(accountIdKey, profitOrder, profitPrice, fillPrice) {
    const profitEl = document.getElementById('order-status-profit-order');

    try {
        profitEl.style.display = 'block';
        profitEl.innerHTML = `<span class="profit-label">Profit Order:</span> Placing...`;

        const response = await fetch('/api/orders/place', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                account_id_key: accountIdKey,
                symbol: profitOrder.symbol,
                quantity: profitOrder.quantity,
                order_action: profitOrder.action,
                order_type: 'LIMIT',
                limit_price: profitPrice,
                profit_target: null
            })
        });

        const data = await response.json();

        if (data.success) {
            profitEl.innerHTML = `<span class="profit-label">Profit Order:</span> ${profitOrder.action} ${profitOrder.quantity} @ ${formatPrice(profitPrice)} (Fill: ${formatPrice(fillPrice)})`;
            profitEl.className = 'profit-success';
        } else {
            profitEl.innerHTML = `<span class="profit-label">Profit Order:</span> Failed - ${data.error}`;
            profitEl.className = 'profit-failed';
        }

    } catch (error) {
        console.error('Profit order failed:', error);
        profitEl.innerHTML = `<span class="profit-label">Profit Order:</span> Failed - ${error.message}`;
        profitEl.className = 'profit-failed';
    }
}

// ==================== HELPERS ====================

function formatCurrency(value) {
    if (value === null || value === undefined) return 'N/A';
    return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPrice(value) {
    if (value === null || value === undefined) return 'N/A';
    return '$' + value.toFixed(2);
}
