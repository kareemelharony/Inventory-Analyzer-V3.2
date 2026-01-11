#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUMIVE Inventory Intelligence Dashboard v3.2
=============================================
Comprehensive inventory management for Amazon + Noon across KSA & UAE

✨ NEW in v3.2:
- Liquidation Pricing: Calculate optimal discount % based on elasticity
- Data Persistence: Save/load sessions to local JSON/Parquet files
- Historical Trends: Compare "This Month vs Last Month" metrics
- Session Management: Save workspace and reload without re-uploading

✨ From v3.1:
- Team authentication system (secure login)
- Upload requirements guide (in app)
- Interactive glossary (20+ inventory terms explained)
- Comprehensive code comments (easy to understand & modify)
- All original features preserved + enhanced

🔐 Default Login Credentials:
- Username: lumive_team
- Password: Lumive@2025

⚡ Features:
- Multi-channel inventory (Amazon + Noon)
- ABC classification by sales volume
- Days of Inventory (DOI) analysis
- Reorder point calculations
- Excess/dead inventory detection with liquidation pricing
- Cross-channel comparison
- Rebalancing opportunities
- Stranded inventory tracking
- Interactive visualizations
- Historical trend analysis

🚀 To Run:
    pip install -r requirements.txt
    streamlit run lumive_inventory_complete.py

📊 Dashboard Includes 10 Tabs:
1. Urgent Actions - Critical issues requiring immediate attention
2. Executive Summary - KPIs and health check
3. Inventory Health - Detailed inventory metrics
4. Reorder & Stockout - What to order and when
5. Dead & Excess - Overstocked items with liquidation pricing
6. Cross-Channel - Same product across all channels
7. Rebalancing - Transfer opportunities
8. Stranded - Unfulfillable inventory
9. SKU Explorer - Deep dive into products
10. Historical Trends - Month-over-month comparison
"""

# =============================================================================
# IMPORTS
# =============================================================================

import io
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import xlsxwriter
import importlib

# Hash for data caching
from pandas.util import hash_pandas_object

# Load styling helper
try:
    from style_helper import apply_styles
except ImportError:
    apply_styles = None

# Database Persistence
import database_manager
from database_manager import (
    DatabaseManager,
    calculate_liquidation_pricing,
    compute_historical_trends,
    get_session_display_name
)

# =============================================================================
# PAGE CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="Lumive Inventory Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# AUTHENTICATION FUNCTION - Check login before showing dashboard
# =============================================================================

def check_password() -> bool:
    """
    Authenticate user with demo credentials before allowing dashboard access.
    Returns True if authenticated, False otherwise.
    
    Demo Credentials:
    - Username: lumive_team
    - Password: Lumive@2025
    
    Easy to customize: Change the credentials below for different users.
    """
    
    def password_entered():
        """Callback when password form is submitted."""
        if (st.session_state.get("username", "") == "lumive_team" and 
            st.session_state.get("password", "") == "Lumive@2025"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    # Initialize session state for authentication tracking
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        # Show login form
        st.markdown("""
        # 🔐 Lumive Inventory Dashboard
        
        ### Secure Team Login
        Enter your credentials to access the dashboard.
        """)
        
        with st.form("login_form"):
            st.text_input(
                "👤 Username",
                key="username",
                placeholder="Enter username"
            )
            st.text_input(
                "🔑 Password",
                type="password",
                key="password",
                placeholder="Enter password"
            )
            st.form_submit_button("🔓 Login", on_click=password_entered)
        
        st.info("""
        **📌 Default Team Credentials:**
        - Username: `lumive_team`
        - Password: `Lumive@2025`
        
        **Need help?** Contact Mai (Operations) or Noha (Marketing)
        """)
        return False
    
    return True


# =============================================================================
# AUTHENTICATION CHECK - Must run first
# =============================================================================

if not check_password():
    st.stop()  # Stop execution if not authenticated


# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

DEFAULT_SAFETY_STOCK_DAYS = 30         # Days of demand to keep as buffer
DEFAULT_EXCESS_THRESHOLD_DAYS = 90     # Days above this = excess stock
DEFAULT_STOCKOUT_THRESHOLD_DAYS = 14   # Days below this = low stock warning
DEFAULT_DEAD_INVENTORY_DAYS = 180      # Days not sold = dead stock

# ABC Thresholds (Pareto principle)
ABC_A_THRESHOLD = 0.80   # A items: top 80% of sales volume
ABC_B_THRESHOLD = 0.95   # B items: 80-95% of sales volume
# C items: remaining 5% of sales volume

# Aging bucket labels for display
AGING_BUCKETS = ['0-30', '31-60', '61-90', '91-180', '181-365', '365+']

# Liquidation Pricing Defaults (v3.2)
DEFAULT_PRICE_ELASTICITY = 1.5    # Moderate elasticity (1.0-2.0 typical for smart home)
LIQUIDATION_TARGET_DOI = 45       # Target DOI after applying discount

# Data Persistence Configuration (v3.2)
DATA_DIR = "lumive_data"          # Local storage folder for sessions and history

# Initialize Database Manager (for session saving and history)
db_manager = DatabaseManager(base_dir=DATA_DIR)


# =============================================================================
# GLOSSARY FUNCTION - Explains inventory management concepts
# =============================================================================

def show_glossary_modal():
    """
    Display interactive glossary explaining inventory management terms
    and concepts used throughout the dashboard.
    
    Covers: Metrics, ABC classification, movement status, channel terms,
    optimization concepts, risk management, and case studies.
    """
    st.markdown("""
    ## 📚 Inventory Management Glossary
    
    ### Core Metrics Explained
    
    **Days of Inventory (DOI)**
    - Formula: `Closing Stock ÷ Daily Velocity`
    - Shows how many days current stock will last at current sales rate
    - Healthy range: 30-60 days (varies by product type)
    - < 14 days = Stockout risk 🚨
    - > 90 days = Excess inventory ⚠️
    
    **Daily Velocity**
    - Average units sold per day
    - Calculated from sales history
    - Used to forecast demand and plan reorders
    - Fast movers (high velocity) = A items (priority)
    
    **Safety Stock**
    - Minimum inventory to prevent stockouts
    - Default: 30 days of demand (configurable)
    - Acts as buffer for demand spikes
    - Balance: Too high = excess, Too low = stockouts
    
    **Reorder Quantity**
    - Units to order when stock depletes
    - Formula: `Max(Safety Stock - Current Stock, 0)`
    - Prevents both over-ordering and under-stocking
    - Shown in "Reorder & Stockout" tab
    
    ---
    
    ### ABC Classification (Pareto Principle)
    
    **A Items (High Value)** - ~5-10% of SKUs, 80% of sales
    - Best sellers, high revenue
    - Strategy: Close monitoring, frequent reorders, minimal safety stock
    
    **B Items (Medium Value)** - ~15-20% of SKUs, 15% of sales
    - Moderate performers
    - Strategy: Balanced approach, monthly reviews
    
    **C Items (Low Value)** - ~70-80% of SKUs, 5% of sales
    - Slow movers, low revenue
    - Strategy: Less frequent reviews, higher safety stock acceptable
    
    ---
    
    ### Movement Status
    
    **Fast Moving** (DOI < 14 days)
    - Quick inventory turnover
    - Low storage risk
    - Strategy: Increase stock slightly to capture more demand
    
    **Slow Moving** (DOI 30-90 days)
    - Sales declining
    - Monitor for obsolescence
    - Strategy: Promotions, bundling, or clearance
    
    **Excess Stock** (DOI > 90 days)
    - Overstocked, will take 3+ months to sell
    - Ties up capital
    - Strategy: Discount, promotion, bundling, or alternative channels
    
    **Dead Stock** (No sales for 180+ days)
    - Likely obsolete
    - Strategy: Write-off, donation, or liquidation
    
    ---
    
    ### Channel-Specific Terms
    
    **FNSKU** (Amazon Fulfillment Network SKU)
    - Amazon's internal product identifier
    - Different from your MSKU
    - Required for FBA tracking
    
    **MSKU** (Merchant SKU)
    - Your internal product code
    - Used in your systems
    - Maps to FNSKU
    
    **Disposition** (Amazon status)
    - Sellable: Normal units, ready to sell
    - Unsellable: Damaged, defective items
    - Unfulfillable: Missing barcode, invalid
    - Restricted: Policy violations
    
    **Fulfillment Type** (Noon)
    - FBN: Noon fulfills from their warehouse
    - Merchant: You fulfill from your location
    
    ---
    
    ### Optimization Concepts
    
    **DOI** (Days of Inventory)
    - Most important metric
    - Balance between too much and too little
    - A items should have lower DOI (fast-moving)
    - C items can have higher DOI (less important)
    
    **Rebalancing**
    - Moving stock between Amazon ↔ Noon (same country)
    - Optimizes based on velocity differences
    - Reduces excess in slow channel, prevents stockouts in fast channel
    
    **Cross-Channel Analysis**
    - View same product across 4 channels:
      Amazon KSA, Amazon UAE, Noon KSA, Noon UAE
    - Identify best-performing channels
    - Optimize inventory allocation
    
    ---
    
    ### Quick Reference Table
    
    | Metric | Formula | Healthy Range | Action if High |
    |--------|---------|---|---|
    | DOI | Stock ÷ Velocity | 30-60 days | Excess, reduce stock |
    | Velocity | Units ÷ Days | Product-specific | N/A |
    | Safety Stock | Velocity × Days | 30 days | Adjust threshold |
    | ABC Class | Revenue % | A>B>C | Rebalance |
    
    ---
    
    ### Real-World Example
    
    **Product:** Smart Door Lock
    - Current Stock: 200 units
    - Daily Velocity: 5 units/day
    - DOI: 200 ÷ 5 = 40 days ✅ (healthy)
    - Safety Stock (30 days): 150 units
    - Status: Normal, no action needed
    
    **If DOI was 150 days:**
    - Would take 5 months to sell out
    - Tied up capital and warehouse space
    - Recommendation: 30% discount promotion
    
    ---
    
    ### Need More Help?
    - Check "📋 Upload Guide" for file instructions
    - Read README.md for full documentation
    - Review code comments for implementation details
    """)


# =============================================================================
# UPLOAD GUIDE FUNCTION - Help team upload correct files
# =============================================================================

def show_upload_requirements():
    """
    Display file upload requirements, naming conventions, and guidelines.
    Helps team members understand which files to upload and how to name them
    to ensure proper auto-detection of country and date.
    """
    st.markdown("## 📋 Upload Requirements & Naming Guide")
    
    with st.expander("📄 **Amazon Inventory File**", expanded=False):
        st.markdown("""
        ### What It Is
        Daily inventory movement report from Amazon Seller Central
        
        ### Where to Get
        1. Login to Amazon Seller Central
        2. Go: Inventory → Manage Inventory
        3. Click: Download Inventory
        4. Format: CSV or Excel
        
        ### Required Columns
        - FNSKU (Fulfillment Network SKU)
        - MSKU (Merchant SKU)
        - Product Name/Title
        - Quantity (or Fulfillable Qty)
        
        ### File Naming (Must Include)
        ✅ **Correct Examples:**
        - `amazon_inventory_KSA_2025-01.csv`
        - `Amazon_Inventory_UAE_January_2025.csv`
        - `inv_amazon_sa_jan_2025.xlsx`
        - `Amazon_KSA_Jan_2025.csv`
        
        ❌ **Avoid These:**
        - `amazon.csv` (no country/month)
        - `inventory_latest.csv` (no date info)
        - `data.csv` (no identifiers)
        
        ### Key Requirements
        - Must include country: **KSA**, **SA**, **UAE**, or **AE**
        - Must include month: Full name (January) or **YYYY-MM** format
        - Must include year: **2025**, **2026**, etc.
        - Platform detected automatically from column names
        """)
    
    with st.expander("🌙 **Noon Inventory File**", expanded=False):
        st.markdown("""
        ### What It Is
        Monthly inventory report from Noon Seller Center
        
        ### Where to Get
        1. Login to Noon Seller Center
        2. Go: Inventory → Active Products
        3. Click: Export or Download
        4. Format: CSV or Excel
        
        ### Required Columns
        - Product Barcode (PBARCODE)
        - Product Title/Name
        - Stock Quantity
        - Fulfillment Type (FBN or Merchant)
        
        ### File Naming (Must Include)
        ✅ **Correct Examples:**
        - `noon_inventory_KSA_2025-01.csv`
        - `Noon_Inventory_UAE_January_2025.csv`
        - `inv_noon_sa_jan_2025.xlsx`
        - `Noon_KSA_Jan_2025.csv`
        
        ❌ **Avoid These:**
        - `noon.csv` (no country/month)
        - `inventory_latest.csv` (unclear)
        - `products.csv` (no identifiers)
        
        ### Key Requirements
        - Must include country: **KSA**, **SA**, **UAE**, or **AE**
        - Must include month: Full name or **YYYY-MM** format
        - Must include year: **2025**, **2026**, etc.
        - Include "noon" in filename to be clear
        """)
    
    with st.expander("⏰ **Monthly Upload Checklist**", expanded=False):
        st.markdown("""
        ### Before Each Month's Upload
        
        **Data Preparation (Day 1-2 of month):**
        - [ ] Export Amazon inventory for KSA
        - [ ] Export Amazon inventory for UAE
        - [ ] Export Noon inventory for KSA
        - [ ] Export Noon inventory for UAE
        
        **File Quality Check:**
        - [ ] All files are in CSV or Excel format
        - [ ] Filenames include country (KSA/UAE)
        - [ ] Filenames include month/year
        - [ ] Files open without errors
        - [ ] Column headers are clear
        
        **Upload & Verification:**
        - [ ] Upload all files to dashboard
        - [ ] Review auto-detected info (country, month, platform)
        - [ ] Check for error messages
        - [ ] Verify data looks reasonable
        
        **After Upload:**
        - [ ] Review dashboard metrics
        - [ ] Share findings with team
        - [ ] Document any issues
        - [ ] Archive files for backup
        """)
    
    st.warning("""
    ⚠️ **Important Notes:**
    1. Remove all confidential pricing/cost information
    2. No need to remove headers or clean data (system handles it)
    3. Larger files: If > 10 MB, split by country
    4. Keep backup of exported files
    5. Use consistent naming across months for easy tracking
    """)


# =============================================================================
# HELPER FUNCTIONS - Normalize and parse data
# =============================================================================

def norm_sku(x) -> str:
    """
    Normalize SKU identifier for matching across systems.
    Converts to uppercase, removes whitespace, handles NaN values.
    
    Args:
        x: SKU value (can be string, number, NaN, None)
    
    Returns:
        Normalized SKU string (uppercase, no spaces) or empty string
    
    Example:
        norm_sku(" B001XYZ ") → "B001XYZ"
        norm_sku(None) → ""
    """
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
        
    s = str(x).strip().upper()
    
    # Handle float-like strings from Excel (e.g., "785571139488.0" -> "785571139488")
    if s.endswith('.0'):
        s = s[:-2]
        
    if not s or s.lower() == 'nan':
        return ""
    return re.sub(r'\s+', '', s)


def parse_int_safe(x) -> float:
    """
    Safely parse integer values from various formats.
    Handles numbers with commas, decimals, text, etc.
    Returns NaN if parsing fails.
    
    Args:
        x: Value to parse (string, number, NaN, etc.)
    
    Returns:
        Float value or NaN if invalid
    
    Example:
        parse_int_safe("1,000") → 1000.0
        parse_int_safe("not_a_number") → NaN
    """
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    try:
        return float(str(x).replace(',', '').strip())
    except:
        return np.nan


def parse_date(x) -> Optional[datetime]:
    """
    Parse date from various formats (MM/DD/YYYY, YYYY-MM-DD, etc.)
    Returns None if parsing fails.
    
    Args:
        x: Date value (string, datetime, etc.)
    
    Returns:
        Datetime object or None if invalid
    """
    if pd.isna(x):
        return None
    try:
        return pd.to_datetime(x)
    except:
        return None


def infer_month_from_filename(filename: str) -> str:
    """
    Extract YYYY-MM from filename patterns.
    Recognizes month names, YYYY-MM format, and other patterns.
    
    Args:
        filename: Filename to parse
    
    Returns:
        YYYY-MM format string or empty string if not found
    
    Examples:
        "amazon_ksa_jan_2025.csv" → "2025-01"
        "report_2025-01-15.xlsx" → "2025-01"
        "inventory_december_2024.csv" → "2024-12"
    """
    filename_lower = filename.lower()
    
    # Month name to number mapping
    months = {
        'jan': '01', 'january': '01',
        'feb': '02', 'february': '02',
        'mar': '03', 'march': '03',
        'apr': '04', 'april': '04',
        'may': '05',
        'jun': '06', 'june': '06',
        'jul': '07', 'july': '07',
        'aug': '08', 'august': '08',
        'sep': '09', 'sept': '09', 'september': '09',
        'oct': '10', 'october': '10', 'ooct': '10',  # Handles typos
        'nov': '11', 'november': '11',
        'dec': '12', 'december': '12'
    }
    
    # Try to find year first (YYYY format)
    year_match = re.search(r'(20\d{2})', filename_lower)
    year = year_match.group(1) if year_match else str(datetime.now().year)
    
    # Try to find month by name
    for month_name, month_num in months.items():
        if re.search(rf'\b{month_name}\b', filename_lower):
            return f"{year}-{month_num}"
    
    # Try YYYY-MM pattern
    ym_match = re.search(r'(20\d{2})[-_](\d{2})', filename_lower)
    if ym_match:
        return f"{ym_match.group(1)}-{ym_match.group(2)}"
    
    return ""


def infer_country_from_filename(filename: str) -> str:
    """
    Extract country (KSA/UAE) from filename.
    Recognizes: KSA, SA, Saudi, UAE, AE, Emirates, etc.
    
    Args:
        filename: Filename to parse
    
    Returns:
        'KSA', 'UAE', or 'Unknown' if not found
    
    Examples:
        "amazon_inventory_KSA_jan.csv" → "KSA"
        "noon_data_emirates_feb.csv" → "UAE"
        "inventory_file.csv" → "Unknown"
    """
    filename_lower = filename.lower()
    if 'ksa' in filename_lower or 'saudi' in filename_lower or '_sa_' in filename_lower:
        return 'KSA'
    if 'uae' in filename_lower or 'emirates' in filename_lower or '_ae_' in filename_lower:
        return 'UAE'
    return 'Unknown'


def infer_channel_from_columns(df: pd.DataFrame) -> str:
    """
    Detect platform (Amazon or Noon) based on column headers.
    
    Args:
        df: Dataframe to analyze
    
    Returns:
        'Amazon', 'Noon', 'Amazon_Aging', or 'Unknown'
    
    Logic:
    - Amazon: Has FNSKU, MSKU, Disposition columns
    - Noon: Has PBARCODE, Fulfillment_Type columns
    - Amazon_Aging: Has aging-related columns
    """
    cols_lower = {c.lower() for c in df.columns}
    
    # Amazon inventory detection
    if 'fnsku' in cols_lower and 'msku' in cols_lower and 'disposition' in cols_lower:
        return 'Amazon'
    
    # Noon inventory detection
    if 'pbarcode' in cols_lower and 'fulfillment_type' in cols_lower:
        return 'Noon'
    
    # Amazon aging report detection
    if 'inv-age-0-to-90-days' in cols_lower or 'units-shipped-t30' in cols_lower:
        return 'Amazon_Aging'
        
    # [NEW] Amazon Business Report Detection
    if '(child) asin' in cols_lower and 'units ordered' in cols_lower:
        return 'Amazon_Business'

    # [NEW] Noon Sales Report Detection
    if 'partner_sku' in cols_lower and 'item_nr' in cols_lower and 'order_timestamp' in cols_lower:
        return 'Noon_Sales'
    
    return 'Unknown'


def load_amazon_business_report(file_content: bytes, filename: str) -> pd.DataFrame:
    """
    Parse Amazon Business Report to get Actual Sales (Units Ordered).
    """
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
        else:
            df = pd.read_excel(io.BytesIO(file_content))
            
        # Clean column names
        df.columns = [str(c).strip() for c in df.columns]
        
        # Verify required columns - ASIN and Units are strictly required
        # Note: Sometimes it's '(Child) ASIN' or just 'ASIN'
        asin_col = next((c for c in df.columns if '(child) asin' in c.lower() or 'asin' == c.lower()), None)
        units_col = next((c for c in df.columns if 'units ordered' in c.lower()), None)
        
        if not asin_col or not units_col:
             # st.warning(f"Skipping {filename}: Could not find ASIN or Units Ordered columns.") # Optional debug
             return pd.DataFrame()

        # Identify optional columns (Sessions, Conversion Rate)
        sessions_col = next((c for c in df.columns if 'sessions' in c.lower() and 'percentage' not in c.lower()), None)
        conv_col = next((c for c in df.columns if 'unit session percentage' in c.lower() or 'conversion' in c.lower()), None)

        # [FIX] Pre-process data for numeric aggregation
        # Convert Units Ordered to numeric, coercing errors to 0
        df[units_col] = pd.to_numeric(df[units_col], errors='coerce').fillna(0)
        
        if sessions_col:
             df[sessions_col] = pd.to_numeric(df[sessions_col], errors='coerce').fillna(0)
             
        if conv_col:
             # Handle percentage strings like "12.5%"
             if df[conv_col].dtype == object:
                 df[conv_col] = df[conv_col].astype(str).str.rstrip('%')
             df[conv_col] = pd.to_numeric(df[conv_col], errors='coerce').fillna(0)
             # If value > 1 (e.g. 12.5 for 12.5%), convert to decimal
             # Heuristic: if max > 1, assume it's percentage points
             if df[conv_col].max() > 1:
                 df[conv_col] = df[conv_col] / 100

        # Prepare aggregation dictionary
        agg_dict = {units_col: 'sum'}
        
        # [NEW] Extract Ordered Product Sales (Revenue)
        sales_amt_col = next((c for c in df.columns if 'ordered product sales' in c.lower() and 'b2b' not in c.lower()), None)
        if sales_amt_col:
             # Clean currency symbols
             if df[sales_amt_col].dtype == object:
                 df[sales_amt_col] = df[sales_amt_col].astype(str).str.replace(r'[^\d.]', '', regex=True)
             df[sales_amt_col] = pd.to_numeric(df[sales_amt_col], errors='coerce').fillna(0)
             agg_dict[sales_amt_col] = 'sum'
             
        if sessions_col:
            agg_dict[sessions_col] = 'sum'
        if conv_col:
            agg_dict[conv_col] = 'mean'

        # Aggregate
        sales_data = df.groupby(asin_col, as_index=False).agg(agg_dict)
        
        # Rename columns to standard 
        rename_map = {
            asin_col: 'asin',
            units_col: 'actual_units_sold'
        }
        if sales_amt_col:
            rename_map[sales_amt_col] = 'actual_sales_amt'
            
        if sessions_col:
            rename_map[sessions_col] = 'sessions'
        if conv_col:
            rename_map[conv_col] = 'conversion_rate'
            
        sales_data.rename(columns=rename_map, inplace=True)
        
        # [NEW] Calculate Average Selling Price (ASP)
        if 'actual_sales_amt' in sales_data.columns:
            sales_data['avg_selling_price'] = np.where(
                sales_data['actual_units_sold'] > 0,
                sales_data['actual_sales_amt'] / sales_data['actual_units_sold'],
                0.0
            )
        else:
            sales_data['avg_selling_price'] = 0.0
        
        # Add missing columns with defaults

        if 'sessions' not in sales_data.columns:
            sales_data['sessions'] = 0
        if 'conversion_rate' not in sales_data.columns:
            sales_data['conversion_rate'] = 0.0

        sales_data['channel'] = 'Amazon'
        
        # [NEW] Calculate duration of the report in days
        report_duration_days = 30 # Default
        if 'date' in df.columns and df['date'].notna().any():
            min_date = df['date'].min()
            max_date = df['date'].max()
            duration = (max_date - min_date).days + 1
            if duration > 0:
                report_duration_days = duration
                
        sales_data['report_days'] = report_duration_days
        sales_month = infer_month_from_filename(filename)
        sales_data['month'] = sales_month
        sales_data['source_file'] = filename
        
        return sales_data
        
    except Exception as e:
        st.error(f"Error parsing Business Report {filename}: {str(e)}")
        return pd.DataFrame()


def load_product_mapping(file_content: bytes, filename: str) -> pd.DataFrame:
    """
    Load Product Master/Mapping file for Cost & Price data.
    """
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
        else:
            df = pd.read_excel(io.BytesIO(file_content))
            
        # Clean column names
        df.columns = [str(c).strip() for c in df.columns]
        
        # Fuzzy Match Columns
        cols = {c.lower(): c for c in df.columns}
        
        # 1. Identifier
        sku_col = next((c for k, c in cols.items() if any(x in k for x in ['sku', 'asin', 'fnsku'])), None)
        
        # 2. Cost
        cost_col = next((c for k, c in cols.items() if any(x in k for x in ['cost', 'cogs', 'cp', 'unit cost'])), None)
        
        # 3. Price
        price_col = next((c for k, c in cols.items() if any(x in k for x in ['selling price', 'price', 'rrp', 'ref price', 'sales price'])), None)
        
        if not sku_col:
            st.warning(f"⚠️ Could not find SKU column in mapping file: {filename}")
            return pd.DataFrame()

        # Rename and clean
        rename_map = {sku_col: 'map_sku'}
        if cost_col: rename_map[cost_col] = 'cost_price'
        if price_col: rename_map[price_col] = 'selling_price'
        
        df = df.rename(columns=rename_map)
        
        # Normalize SKU for matching
        df['map_sku'] = df['map_sku'].apply(norm_sku)
        
        # Clean numeric
        for col in ['cost_price', 'selling_price']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Return only relevant columns
        keep_cols = ['map_sku']
        if 'cost_price' in df.columns: keep_cols.append('cost_price')
        if 'selling_price' in df.columns: keep_cols.append('selling_price')
        
        return df[keep_cols]
        
    except Exception as e:
        st.error(f"Error loading mapping file {filename}: {str(e)}")
        return pd.DataFrame()


def load_noon_sales_report(file_content: bytes, filename: str) -> pd.DataFrame:
    """
    Parse Noon Sales Report to get Actual Sales (Count of Orders).
    """
    try:
        if filename.endswith('.csv'):
            # Noon CSVs often have specific encodings or delimiters, try standard first
            df = pd.read_csv(io.BytesIO(file_content))
        else:
            df = pd.read_excel(io.BytesIO(file_content))
            
        # Clean column names
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        # Verify required columns (partner_sku is key)
        if 'partner_sku' not in df.columns:
            return pd.DataFrame()

        # Count orders per partner_sku 
        # We assume every row is an order item provided it's not cancelled?
        # User said "Use these data for sales", implies using the rows as sales.
        
        if 'partner_sku' not in df.columns:
            return pd.DataFrame()

        # [NEW] Extract Price Column
        price_col = next((c for c in df.columns if any(x in c for x in ['unit_price', 'item_price', 'price'])), None)
        
        # Prepare aggregation
        agg_dict = {'partner_sku': 'count'} # Count rows as units sold
        if price_col:
             # Ensure numeric
             df[price_col] = pd.to_numeric(df[price_col], errors='coerce').fillna(0)
             agg_dict[price_col] = 'mean'
        
        # Group by partner_sku
        # Note: Aggregating price by mean to get avg selling price
        # Renaming 'partner_sku' to 'actual_units_sold' is tricky with agg syntax, so we rely on column renaming after
        
        sales_data = df.groupby('partner_sku').agg(agg_dict).rename(columns={'partner_sku': 'actual_units_sold'})
        
        # If 'actual_units_sold' became index or lost, reset index.
        # groupby().agg() puts partner_sku in index.
        sales_data = sales_data.reset_index()
        
        rename_map = {'partner_sku': 'fnsku', 'actual_units_sold': 'actual_units_sold'} # 'actual_units_sold' col actually named 'partner_sku' in count agg? 
        # Wait, agg output col name for count on partner_sku is partner_sku.
        
        if price_col:
            rename_map[price_col] = 'avg_selling_price'
        
        sales_data.rename(columns=rename_map, inplace=True)
        
        if 'avg_selling_price' not in sales_data.columns:
             sales_data['avg_selling_price'] = 0.0
             
        sales_data['channel'] = 'Noon'
        
        # [NEW] Extract month from filename
        sales_month = infer_month_from_filename(filename)
        sales_data['month'] = sales_month
        sales_data['source_file'] = filename
        
        return sales_data
        
    except Exception as e:
        st.error(f"Error parsing Noon Sales Report {filename}: {str(e)}")
        return pd.DataFrame()


def categorize_product(title: str) -> str:
    """
    Categorize product based on keywords in product title.
    Used to group products by type for analysis and filtering.
    
    Args:
        title: Product title/name
    
    Returns:
        Category name or 'Other'
    
    Examples:
        "Smart Door Lock Pro" → "Door Lock"
        "Bluetooth Tracker Blue" → "Tracker"
        "RGB LED Strip 5m" → "LED Lights"
    """
    if pd.isna(title):
        return 'Other'
    
    title_lower = str(title).lower()
    
    categories = {
        'Door Lock': ['door lock', 'smart lock', 'fingerprint lock', 'deadbolt', 'cylinder'],
        'Tracker': ['tracker', 'airtag', 'bluetooth tracker', 'find my', 'carekit'],
        'LED Lights': ['led strip', 'led light', 'rgb light', 'ceiling light', 'wall light', 'bulb', 'neon'],
        'Smart Switch': ['smart switch', 'light switch', 'touch switch', 'wall switch'],
        'IR Remote': ['ir remote', 'wifi remote', 'ir hub', 'remote control'],
        'Smart Plug': ['smart plug'],
        'Water Flosser': ['water flosser', 'oral cleaner'],
        'Garage Opener': ['garage door', 'garage opener'],
        'Gateway/Hub': ['gateway', 'hub', 'bridge'],
        'Cards/Accessories': ['ic card', 'rfid', 'cards for'],
        'Doorbell': ['doorbell', 'door bell'],
    }
    
    for category, keywords in categories.items():
        if any(kw in title_lower for kw in keywords):
            return category
    
    return 'Other'


def convert_df_to_excel(dfs_dict: Dict[str, pd.DataFrame]) -> bytes:
    """
    Convert multiple dataframes to a single Excel file with multiple tabs.
    Each dataframe becomes a separate sheet with auto-formatted columns.
    
    Args:
        dfs_dict: Dictionary of {sheet_name: dataframe}
    
    Returns:
        Excel file as bytes (ready to download)
    
    Example:
        excel_bytes = convert_df_to_excel({
            'Summary': df1,
            'Reorder': df2,
            'Excess': df3
        })
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for sheet_name, df in dfs_dict.items():
            if df is not None and not df.empty:
                # Clean sheet name (Excel limit: 31 chars, no special chars)
                clean_name = re.sub(r'[^\w\s]', '', sheet_name)[:31]
                df.to_excel(writer, sheet_name=clean_name, index=False)
                
                # Auto-adjust column width for readability
                worksheet = writer.sheets[clean_name]
                for i, col in enumerate(df.columns):
                    max_len = max(
                        df[col].astype(str).map(len).max() if len(df) > 0 else 0,
                        len(str(col))
                    ) + 2
                    worksheet.set_column(i, i, min(max_len, 50))
    
    return output.getvalue()


def create_mapping_template() -> bytes:
    """
    Create a sample mapping template for download.
    Shows users the expected format for SKU mapping files.
    
    Returns:
        Excel template file as bytes
    """
    template_data = pd.DataFrame({
        "ASIN": ["B01EXAMPLE", "B02EXAMPLE"],
        "Product Title": ["Lumive Smart Lock Black 60mm", "Lumive LED Strip 5m RGB"],
        "Short Name": ["Smart Lock Black", "LED Strip 5m"],
        "FNSKU (KSA)": ["X001ABC123", "X001DEF456"],
        "FNSKU (UAE)": ["X002ABC123", "X002DEF456"],
        "Amazon SKU (KSA)": ["LMV-LOCK-BLK", "LMV-LED-5M"],
        "Amazon SKU (UAE)": ["LMV-LOCK-BLK-AE", "LMV-LED-5M-AE"],
        "Noon SKU": ["ZABC123Z-1", "ZDEF456Z-1"],
        "Master SKU": ["LOCK-BLK-60", "LED-RGB-5M"],
        "Available KSA": ["YES", "YES"],
        "Available UAE": ["YES", "NO"]
    })
    
    output = io.BytesIO()
    template_data.to_excel(output, index=False, sheet_name="Product Mapping")
    return output.getvalue()


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FileMetadata:
    """
    Stores metadata extracted from uploaded filename and file analysis.
    
    Attributes:
        filename: Original filename
        channel: Platform detected (Amazon, Noon, Amazon_Aging, Unknown)
        country: Country detected (KSA, UAE, Unknown)
        month: Month detected (YYYY-MM format)
    """
    filename: str
    channel: str
    country: str
    month: str


# =============================================================================
# DATA LOADING FUNCTIONS - With caching for performance
# =============================================================================

@st.cache_data(ttl=3600, show_spinner=False)
def load_mapping_file(file_bytes: bytes) -> Tuple[pd.DataFrame, dict]:
    """
    Load product mapping file and create lookup dictionary.
    Used to match products across channels and systems.
    
    Args:
        file_bytes: Excel file bytes
    
    Returns:
        (dataframe, column_mapping_dict)
    """
    try:
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
        
        # Find the right sheet
        sheet_name = None
        for name in xl.sheet_names:
            if 'product' in name.lower() or 'mapping' in name.lower():
                sheet_name = name
                break
        if sheet_name is None:
            sheet_name = xl.sheet_names[0]
        
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)
        df.columns = [str(c).strip() for c in df.columns]
        
        # Find key columns
        col_mapping = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'asin' in col_lower and 'parent' not in col_lower:
                col_mapping['asin'] = col
            elif 'fnsku' in col_lower and 'ksa' in col_lower:
                col_mapping['fnsku_ksa'] = col
            elif 'fnsku' in col_lower and 'uae' in col_lower:
                col_mapping['fnsku_uae'] = col
            elif 'fnsku' in col_lower:
                col_mapping['fnsku'] = col
            elif 'amazon sku' in col_lower and 'ksa' in col_lower:
                col_mapping['msku_ksa'] = col
            elif 'amazon sku' in col_lower and 'uae' in col_lower:
                col_mapping['msku_uae'] = col
            elif 'msku' in col_lower or 'seller sku' in col_lower:
                col_mapping['msku'] = col
            elif 'noon sku' in col_lower:
                col_mapping['noon_sku'] = col
            elif 'short name' in col_lower:
                col_mapping['short_name'] = col
            elif 'product title' in col_lower or col_lower == 'title':
                col_mapping['title'] = col
            elif 'master' in col_lower and 'sku' in col_lower:
                col_mapping['master_sku'] = col
            # [NEW] Cost & Price Columns
            elif any(x in col_lower for x in ['cost', 'cogs', 'cp', 'unit cost']):
                col_mapping['cost_price'] = col
            elif any(x in col_lower for x in ['selling price', 'price', 'rrp', 'ref price', 'sales price']) and 'cost' not in col_lower:
                col_mapping['selling_price'] = col
             # [NEW] Additional Identifiers
            elif 'additional sku' in col_lower:
                col_mapping['additional_sku'] = col
            elif 'additional barcode' in col_lower:
                col_mapping['additional_barcode'] = col
        
        # [NEW] Ensure numeric types for Cost/Price if found
        if 'cost_price' in col_mapping:
            df[col_mapping['cost_price']] = pd.to_numeric(df[col_mapping['cost_price']], errors='coerce').fillna(0)
        if 'selling_price' in col_mapping:
             df[col_mapping['selling_price']] = pd.to_numeric(df[col_mapping['selling_price']], errors='coerce').fillna(0)
            
        return df, col_mapping
    
    except Exception as e:
        st.error(f"Error loading mapping file: {e}")
        return pd.DataFrame(), {}


@st.cache_data(show_spinner=False)
def load_amazon_inventory(_file_bytes: bytes, filename: str) -> Tuple[pd.DataFrame, FileMetadata]:
    """
    Load Amazon daily inventory movement file.
    Contains daily stock changes, movements, and transactions.
    """
    df = pd.read_csv(io.BytesIO(_file_bytes))
    df.columns = [c.strip() for c in df.columns]
    
    meta = FileMetadata(
        filename=filename,
        channel='Amazon',
        country=infer_country_from_filename(filename),
        month=infer_month_from_filename(filename)
    )
    
    if 'Date' in df.columns:
        df['date'] = pd.to_datetime(df['Date'], errors='coerce')
        if not meta.month and df['date'].notna().any():
            meta.month = df['date'].dropna().iloc[0].strftime('%Y-%m')
    
    # Clean string columns
    for col in ['FNSKU', 'ASIN', 'MSKU', 'Title', 'Disposition', 'Location']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    
    # Parse numeric columns
    num_cols = [
        'Starting Warehouse Balance', 'Ending Warehouse Balance',
        'Receipts', 'Customer Shipments', 'Customer Returns',
        'In Transit Between Warehouses', 'Vendor Returns',
        'Warehouse Transfer In/Out', 'Found', 'Lost', 'Damaged', 'Disposed'
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    return df, meta


@st.cache_data(show_spinner=False)
def load_amazon_aging(_file_bytes: bytes, filename: str) -> Tuple[pd.DataFrame, FileMetadata]:
    """
    Load Amazon aging/inventory health report.
    Contains inventory age distribution and health metrics.
    """
    df = pd.read_csv(io.BytesIO(_file_bytes))
    df.columns = [c.strip().lstrip('\ufeff') for c in df.columns]
    
    meta = FileMetadata(
        filename=filename,
        channel='Amazon_Aging',
        country=infer_country_from_filename(filename),
        month=infer_month_from_filename(filename)
    )
    
    if 'snapshot-date' in df.columns:
        df['snapshot_date'] = pd.to_datetime(df['snapshot-date'], errors='coerce')
        if not meta.month and df['snapshot_date'].notna().any():
            meta.month = df['snapshot_date'].dropna().iloc[0].strftime('%Y-%m')
    
    # Clean string columns
    for col in ['sku', 'fnsku', 'asin', 'product-name']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    
    # Parse numeric aging columns
    num_cols = [
        'available', 'pending-removal-quantity', 'unfulfillable-quantity',
        'inv-age-0-to-30-days', 'inv-age-31-to-60-days', 'inv-age-61-to-90-days',
        'inv-age-0-to-90-days', 'inv-age-91-to-180-days', 
        'inv-age-181-to-270-days', 'inv-age-181-to-330-days',
        'inv-age-271-to-365-days', 'inv-age-331-to-365-days', 'inv-age-365-plus-days',
        'units-shipped-t7', 'units-shipped-t30', 'units-shipped-t60', 'units-shipped-t90',
        'days-of-supply', 'weeks-of-cover-t30', 'weeks-of-cover-t90',
        'qty-to-be-charged-ltsf-6-mo', 'projected-ltsf-6-mo',
        'qty-to-be-charged-ltsf-12-mo', 'estimated-ltsf-next-charge',
        'estimated-storage-cost-next-month', 'estimated-excess-quantity',
        'inbound-quantity', 'inbound-working', 'inbound-shipped', 'inbound-received',
        'Total Reserved Quantity'
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    return df, meta


@st.cache_data(show_spinner=False)
def load_noon_inventory(_file_bytes: bytes, filename: str) -> Tuple[pd.DataFrame, FileMetadata]:
    """
    Load Noon monthly inventory movement file.
    Contains stock levels and movement data for Noon marketplace.
    """
    df = pd.read_csv(io.BytesIO(_file_bytes))
    df.columns = [c.strip().lower() for c in df.columns]
    
    meta = FileMetadata(
        filename=filename,
        channel='Noon',
        country=infer_country_from_filename(filename),
        month=infer_month_from_filename(filename)
    )
    
    # Try to detect country from data if not in filename
    if 'country_code' in df.columns:
        country_codes = df['country_code'].dropna().unique()
        if 'SA' in country_codes:
            meta.country = 'KSA'
        elif 'AE' in country_codes:
            meta.country = 'UAE'
    
    # Clean string columns
    for col in ['pbarcode', 'sku']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    
    # Parse numeric columns
    num_cols = [
        'opening_stock', 'closing_stock', 'in_transit', 'inbound_received',
        'customer_shipment', 'return_reinbound', 'qc_fail_return',
        'warehouse_transfer', 'manual_adjustment', 'damaged', 'lost',
        'disposal_quantity'
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    return df, meta


# =============================================================================
# PROCESSING FUNCTIONS - Main data transformation logic
# =============================================================================

def build_sku_lookup(mapping_df: pd.DataFrame, col_mapping: dict) -> Dict[str, dict]:
    """
    Build SKU lookup dictionary for matching products across channels.
    
    This version builds a multi-key lookup to find products by ANY identifier:
    ASIN, FNSKU (KSA/UAE), MSKU (KSA/UAE), Noon SKU.
    
    Args:
        mapping_df: Product mapping dataframe
        col_mapping: Column name mapping dictionary
    
    Returns:
        Lookup dict: any_sku → {master_sku, title, short_name, etc.}
    """
    lookup = {}
    
    for _, row in mapping_df.iterrows():
        short_name = str(row.get(col_mapping.get('short_name', ''), '')).strip()
        title = str(row.get(col_mapping.get('title', ''), '')).strip()
        master_sku = str(row.get(col_mapping.get('master_sku', ''), '')).strip()
        
        product_info = {
            'short_name': short_name if short_name and short_name.lower() != 'nan' else '',
            'title': title if title and title.lower() != 'nan' else '',
            'master_sku': master_sku if master_sku and master_sku.lower() != 'nan' else ''
        }
        
        # Build lookup with ALL possible keys for this product
        all_keys = [
            'asin', 'fnsku', 'fnsku_ksa', 'fnsku_uae', 'msku', 'msku_ksa', 'msku_uae', 'noon_sku',
            'additional_sku', 'additional_barcode'  # [NEW] Add extra keys
        ]
        
        for col_key in all_keys:
            if col_key in col_mapping:
                val = norm_sku(row.get(col_mapping[col_key], ''))
                if val and val.lower() != 'nan':
                    lookup[val] = product_info
    
    return lookup


@st.cache_data(show_spinner=False)
def process_amazon_inventory(df_hash: str, df: pd.DataFrame, meta_dict: dict) -> pd.DataFrame:
    """
    Process Amazon daily inventory to get monthly summary.
    Original working logic - preserves all calculations.
    """
    if df.empty or 'date' not in df.columns:
        return pd.DataFrame()
    
    min_date = df['date'].min()
    max_date = df['date'].max()
    
    results = []
    for (fnsku, disposition), grp in df.groupby(['FNSKU', 'Disposition']):
        opening_rows = grp[grp['date'] == min_date]
        closing_rows = grp[grp['date'] == max_date]
        opening = opening_rows['Starting Warehouse Balance'].sum() if len(opening_rows) > 0 else 0
        closing = closing_rows['Ending Warehouse Balance'].sum() if len(closing_rows) > 0 else 0
        
        receipts = grp['Receipts'].sum()
        customer_shipments = abs(grp['Customer Shipments'].sum())
        customer_returns = grp['Customer Returns'].sum()
        in_transit = grp['In Transit Between Warehouses'].sum() if 'In Transit Between Warehouses' in grp.columns else 0
        
        first_row = grp.iloc[0]
        
        results.append({
            'channel': 'Amazon',
            'country': meta_dict.get('country', 'Unknown'),
            'month': meta_dict.get('month', ''),
            'fnsku': fnsku,
            'asin': first_row.get('ASIN', ''),
            'msku': first_row.get('MSKU', ''),
            'title': first_row.get('Title', ''),
            'disposition': disposition,
            'opening_stock': opening,
            'closing_stock': closing,
            'receipts': receipts,
            'sold_units': customer_shipments,
            'returns': customer_returns,
            'in_transit': in_transit,
            'source_file': meta_dict.get('filename', '')
        })
    
    return pd.DataFrame(results)


@st.cache_data(show_spinner=False)
def process_amazon_aging(_df_hash: str, df: pd.DataFrame, meta_dict: dict) -> pd.DataFrame:
    """
    Process Amazon aging report: extract complete age distribution and health metrics.
    
    Extracts 30+ fields including:
    - Age buckets (0-30, 31-60, 61-90, 91-180, 181-365, 365+)
    - Units shipped metrics (t7, t30, t60, t90)
    - LTSF (Long-Term Storage Fee) quantities
    - Alerts and recommended actions
    - Excess quantity estimates
    """
    meta = FileMetadata(**meta_dict)
    
    if df.empty:
        return pd.DataFrame()
    
    results = []
    for _, row in df.iterrows():
        # Age buckets with fallback logic
        age_0_30 = row.get('inv-age-0-to-30-days', 0) or 0
        age_31_60 = row.get('inv-age-31-to-60-days', 0) or 0
        age_61_90 = row.get('inv-age-61-to-90-days', 0) or 0
        
        # If no granular 0-30/31-60/61-90, use combined 0-90
        if age_0_30 == 0 and age_31_60 == 0 and age_61_90 == 0:
            age_0_90 = row.get('inv-age-0-to-90-days', 0) or 0
            age_0_30 = age_0_90
        
        age_91_180 = row.get('inv-age-91-to-180-days', 0) or 0
        
        # Age 181-365 with multiple column name variants
        age_181_365 = (row.get('inv-age-181-to-270-days', 0) or 0) + \
                      (row.get('inv-age-271-to-365-days', 0) or 0)
        if age_181_365 == 0:
            age_181_365 = (row.get('inv-age-181-to-330-days', 0) or 0) + \
                          (row.get('inv-age-331-to-365-days', 0) or 0)
        
        age_365_plus = row.get('inv-age-365-plus-days', 0) or 0
        
        results.append({
            'channel': 'Amazon',
            'country': meta.country,
            'month': meta.month,
            'fnsku': str(row.get('fnsku', '')).strip(),
            'asin': str(row.get('asin', '')).strip(),
            'msku': str(row.get('sku', '')).strip(),
            'title': str(row.get('product-name', '')).strip(),
            'available': row.get('available', 0) or 0,
            'unfulfillable': row.get('unfulfillable-quantity', 0) or 0,
            'reserved': row.get('Total Reserved Quantity', 0) or 0,
            'pending_removal': row.get('pending-removal-quantity', 0) or 0,
            'age_0_30': age_0_30,
            'age_31_60': age_31_60,
            'age_61_90': age_61_90,
            'age_91_180': age_91_180,
            'age_181_365': age_181_365,
            'age_365_plus': age_365_plus,
            'units_shipped_t7': row.get('units-shipped-t7', 0) or 0,
            'units_shipped_t30': row.get('units-shipped-t30', 0) or 0,
            'units_shipped_t60': row.get('units-shipped-t60', 0) or 0,
            'units_shipped_t90': row.get('units-shipped-t90', 0) or 0,
            'days_of_supply': row.get('days-of-supply', 0) or 0,
            'weeks_cover_t30': row.get('weeks-of-cover-t30', 0) or 0,
            'weeks_cover_t90': row.get('weeks-of-cover-t90', 0) or 0,
            'ltsf_qty_6mo': row.get('qty-to-be-charged-ltsf-6-mo', 0) or 0,
            'ltsf_qty_12mo': row.get('qty-to-be-charged-ltsf-12-mo', 0) or 0,
            'inbound_total': row.get('inbound-quantity', 0) or 0,
            'inbound_working': row.get('inbound-working', 0) or 0,
            'inbound_shipped': row.get('inbound-shipped', 0) or 0,
            'inbound_received': row.get('inbound-received', 0) or 0,
            'alert': str(row.get('alert', '')).strip(),
            'recommended_action': str(row.get('recommended-action', '')).strip(),
            'excess_quantity': row.get('estimated-excess-quantity', 0) or 0,
            'product_group': str(row.get('product-group', '')).strip(),
            'source_file': meta.filename
        })
    
    return pd.DataFrame(results)


@st.cache_data(show_spinner=False)
def process_noon_inventory(_df_hash: str, df: pd.DataFrame, meta_dict: dict) -> pd.DataFrame:
    """
    Process Noon monthly inventory.
    Original working logic - groups by pbarcode and sums inventory movements.
    """
    if df.empty:
        return pd.DataFrame()
    
    results = []
    for pbarcode, grp in df.groupby('pbarcode'):
        opening = grp['opening_stock'].sum()
        closing = grp['closing_stock'].sum()
        in_transit = grp['in_transit'].sum()
        inbound = grp['inbound_received'].sum()
        sold = abs(grp['customer_shipment'].sum())
        returns = grp['return_reinbound'].sum()
        
        first_row = grp.iloc[0]
        noon_sku = first_row.get('sku', '')
        
        results.append({
            'channel': 'Noon',
            'country': meta_dict.get('country', 'Unknown'),
            'month': meta_dict.get('month', ''),
            'fnsku': pbarcode,
            'asin': '',
            'msku': '',
            'noon_sku': noon_sku,
            'title': '',
            'disposition': 'SELLABLE',
            'opening_stock': opening,
            'closing_stock': closing,
            'receipts': inbound,
            'sold_units': sold,
            'returns': returns,
            'in_transit': in_transit,
            'source_file': meta_dict.get('filename', '')
        })
    
    return pd.DataFrame(results)


def enrich_inventory_data(inv_df: pd.DataFrame, sku_lookup: Dict[str, dict]) -> pd.DataFrame:
    """
    Enrich inventory data with mapping information.
    
    Uses row-by-row matching with multiple fallback keys:
    fnsku, asin, msku, noon_sku - tries each until a match is found.
    
    Args:
        inv_df: Inventory dataframe
        sku_lookup: SKU lookup dictionary
    
    Returns:
        Enriched dataframe with additional columns including:
        - short_name, master_sku from mapping
        - display_name (short_name or truncated title)
        - category from categorize_product()
    """
    if inv_df.empty:
        return inv_df
    
    df = inv_df.copy()
    
    df['short_name'] = ''
    df['master_sku'] = ''
    
    # Row-by-row matching with multiple fallback keys
    for idx, row in df.iterrows():
        keys_to_try = [
            norm_sku(row.get('fnsku', '')),
            norm_sku(row.get('asin', '')),
            norm_sku(row.get('msku', '')),
            norm_sku(row.get('noon_sku', ''))
        ]
        
        for key in keys_to_try:
            if key and key in sku_lookup:
                info = sku_lookup[key]
                df.at[idx, 'short_name'] = info.get('short_name', '')
                df.at[idx, 'master_sku'] = info.get('master_sku', '')
                break
    
    # Create display_name: prefer short_name, else truncated title
    # Create display_name: prefer short_name, else truncated title, else FNSKU
    def get_display_name(row):
        if row.get('short_name'):
            return row['short_name']
        
        title = str(row.get('title', ''))
        if title and title.lower() != 'nan' and title.strip():
             return title[:60] + '...' if len(title) > 60 else title
             
        return row.get('fnsku', 'Unknown Item')

    df['display_name'] = df.apply(get_display_name, axis=1)
    
    # Categorize products based on title keywords
    df['category'] = df['title'].apply(categorize_product)
    
    return df


def calculate_stock_balancing(df: pd.DataFrame, excess_thresh: int, safety_thresh: int) -> pd.DataFrame:
    """
    Identify stock balancing opportunities (Transfers).
    
    Logic: Move From Excess (DOI > Excess Threshold) To Low Stock (DOI < Safety Threshold) 
           for the same product in the same country.
           
    Formulas:
    ---------
    1. Excess Qty = Source Stock - (Source Velocity * Excess Threshold Days)
    2. Need Qty = (Destination Velocity * Safety Stock Days) - Destination Stock
    3. Transfer Qty = MIN(Excess Qty, Need Qty)
    4. Est. Capital Savings = Transfer Qty * Cost Price
    5. Est. Revenue Protected = Transfer Qty * Selling Price
    """
    if df.empty:
        return pd.DataFrame()

    balancing_opps = []
    
    # helper for grouping key
    df['match_key'] = df.apply(
        lambda x: x['master_sku'] if x['master_sku'] else x['short_name'], 
        axis=1
    )
    
    # Filter valid keys
    valid_df = df[df['match_key'] != ''].copy()
    
    # Group by Country + Product
    for (country, match_key), group in valid_df.groupby(['country', 'match_key']):
        if len(group) < 2:
            continue
            
        # Identify sources (Excess) and destinations (Need)
        sources = group[group['is_excess']].copy()
        destinations = group[group['doi'] < safety_thresh].copy()
        
        if sources.empty or destinations.empty:
            continue
            
        # Simplification: Take top source and top destination
        # In reality, could be many-to-many, but we'll do 1-to-1 max match for UI clarity
        
        for _, src in sources.iterrows():
            excess_qty = src['excess_units']
            if excess_qty <= 0: continue
            
            for _, dst in destinations.iterrows():
                if src['channel'] == dst['channel']: continue # No same-channel transfers
                
                # Calculate need
                target_stock = dst['daily_velocity'] * safety_thresh
                current_stock = dst['closing_stock'] + dst['inbound_total']
                need_qty = target_stock - current_stock
                
                if need_qty <= 0: continue
                
                # Transfer amount is min of available excess and needed stock
                transfer_qty = min(excess_qty, need_qty)
                
                if transfer_qty > 0:
                    est_savings = transfer_qty * dst['cost_price'] # Avoid buying new stock
                    est_revenue = transfer_qty * dst['selling_price'] # Protected revenue
                    
                    balancing_opps.append({
                        'match_key': match_key,
                        'display_name': dst['display_name'],
                        'country': country,
                        'from_channel': src['channel'],
                        'to_channel': dst['channel'],
                        'transfer_qty': int(transfer_qty),
                        'est_savings': est_savings,
                        'est_revenue_protected': est_revenue,
                        'from_fnsku': src['fnsku'],
                        'to_fnsku': dst['fnsku'],
                        # [NEW] Fields required for Urgent Actions tab
                        'from_doi': src['doi'],
                        'to_doi': dst['doi'],
                        'from_stock': src['closing_stock'],
                        'to_stock': dst['closing_stock'],
                        'suggested_transfer': int(transfer_qty),
                        'reason': f"Excess in {src['channel']} ({int(src['doi']) if src['doi'] < 10000 else '>365'}d) vs Need in {dst['channel']} ({int(dst['doi']) if dst['doi'] < 10000 else '>365'}d)"
                    })
                    
                    # Decrement source excess to avoid double counting (greedy approach)
                    excess_qty -= transfer_qty
                    if excess_qty <= 0: break
    
    return pd.DataFrame(balancing_opps)

@st.cache_data(show_spinner=False)
def compute_inventory_metrics(inv_df: pd.DataFrame, aging_df: pd.DataFrame,
                              safety_days: int, excess_days: int,
                              sales_df: pd.DataFrame = None,
                              mapping_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Compute key inventory metrics with proper aggregation and aging integration.
    
    This is the core calculation engine that:
    1. Filters to SELLABLE disposition only
    2. Groups by (channel, country, fnsku) with proper aggregations
    3. Merges aging data when available
    4. [NEW] Merges Actual Sales data (sales_df) to override calculated velocity
    5. Uses units_shipped_t30 for velocity when available (if no actual sales)
    6. Calculates aging risk metrics
    
    Formulas:
    ---------
    1. DOI (Days of Inventory) = Closing Stock / Daily Velocity
    2. Estimated Lost Revenue = Days Out of Stock * Daily Velocity * Selling Price
       - Days Out of Stock = 30 - DOI (if DOI < 30)
    3. GMROI = (Margin $) / (Avg Inventory Cost)
       - Margin $ = (Selling Price - Cost Price) * Sold Units
       - Inventory Cost = Closing Stock * Cost Price
    4. Sell-Through Rate (STR) = Sold Units / (Sold Units + Closing Stock)
    """
    if inv_df.empty:
        return pd.DataFrame()
    
    # Filter to SELLABLE disposition only
    df = inv_df[inv_df['disposition'] == 'SELLABLE'].copy()
    
    # CRITICAL: Sort by month FIRST so 'last' gives the latest month's data
    if 'month' in df.columns:
        df = df.sort_values('month').copy()
    
    # Define aggregation - use 'first' for opening, 'last' for closing
    agg_cols = {
        'opening_stock': 'first',
        'closing_stock': 'last',
        'sold_units': 'sum',
        'returns': 'sum',
        'receipts': 'sum',
        'in_transit': 'last',
        'title': 'first',
        'asin': 'first',
        'msku': 'first',
        'short_name': 'first',
        'display_name': 'first',
        'master_sku': 'first',
        'category': 'first',
        'month': 'last'
    }
    
    # Only include columns that exist
    agg_cols = {k: v for k, v in agg_cols.items() if k in df.columns}
    
    # Group by channel, country, fnsku
    df = df.groupby(['channel', 'country', 'fnsku'], as_index=False).agg(agg_cols)
    
    # [NEW] Merge Mapping Data (Cost/Price)
    if mapping_df is not None and not mapping_df.empty:
        # Use a temp column for matching
        df['norm_fnsku'] = df['fnsku'].apply(norm_sku)
        
        # Merge
        df = df.merge(mapping_df, left_on='norm_fnsku', right_on='map_sku', how='left')
        df.drop(columns=['norm_fnsku', 'map_sku'], inplace=True, errors='ignore')
    
    # [FIX] Ensure columns exist even if mapping merge failed or was partial
    for col in ['cost_price', 'selling_price']:
        if col not in df.columns:
            df[col] = 0.0
        
    # Fill missing finance data
    df['cost_price'] = pd.to_numeric(df['cost_price'], errors='coerce').fillna(0.0)
    df['selling_price'] = pd.to_numeric(df['selling_price'], errors='coerce').fillna(0.0)

    # [NEW] Merge Actual Sales Data if available
    df['sales_source'] = 'Calculated' # Default source
    
    if sales_df is not None and not sales_df.empty:
        # We need to merge carefully.
        # Amazon joins on ASIN (because Business Reports use ASIN, and we want to apply to all FNSKUs of that ASIN)
        # However, FNSKU level velocity is better. 
        # But Business Reports are child ASIN level.
        # So we should distribute the sales or just map by ASIN.
        # Ideally, map by ASIN.
        
        # Split sales by channel
        amz_sales = sales_df[sales_df['channel'] == 'Amazon']
        noon_sales = sales_df[sales_df['channel'] == 'Noon']
        
        # 1. Apply Amazon Sales (Match by ASIN)
        if not amz_sales.empty:
             # Aggregate sales by ASIN (in case of duplicates)
             # [NEW] Include avg_selling_price (mean)
             amz_sales_agg = amz_sales.groupby('asin', as_index=False).agg({
                 'actual_units_sold': 'sum',
                 'avg_selling_price': 'mean'
             })
             
             # Merge temporary
             df = df.merge(amz_sales_agg, on='asin', how='left', suffixes=('', '_actual'))
             
             # Apply override for Amazon rows
             mask_amz = (df['channel'] == 'Amazon') & (df['actual_units_sold'].notna())
             if mask_amz.any():
                 df.loc[mask_amz, 'sold_units'] = df.loc[mask_amz, 'actual_units_sold']
                 df.loc[mask_amz, 'sales_source'] = 'Actual (Biz Report)'
                 
                 # [NEW] Override Selling Price from Business Report if available
                 # Only override if the report price > 0
                 mask_price = mask_amz & (df['avg_selling_price'] > 0)
                 df.loc[mask_price, 'selling_price'] = df.loc[mask_price, 'avg_selling_price']
                 
             # Cleanup
             df.drop(columns=['actual_units_sold', 'avg_selling_price'], inplace=True, errors='ignore')


        # 2. Apply Noon Sales (Match by FNSKU)
        if not noon_sales.empty:
             # Noon join on FNSKU
             # [NEW] Include avg_selling_price (mean)
             noon_sales_agg = noon_sales.groupby('fnsku', as_index=False).agg({
                 'actual_units_sold': 'sum',
                 'avg_selling_price': 'mean'
             })
             
             df = df.merge(noon_sales_agg, on='fnsku', how='left', suffixes=('', '_noon'))
             
             mask_noon = (df['channel'] == 'Noon') & (df['actual_units_sold'].notna())
             if mask_noon.any():
                 df.loc[mask_noon, 'sold_units'] = df.loc[mask_noon, 'actual_units_sold']
                 df.loc[mask_noon, 'sales_source'] = 'Actual (Noon Report)'
                 
                 # [NEW] Override Selling Price from Noon Report
                 mask_price_noon = mask_noon & (df['avg_selling_price'] > 0)
                 df.loc[mask_price_noon, 'selling_price'] = df.loc[mask_price_noon, 'avg_selling_price']
                 
             df.drop(columns=['actual_units_sold', 'avg_selling_price'], inplace=True, errors='ignore')

    # Calculate velocity dynamically based on report duration
    # If 'report_days' exists (from Amazon loader), use it. Else default to 30.
    if 'report_days' in df.columns:
        # Use the maximum report days found for the file/group
        # (Handling cases where merge might have varying values, though usually 1 file = 1 val)
        # However, merged DF usually aligns rows.
        # Let's perform row-wise division
        df['daily_velocity'] = df.apply(
            lambda x: x['sold_units'] / x['report_days'] if x['report_days'] > 0 else x['sold_units'] / 30, 
            axis=1
        )
    else:
        # Fallback to previous logic
        days_in_period = 30
        if sales_df is not None and not sales_df.empty and 'month' in sales_df.columns:
            unique_months = sales_df['month'].dropna().nunique()
            if unique_months > 1:
                days_in_period = unique_months * 30
        df['daily_velocity'] = df['sold_units'] / days_in_period
    
    # Calculate DOI (Days of Inventory)
    df['doi'] = np.where(
        df['daily_velocity'] > 0,
        df['closing_stock'] / df['daily_velocity'],
        np.inf
    )
    
    # Merge aging data if available
    if not aging_df.empty:
        # Aggregate aging data
        aging_agg_cols = {
            'available': 'last',
            'unfulfillable': 'sum',
            'reserved': 'last',
            'age_0_30': 'last',
            'age_31_60': 'last',
            'age_61_90': 'last',
            'age_91_180': 'last',
            'age_181_365': 'last',
            'age_365_plus': 'last',
            'units_shipped_t7': 'last',
            'units_shipped_t30': 'last',
            'units_shipped_t90': 'last',
            'days_of_supply': 'last',
            'ltsf_qty_6mo': 'last',
            'inbound_total': 'last',
            'alert': 'last',
            'recommended_action': 'last',
            'excess_quantity': 'last',
            'product_group': 'first'
        }
        
        # Only aggregate columns that exist
        aging_agg_cols = {k: v for k, v in aging_agg_cols.items() if k in aging_df.columns}
        
        if aging_agg_cols:
            aging_agg = aging_df.groupby(['channel', 'country', 'fnsku'], as_index=False).agg(aging_agg_cols)
            df = df.merge(aging_agg, on=['channel', 'country', 'fnsku'], how='left', suffixes=('', '_aging'))
            
            # Use units_shipped_t30 for more accurate velocity when available
            if 'units_shipped_t30' in df.columns:
                df['daily_velocity'] = np.where(
                    df['units_shipped_t30'].fillna(0) > 0,
                    df['units_shipped_t30'] / 30,
                    df['daily_velocity']
                )
                
                # Recalculate DOI with updated velocity
                df['doi'] = np.where(
                    df['daily_velocity'] > 0,
                    df['closing_stock'] / df['daily_velocity'],
                    np.inf
                )
    else:
        # Add empty aging columns if no aging data
        for col in ['age_0_30', 'age_31_60', 'age_61_90', 'age_91_180', 'age_181_365', 'age_365_plus',
                    'unfulfillable', 'ltsf_qty_6mo', 'inbound_total', 'excess_quantity']:
            df[col] = 0
        df['alert'] = ''
        df['recommended_action'] = ''
        df['product_group'] = ''
    
    # Safety stock calculation
    df['safety_stock'] = df['daily_velocity'] * safety_days
    df['reorder_point'] = df['safety_stock']
    df['reorder_qty'] = np.maximum(0, df['reorder_point'] - df['closing_stock'] - df['inbound_total'].fillna(0))
    
    # [NEW] Advanced Financial Metrics
    # 1. Lost Revenue (Monthly Estimate for Stockouts)
    # If Stock is 0, we lose full monthly sales potential? Or proportional?
    # Simple model: Lost Revenue = (Days Out of Stock) * Velocity * Price
    # We estimate stockout days based on DOS. If DOI < 30, projected stockout days = 30 - DOI
    
    df['days_out_of_stock'] = np.where(
        df['closing_stock'] <= 0, 30,
        np.where(df['doi'] < 30, (30 - df['doi']).clip(lower=0), 0)
    )
    
    df['lost_revenue'] = df['days_out_of_stock'] * df['daily_velocity'] * df['selling_price']
    
    # 2. STR (Sell-Through Rate)
    # STR = Sold / (Stock + Sold)
    total_avail = df['closing_stock'] + df['sold_units']
    df['str'] = np.where(total_avail > 0, df['sold_units'] / total_avail, 0)
    
    # 3. GMROI (Gross Margin Return on Investment)
    # Margin $ = (Price - Cost) * Sold
    # Inventory $ = Cost * (Closing Stock)
    df['gross_margin_amt'] = (df['selling_price'] - df['cost_price']) * df['sold_units']
    inventory_val = df['cost_price'] * df['closing_stock']
    
    df['gm_roi'] = np.where(
        inventory_val > 0,
        df['gross_margin_amt'] / inventory_val,
        0
    )

    # 4. Volatility (Placeholder - requires history lookup)
    df['volatility'] = 0.0 
    
    # Risk flags
    df['is_stockout_risk'] = (df['closing_stock'] > 0) & (df['doi'] < DEFAULT_STOCKOUT_THRESHOLD_DAYS) & (df['sold_units'] > 0)
    df['is_excess'] = (df['doi'] > excess_days) & (df['closing_stock'] > 0)
    
    # [NEW] Calculate Excess Units (for Balancing)
    # Excess = Stock - (Target DOI * Velocity)
    # We use excess_days as the threshold. Anything above that is excess.
    df['excess_units'] = np.where(
        df['is_excess'],
        df['closing_stock'] - (df['daily_velocity'] * excess_days),
        0
    )
    
    df['is_dead'] = (df['sold_units'] == 0) & (df['closing_stock'] > 0)
    
    # Movement classification based on actual sales volume
    def classify_movement(row):
        if row['sold_units'] >= 15:
            return 'Fast'
        elif row['sold_units'] >= 5:
            return 'Moving'
        elif row['sold_units'] >= 1:
            return 'Slow'
        else:
            return 'Dead'
    
    df['movement'] = df.apply(classify_movement, axis=1)
    
    # Aging risk calculation
    df['aging_risk_units'] = df.get('age_91_180', pd.Series([0] * len(df))).fillna(0) + \
                             df.get('age_181_365', pd.Series([0] * len(df))).fillna(0) + \
                             df.get('age_365_plus', pd.Series([0] * len(df))).fillna(0)
    df['aging_risk_pct'] = np.where(
        df['closing_stock'] > 0,
        df['aging_risk_units'] / df['closing_stock'] * 100,
        0
    )
    
    return df


def compute_abc_analysis(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute ABC classification based on sales volume (Pareto principle).
    A: 80% of volume, B: 15%, C: 5%
    """
    metrics_df = metrics_df.copy()
    
    # Sort by sold units descending
    metrics_df = metrics_df.sort_values('sold_units', ascending=False).reset_index(drop=True)
    
    # Calculate cumulative percentage
    total_sold = metrics_df['sold_units'].sum()
    metrics_df['cum_pct'] = metrics_df['sold_units'].cumsum() / total_sold
    
    # Assign ABC class
    metrics_df['abc_class'] = 'C'
    metrics_df.loc[metrics_df['cum_pct'] <= ABC_A_THRESHOLD, 'abc_class'] = 'A'
    metrics_df.loc[(metrics_df['cum_pct'] > ABC_A_THRESHOLD) & (metrics_df['cum_pct'] <= ABC_B_THRESHOLD), 'abc_class'] = 'B'
    
    return metrics_df


def compute_cross_channel_view(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create cross-channel view showing same product across all 4 channels.
    
    Creates explicit columns for:
    - Amazon KSA, Amazon UAE, Noon KSA, Noon UAE
    - Each with stock, sold, and DOI metrics
    - Handles missing channels gracefully
    """
    if df.empty:
        return pd.DataFrame()
    
    results = []
    
    for fnsku in df['fnsku'].unique():
        grp = df[df['fnsku'] == fnsku]
        row = {
            'fnsku': fnsku,
            'display_name': grp['display_name'].iloc[0],
            'category': grp['category'].iloc[0] if 'category' in grp.columns else '',
            'abc_class': grp['abc_class'].iloc[0] if 'abc_class' in grp.columns else ''
        }
        
        # Add metrics for each channel/country combination found
        for _, r in grp.iterrows():
            prefix = f"{r['channel']}_{r['country']}"
            row[f"{prefix}_stock"] = r['closing_stock']
            row[f"{prefix}_sold"] = r['sold_units']
            row[f"{prefix}_doi"] = r['doi']
        
        results.append(row)
    
    cross_df = pd.DataFrame(results)
    
    # Ensure all possible channel/country combinations exist
    for channel in ['Amazon', 'Noon']:
        for country in ['KSA', 'UAE']:
            prefix = f"{channel}_{country}"
            for metric in ['stock', 'sold', 'doi']:
                col = f"{prefix}_{metric}"
                if col not in cross_df.columns:
                    cross_df[col] = 0
    
    # Calculate totals across all channels
    cross_df['total_stock'] = (
        cross_df.get('Amazon_KSA_stock', pd.Series([0] * len(cross_df))).fillna(0) +
        cross_df.get('Amazon_UAE_stock', pd.Series([0] * len(cross_df))).fillna(0) +
        cross_df.get('Noon_KSA_stock', pd.Series([0] * len(cross_df))).fillna(0) +
        cross_df.get('Noon_UAE_stock', pd.Series([0] * len(cross_df))).fillna(0)
    )
    
    cross_df['total_sold'] = (
        cross_df.get('Amazon_KSA_sold', pd.Series([0] * len(cross_df))).fillna(0) +
        cross_df.get('Amazon_UAE_sold', pd.Series([0] * len(cross_df))).fillna(0) +
        cross_df.get('Noon_KSA_sold', pd.Series([0] * len(cross_df))).fillna(0) +
        cross_df.get('Noon_UAE_sold', pd.Series([0] * len(cross_df))).fillna(0)
    )
    
    return cross_df


def compute_rebalancing_opportunities(df: pd.DataFrame) -> pd.DataFrame:
    """
    Find rebalancing opportunities within same country.
    
    Identifies two types of opportunities:
    1. Excess → Stockout Risk: Move from channel with excess to one at stockout risk
    2. Velocity Gap: Move from slow-selling channel to fast-selling one
    """
    if df.empty:
        return pd.DataFrame()
    
    opportunities = []
    
    for country in ['KSA', 'UAE']:
        country_df = df[df['country'] == country]
        
        for fnsku in country_df['fnsku'].unique():
            sku_data = country_df[country_df['fnsku'] == fnsku]
            
            if len(sku_data) < 2:
                continue
            
            # Type 1: Excess to Stockout Risk transfer
            excess_channels = sku_data[sku_data['is_excess']]
            stockout_channels = sku_data[sku_data['is_stockout_risk']]
            
            for _, excess_row in excess_channels.iterrows():
                for _, stockout_row in stockout_channels.iterrows():
                    excess_qty = excess_row['closing_stock'] - (excess_row['daily_velocity'] * DEFAULT_EXCESS_THRESHOLD_DAYS)
                    needed_qty = stockout_row['reorder_point'] - stockout_row['closing_stock']
                    transfer_qty = min(max(0, excess_qty), max(0, needed_qty))
                    
                    if transfer_qty > 0:
                        opportunities.append({
                            'country': country,
                            'fnsku': fnsku,
                            'display_name': excess_row['display_name'],
                            'from_channel': excess_row['channel'],
                            'to_channel': stockout_row['channel'],
                            'from_stock': int(excess_row['closing_stock']),
                            'from_doi': round(excess_row['doi'], 1) if not np.isinf(excess_row['doi']) else 999,
                            'to_stock': int(stockout_row['closing_stock']),
                            'to_doi': round(stockout_row['doi'], 1) if not np.isinf(stockout_row['doi']) else 999,
                            'suggested_transfer': int(transfer_qty),
                            'reason': 'Excess → Stockout Risk'
                        })
            
            # Type 2: Velocity gap - move from slow channel to fast channel
            if len(sku_data) >= 2:
                sku_sorted = sku_data.sort_values('daily_velocity', ascending=False)
                fast = sku_sorted.iloc[0]
                slow = sku_sorted.iloc[-1]
                
                # Check: fast channel has low DOI, slow has high DOI, different channels
                if (fast['doi'] < 30 and slow['doi'] > 60 and 
                    fast['channel'] != slow['channel'] and
                    not fast['is_stockout_risk'] and
                    not np.isinf(slow['doi'])):
                    
                    transfer_qty = int(min(
                        slow['closing_stock'] * 0.3,
                        fast['daily_velocity'] * 30
                    ))
                    
                    if transfer_qty >= 5:
                        opportunities.append({
                            'country': country,
                            'fnsku': fnsku,
                            'display_name': fast['display_name'],
                            'from_channel': slow['channel'],
                            'to_channel': fast['channel'],
                            'from_stock': int(slow['closing_stock']),
                            'from_doi': round(slow['doi'], 1),
                            'to_stock': int(fast['closing_stock']),
                            'to_doi': round(fast['doi'], 1) if not np.isinf(fast['doi']) else 999,
                            'suggested_transfer': transfer_qty,
                            'reason': f"Velocity imbalance ({fast['channel']} sells faster)"
                        })
    
    return pd.DataFrame(opportunities)


def get_stranded_inventory(inv_df: pd.DataFrame, aging_df: pd.DataFrame) -> pd.DataFrame:
    """
    Identify stranded/unfulfillable inventory (Amazon-specific).
    """
    if aging_df.empty:
        return pd.DataFrame()
    
    amazon_data = aging_df[aging_df['channel'] == 'Amazon_Aging'].copy()
    
    if amazon_data.empty:
        return pd.DataFrame()
    
    stranded = []
    
    for idx, row in amazon_data.iterrows():
        unfulfillable = row.get('unfulfillable-quantity', 0) if 'unfulfillable-quantity' in aging_df.columns else 0
        
        if unfulfillable > 0:
            stranded.append({
                'fnsku': row.get('fnsku', ''),
                'display_name': row.get('product-name', ''),
                'quantity': unfulfillable,
                'disposition': 'Unfulfillable',
                'channel': 'Amazon',
                'country': row.get('country', 'Unknown')
            })
    
    return pd.DataFrame(stranded)


# =============================================================================
# MAIN APPLICATION STARTS HERE
# =============================================================================

st.markdown("# 📦 Lumive Inventory Intelligence Dashboard v3.2")
st.markdown("*Smart inventory management for Amazon + Noon (KSA & UAE)*")

# =============================================================================
# SIDEBAR - Navigation and help tools
# =============================================================================

with st.sidebar:
    st.markdown("### 🛠️ Tools & Resources")
    
    # Show upload guide toggle
    show_guide = st.checkbox("📋 Show Upload Guide", value=False)
    
    # Show glossary toggle
    show_glossary = st.checkbox("📚 Show Glossary", value=False)
    
    # Download mapping template
    st.markdown("---")
    st.markdown("### 📥 Download Templates")
    
    mapping_template = create_mapping_template()
    st.download_button(
        label="📋 Download SKU Mapping Template",
        data=mapping_template,
        file_name="sku_mapping_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.markdown("---")
    st.markdown("### 👥 Status")
    st.success("✅ Team Access Granted")
    st.caption(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # =========================================================================
    # SESSION MANAGEMENT (v3.2)
    # =========================================================================
    st.markdown("---")
    st.markdown("### 💾 Session Management")
    
    # Load saved session
    saved_sessions = db_manager.list_sessions()
    if saved_sessions:
        with st.expander("📂 Load Saved Session", expanded=False):
            session_options = ["-- Select Session --"] + [
                get_session_display_name(s) for s in saved_sessions
            ]
            selected_session_display = st.selectbox(
                "Choose session",
                session_options,
                key="load_session_select"
            )
            
            if selected_session_display != "-- Select Session --":
                # Extract session name from display
                session_name = selected_session_display.split(" (")[0]
                
                col_load, col_del = st.columns(2)
                with col_load:
                    if st.button("📂 Load", key="load_session_btn"):
                        loaded_data = db_manager.load_session(session_name)
                        if loaded_data:
                            st.session_state['loaded_session'] = loaded_data
                            st.session_state['loaded_session_name'] = session_name
                            st.success(f"✅ Loaded: {session_name}")
                            st.rerun()
                        else:
                            st.error("❌ Failed to load session")
                
                with col_del:
                    if st.button("🗑️ Delete", key="delete_session_btn"):
                        if db_manager.delete_session(session_name):
                            st.success(f"🗑️ Deleted: {session_name}")
                            st.rerun()
    else:
        st.caption("No saved sessions yet")
    
    # Check if using loaded session
    if 'loaded_session' in st.session_state:
        st.info(f"📂 Using: {st.session_state.get('loaded_session_name', 'Loaded Session')}")
        if st.button("❌ Clear Loaded Session", key="clear_session"):
            del st.session_state['loaded_session']
            if 'loaded_session_name' in st.session_state:
                del st.session_state['loaded_session_name']
            st.rerun()


# Display guides if selected
if show_guide:
    st.markdown("---")
    show_upload_requirements()
    st.markdown("---")

if show_glossary:
    st.markdown("---")
    show_glossary_modal()
    st.markdown("---")


# =============================================================================
# FILE UPLOAD SECTION
# =============================================================================

st.subheader("📤 Upload Your Inventory Files")

st.info("""
📌 **Instructions:**
1. Prepare files: Export from Amazon Seller Central or Noon Seller Center
2. Name files correctly: Include country (KSA/UAE) and month (Jan/Feb or YYYY-MM)
3. Upload: Select multiple files at once
4. System auto-detects: Country, platform, month from filename and columns
5. Review: Check detection results below
6. Analyze: Use tabs to explore insights

💡 **Need help?** Click "📋 Show Upload Guide" in the sidebar
""")

# Create four columns for different file types
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("#### Amazon Inventory")
    amazon_inv_files = st.file_uploader(
        "Upload Amazon inventory files",
        type=['csv', 'xlsx'],
        accept_multiple_files=True,
        key='amazon_inv',
        help="Daily inventory movement from Seller Central"
    )

with col2:
    st.markdown("#### Amazon Aging")
    amazon_aging_files = st.file_uploader(
        "Upload Amazon aging reports",
        type=['csv', 'xlsx'],
        accept_multiple_files=True,
        key='amazon_aging',
        help="Aging/Health report from Seller Central"
    )

with col3:
    st.markdown("#### Noon Inventory")
    noon_inv_files = st.file_uploader(
        "Upload Noon inventory files",
        type=['csv', 'xlsx'],
        accept_multiple_files=True,
        key='noon_inv',
        help="Monthly inventory from Seller Center"
    )

with col4:
    st.markdown("#### 📊 Sales Reports")
    sales_files = st.file_uploader(
        "Upload Sales/Business Reports",
        type=['csv', 'xlsx'],
        accept_multiple_files=True,
        key='sales_reports',
        help="Amazon Business Reports or Noon Sales Reports for accurate velocity"
    )

st.markdown("---")

# Product mapping file (required)
st.subheader("🔗 Product Mapping File (Required)")
st.caption("Links your internal SKUs to FNSKU/MSKU across channels")

mapping_file = st.file_uploader(
    "Upload your product mapping file",
    type=['xlsx', 'xls', 'csv'],
    help="Excel/CSV file with SKU, Cost, and Price columns. Download template in sidebar →"
)

# Check for minimum required files (or loaded session)
use_loaded_session = 'loaded_session' in st.session_state and st.session_state['loaded_session'] is not None

if not use_loaded_session:
    if not mapping_file:
        st.info("👈 Upload your Product Mapping file (Excel) to get started.")
        st.info("💡 Or load a saved session from the sidebar →")
        st.stop()
    
    if not amazon_inv_files and not noon_inv_files:
        st.info("👈 Upload at least one inventory file (Amazon or Noon).")
        st.info("💡 Or load a saved session from the sidebar →")
        st.stop()

# =============================================================================
# LOAD AND PROCESS FILES (or use loaded session)
# =============================================================================

st.markdown("---")

# Check if using a loaded session
if use_loaded_session:
    st.subheader("📂 Using Saved Session")
    loaded = st.session_state['loaded_session']
    
    # Extract data from loaded session
    metrics_df = loaded.get('metrics_df', pd.DataFrame())
    aging_df = loaded.get('aging_df', pd.DataFrame())
    # Sales DF might not exist in old sessions, handle gracefully
    sales_df = pd.DataFrame() 
    session_settings = loaded.get('settings', {})
    file_metadata_list = loaded.get('file_metadata', [])
    
    # Convert file_metadata dicts back to FileMetadata objects if needed
    file_metadata = []
    for fm in file_metadata_list:
        if isinstance(fm, dict):
            file_metadata.append(FileMetadata(
                filename=fm.get('filename', ''),
                channel=fm.get('channel', ''),
                country=fm.get('country', ''),
                month=fm.get('month', '')
            ))
        else:
            file_metadata.append(fm)
    
    # Skip to metrics computation (metrics_df already loaded)
    inv_df = pd.DataFrame()  # Empty, we use metrics_df directly
    
    st.success(f"✅ Loaded {len(metrics_df)} SKUs from saved session")
    
    # Show session info
    session_info = loaded.get('session_info', {})
    if session_info:
        st.caption(f"📅 Saved: {session_info.get('created_at', 'Unknown')[:16]}")
        if session_info.get('description'):
            st.caption(f"📝 {session_info.get('description')}")

else:
    # Normal file processing
    
    # Initialize or get processing state
    if 'processed_files_list' not in st.session_state:
        st.session_state['processed_files_list'] = []
    if 'needs_recalculation' not in st.session_state:
        st.session_state['needs_recalculation'] = True
    
    # Count current files
    current_file_count = (
        len(amazon_inv_files or []) + 
        len(amazon_aging_files or []) + 
        len(noon_inv_files or []) + 
        len(sales_files or [])
    )
    
    # Check if files changed
    if 'last_file_count' not in st.session_state:
        st.session_state['last_file_count'] = 0
    
    if current_file_count != st.session_state['last_file_count']:
        st.session_state['needs_recalculation'] = True
        st.session_state['last_file_count'] = current_file_count
    
    # Show file summary and recalculate button
    file_summary_col, recalc_col = st.columns([3, 1])
    
    with file_summary_col:
        st.markdown(f"**📁 {current_file_count} files uploaded** - Ready to process")
    
    with recalc_col:
        # Auto-recalculate is annoying, add explicit button
        if st.button("🔄 Recalculate", key="recalculate_btn", type="primary"):
            st.session_state['needs_recalculation'] = True
            st.session_state['processed_files_list'] = []
            st.rerun()
    
    # Process files
    processed_files_log = []
    
    # Load mapping (Legacy for names)
    mapping_df, col_mapping = load_mapping_file(mapping_file.getvalue())
    sku_lookup = build_sku_lookup(mapping_df, col_mapping)
    
    # [FIX] Load mapping (Financial for Cost/Price)
    # Re-load using the new specialized function that creates 'map_sku', 'cost_price', 'selling_price'
    financial_mapping_df = load_product_mapping(mapping_file.getvalue(), mapping_file.name)
    
    # Process all files
    all_inventory = []
    all_aging = []
    all_sales = []
    file_metadata = []
    
    # Process Amazon inventory files
    for f in amazon_inv_files or []:
        df, meta = load_amazon_inventory(f.getvalue(), f.name)
        df_hash = str(hash(f.getvalue()))
        meta_dict = {
            'filename': meta.filename,
            'channel': meta.channel,
            'country': meta.country,
            'month': meta.month
        }
        processed = process_amazon_inventory(df_hash, df, meta_dict)
        if not processed.empty:
            processed = enrich_inventory_data(processed, sku_lookup)
            all_inventory.append(processed)
            file_metadata.append(meta)
            processed_files_log.append({
                'file': f.name,
                'type': 'Amazon Inventory',
                'country': meta.country,
                'month': meta.month,
                'skus': len(processed),
                'status': '✅ Processed'
            })
    
    # Process Amazon aging files
    for f in amazon_aging_files or []:
        df, meta = load_amazon_aging(f.getvalue(), f.name)
        df_hash = str(hash(f.getvalue()))
        meta_dict = {
            'filename': meta.filename,
            'channel': meta.channel,
            'country': meta.country,
            'month': meta.month
        }
        processed = process_amazon_aging(df_hash, df, meta_dict)
        if not processed.empty:
            all_aging.append(processed)
            file_metadata.append(meta)
            processed_files_log.append({
                'file': f.name,
                'type': 'Amazon Aging',
                'country': meta.country,
                'month': meta.month,
                'skus': len(processed),
                'status': '✅ Aging Data'
            })
    
    # Process Noon inventory files
    for f in noon_inv_files or []:
        df, meta = load_noon_inventory(f.getvalue(), f.name)
        df_hash = str(hash(f.getvalue()))
        meta_dict = {
            'filename': meta.filename,
            'channel': meta.channel,
            'country': meta.country,
            'month': meta.month
        }
        processed = process_noon_inventory(df_hash, df, meta_dict)
        if not processed.empty:
            processed = enrich_inventory_data(processed, sku_lookup)
            all_inventory.append(processed)
            file_metadata.append(meta)
            processed_files_log.append({
                'file': f.name,
                'type': 'Noon Inventory',
                'country': meta.country,
                'month': meta.month,
                'skus': len(processed),
                'status': '✅ Processed'
            })

    # [NEW] Process Sales Reports
    for f in sales_files or []:
        # Auto-detect type by reading first few lines internally or similar? 
        # But we added detection logic based on columns in load functions wrapper if available
        # or we just try both.
        
        # Simple detection by extension/content
        content = f.getvalue()
        try:
             # Just try both or detect by columns directly
             if f.name.endswith('.csv'):
                 sample_df = pd.read_csv(io.BytesIO(content), nrows=5)
             else:
                 sample_df = pd.read_excel(io.BytesIO(content), nrows=5)
             
             cols_lower = [str(c).lower().strip() for c in sample_df.columns]
             
             processed_sales = pd.DataFrame()
             report_type = "Unknown"
             
             if '(child) asin' in cols_lower and 'units ordered' in cols_lower:
                 processed_sales = load_amazon_business_report(content, f.name)
                 report_type = "Amazon Business Report"
             elif 'partner_sku' in cols_lower or 'item_nr' in cols_lower:
                 # Noon
                 processed_sales = load_noon_sales_report(content, f.name)
                 report_type = "Noon Sales Report"
             
             if not processed_sales.empty:
                 all_sales.append(processed_sales)
                 processed_files_log.append({
                    'file': f.name,
                    'type': report_type,
                    'country': 'Unknown', # Could infer from filename
                    'month': 'Actual Sales',
                    'skus': len(processed_sales),
                    'status': '✅ Sales Data'
                 })
                 
        except Exception as e:
            st.error(f"Error checking file {f.name}: {e}")

    
    # Show processed files in a compact expander
    with st.expander(f"📋 Processed Files ({len(processed_files_log)} files)", expanded=False):
        if processed_files_log:
            files_df = pd.DataFrame(processed_files_log)
            st.dataframe(
                files_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    'file': st.column_config.TextColumn("Filename", width="large"),
                    'type': st.column_config.TextColumn("Type"),
                    'country': st.column_config.TextColumn("Country"),
                    'month': st.column_config.TextColumn("Month"),
                    'skus': st.column_config.NumberColumn("SKUs", format="%d"),
                    'status': st.column_config.TextColumn("Status")
                }
            )
        else:
            st.warning("No files processed yet")
    
    # Combine all data
    inv_df = pd.concat(all_inventory, ignore_index=True) if all_inventory else pd.DataFrame()
    aging_df = pd.concat(all_aging, ignore_index=True) if all_aging else pd.DataFrame()
    sales_df = pd.concat(all_sales, ignore_index=True) if all_sales else pd.DataFrame()
    
    if inv_df.empty:
        st.error("❌ No inventory data could be processed. Check your files.")
        st.stop()
    
    # Set metrics_df to None to indicate it needs to be computed
    metrics_df = None

# Compute metrics (or use loaded metrics from session)
st.markdown("---")

# [NEW] Data Quality Traffic Light
if pd.notna(metrics_df) is False: # Only show during fresh calc
    st.markdown("### 🚦 Data Quality Status")
    col_q1, col_q2, col_q3 = st.columns(3)
    
    with col_q1:
        if 'financial_mapping_df' in locals() and not financial_mapping_df.empty:
            st.markdown("🟢 **Financial Data**: Active")
        else:
            st.markdown("🔴 **Financial Data**: Missing Cost/Price")
            
    with col_q2:
        # Check if sales data was loaded
        if 'sales_df' in locals() and not sales_df.empty:
            st.markdown("🟢 **Sales Data**: Actual Reports")
        else:
            st.markdown("🟡 **Sales Data**: Calculated (Approx)")
            
    with col_q3:
        st.markdown("🟢 **Inventory**: Loaded")
        
    st.divider()

st.subheader("⚙️ Adjust Thresholds & Scope")

# [NEW] Sidebar Month Filter Integration
# We need to filter BEFORE computation to ensure aggregates are correct based on user selection
all_available_months = set()
if 'month' in inv_df.columns:
    all_available_months.update(inv_df['month'].dropna().unique())
if 'month' in sales_df.columns:
    all_available_months.update(sales_df['month'].dropna().unique())

selected_months = sorted(list(all_available_months))

# Add filter to sidebar if months exist
if selected_months:
    with st.sidebar:
        st.markdown("### 📅 Analysis Period")
        # Default to all months selected
        selected_analysis_months = st.multiselect(
            "Select Months to Include",
            options=selected_months,
            default=selected_months,
            help="Uncheck months to exclude them from calculations"
        )
else:
    selected_analysis_months = []

# Apply Month Filter to Dataframes BEFORE Computation
if selected_analysis_months:
    # Filter Inventory
    if 'month' in inv_df.columns:
        inv_df = inv_df[inv_df['month'].isin(selected_analysis_months)].copy()
    
    # Filter Sales
    if 'month' in sales_df.columns:
        sales_df = sales_df[sales_df['month'].isin(selected_analysis_months)].copy()
        
    # Recalculate if empty after filter
    if inv_df.empty:
        st.warning("⚠️ No data available for the selected months.")
        st.stop()

col1, col2 = st.columns(2)
with col1:
    safety_days = st.slider(
        "Safety Stock Days",
        7, 90, DEFAULT_SAFETY_STOCK_DAYS,
        help="Days of sales to keep as safety buffer"
    )
with col2:
    excess_days = st.slider(
        "Excess Threshold (Days)",
        30, 365, DEFAULT_EXCESS_THRESHOLD_DAYS,
        help="DOI above this = excess inventory"
    )

# Compute or use loaded metrics
if metrics_df is None:
    # Fresh data - compute metrics
    with st.spinner("Computing inventory metrics..."):
        
        # [FIX] Handle Multi-Month Uploads
        # If multiple months are present, compute metrics for each month separately
        # Save them to history, and use the LATEST month as the current metrics_df
        
        if 'month' in inv_df.columns and inv_df['month'].nunique() > 1:
            months = sorted(inv_df['month'].dropna().unique())
            st.info(f"📅 Multi-month upload detected: {', '.join(months)}. Processing historical trends...")
            
            # 1. PROCESS HISTORY: Save each month individually to the database
            for m in months:
                # Filter data for this month
                month_inv = inv_df[inv_df['month'] == m].copy()
                
                # Filter sales data for this month (if available)
                month_sales = None
                if not sales_df.empty and 'month' in sales_df.columns:
                    month_sales = sales_df[sales_df['month'] == m].copy()
                
                # Compute metrics for this month using ACTUAL sales if available
                m_metrics = compute_inventory_metrics(month_inv, aging_df, safety_days, excess_days, sales_df=month_sales, mapping_df=financial_mapping_df)
                
                if not m_metrics.empty:
                    # Save to history automatically
                    db_manager.save_history(m_metrics, m)
            
            # 2. COMPUTE DASHBOARD METRICS: Use ALL data aggregated
            
            # This ensures 'sold_units' sums up across all uploaded months (e.g. Oct+Nov+Dec sales)
            # while 'closing_stock' takes the latest month's value due to the 'last' aggregation in compute_metrics
            metrics_df = compute_inventory_metrics(inv_df, aging_df, safety_days, excess_days, sales_df, mapping_df=financial_mapping_df)
            st.success(f"✅ Aggregated data from {len(months)} months. Current stock based on {months[-1]}.")

        else:
            # Single month or no month column
            metrics_df = compute_inventory_metrics(inv_df, aging_df, safety_days, excess_days, sales_df, mapping_df=financial_mapping_df)
            
        metrics_df = compute_abc_analysis(metrics_df)
else:
    # Using loaded metrics from session
    # Ensure ABC classification exists
    if 'abc_class' not in metrics_df.columns:
        metrics_df = compute_abc_analysis(metrics_df)

# [NEW] Enrich with Historical Trends (Volatility & Sparklines)
with st.spinner("Fetching historical trends..."):
    try:
        if 'db_manager' in locals():
            trend_df = db_manager.get_trend_matrix()
            if not trend_df.empty:
                # Identify sales columns (YYYY-MM)
                sales_cols = [c for c in trend_df.columns if re.match(r'\d{4}-\d{2}', str(c))]
                
                if sales_cols:
                    # 1. Volatility (CV)
                    trend_vals = trend_df[sales_cols].fillna(0)
                    mean_vals = trend_vals.mean(axis=1).replace(0, 1) # avoid div by 0
                    trend_df['volatility'] = trend_vals.std(axis=1) / mean_vals
                    
                    # 2. Sparkline (List of floats)
                    trend_df['sparkline'] = trend_vals.values.tolist()
                    
                    # Reset index to merge (channel, country, fnsku are index)
                    trend_reset = trend_df[['volatility', 'sparkline']].reset_index()
                    
                    # Merge
                    match_cols = ['channel', 'country', 'fnsku']
                    # Ensure matching types (strip just in case)
                    metrics_df = metrics_df.merge(trend_reset, on=match_cols, how='left')
                    
                    # Fill NaNs
                    metrics_df['volatility'] = metrics_df['volatility'].fillna(0.0)
                    # Sparkline must be list
                    metrics_df['sparkline'] = metrics_df['sparkline'].apply(lambda x: x if isinstance(x, list) else [])
                    
    except Exception as e:
        st.warning(f"Could not load trends: {str(e)}")

# Compute derived views
cross_channel_df = compute_cross_channel_view(metrics_df)
rebalancing_df = compute_rebalancing_opportunities(metrics_df)
stranded_df = get_stranded_inventory(inv_df, aging_df) if not inv_df.empty else pd.DataFrame()

st.success(f"✅ Successfully processed {len(metrics_df)} unique SKUs")

# Show loaded files info
if file_metadata:
    with st.expander("📄 Loaded Files Summary", expanded=False):
        files_info = pd.DataFrame([{
            'Filename': m.filename,
            'Channel': m.channel,
            'Country': m.country,
            'Month': m.month
        } for m in file_metadata])
        st.dataframe(files_info, use_container_width=True, hide_index=True)

# =============================================================================
# SAVE SESSION OPTION (v3.2) - After processing, before filters
# =============================================================================

if not use_loaded_session:
    with st.expander("💾 Save This Session", expanded=False):
        st.caption("Save your current workspace to reload later without re-uploading files")
        
        save_col1, save_col2 = st.columns([2, 1])
        with save_col1:
            new_session_name = st.text_input(
                "Session Name",
                value=f"Session_{datetime.now().strftime('%Y%m%d')}",
                key="save_session_name"
            )
        with save_col2:
            save_description = st.text_input(
                "Description (optional)",
                placeholder="e.g., January data",
                key="save_session_desc"
            )
        
        if st.button("💾 Save Session", key="save_session_btn"):
            # Prepare file metadata for serialization
            file_metadata_dicts = [{
                'filename': m.filename,
                'channel': m.channel,
                'country': m.country,
                'month': m.month
            } for m in file_metadata]
            
            session_data = {
                'metrics_df': metrics_df,
                'aging_df': aging_df,
                'file_metadata': file_metadata_dicts,
                'settings': {
                    'safety_days': safety_days,
                    'excess_days': excess_days
                }
            }
            
            if db_manager.save_session(new_session_name, session_data, save_description):
                # Also save to history for trend analysis
                current_month = metrics_df['month'].max() if 'month' in metrics_df.columns else datetime.now().strftime('%Y-%m')
                db_manager.save_history(metrics_df, current_month)
                
                st.success(f"✅ Session saved: {new_session_name}")
                st.caption("📊 Historical data also saved for trend analysis")
            else:
                st.error("❌ Failed to save session")

# =============================================================================
# FILTERS (Moved to Sidebar)
# =============================================================================

with st.sidebar:
    st.markdown("---")
    st.subheader("🔍 Global Filters")
    
    channels = sorted(metrics_df['channel'].unique())
    selected_channels = st.multiselect("Channel", channels, default=channels)

    countries = sorted(metrics_df['country'].unique())
    selected_countries = st.multiselect("Country", countries, default=countries)

    categories = sorted(metrics_df['category'].dropna().unique())
    selected_categories = st.multiselect("Category", categories, default=categories)
    
    st.markdown("---")
    search_term = st.text_input("🔍 Search SKU/Name", help="Search by FNSKU or Product Name")

# Apply filters
filtered_df = metrics_df[
    (metrics_df['channel'].isin(selected_channels)) &
    (metrics_df['country'].isin(selected_countries)) &
    (metrics_df['category'].isin(selected_categories))
].copy()

if search_term:
    search_lower = search_term.lower()
    filtered_df = filtered_df[
        filtered_df['fnsku'].str.lower().str.contains(search_lower, na=False) |
        filtered_df['display_name'].str.lower().str.contains(search_lower, na=False)
    ]

# [NEW] Calculate Stock Balancing globally (used in Tab 0 and Tab 3)
# Depends on filtered_df, excess_days, safety_days
if 'excess_days' not in locals(): excess_days = DEFAULT_EXCESS_THRESHOLD_DAYS
if 'safety_days' not in locals(): safety_days = DEFAULT_SAFETY_STOCK_DAYS

rebalancing_df = calculate_stock_balancing(filtered_df, excess_days, safety_days)

# =============================================================================
# TABS
# =============================================================================

st.markdown("---")
st.subheader("📊 Analysis Tabs")

tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "🚨 Urgent Actions",
    "📊 Executive Summary",
    "🏥 Inventory Health",
    "🔄 Reorder & Stockout",
    "💀 Dead & Excess",
    "🌐 Cross-Channel",
    "⚖️ Rebalancing",
    "🚫 Stranded",
    "🔍 SKU Explorer",
    "📈 Historical Trends"
])

# =============================================================================
# TAB 0: URGENT ACTIONS (v3.2 - Priority View)
# =============================================================================

with tab0:
    st.subheader("🚨 Urgent Actions Required")
    st.caption("Critical inventory issues requiring immediate attention - sorted by priority")
    
    urgent_items = []
    
    # 1. CRITICAL STOCKOUT RISK (DOI < 7 days with sales)
    critical_stockout = filtered_df[
        (filtered_df['doi'] < 7) & 
        (filtered_df['doi'] > 0) & 
        (filtered_df['sold_units'] > 0) &
        (filtered_df['closing_stock'] > 0)
    ].copy()
    
    for _, row in critical_stockout.iterrows():
        urgent_items.append({
            'priority': 1,
            'priority_label': '🔴 CRITICAL',
            'action_type': 'Stockout Imminent',
            'product': row.get('display_name', row['fnsku']),
            'channel': row['channel'],
            'country': row['country'],
            'current_stock': int(row['closing_stock']),
            'doi': round(row['doi'], 1),
            'daily_velocity': round(row['daily_velocity'], 2),
            'recommended_action': f"Reorder {int(row.get('reorder_qty', 0))} units immediately",
            'impact': 'Lost sales if not acted on'
        })
    
    # 2. SEVERE EXCESS (DOI > 365 days) - needs aggressive liquidation
    severe_excess = filtered_df[
        (filtered_df['doi'] > 365) & 
        (filtered_df['closing_stock'] > 0)
    ].copy()
    
    for _, row in severe_excess.iterrows():
        result = calculate_liquidation_pricing(row, target_doi=45, elasticity=DEFAULT_PRICE_ELASTICITY)
        urgent_items.append({
            'priority': 2,
            'priority_label': '🟠 HIGH',
            'action_type': 'Severe Excess (1yr+ DOI)',
            'product': row.get('display_name', row['fnsku']),
            'channel': row['channel'],
            'country': row['country'],
            'current_stock': int(row['closing_stock']),
            'doi': round(row['doi'], 0) if row['doi'] < float('inf') else 'Infinite',
            'daily_velocity': round(row['daily_velocity'], 2),
            'recommended_action': f"{result['action']} - {result['discount_pct']}% off",
            'impact': f"{result['excess_units']} excess units tying up capital"
        })
    
    # 3. URGENT REBALANCING (Large DOI gaps within same country)
    if not rebalancing_df.empty:
        urgent_rebal = rebalancing_df[
            (rebalancing_df['from_doi'] > 180) &  # Source has 6mo+ stock
            (rebalancing_df['to_doi'] < 30)        # Destination low on stock
        ].copy()
        
        for _, row in urgent_rebal.iterrows():
            urgent_items.append({
                'priority': 2,
                'priority_label': '🟠 HIGH',
                'action_type': 'Rebalance Needed',
                'product': row.get('display_name', 'Unknown'),
                'channel': f"{row['from_channel']} → {row['to_channel']}",
                'country': row['country'],
                'current_stock': int(row['from_stock']),
                'doi': f"{int(row['from_doi']) if row['from_doi'] < 10000 else '>365'} → {int(row['to_doi']) if row['to_doi'] < 10000 else '>365'}",
                'daily_velocity': '-',
                'recommended_action': f"Transfer {int(row['suggested_transfer'])} units to {row['to_channel']}",
                'impact': row.get('reason', 'Stock imbalance')
            })
    
    # 3b. MARKETING OPPORTUNITIES (Traffic/Conversion Mismatch)
    # Only if sessions data is available
    if 'sessions' in filtered_df.columns and 'conversion_rate' in filtered_df.columns and filtered_df['sessions'].max() > 0:
        # Filter for items with sessions
        mkt_df = filtered_df[filtered_df['sessions'] > 0].copy()
        if not mkt_df.empty:
            median_sess = mkt_df['sessions'].median()
            median_conv = mkt_df['conversion_rate'].median()
            
            # High Traffic, Low Conv -> Fix Listing
            fix_listing = mkt_df[
                (mkt_df['sessions'] > median_sess) & 
                (mkt_df['conversion_rate'] < median_conv)
            ].sort_values('sessions', ascending=False)
            
            for _, row in fix_listing.head(5).iterrows():
                urgent_items.append({
                    'priority': 3, # Medium Priority
                    'priority_label': '🟣 OPPORTUNITY',
                    'action_type': 'Fix Listing Content',
                    'product': row.get('display_name', row['fnsku']),
                    'channel': row['channel'],
                    'country': row['country'],
                    'current_stock': int(row['closing_stock']),
                    'doi': round(row['doi'], 1),
                    'daily_velocity': round(row['daily_velocity'], 2) if row['daily_velocity'] > 0 else 0,
                    'recommended_action': f"Improve images/pricing (Conv: {row['conversion_rate']:.1%})",
                    'impact': f"High Traffic ({int(row['sessions'])}) wasted"
                })
                
            # Low Traffic, High Conv -> Run Ads
            run_ads = mkt_df[
                (mkt_df['sessions'] < median_sess) & 
                (mkt_df['conversion_rate'] > median_conv) # Strong conversion
            ].sort_values('conversion_rate', ascending=False)
            
            for _, row in run_ads.head(5).iterrows():
                urgent_items.append({
                    'priority': 3,
                    'priority_label': '🟣 OPPORTUNITY',
                    'action_type': 'Increase Traffic/Ads',
                    'product': row.get('display_name', row['fnsku']),
                    'channel': row['channel'],
                    'country': row['country'],
                    'current_stock': int(row['closing_stock']),
                    'doi': round(row['doi'], 1),
                    'daily_velocity': round(row['daily_velocity'], 2) if row['daily_velocity'] > 0 else 0,
                    'recommended_action': f"Launch PPC campaigns (Conv: {row['conversion_rate']:.1%})",
                    'impact': "High potential for sales growth"
                })

    # 4. DEAD STOCK (Zero sales)
    dead_stock = filtered_df[
        (filtered_df['is_dead']) & 
        (filtered_df['closing_stock'] > 10)  # Only flag if significant quantity
    ].copy()
    
    for _, row in dead_stock.iterrows():
        urgent_items.append({
            'priority': 3,
            'priority_label': '🟡 MEDIUM',
            'action_type': 'Dead Stock',
            'product': row.get('display_name', row['fnsku']),
            'channel': row['channel'],
            'country': row['country'],
            'current_stock': int(row['closing_stock']),
            'doi': 'No Sales',
            'daily_velocity': 0,
            'recommended_action': 'Liquidate at 50%+ discount or write-off',
            'impact': f"{int(row['closing_stock'])} units with zero demand"
        })
    
    # 5. LOW STOCK WARNING (DOI 7-14 days)
    low_stock = filtered_df[
        (filtered_df['doi'] >= 7) & 
        (filtered_df['doi'] < 14) & 
        (filtered_df['sold_units'] > 5) &  # Only active products
        (filtered_df['closing_stock'] > 0)
    ].copy()
    
    for _, row in low_stock.iterrows():
        urgent_items.append({
            'priority': 4,
            'priority_label': '🔵 LOW',
            'action_type': 'Low Stock Warning',
            'product': row.get('display_name', row['fnsku']),
            'channel': row['channel'],
            'country': row['country'],
            'current_stock': int(row['closing_stock']),
            'doi': round(row['doi'], 1),
            'daily_velocity': round(row['daily_velocity'], 2),
            'recommended_action': f"Monitor - may need {int(row.get('reorder_qty', 0))} units soon",
            'impact': 'Potential stockout in 1-2 weeks'
        })
    
    # Create DataFrame and display
    if urgent_items:
        urgent_df = pd.DataFrame(urgent_items)
        urgent_df = urgent_df.sort_values('priority')
        
        # Summary metrics
        st.markdown("### 📋 Action Summary")
        sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
        
        critical_count = len(urgent_df[urgent_df['priority'] == 1])
        high_count = len(urgent_df[urgent_df['priority'] == 2])
        medium_count = len(urgent_df[urgent_df['priority'] == 3])
        low_count = len(urgent_df[urgent_df['priority'] == 4])
        
        sum_col1.metric("🔴 Critical", critical_count, help="Stockout imminent - act today")
        sum_col2.metric("🟠 High", high_count, help="Severe excess or rebalancing needed")
        sum_col3.metric("🟡 Medium", medium_count, help="Dead stock requiring action")
        sum_col4.metric("🔵 Low", low_count, help="Monitor closely")
        
        st.markdown("---")
        
        # Filter by priority
        priority_filter = st.selectbox(
            "Filter by Priority",
            ["All", "🔴 CRITICAL", "🟠 HIGH", "🟡 MEDIUM", "🔵 LOW"],
            key="urgent_priority_filter"
        )
        
        display_urgent = urgent_df.copy()
        if priority_filter != "All":
            display_urgent = display_urgent[display_urgent['priority_label'] == priority_filter]
        
        # Display table
        display_cols = ['priority_label', 'action_type', 'product', 'channel', 'country',
                       'current_stock', 'doi', 'recommended_action', 'impact']
        
        st.dataframe(
            display_urgent[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                'priority_label': st.column_config.TextColumn("Priority", width="small"),
                'action_type': st.column_config.TextColumn("Issue Type", width="medium"),
                'product': st.column_config.TextColumn("Product", width="medium"),
                'channel': st.column_config.TextColumn("Channel"),
                'country': st.column_config.TextColumn("Country"),
                'current_stock': st.column_config.NumberColumn("Stock", format="%d"),
                'doi': st.column_config.TextColumn("DOI"),
                'recommended_action': st.column_config.TextColumn("Recommended Action", width="large"),
                'impact': st.column_config.TextColumn("Impact", width="medium")
            }
        )
        
        # Download urgent actions
        st.markdown("---")
        urgent_excel = convert_df_to_excel({'Urgent Actions': urgent_df})
        st.download_button(
            "📥 Download Urgent Actions Report",
            urgent_excel,
            f"Urgent_Actions_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Quick action guide
        with st.expander("📋 Action Priority Guide", expanded=False):
            st.markdown("""
            | Priority | Timeframe | Action Type |
            |----------|-----------|-------------|
            | 🔴 CRITICAL | Today | Stockout imminent - reorder or expedite shipment |
            | 🟠 HIGH | This Week | Severe excess or urgent rebalancing needed |
            | 🟡 MEDIUM | This Month | Dead stock - plan liquidation or write-off |
            | 🔵 LOW | Monitor | Low stock warning - prepare reorder |
            
            **DOI Interpretation:**
            - DOI < 7: Will stockout within a week
            - DOI 7-14: Low stock, monitor closely
            - DOI > 365: Over 1 year of stock - urgent liquidation needed
            - Infinite/No Sales: Dead stock with zero demand
            """)
    else:
        st.success("✅ No urgent actions required! Inventory is healthy.")
        st.balloons()

# =============================================================================
# TAB 1: Executive Summary
# =============================================================================

with tab1:
    st.subheader("📊 Executive Summary")
    st.caption("Key inventory health metrics and overview")
    
    # Show data date
    if 'month' in filtered_df.columns:
        latest_month = filtered_df['month'].max() if not filtered_df.empty else 'N/A'
        st.caption(f"📅 Data as of: **{latest_month}**")
    
    # KPI metrics
    k1, k2, k3, k4, k5 = st.columns(5)
    
    total_stock = int(filtered_df['closing_stock'].sum())
    total_skus = filtered_df['fnsku'].nunique()
    total_sold = int(filtered_df['sold_units'].sum())
    stockout_risk = int(filtered_df['is_stockout_risk'].sum())
    excess_count = int(filtered_df['is_excess'].sum())
    
    k1.metric("Total SKUs", f"{total_skus:,}")
    k2.metric("Total Stock", f"{total_stock:,} units")
    k3.metric("Units Sold", f"{total_sold:,}")
    k4.metric("🚨 Stockout Risk", f"{stockout_risk}", delta_color="inverse")
    k5.metric("📦 Excess Items", f"{excess_count}", delta_color="inverse")
    
    # [NEW] Financial Metrics Row
    m1, m2, m3, m4 = st.columns(4)
    
    # Calculate aggregates
    total_lost_revenue = filtered_df['lost_revenue'].sum() if 'lost_revenue' in filtered_df.columns else 0
    
    # Global GMROI
    total_gross_margin = filtered_df['gross_margin_amt'].sum() if 'gross_margin_amt' in filtered_df.columns else 0
    total_inv_val = (filtered_df['cost_price'] * filtered_df['closing_stock']).sum() if 'cost_price' in filtered_df.columns else 0
    global_gmroi = (total_gross_margin / total_inv_val) if total_inv_val > 0 else 0
    
    # Global STR
    global_str = (total_sold / (total_stock + total_sold) * 100) if (total_stock + total_sold) > 0 else 0

    m1.metric("💸 Est. Lost Revenue", f"${total_lost_revenue:,.0f}", help="Monthly potential revenue lost due to stockouts")
    m2.metric("💰 GMROI", f"{global_gmroi:.2f}", help="Gross Margin Return on Inventory Investment")
    m3.metric("📉 Sell-Through Rate", f"{global_str:.1f}%", help="Units sold / (Stock + Sold)")
    
    st.markdown("---")

    # [NEW] Metric Drill Down Inspector
    st.markdown("##### 🔎 Metric Inspector")
    drill_option = st.radio(
        "Select metric to view details:",
        options=["None", "🚨 Stockout Risk", "📦 Excess Items", "💸 High Lost Revenue", "📉 Low GMROI", "💀 Dead Stock", "🔥 Top Sellers"],
        horizontal=True,
        label_visibility="collapsed"
    )
    
    if drill_option == "🚨 Stockout Risk":
        # check columns exist
        cols = ['fnsku', 'display_name', 'channel', 'country', 'doi', 'closing_stock', 'daily_velocity']
        cols = [c for c in cols if c in filtered_df.columns]
        st.dataframe(
            filtered_df[filtered_df['is_stockout_risk']][cols],
            use_container_width=True, hide_index=True
        )
    elif drill_option == "📦 Excess Items":
        cols = ['fnsku', 'display_name', 'channel', 'country', 'doi', 'closing_stock', 'excess_units']
        cols = [c for c in cols if c in filtered_df.columns]
        st.dataframe(
            filtered_df[filtered_df['is_excess']][cols],
            use_container_width=True, hide_index=True
        )
    elif drill_option == "💸 High Lost Revenue":
        cols = ['fnsku', 'display_name', 'channel', 'country', 'lost_revenue', 'days_out_of_stock', 'daily_velocity']
        cols = [c for c in cols if c in filtered_df.columns]
        # Show top 20 by lost revenue
        st.dataframe(
            filtered_df.sort_values('lost_revenue', ascending=False).head(20)[cols],
            use_container_width=True, hide_index=True,
            column_config={
                'lost_revenue': st.column_config.NumberColumn("Est. Loss", format="$%d")
            }
        )
    elif drill_option == "📉 Low GMROI":
        cols = ['fnsku', 'display_name', 'channel', 'country', 'gm_roi', 'closing_stock', 'gross_margin_amt']
        cols = [c for c in cols if c in filtered_df.columns]
        # Show items with stock but low GMROI
        low_gmroi_df = filtered_df[(filtered_df['closing_stock'] > 0) & (filtered_df['gm_roi'] < 1.0)]
        st.dataframe(
            low_gmroi_df.sort_values('gm_roi', ascending=True).head(20)[cols],
            use_container_width=True, hide_index=True,
            column_config={
                'gm_roi': st.column_config.NumberColumn("GMROI", format="%.2f"),
                'gross_margin_amt': st.column_config.NumberColumn("Margin $", format="$%d")
            }
        )
    elif drill_option == "💀 Dead Stock":
        cols = ['fnsku', 'display_name', 'channel', 'country', 'closing_stock']
        cols = [c for c in cols if c in filtered_df.columns]
        st.dataframe(
            filtered_df[filtered_df['is_dead']][cols],
            use_container_width=True, hide_index=True
        )
    elif drill_option == "🔥 Top Sellers":
        cols = ['fnsku', 'display_name', 'channel', 'country', 'sold_units', 'daily_velocity']
        cols = [c for c in cols if c in filtered_df.columns]
        st.dataframe(
            filtered_df.sort_values('sold_units', ascending=False).head(20)[cols],
            use_container_width=True, hide_index=True
        )

    st.markdown("---")
    
    col_left, col_right = st.columns(2)
    
    # ABC Analysis
    with col_left:
        st.markdown("### 📈 ABC Analysis")
        if 'abc_class' in filtered_df.columns:
            abc_summary = filtered_df.groupby('abc_class').agg({
                'fnsku': 'nunique',
                'sold_units': 'sum',
                'closing_stock': 'sum'
            }).reset_index()
            abc_summary.columns = ['ABC Class', 'SKU Count', 'Units Sold', 'Stock Units']
            
            st.dataframe(abc_summary, use_container_width=True, hide_index=True)
            
            # ABC pie chart
            fig = px.pie(
                abc_summary,
                values='Units Sold',
                names='ABC Class',
                title="Sales Distribution by ABC Class",
                color_discrete_map={'A': '#27ae60', 'B': '#f39c12', 'C': '#e74c3c'}
            )
            st.plotly_chart(fig, use_container_width=True)
    

    
    # Movement distribution
    with col_right:
        st.markdown("### 🚀 Movement Status")
        if 'movement' in filtered_df.columns:
            movement_summary = filtered_df['movement'].value_counts().reset_index()
            movement_summary.columns = ['Status', 'Count']
            
            st.dataframe(movement_summary, use_container_width=True, hide_index=True)
            
            # Movement pie chart
            colors = {'Fast': '#27ae60', 'Normal': '#3498db', 'Excess': '#f39c12', 'Dead': '#e74c3c'}
            fig = px.pie(
                movement_summary,
                values='Count',
                names='Status',
                title="Inventory by Movement Status",
                color_discrete_map=colors
            )
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🏆 Top & Bottom Performers (By Actual Sales)")
    
    perf_col1, perf_col2 = st.columns(2)
    
    # Sort for top performers
    # Filter out 0 sales first for cleaner "Bottom" view
    active_items = filtered_df[filtered_df['sold_units'] > 0]
    
    with perf_col1:
        st.markdown("##### 🔥 Top 10 Best Sellers")
        if not filtered_df.empty:
            top_10 = filtered_df.sort_values('sold_units', ascending=False).head(10)
            
            st.dataframe(
                top_10[['display_name', 'sold_units', 'daily_velocity', 'channel', 'country']],
                use_container_width=True,
                hide_index=True,
                column_config={
                    'display_name': st.column_config.TextColumn("Product"),
                    'sold_units': st.column_config.ProgressColumn("Sales", format="%d", min_value=0, max_value=int(top_10['sold_units'].max()) if not top_10.empty else 100),
                    'daily_velocity': st.column_config.NumberColumn("Velocity/Day"),
                    'channel': "Ch", 'country': "Ctry"
                }
            )
        else:
            st.info("No sales data available.")

    with perf_col2:
        st.markdown("##### ❄️ Bottom 10 (Lowest Sales > 0)")
        if not active_items.empty:
            # Bottom 10 of items that have AT LEAST sold 1 unit (true slow movers, not dead)
            bottom_10 = active_items.sort_values('sold_units', ascending=True).head(10)
             
            st.dataframe(
                bottom_10[['display_name', 'sold_units', 'closing_stock', 'doi', 'channel']],
                use_container_width=True,
                hide_index=True,
                column_config={
                     'display_name': st.column_config.TextColumn("Product"),
                     'sold_units': st.column_config.NumberColumn("Sales"),
                     'closing_stock': st.column_config.NumberColumn("Stock"),
                     'doi': st.column_config.NumberColumn("DOI"),
                     'channel': "Channel"
                }
            )
        else:
            st.info("No active sales data found.")

    # Conversion Rate Analysis (Amazon Business Reports only)
    if 'conversion_rate' in filtered_df.columns and filtered_df['conversion_rate'].sum() > 0:
        st.markdown("---")
        st.markdown("### 💡 Conversion Rate Insights (Amazon)")
        
        # Filter for items with sessions
        conv_df = filtered_df[filtered_df['sessions'] > 0].copy()
        
        if not conv_df.empty:
            # Quadrant Analysis
            # High Traffic (Sessions > Median), Low Conv (Conv < Median) -> Opportunity
            median_sess = conv_df['sessions'].median()
            median_conv = conv_df['conversion_rate'].median()
            
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown(f"**📉 High Traffic, Low Conversion** (Fix Listing)")
                # Opportunities to improve content/price
                fix_listing = conv_df[
                    (conv_df['sessions'] > median_sess) & 
                    (conv_df['conversion_rate'] < median_conv)
                ].sort_values('sessions', ascending=False).head(5)
                
                if not fix_listing.empty:
                    for _, row in fix_listing.iterrows():
                        st.warning(f"**{row['display_name'][:40]}...** \n"
                                   f"👀 {int(row['sessions'])} Sessions | 📉 {row['conversion_rate']:.1%} Conv")
                else:
                    st.success("No critical listing issues found.")
            
            with c2:
                st.markdown(f"**💎 Low Traffic, High Conversion** (Advertise More)")
                # Opportunities to run ads
                run_ads = conv_df[
                    (conv_df['sessions'] < median_sess) & 
                    (conv_df['conversion_rate'] > median_conv)
                ].sort_values('conversion_rate', ascending=False).head(5)
                
                if not run_ads.empty:
                    for _, row in run_ads.iterrows():
                        st.success(f"**{row['display_name'][:40]}...** \n"
                                   f"💎 {row['conversion_rate']:.1%} Conv | 👀 {int(row['sessions'])} Sessions")
                else:
                    st.info("No hidden gems found.")



# =============================================================================
# TAB 2: Inventory Health
# =============================================================================

with tab2:
    st.subheader("🏥 Inventory Health Details")
    st.caption("Full inventory metrics by product")
    
    # Display columns
    display_cols = ['fnsku', 'display_name', 'channel', 'country', 'closing_stock', 
                   'sold_units', 'daily_velocity', 'doi', 'lost_revenue', 'gm_roi', 'str', 'volatility', 'sparkline', 'abc_class', 'movement', 'sales_source']
    display_cols = [c for c in display_cols if c in filtered_df.columns]
    
    # Format display dataframe
    health_df = filtered_df[display_cols].copy()
    health_df['closing_stock'] = health_df['closing_stock'].astype(int)
    health_df['sold_units'] = health_df['sold_units'].astype(int)
    health_df = health_df.sort_values('doi', ascending=True).round(2)
    
    st.dataframe(
        health_df.head(100).style.background_gradient(subset=['doi'], cmap='RdYlGn_r', vmin=0, vmax=180), 
        use_container_width=True, 
        hide_index=True,
        column_config={
            'lost_revenue': st.column_config.NumberColumn("Est. Loss", format="$%d"),
            'gm_roi': st.column_config.NumberColumn("GMROI", format="%.2f"),
            'str': st.column_config.NumberColumn("STR", format="%.1f%%"),
            'volatility': st.column_config.NumberColumn("Vol(CV)", format="%.2f"),
            'sparkline': st.column_config.LineChartColumn("6-Mo Trend", y_min=0)
        }
    )
    
    # DOI distribution chart
    st.markdown("### 📊 DOI Distribution")
    fig = px.histogram(
        filtered_df,
        x='doi',
        nbins=20,
        title="Distribution of Days of Inventory",
        labels={'doi': 'Days of Inventory'},
        color_discrete_sequence=['#3498db']
    )
    fig.add_vline(x=DEFAULT_EXCESS_THRESHOLD_DAYS, line_dash="dash", line_color="red",
                  annotation_text=f"Excess ({DEFAULT_EXCESS_THRESHOLD_DAYS}d)")
    fig.add_vline(x=DEFAULT_STOCKOUT_THRESHOLD_DAYS, line_dash="dash", line_color="orange",
                  annotation_text=f"Low Stock ({DEFAULT_STOCKOUT_THRESHOLD_DAYS}d)")
    st.plotly_chart(fig, use_container_width=True)


# =============================================================================
# TAB 3: Reorder & Stockout
# =============================================================================

with tab3:
    st.subheader("🔄 Reorder Planning")
    st.caption("Items that need reordering to maintain safety stock")
    
    st.caption("Items that need reordering to maintain safety stock")
    
    # [NEW] What-If Simulator
    with st.expander("🔮 What-If Simulator (Scenario Planning)", expanded=True):
        st.caption("Adjust projected growth to see impact on reorder quantities.")
        growth_pct = st.slider("Projected Sales Growth (%)", -50, 100, 0, step=5)
    
    # Base Reorder Calculation
    base_reorder = filtered_df[filtered_df['reorder_qty'] > 0].copy()
    
    if growth_pct != 0:
        sim_df = filtered_df.copy()
        sim_df['sim_velocity'] = sim_df['daily_velocity'] * (1 + growth_pct/100)
        sim_df['sim_safety_stock'] = sim_df['sim_velocity'] * safety_days
        sim_df['sim_reorder_qty'] = np.maximum(0, sim_df['sim_safety_stock'] - sim_df['closing_stock'] - sim_df['inbound_total'].fillna(0))
        
        reorder_items = sim_df[sim_df['sim_reorder_qty'] > 0].sort_values('sim_reorder_qty', ascending=False)
        reorder_items['reorder_qty'] = reorder_items['sim_reorder_qty'] # Override for display
        
        st.info(f"Scenario: {growth_pct:+}% Growth | Reorder Items: {len(reorder_items)} (vs {len(base_reorder)} base)")
    else:
        reorder_items = base_reorder.sort_values('reorder_qty', ascending=False)
    
    if not reorder_items.empty:
        st.metric("Items Needing Reorder", len(reorder_items))
        
        display_cols = ['fnsku', 'display_name', 'channel', 'country', 'closing_stock', 
                       'daily_velocity', 'doi', 'safety_stock', 'reorder_qty', 'lost_revenue', 'gm_roi', 'abc_class']
        display_cols = [c for c in display_cols if c in reorder_items.columns]
        
        st.dataframe(
            reorder_items[display_cols].head(50).round(2),
            use_container_width=True,
            hide_index=True,
            column_config={
                'lost_revenue': st.column_config.NumberColumn("Risk Loss", format="$%d"),
                'gm_roi': st.column_config.NumberColumn("GMROI", format="%.2f")
            }
        )
        
        # Reorder by ABC class
        st.markdown("### 📊 Reorder Quantity by ABC Class")
        abc_reorder = reorder_items.groupby('abc_class')['reorder_qty'].sum().reset_index()
        
        fig = px.bar(
            abc_reorder,
            x='abc_class',
            y='reorder_qty',
            title="Units to Reorder by ABC Class",
            color='abc_class',
            color_discrete_map={'A': '#27ae60', 'B': '#f39c12', 'C': '#e74c3c'},
            labels={'reorder_qty': 'Units to Order'}
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.success("✅ No reorder needed! All items above safety stock.")

    # =========================================================================
    # STOCK BALANCING (Cross-Channel Transfers) - v3.3
    # =========================================================================
    
    st.markdown("---")
    st.markdown("### ⚖️ Stock Balancing Opportunities")
    st.caption("Transfer inventory between channels (e.g., Amazon ↔ Noon) to resolve excess/stockouts without ordering new stock.")
    
    # Use globally calculated dataframe
    balancing_df = rebalancing_df
    
    if not balancing_df.empty:
        total_transfer_units = balancing_df['transfer_qty'].sum()
        total_savings = balancing_df['est_savings'].sum()
        
        b1, b2 = st.columns(2)
        b1.metric("Units to Transfer", f"{total_transfer_units:,}")
        b2.metric("Est. Capital Saved", f"${total_savings:,.0f}", help="Cost of goods you don't need to buy")
        
        st.dataframe(
            balancing_df,
            column_config={
                'display_name': st.column_config.TextColumn("Product", width="large"),
                'country': st.column_config.TextColumn("Country"),
                'from_channel': st.column_config.TextColumn("From (Excess)"),
                'to_channel': st.column_config.TextColumn("To (Need)"),
                'transfer_qty': st.column_config.NumberColumn("Transfer Qty"),
                'est_savings': st.column_config.NumberColumn("Cap. Saving", format="$%d"),
                'est_revenue_protected': st.column_config.NumberColumn("Rev. Protected", format="$%d"),
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("No balancing opportunities found (no simultaneous Excess & Need for the same items).")


# =============================================================================
# TAB 4: Dead & Excess
# =============================================================================

with tab4:
    st.subheader("💀 Dead & Excess Inventory")
    st.caption("Items requiring action")
    
    col1, col2 = st.columns(2)
    
    # Excess inventory
    with col1:
        st.markdown("### 📦 Excess Stock (DOI > 90 days)")
        excess_items = filtered_df[filtered_df['is_excess']].copy()
        
        if not excess_items.empty:
            excess_units = int(excess_items['closing_stock'].sum())
            st.metric("Excess Units", f"{excess_units:,}")
            
            display_cols = ['fnsku', 'display_name', 'channel', 'country', 'closing_stock', 
                          'doi', 'daily_velocity', 'abc_class']
            display_cols = [c for c in display_cols if c in excess_items.columns]
            st.dataframe(
                excess_items[display_cols].head(20).round(2),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("✅ No excess inventory!")
    
    # Dead inventory
    with col2:
        st.markdown("### 💀 Dead Stock (No sales 180+ days)")
        dead_items = filtered_df[filtered_df['is_dead']].copy()
        
        if not dead_items.empty:
            dead_units = int(dead_items['closing_stock'].sum())
            st.metric("Dead Units", f"{dead_units:,}")
            
            display_cols = ['fnsku', 'display_name', 'channel', 'country', 'closing_stock', 
                          'doi', 'abc_class']
            display_cols = [c for c in display_cols if c in dead_items.columns]
            st.dataframe(
                dead_items[display_cols].head(20).round(2),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("✅ No dead inventory!")
    
    # =========================================================================
    # LIQUIDATION PRICING SECTION (v3.2 - New Feature)
    # =========================================================================
    
    st.markdown("---")
    st.markdown("### 💰 Liquidation Pricing Recommendations")
    st.caption("Optimal discount % to clear excess stock based on price elasticity")
    
    # Combine excess and dead items for liquidation analysis
    liquidation_candidates = filtered_df[
        (filtered_df['is_excess']) | (filtered_df['is_dead'])
    ].copy()
    
    if not liquidation_candidates.empty:
        # Elasticity slider
        col_elast, col_target = st.columns(2)
        with col_elast:
            elasticity = st.slider(
                "Price Elasticity",
                min_value=0.5,
                max_value=3.0,
                value=DEFAULT_PRICE_ELASTICITY,
                step=0.1,
                help="Higher = products are more price-sensitive (small discount = big demand increase)"
            )
        with col_target:
            target_doi = st.slider(
                "Target DOI (after liquidation)",
                min_value=30,
                max_value=90,
                value=LIQUIDATION_TARGET_DOI,
                step=5,
                help="Target Days of Inventory after applying discount"
            )
        
        # Calculate liquidation recommendations
        liquidation_results = []
        for _, row in liquidation_candidates.iterrows():
            result = calculate_liquidation_pricing(row, target_doi=target_doi, elasticity=elasticity)
            result['fnsku'] = row['fnsku']
            result['display_name'] = row.get('display_name', '')
            result['channel'] = row['channel']
            result['country'] = row['country']
            result['current_stock'] = int(row['closing_stock'])
            result['current_doi'] = round(row['doi'], 1) if row['doi'] < float('inf') else 'N/A'
            result['current_velocity'] = round(row['daily_velocity'], 2)
            liquidation_results.append(result)
        
        liq_df = pd.DataFrame(liquidation_results)
        
        # Sort by discount needed (highest first)
        liq_df = liq_df.sort_values('discount_pct', ascending=False)
        
        # Display summary metrics
        high_discount_count = len(liq_df[liq_df['discount_pct'] >= 30])
        moderate_discount_count = len(liq_df[(liq_df['discount_pct'] >= 15) & (liq_df['discount_pct'] < 30)])
        light_discount_count = len(liq_df[(liq_df['discount_pct'] > 0) & (liq_df['discount_pct'] < 15)])
        
        liq_col1, liq_col2, liq_col3 = st.columns(3)
        liq_col1.metric("🔴 Heavy Discount (30%+)", high_discount_count)
        liq_col2.metric("🟡 Moderate (15-30%)", moderate_discount_count)
        liq_col3.metric("🟢 Light (<15%)", light_discount_count)
        
        # Display table
        display_liq_cols = ['display_name', 'channel', 'country', 'current_stock', 
                          'current_doi', 'current_velocity', 'discount_pct',
                          'expected_new_velocity', 'days_to_clear', 'action']
        display_liq_cols = [c for c in display_liq_cols if c in liq_df.columns]
        
        st.dataframe(
            liq_df[display_liq_cols].head(30),
            use_container_width=True,
            hide_index=True,
            column_config={
                'display_name': st.column_config.TextColumn("Product", width="medium"),
                'current_stock': st.column_config.NumberColumn("Stock", format="%d"),
                'current_doi': st.column_config.TextColumn("DOI (days)"),
                'current_velocity': st.column_config.NumberColumn("Velocity/day", format="%.2f"),
                'discount_pct': st.column_config.NumberColumn("Discount %", format="%d%%"),
                'expected_new_velocity': st.column_config.NumberColumn("New Velocity", format="%.2f"),
                'days_to_clear': st.column_config.NumberColumn("Days to Clear", format="%d"),
                'action': st.column_config.TextColumn("Recommendation", width="medium")
            }
        )
        
        # Download button for liquidation report
        if st.button("📥 Download Liquidation Report", key="download_liquidation"):
            liq_excel = convert_df_to_excel({'Liquidation Recommendations': liq_df})
            st.download_button(
                label="⬇️ Download Excel",
                data=liq_excel,
                file_name=f"Liquidation_Recommendations_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.success("✅ No excess or dead inventory requires liquidation!")


# =============================================================================
# TAB 5: Cross-Channel View
# =============================================================================

with tab5:
    st.subheader("🌐 Cross-Channel Inventory")
    st.caption("Same products across Amazon KSA, Amazon UAE, Noon KSA, Noon UAE")
    
    if not cross_channel_df.empty:
        # 1. Summary Metrics & Charts (Visual View)
        # Aggregate data by channel/country for high-level view
        channel_summary = filtered_df.groupby(['channel', 'country']).agg({
            'closing_stock': 'sum',
            'sold_units': 'sum'
        }).reset_index()
        
        channel_summary['Market'] = channel_summary['channel'] + " " + channel_summary['country']
        
        col_charts1, col_charts2, col_charts3 = st.columns(3)
        
        with col_charts1:
            st.markdown("##### 🌍 Stock Distribution")
            fig_stock = px.pie(
                channel_summary,
                values='closing_stock',
                names='Market',
                title='Stock Units',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            st.plotly_chart(fig_stock, use_container_width=True)

        with col_charts2:
            st.markdown("##### 💸 Sales Distribution")
            fig_sales = px.pie(
                channel_summary,
                values='sold_units',
                names='Market',
                title='Sales Units',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Bold
            )
            st.plotly_chart(fig_sales, use_container_width=True)
            
        with col_charts3:
            st.markdown("##### 📊 Performance")
            # Melt for side-by-side bars
            chart_df = channel_summary.melt(id_vars=['Market'], value_vars=['sold_units', 'closing_stock'], 
                                          var_name='Metric', value_name='Units')
            chart_df['Metric'] = chart_df['Metric'].replace({'sold_units': 'Sales', 'closing_stock': 'Stock'})
            
            fig_bar = px.bar(
                chart_df,
                x='Market',
                y='Units',
                color='Metric',
                title='Sales vs Stock',
                barmode='group',
                color_discrete_map={'Sales': '#27ae60', 'Stock': '#2980b9'}
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")
        
        # 2. Detailed Data view
        st.markdown("##### 📋 Detailed Product Comparison")
        st.caption("Side-by-side view of stock levels across all markets")
        
        # Optimize the dataframe display - use column config if possible or just show
        # The cross_channel_df structure is pivoted with dynamic columns
        st.dataframe(
            cross_channel_df.head(100),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Upload data from multiple channels to see cross-channel comparison.")


# =============================================================================
# TAB 6: Rebalancing
# =============================================================================

with tab6:
    st.subheader("⚖️ Rebalancing Opportunities")
    st.caption("Move stock between Amazon ↔ Noon (same country)")
    
    if not rebalancing_df.empty:
        rebal_filtered = rebalancing_df[rebalancing_df['country'].isin(selected_countries)]
        
        if not rebal_filtered.empty:
            for country in sorted(rebal_filtered['country'].unique()):
                st.markdown(f"##### {'🇸🇦' if country == 'KSA' else '🇦🇪'} {country}")
                
                country_rebal = rebal_filtered[rebal_filtered['country'] == country].sort_values(
                    'suggested_transfer', ascending=False
                )
                
                st.dataframe(
                    country_rebal[['display_name', 'from_channel', 'to_channel', 
                                  'from_stock', 'from_doi', 'to_stock', 'to_doi',
                                  'suggested_transfer', 'reason']],
                    use_container_width=True,
                    hide_index=True
                )
                st.markdown("---")
        else:
            st.success("✅ No rebalancing opportunities for selected filters.")
    else:
        st.info("Upload data from multiple channels (Amazon + Noon) in the same country.")


# =============================================================================
# TAB 7: Stranded Inventory
# =============================================================================

with tab7:
    st.subheader("🚫 Stranded & Unfulfillable Inventory")
    st.caption("Items that cannot be sold (Amazon-specific)")
    
    if not stranded_df.empty:
        total_stranded = int(stranded_df['quantity'].sum())
        st.metric("Total Stranded Units", f"{total_stranded:,}")
        
        st.dataframe(
            stranded_df.sort_values('quantity', ascending=False),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.success("✅ No stranded or unfulfillable inventory detected!")


# =============================================================================
# TAB 8: SKU Explorer
# =============================================================================

with tab8:
    st.subheader("🔍 SKU Explorer")
    st.caption("Deep dive into individual SKU performance")
    
    sku_options = sorted(filtered_df['fnsku'].unique())
    selected_sku = st.selectbox("Select SKU (FNSKU)", sku_options)
    
    if selected_sku:
        sku_data = filtered_df[filtered_df['fnsku'] == selected_sku]
        
        if not sku_data.empty:
            first_row = sku_data.iloc[0]
            
            st.markdown(f"### {first_row.get('display_name', selected_sku)}")
            st.caption(f"FNSKU: {selected_sku} | Category: {first_row.get('category', 'N/A')} | ABC: {first_row.get('abc_class', 'N/A')}")
            
            st.markdown("##### Performance by Channel")
            
            channel_metrics = sku_data[['channel', 'country', 'closing_stock', 'sold_units', 
                                        'daily_velocity', 'doi', 'abc_class']].copy()
            channel_metrics['closing_stock'] = channel_metrics['closing_stock'].astype(int)
            channel_metrics['sold_units'] = channel_metrics['sold_units'].astype(int)
            st.dataframe(channel_metrics.round(2), use_container_width=True, hide_index=True)


# =============================================================================
# TAB 9: Historical Trends (v3.2 - Enhanced Multi-Month Comparison)
# =============================================================================

with tab9:
    st.subheader("📈 Historical Trends")
    st.caption("Compare performance across multiple months")
    
    # Get unique months from current data
    if 'month' in metrics_df.columns and not metrics_df.empty:
        available_months_in_data = sorted(metrics_df['month'].dropna().unique())
    else:
        available_months_in_data = []
    
    # Also check saved historical data
    saved_history_months = db_manager.get_available_months()
    
    # Combine all available months
    all_available_months = list(set(available_months_in_data + saved_history_months))
    all_available_months = sorted(all_available_months, reverse=True)  # Most recent first
    
    st.markdown(f"**📅 Available Months:** {', '.join(all_available_months) if all_available_months else 'None'}")
    
    if len(all_available_months) >= 3:
        # Multi-Month Evolution Mode (3+ months)
        st.success(f"✅ Found {len(all_available_months)} months of data. Showing Multi-Month Evolution.")
        
        # Select up to 6 most recent months
        selected_months = all_available_months[:6]
        
        # Get trend matrix
        trend_matrix = db_manager.get_trend_matrix(selected_analysis_months)
        
        if not trend_matrix.empty:
            # 1. Summary of Evolution
            st.markdown(f"### 📈 Sales Evolution ({selected_months[-1]} to {selected_months[0]})")
            
            # Prepare data for line chart (Highcharts/Plotly style)
            # We need long format for plotting: month, units, product
            plot_months = sorted(selected_months)
            
            # Identify Top 5 Growing Products (by absolute unit change start to end)
            start_month_col = f"sold_units_{plot_months[0]}"
            end_month_col = f"sold_units_{plot_months[-1]}"
            
            if start_month_col in trend_matrix.columns and end_month_col in trend_matrix.columns:
                trend_matrix['abs_growth'] = trend_matrix[end_month_col].fillna(0) - trend_matrix[start_month_col].fillna(0)
                top_growing = trend_matrix.nlargest(5, 'abs_growth')
                
                # Create chart data for top 5
                chart_data_list = []
                for _, row in top_growing.iterrows():
                    for m in plot_months:
                        col = f"sold_units_{m}"
                        if col in row.index:
                            chart_data_list.append({
                                'Month': m,
                                'Sold Units': row.get(col, 0),
                                'Product': row.get('display_name', 'Unknown')
                            })
                
                chart_df = pd.DataFrame(chart_data_list)
                
                if not chart_df.empty:
                    fig_evol = px.line(
                        chart_df, 
                        x='Month', 
                        y='Sold Units', 
                        color='Product',
                        markers=True,
                        title="Top 5 Products by Sales Growth (Units)",
                        labels={'Sold Units': 'Units Sold', 'Month': 'Month'}
                    )
                    st.plotly_chart(fig_evol, use_container_width=True)
            
            # 2. Detailed Multi-Month Table
            st.markdown("### 📋 Multi-Month Sales Data")
            
            # Select columns to display: Product, Channel, then Sold Units for each month
            display_cols = ['display_name', 'channel', 'country'] + [f"sold_units_{m}" for m in selected_months]
            display_cols = [c for c in display_cols if c in trend_matrix.columns]
            
            # Create cleaner column names for display
            column_config = {
                'display_name': st.column_config.TextColumn("Product", width="medium"),
                'channel': st.column_config.TextColumn("Channel", width="small"),
                'country': st.column_config.TextColumn("Country", width="small"),
            }
            for m in selected_months:
                column_config[f"sold_units_{m}"] = st.column_config.NumberColumn(f"{m}", format="%d")

            st.dataframe(
                trend_matrix[display_cols].fillna(0).head(100),
                use_container_width=True,
                hide_index=True,
                column_config=column_config
            )

            # Download full matrix
            matrix_excel = convert_df_to_excel({'Multi-Month Trends': trend_matrix})
            st.download_button(
                "📥 Download Data",
                matrix_excel,
                f"Multi_Month_Sales_{selected_months[0]}_{selected_months[-1]}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    elif len(all_available_months) == 2:
        st.success(f"✅ Found {len(all_available_months)} months of data available for comparison")
        
        # Month selection
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            current_month = st.selectbox(
                "Current Month (to analyze)",
                all_available_months,
                index=0,
                key="trend_current_month"
            )
        with col_m2:
            # Filter out current month from comparison options
            comparison_options = [m for m in all_available_months if m != current_month]
            if comparison_options:
                compare_month = st.selectbox(
                    "Compare With (previous month)",
                    comparison_options,
                    index=0,
                    key="trend_compare_month"
                )
            else:
                compare_month = None
                st.warning("No other month available for comparison")
        
        if current_month and compare_month:
            st.markdown(f"### 📊 Comparing: **{current_month}** vs **{compare_month}**")
            
            # Get data for each month
            def get_month_data(month_str):
                """Get data for a specific month from current data or saved history"""
                # First try current uploaded data
                if 'month' in metrics_df.columns:
                    month_data = metrics_df[metrics_df['month'] == month_str].copy()
                    if not month_data.empty:
                        return month_data
                
                # Fall back to saved history
                all_history = db_manager.get_all_history()
                if all_history is not None and 'snapshot_month' in all_history.columns:
                    month_data = all_history[all_history['snapshot_month'] == month_str].copy()
                    if not month_data.empty:
                        return month_data
                
                return pd.DataFrame()
            
            current_data = get_month_data(current_month)
            previous_data = get_month_data(compare_month)
            
            if not current_data.empty and not previous_data.empty:
                # Compute trends between the two months
                trends_df = compute_historical_trends(current_data, previous_data)
                
                if not trends_df.empty:
                    # Summary metrics
                    st.markdown("### 📋 Trend Summary")
                    tr_col1, tr_col2, tr_col3, tr_col4 = st.columns(4)
                    
                    growing = len(trends_df[trends_df['trend'].str.contains('Growing|Growth', na=False)])
                    declining = len(trends_df[trends_df['trend'].str.contains('Declining', na=False)])
                    stable = len(trends_df[trends_df['trend'].str.contains('Stable', na=False)])
                    stock_change = len(trends_df[trends_df['trend'].str.contains('Building|Clearing', na=False)])
                    
                    tr_col1.metric("🚀 Growing", growing)
                    tr_col2.metric("📉 Declining", declining)
                    tr_col3.metric("➡️ Stable", stable)
                    tr_col4.metric("📦 Stock Change", stock_change)
                    
                    # Overall velocity change
                    avg_vel_change = trends_df['velocity_change_pct'].mean()
                    total_sales_change = trends_df['sold_units_growth_pct'].mean() if 'sold_units_growth_pct' in trends_df.columns else 0
                    
                    st.markdown("---")
                    
                    overall_col1, overall_col2 = st.columns(2)
                    with overall_col1:
                        delta_color = "normal" if avg_vel_change >= 0 else "inverse"
                        st.metric(
                            "Total Sales Change", 
                            f"{total_sales_change:+.1f}%",
                            delta=f"{'📈' if total_sales_change > 0 else '📉'} vs {compare_month}"
                        )
                    with overall_col2:
                         avg_return_rate = trends_df['return_rate'].mean() if 'return_rate' in trends_df.columns else 0
                         avg_return_change = trends_df['return_rate_change'].mean() if 'return_rate_change' in trends_df.columns else 0
                         st.metric(
                            "Average Return Rate", 
                            f"{avg_return_rate:.1f}%",
                            delta=f"{avg_return_change:+.1f}% vs {compare_month}",
                            delta_color="inverse"
                         )
                    
                    st.markdown("---")
                    
                    # Filter by trend type
                    trend_filter = st.selectbox(
                        "Filter by Trend",
                        ["All", "🚀 Strong Growth", "📈 Growing", "📉 Declining", "⚠️ Declining Fast", "➡️ Stable"],
                        key="hist_trend_filter"
                    )
                    
                    display_trends = trends_df.copy()
                    if trend_filter != "All":
                        trend_filter_clean = trend_filter.replace("🚀 ", "").replace("📈 ", "").replace("📉 ", "").replace("⚠️ ", "").replace("➡️ ", "")
                        display_trends = display_trends[display_trends['trend'].str.contains(trend_filter_clean, na=False)]
                    
                    # Display detailed table
                    st.markdown("### 📋 Product-Level Changes")
                    trend_cols = ['display_name', 'channel', 'country', 'closing_stock', 
                                 'sold_units', 'sold_units_change', 'sold_units_growth_pct', 'return_rate']
                    trend_cols = [c for c in trend_cols if c in display_trends.columns]
                    
                    st.dataframe(
                        display_trends[trend_cols].head(100),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            'display_name': st.column_config.TextColumn("Product", width="medium"),
                            'closing_stock': st.column_config.NumberColumn(f"Stock", format="%d"),
                            'sold_units': st.column_config.NumberColumn(f"Units Sold", format="%d"),
                            'sold_units_change': st.column_config.NumberColumn(f"Units Δ", format="%+d"),
                            'sold_units_growth_pct': st.column_config.NumberColumn("Growth %", format="%+.1f%%"),
                            'return_rate': st.column_config.NumberColumn("Return %", format="%.1f%%"),
                        }
                    )
                    
                    # Sales Growth chart
                    st.markdown(f"### 📊 Top Sales Growth: {current_month} vs {compare_month}")
                    
                    # Get top gainers and losers in sales
                    cols_to_plot = ['display_name', 'sold_units_growth_pct', 'sold_units']
                    if all(c in trends_df.columns for c in cols_to_plot):
                        top_gainers = trends_df.nlargest(5, 'sold_units_growth_pct')[cols_to_plot]
                        top_losers = trends_df.nsmallest(5, 'sold_units_growth_pct')[cols_to_plot]
                        
                        chart_data = pd.concat([top_gainers, top_losers]).drop_duplicates()
                        chart_data = chart_data.sort_values('sold_units_growth_pct', ascending=True)
                        
                        fig = px.bar(
                            chart_data,
                            x='sold_units_growth_pct',
                            y='display_name',
                            orientation='h',
                            title=f"Top Sales Growth",
                            labels={'sold_units_growth_pct': 'Sales Growth %', 'display_name': 'Product'},
                            color='sold_units_growth_pct',
                            color_continuous_scale=['#e74c3c', '#f39c12', '#27ae60']
                        )
                    fig.update_layout(yaxis={'categoryorder': 'total ascending'})
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Download trends report
                    trends_excel = convert_df_to_excel({
                        'Trends Summary': trends_df,
                        f'{current_month} Data': current_data,
                        f'{compare_month} Data': previous_data
                    })
                    st.download_button(
                        "📥 Download Trends Report",
                        trends_excel,
                        f"Historical_Trends_{current_month}_vs_{compare_month}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                else:
                    st.warning("Could not compute trends. The months may not have matching products.")
            else:
                if current_data.empty:
                    st.error(f"No data found for {current_month}")
                if previous_data.empty:
                    st.error(f"No data found for {compare_month}")
    
    elif len(all_available_months) == 1:
        st.info(f"📊 Only one month of data available: **{all_available_months[0]}**")
        st.caption("Upload files from additional months OR save this session and upload new data next month to see trends.")
        
        st.markdown("---")
        st.markdown("### 💡 How to Get Historical Trends")
        st.markdown("""
        **Option 1: Upload Multiple Months**
        - Include files from 2-4 previous months in your upload
        - Name files with the month (e.g., `amazon_ksa_nov_2025.csv`, `amazon_ksa_dec_2025.csv`)
        
        **Option 2: Build History Over Time**
        1. Save your current session using the "💾 Save This Session" expander
        2. Next month, upload new data and save again
        3. This tab will then show month-over-month trends
        """)
    else:
        st.warning("No month data available in current dataset.")
        st.caption("Ensure your files are named with month information (e.g., `amazon_ksa_jan_2025.csv`)")


# =============================================================================
# DOWNLOAD SECTION
# =============================================================================

st.markdown("---")
st.subheader("📥 Export Data")
st.caption("Download reports and data for sharing")

# Prepare export dataframes
export_cols = ['display_name', 'channel', 'country', 'closing_stock', 'sold_units', 
               'daily_velocity', 'doi', 'safety_stock', 'reorder_qty', 'abc_class', 
               'movement', 'category', 'fnsku', 'month']
export_cols = [c for c in export_cols if c in filtered_df.columns]

export_df = filtered_df[export_cols].copy()
export_df['closing_stock'] = export_df['closing_stock'].astype(int)
export_df['sold_units'] = export_df['sold_units'].astype(int)
export_df = export_df.round(2)

reorder_df = export_df[export_df['reorder_qty'] > 0].sort_values('reorder_qty', ascending=False)

col1, col2 = st.columns(2)

with col1:
    # Multi-tab Excel export
    excel_data = convert_df_to_excel({
        'Summary': export_df,
        'Reorder List': reorder_df,
        'Rebalancing': rebalancing_df if not rebalancing_df.empty else pd.DataFrame(),
        'Stranded': stranded_df if not stranded_df.empty else pd.DataFrame(),
        'Cross Channel': cross_channel_df if not cross_channel_df.empty else pd.DataFrame()
    })
    
    st.download_button(
        label="📥 Download Master Excel Report",
        data=excel_data,
        file_name=f"Lumive_Inventory_Report_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

with col2:
    # CSV export
    csv_data = export_df.to_csv(index=False)
    st.download_button(
        "📄 Download Summary CSV",
        csv_data,
        f"lumive_inventory_summary_{datetime.now().strftime('%Y%m%d')}.csv",
        "text/csv"
    )

# =============================================================================
# FOOTER
# =============================================================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; font-size: 0.85em;'>
    <p>
    <strong>Lumive Inventory Intelligence Dashboard v3.2</strong><br>
    Smart inventory management for Amazon + Noon (KSA & UAE)<br>
    Secure • Real-time • Collaborative • Persistent<br>
    © 2025 Lumive. All rights reserved.
    </p>
</div>
""", unsafe_allow_html=True)