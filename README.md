# Lumive Inventory Intelligence Dashboard v3.3

> Smart inventory management for Amazon + Noon marketplaces across KSA & UAE

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)
![License](https://img.shields.io/badge/License-Proprietary-green.svg)

## 🎯 Overview

The **Lumive Inventory Intelligence Dashboard** is a comprehensive inventory analytics platform designed for e-commerce businesses operating on Amazon and Noon marketplaces in Saudi Arabia and UAE. It provides real-time insights into inventory health, reorder recommendations, excess stock liquidation pricing, and historical trend analysis.

### Key Capabilities

- 📊 **Multi-Channel Inventory Tracking** - Unified view across Amazon KSA, Amazon UAE, Noon KSA, Noon UAE
- 🔄 **Smart Reorder Recommendations** - Safety stock-based reorder quantities
- ⚖️ **Inventory Balancing** - Cross-channel transfer opportunities (e.g., Amazon → Noon) to save capital
- 💸 **Advanced Financial Support** - `Lost Revenue`, `GMROI`, `Sell-Through Rate` tracking
- 💰 **Liquidation Pricing Calculator** - Elasticity-based discount recommendations for excess stock
- 📈 **Historical Trend Analysis** - Multi-month sales evolution and growth tracking
- 💾 **Session Persistence** - Save and reload workspaces without re-uploading files
- 🚨 **Urgent Actions Dashboard** - Priority-sorted critical issues requiring immediate attention

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Installation

```bash
# Clone or download the project
cd "Inventory Planning"

# Install dependencies
pip install -r requirements.txt

# Run the dashboard
streamlit run lumive_inventory_complete.py
```

### Required Python Packages

```
streamlit>=1.28.0
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.18.0
openpyxl>=3.1.0
pyarrow>=14.0.0
xlsxwriter>=3.1.0
```

---

## 📂 File Structure

```
Inventory Planning/
├── lumive_inventory_complete.py   # Main application (v3.3)
├── database_manager.py            # Data persistence & calculations
├── requirements.txt               # Python dependencies
├── README.md                      # This file
└── lumive_data/                   # Auto-created data directory
    ├── sessions_index.json        # Session metadata
    ├── history.parquet            # Historical data
    └── sessions/                  # Saved session files
        └── {session_name}.parquet
```

---

## 📊 Dashboard Tabs

### 1. 🚨 Urgent Actions
**Priority-sorted issues requiring immediate attention**

| Priority | Issue Type | Timeframe |
|----------|------------|-----------|
| 🔴 CRITICAL | Stockout Imminent (DOI < 7 days) | Act today |
| 🟠 HIGH | Severe Excess (DOI > 365 days) | This week |
| 🟡 MEDIUM | Dead Stock (zero sales) | This month |
| 🔵 LOW | Low Stock Warning (DOI 7-14 days) | Monitor |

### 2. 📊 Executive Summary
- Total SKUs, Total Stock Value
- Healthy vs At-Risk inventory breakdown
- **Financial KPIs**: Estimated Lost Revenue, GMROI, Sell-Through Rate (STR)
- ABC classification distribution (A: 80% revenue, B: 15%, C: 5%)
- Channel comparison metrics

### 3. 🏥 Inventory Health
- DOI (Days of Inventory) distribution
- **Sparklines**: 6-month sales trend visualization per product
- Aging analysis across buckets (0-30, 31-60, 61-90, 91-180, 181-365, 365+ days)
- Movement classification (Fast, Moving, Slow, Dead)
- Visual charts and heatmaps

### 4. 🔄 Reorder & Stockout
- Items needing reorder (stock below safety level)
- Reorder quantities by ABC class
- **Stock Balancing Opportunities**: Move excess stock to channels with need
- Stockout risk identification

**Reorder Formula:**
```
Reorder Qty = max(0, Safety Stock - Current Stock - Inbound)
Safety Stock = Daily Velocity × Safety Days
```

### 5. 💀 Dead & Excess
- Excess inventory (DOI > threshold)
- Dead stock (zero sales)
- **Liquidation Pricing Recommendations** with:
  - Elasticity-based discount calculations
  - Expected new velocity after discount
  - Days to clear estimates

### 6. 🌐 Cross-Channel
- Same product across all 4 channels
- Stock, sales, and DOI comparison
- Identifies imbalances

### 7. ⚖️ Rebalancing
- Transfer opportunities between channels
- From excess (high DOI) to shortage (low DOI)
- Same-country transfers (Amazon ↔ Noon)

### 8. 🚫 Stranded
- Unfulfillable inventory
- Reserved stock issues
- Recommended actions

### 9. 🔍 SKU Explorer
- Deep dive into individual product performance
- Channel-by-channel metrics
- Historical performance

### 10. 📈 Historical Trends
- Month-over-month comparison
- Velocity changes
- Stock level trends
- Growth/decline classification

---

## 📁 Supported File Formats

### Amazon Files
- **Inventory Reports** (CSV/XLSX)
  - Expected columns: `fnsku`, `asin`, `msku`, `title`, `disposition`, `quantity`, etc.
- **Aging Reports** (CSV/XLSX)
  - Expected columns: `fnsku`, `inv-age-0-to-30-days`, `inv-age-31-to-60-days`, etc.
- **Business Reports** (CSV)
  - Sales data mapping by ASIN

### Noon Files
- **Stock Reports** (CSV/XLSX)
  - Expected columns: `partner_sku`, `psku`, `product_name`, `quantity`, etc.
- **Sales Reports** (CSV)
  - Sales data mapping by SKU

### Product Mapping (Required)
- **Mapping Template** (XLSX)
  - Links SKUs across platforms to a unified `Master SKU`
  - Contains `Cost Price` and `Selling Price` for financial calculations
  - Download template from the sidebar

---

## ⚙️ Configuration

### Threshold Settings (Adjustable in UI)

| Setting | Default | Description |
|---------|---------|-------------|
| Safety Stock Days | 30 | Days of sales to keep as buffer |
| Excess Threshold | 90 | DOI above this = excess inventory |
| Stockout Threshold | 14 | DOI below this = stockout risk |

### Liquidation Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Price Elasticity | 1.5 | Demand sensitivity to price changes |
| Target DOI | 45 | Target days after liquidation |

---

## 💾 Session Management

### Saving a Session
1. Upload and process your files
2. Expand "💾 Save This Session" section
3. Enter a name and optional description
4. Click Save

### Loading a Session
1. Open the sidebar
2. Expand "📂 Load Saved Session"
3. Select from dropdown
4. Click Load

Sessions include:
- Processed metrics data
- Aging data
- File metadata
- Threshold settings

---

## 📈 Historical Trends

The dashboard supports two ways to compare historical data:

### Option 1: Multi-Month Upload
Upload files from multiple months in one session. The dashboard will detect and allow comparison between months.

### Option 2: Session History
1. Save your session each month
2. Historical data accumulates automatically
3. Compare any two periods

---

## 🔐 Authentication

The dashboard includes optional password protection:

```python
# In lumive_inventory_complete.py
ALLOWED_USERS = {
    "lumive": "lumive2025",
    "admin": "admin123"
}
```

To disable authentication, comment out the `check_password()` call in `main()`.

---

## 📊 Key Formulas

### Days of Inventory (DOI)
```
DOI = Closing Stock / Daily Velocity
Daily Velocity = Sold Units / Report Duration (or 30 days)
```

### Reorder Quantity
```
Reorder Qty = max(0, (Velocity × Safety Days) - Current Stock - Inbound)
```

### Stock Balancing (Transfer Qty)
```
Transfer Qty = min(Excess Qty Source, Need Qty Destination)
Excess Qty = Stock - (Velocity × Excess Days)
Need Qty = (Velocity × Safety Days) - Stock
```

### Financial Metrics
```
Lost Revenue = Days Out of Stock × Velocity × Selling Price
GMROI = (Price - Cost) × Sold / (Cost × Stock)
Sell-Through Rate (STR) = Sold / (Stock + Sold)
```

### Liquidation Discount
```
Required Velocity = Current Stock / Target DOI
Velocity Increase % = (Required Velocity / Current Velocity - 1) × 100
Discount % = Velocity Increase % / Elasticity
```

### ABC Classification
- **A Items**: Top products contributing to 80% of sales volume
- **B Items**: Next tier contributing to 15% of sales volume
- **C Items**: Remaining products contributing to 5% of sales volume

---

## 🛠️ Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| "No inventory data found" | Ensure files match expected column names |
| Historical trends not showing | Upload multiple months or save sessions |
| High DOI but no reorder | Correct - excess items don't need reorder |
| Session won't load | Check `lumive_data/` folder permissions |
| "KeyError: excess_units" | Fixed in v3.3 by ensuring calculation order |

### Debug Mode
Add `?debug=true` to the URL to see processing details.

---

## 📝 Changelog

### v3.3 (Current)
- ✨ **Inventory Balancing**: Cross-channel transfer recommendations
- ✨ **Financial Intelligence**: Lost Revenue, GMROI, STR, Volatility
- ✨ **Robust Data**: Multi-month sales logic, improved SKU matching
- 🔧 Fixed crashes: `excess_units`, `from_doi`, `trend_matrix`
- 🎨 UI improvements: Sparklines, Gradients, Traffic Light indicators

### v3.2
- ✨ Added Urgent Actions tab (priority-sorted issues)
- ✨ Added Liquidation Pricing calculator
- ✨ Added Session saving/loading
- ✨ Added Historical Trends with multi-month support
- 🔧 Improved DOI calculations with aging data integration

### v3.1
- Multi-channel support (Amazon + Noon, KSA + UAE)
- ABC classification
- Rebalancing recommendations
- Cross-channel view

---

## 📞 Support

For issues or feature requests, contact the Lumive development team.

---

## 📜 License

Proprietary - © 2025 Lumive. All rights reserved.
