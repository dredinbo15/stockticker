"""
Basic HTML templates for the stock tracker web interface.
"""

stock_list_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Stock Tracker</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .stock { border: 1px solid #ddd; padding: 10px; margin: 10px 0; }
        .stock h3 { margin: 0; }
    </style>
</head>
<body>
    <h1>Stock Tracking Dashboard</h1>
    <div id="stocks">
        {% for stock in stocks %}
        <div class="stock">
            <h3>{{ stock.symbol }}</h3>
            <p>{{ stock.name }} - {{ stock.sector }}</p>
            {% if stock.price is not none %}
            <p><strong>Price:</strong> ${{ "%.2f" | format(stock.price) }} {% if stock.price_timestamp %}(<small>{{ stock.price_timestamp }}</small>){% endif %}</p>
            {% endif %}
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

dashboard_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Stock Tracker Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .module { border: 1px solid #ddd; padding: 15px; margin: 10px 0; }
        button { padding: 10px 15px; margin: 5px; cursor: pointer; }
    </style>
</head>
<body>
    <h1>Stock Tracker Control Panel</h1>

    <div class="module">
        <h2>Weather Data Collection</h2>
        <button onclick="collectWeather()">Collect Weather Data</button>
    </div>

    <div class="module">
        <h2>News Collection & Enrichment</h2>
        <button onclick="collectNews()">Collect News</button>
    </div>

    <div class="module">
        <h2>SEC Form 4 Collection</h2>
        <button onclick="collectSECData()">Collect SEC Data</button>
    </div>

    <div class="module">
        <h2>Stock Price Collection</h2>
        <button onclick="collectPrices()">Collect Latest Prices</button>
    </div>

    <div class="module">
        <h2>View Data</h2>
        <a href="/stocks">View All Stocks</a>
    </div>

    <script>
        function collectWeather() {
            fetch('/api/collect/weather', { method: 'POST' })
                .then(response => response.json())
                .then(data => alert('Weather collection started'));
        }

        function collectNews() {
            fetch('/api/collect/news', { method: 'POST' })
                .then(response => response.json())
                .then(data => alert('News collection started'));
        }

        function collectSECData() {
            fetch('/api/collect/sec', { method: 'POST' })
                .then(response => response.json())
                .then(data => alert('SEC data collection started'));
        }

        function collectPrices() {
            fetch('/api/collect/prices', { method: 'POST' })
                .then(response => response.json())
                .then(data => alert('Price collection started'));
        }
    </script>
</body>
</html>
"""