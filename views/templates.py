dashboard_template = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Stock Tracker Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #0f1117; color: #e0e0e0; padding: 2rem; }
    h1 { font-size: 1.8rem; margin-bottom: 0.5rem; color: #fff; }
    p.subtitle { color: #888; margin-bottom: 2rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 1rem; }
    .card {
      background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 8px;
      padding: 1.25rem; text-decoration: none; color: inherit;
      transition: border-color 0.15s;
    }
    .card:hover { border-color: #4f8ef7; }
    .card h2 { font-size: 1rem; margin-bottom: 0.35rem; color: #fff; }
    .card p { font-size: 0.85rem; color: #888; }
    .badge {
      display: inline-block; font-size: 0.7rem; padding: 0.15rem 0.5rem;
      border-radius: 999px; background: #2a2d3a; color: #4f8ef7; margin-top: 0.5rem;
    }
  </style>
</head>
<body>
  <h1>Stock Tracker</h1>
  <p class="subtitle">Neo4j-based stock tracking and modeling system</p>
  <div class="grid">
    <a class="card" href="/stocks">
      <h2>Stocks</h2>
      <p>Browse all tracked stocks</p>
      <span class="badge">GET /stocks</span>
    </a>
    <a class="card" href="/stocks/view">
      <h2>Stock List View</h2>
      <p>Paginated HTML view of stocks</p>
      <span class="badge">GET /stocks/view</span>
    </a>
    <a class="card" href="/docs">
      <h2>API Docs</h2>
      <p>Interactive Swagger UI</p>
      <span class="badge">GET /docs</span>
    </a>
    <a class="card" href="/api/model/metrics">
      <h2>Model Metrics</h2>
      <p>XGBoost training results</p>
      <span class="badge">GET /api/model/metrics</span>
    </a>
    <a class="card" href="/api/model/features">
      <h2>Feature Importances</h2>
      <p>Top predictors from last training run</p>
      <span class="badge">GET /api/model/features</span>
    </a>
  </div>
</body>
</html>
"""

stock_list_template = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Stock List</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #0f1117; color: #e0e0e0; padding: 2rem; }
    h1 { font-size: 1.5rem; margin-bottom: 1.5rem; color: #fff; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    thead th {
      text-align: left; padding: 0.6rem 1rem;
      background: #1a1d27; color: #888; border-bottom: 1px solid #2a2d3a;
    }
    tbody tr { border-bottom: 1px solid #1e2130; }
    tbody tr:hover { background: #1a1d27; }
    tbody td { padding: 0.6rem 1rem; }
    .symbol { font-weight: 600; color: #4f8ef7; }
    .price { font-variant-numeric: tabular-nums; }
    .no-data { color: #555; }
    .back { display: inline-block; margin-bottom: 1.5rem; color: #4f8ef7; text-decoration: none; font-size: 0.85rem; }
    .back:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <a class="back" href="/dashboard">&larr; Dashboard</a>
  <h1>Stocks</h1>
  {% if stocks %}
  <table>
    <thead>
      <tr>
        <th>Symbol</th>
        <th>Name</th>
        <th>Sector</th>
        <th>Price</th>
        <th>Last Updated</th>
      </tr>
    </thead>
    <tbody>
      {% for stock in stocks %}
      <tr>
        <td class="symbol">{{ stock.symbol }}</td>
        <td>{{ stock.name or '<span class="no-data">—</span>' }}</td>
        <td>{{ stock.sector or '<span class="no-data">—</span>' }}</td>
        <td class="price">
          {% if stock.price is not none %}
            ${{ "%.2f"|format(stock.price) }}
          {% else %}
            <span class="no-data">—</span>
          {% endif %}
        </td>
        <td>{{ stock.price_timestamp or '<span class="no-data">—</span>' }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p style="color:#888;">No stocks found. Use <code>POST /api/stocks</code> or run a data collection job.</p>
  {% endif %}
</body>
</html>
"""
