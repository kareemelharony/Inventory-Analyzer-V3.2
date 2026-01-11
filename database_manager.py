#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DatabaseManager - Data Persistence for Lumive Inventory Dashboard
=================================================================
Handles saving/loading sessions and historical data using local JSON/Parquet files.

Features:
- Session saving: Save current workspace state to reload later
- Historical trends: Store monthly snapshots for comparison
- Lightweight: Uses local files, no database server needed

Storage Structure:
    lumive_data/
    ├── sessions_index.json     # List of saved sessions with metadata
    ├── history.parquet         # Historical metrics data
    └── sessions/               # Individual session files
        └── {session_name}.parquet
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np


class DatabaseManager:
    """
    Manages local data persistence using JSON and Parquet files.
    
    Parquet is used for dataframes (efficient, compressed, preserves types).
    JSON is used for metadata and session index.
    
    Usage:
        db = DatabaseManager()
        db.save_session("jan_2025", {"metrics_df": df, "settings": {...}})
        data = db.load_session("jan_2025")
    """
    
    def __init__(self, base_dir: str = "lumive_data"):
        """
        Initialize database manager.
        
        Args:
            base_dir: Directory for storing data files (relative to app or absolute)
        """
        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / "sessions"
        self.sessions_index_file = self.base_dir / "sessions_index.json"
        self.history_file = self.base_dir / "history.parquet"
        
        # Create directories if they don't exist
        self.base_dir.mkdir(exist_ok=True)
        self.sessions_dir.mkdir(exist_ok=True)
        
        # Initialize sessions index if not exists
        if not self.sessions_index_file.exists():
            self._save_sessions_index([])
    
    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================
    
    def save_session(self, session_name: str, data: Dict[str, Any], 
                     description: str = "") -> bool:
        """
        Save current workspace to a named session.
        
        Args:
            session_name: Unique name for this session
            data: Dictionary containing session data
                  Expected keys: metrics_df, aging_df, file_metadata, settings
            description: Optional description of this session
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Clean session name (remove special chars)
            clean_name = "".join(c for c in session_name if c.isalnum() or c in "-_").strip()
            if not clean_name:
                clean_name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            session_path = self.sessions_dir / f"{clean_name}.parquet"
            metadata_path = self.sessions_dir / f"{clean_name}_meta.json"
            
            # Save dataframes to parquet
            if 'metrics_df' in data and isinstance(data['metrics_df'], pd.DataFrame):
                data['metrics_df'].to_parquet(session_path, index=False)
            
            # Save metadata (settings, file info, etc.) to JSON
            metadata = {
                'session_name': clean_name,
                'created_at': datetime.now().isoformat(),
                'description': description,
                'settings': data.get('settings', {}),
                'file_metadata': data.get('file_metadata', []),
                'has_aging_data': 'aging_df' in data and not data.get('aging_df', pd.DataFrame()).empty,
                'sku_count': len(data.get('metrics_df', pd.DataFrame())),
            }
            
            # Save aging data if present
            if 'aging_df' in data and isinstance(data['aging_df'], pd.DataFrame):
                if not data['aging_df'].empty:
                    aging_path = self.sessions_dir / f"{clean_name}_aging.parquet"
                    data['aging_df'].to_parquet(aging_path, index=False)
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2, default=str)
            
            # Update sessions index
            self._update_sessions_index(clean_name, metadata)
            
            return True
            
        except Exception as e:
            print(f"Error saving session: {e}")
            return False
    
    def load_session(self, session_name: str) -> Optional[Dict[str, Any]]:
        """
        Load a previously saved session.
        
        Args:
            session_name: Name of session to load
        
        Returns:
            Dictionary with session data or None if not found
        """
        try:
            session_path = self.sessions_dir / f"{session_name}.parquet"
            metadata_path = self.sessions_dir / f"{session_name}_meta.json"
            
            if not session_path.exists():
                return None
            
            result = {
                'metrics_df': pd.read_parquet(session_path),
                'settings': {},
                'file_metadata': [],
                'session_info': {}
            }
            
            # Load metadata
            if metadata_path.exists():
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    result['settings'] = metadata.get('settings', {})
                    result['file_metadata'] = metadata.get('file_metadata', [])
                    result['session_info'] = metadata
            
            # Load aging data if exists
            aging_path = self.sessions_dir / f"{session_name}_aging.parquet"
            if aging_path.exists():
                result['aging_df'] = pd.read_parquet(aging_path)
            else:
                result['aging_df'] = pd.DataFrame()
            
            return result
            
        except Exception as e:
            print(f"Error loading session: {e}")
            return None
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all saved sessions with metadata.
        
        Returns:
            List of session metadata dictionaries
        """
        try:
            if not self.sessions_index_file.exists():
                return []
            
            with open(self.sessions_index_file, 'r') as f:
                return json.load(f)
        except:
            return []
    
    def delete_session(self, session_name: str) -> bool:
        """
        Remove a saved session.
        
        Args:
            session_name: Name of session to delete
        
        Returns:
            True if successful
        """
        try:
            # Remove files
            for suffix in ['.parquet', '_meta.json', '_aging.parquet']:
                path = self.sessions_dir / f"{session_name}{suffix}"
                if path.exists():
                    path.unlink()
            
            # Update index
            sessions = self.list_sessions()
            sessions = [s for s in sessions if s.get('session_name') != session_name]
            self._save_sessions_index(sessions)
            
            return True
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False
    
    # =========================================================================
    # HISTORICAL DATA MANAGEMENT
    # =========================================================================
    
    def save_history(self, metrics_df: pd.DataFrame, month: str) -> bool:
        """
        Append current metrics to historical data.
        
        Args:
            metrics_df: Current month's inventory metrics
            month: Month identifier (YYYY-MM format)
        
        Returns:
            True if successful
        """
        try:
            if metrics_df.empty:
                return False
            
            # Prepare data with snapshot timestamp
            df = metrics_df.copy()
            df['snapshot_month'] = month
            df['snapshot_date'] = datetime.now().isoformat()
            
            # Append to existing history or create new
            if self.history_file.exists():
                existing = pd.read_parquet(self.history_file)
                # Remove existing data for same month (update rather than duplicate)
                existing = existing[existing['snapshot_month'] != month]
                combined = pd.concat([existing, df], ignore_index=True)
            else:
                combined = df
            
            combined.to_parquet(self.history_file, index=False)
            return True
            
        except Exception as e:
            print(f"Error saving history: {e}")
            return False
    
    def get_historical_comparison(self, current_month: str) -> Optional[pd.DataFrame]:
        """
        Get previous month data for comparison.
        
        Args:
            current_month: Current month in YYYY-MM format
        
        Returns:
            DataFrame with previous month data or None
        """
        try:
            if not self.history_file.exists():
                return None
            
            history = pd.read_parquet(self.history_file)
            
            if 'snapshot_month' not in history.columns:
                return None
            
            # Get unique months sorted
            months = sorted(history['snapshot_month'].unique())
            
            if current_month not in months:
                return None
            
            current_idx = months.index(current_month)
            if current_idx == 0:
                return None  # No previous month
            
            previous_month = months[current_idx - 1]
            return history[history['snapshot_month'] == previous_month]
            
        except Exception as e:
            print(f"Error getting historical data: {e}")
            return None
    
    def get_all_history(self) -> Optional[pd.DataFrame]:
        """
        Get all historical data.
        
        Returns:
            DataFrame with all historical data or None
        """
        try:
            if not self.history_file.exists():
                return None
            return pd.read_parquet(self.history_file)
        except:
            return None
    
    def get_available_months(self) -> List[str]:
        """
        Get list of months with historical data.
        
        Returns:
            Sorted list of month strings (YYYY-MM)
        """
        try:
            if not self.history_file.exists():
                return []
            
            history = pd.read_parquet(self.history_file)
            if 'snapshot_month' not in history.columns:
                return []
            
            return sorted(history['snapshot_month'].unique())
        except:
            return []

    def get_trend_matrix(self, months: List[str] = None) -> pd.DataFrame:
        """
        Get matrix of metrics across multiple months.
        
        Args:
            months: List of month strings (YYYY-MM) to include. If None/empty, returns empty.
            
        Returns:
            DataFrame with product keys and columns for each month's metrics
            metrics: sold_units, daily_velocity, closing_stock
        """
        try:
            if not self.history_file.exists() or not months:
                return pd.DataFrame()
            
            history = pd.read_parquet(self.history_file)
            
            # Filter for requested months
            df = history[history['snapshot_month'].isin(months)].copy()
            
            if df.empty:
                return pd.DataFrame()
            
            # Pivot data to get wide format
            # Key: channel, country, fnsku
            # Values: sold_units, daily_velocity, closing_stock
            
            id_vars = ['channel', 'country', 'fnsku', 'display_name', 'snapshot_month']
            value_vars = ['sold_units', 'daily_velocity', 'closing_stock']
            
            # Keep only available columns
            value_vars = [c for c in value_vars if c in df.columns]
            
            # Pivot
            pivot = df.pivot_table(
                index=['channel', 'country', 'fnsku', 'display_name'], 
                columns='snapshot_month', 
                values=value_vars,
                aggfunc='first' # Should be unique per month
            )
            
            # Flatten columns
            pivot.columns = [f"{col[0]}_{col[1]}" for col in pivot.columns]
            pivot = pivot.reset_index()
            
            return pivot
            
        except Exception as e:
            print(f"Error getting trend matrix: {e}")
            return pd.DataFrame()
    
    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================
    
    def _save_sessions_index(self, sessions: List[Dict]) -> None:
        """Save sessions index to JSON file."""
        with open(self.sessions_index_file, 'w') as f:
            json.dump(sessions, f, indent=2, default=str)
    
    def _update_sessions_index(self, session_name: str, metadata: Dict) -> None:
        """Add or update a session in the index."""
        sessions = self.list_sessions()
        
        # Remove existing entry if updating
        sessions = [s for s in sessions if s.get('session_name') != session_name]
        
        # Add new entry
        sessions.append({
            'session_name': session_name,
            'created_at': metadata.get('created_at'),
            'description': metadata.get('description', ''),
            'sku_count': metadata.get('sku_count', 0),
            'has_aging_data': metadata.get('has_aging_data', False)
        })
        
        # Sort by date descending
        sessions.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        self._save_sessions_index(sessions)


# =============================================================================
# LIQUIDATION PRICING CALCULATOR
# =============================================================================

def calculate_liquidation_pricing(row: pd.Series, target_doi: int = 45, 
                                   elasticity: float = 1.5) -> Dict[str, Any]:
    """
    Calculate discount % needed to clear excess stock based on price elasticity.
    
    Uses the price elasticity of demand concept:
    - Elasticity > 1: Demand is elastic (price changes significantly affect demand)
    - Elasticity < 1: Demand is inelastic (price changes have less effect)
    
    Formula:
    Required velocity increase = (Current Stock - Target Stock) / Days to Clear
    Price reduction needed = (Velocity Increase %) / Elasticity
    
    Args:
        row: DataFrame row with closing_stock, daily_velocity, doi
        target_doi: Target days of inventory after liquidation (default 45)
        elasticity: Price elasticity coefficient (default 1.5)
    
    Returns:
        Dict with discount_pct, expected_new_velocity, days_to_clear, action
    """
    try:
        closing_stock = float(row.get('closing_stock', 0))
        daily_velocity = float(row.get('daily_velocity', 0))
        current_doi = float(row.get('doi', float('inf')))
        
        # Handle edge cases
        if closing_stock <= 0 or np.isinf(current_doi):
            return {
                'discount_pct': 0,
                'expected_new_velocity': 0,
                'days_to_clear': None,
                'action': 'No Action - Zero Stock',
                'excess_units': 0
            }
        
        if current_doi <= target_doi:
            return {
                'discount_pct': 0,
                'expected_new_velocity': daily_velocity,
                'days_to_clear': int(current_doi),
                'action': 'No Action - Within Target',
                'excess_units': 0
            }
        
        # Calculate target stock level
        target_stock = daily_velocity * target_doi
        excess_units = max(0, closing_stock - target_stock)
        
        # If no velocity (dead stock), recommend aggressive discount
        if daily_velocity <= 0:
            return {
                'discount_pct': min(70, 30 + (current_doi / 10)),  # 30-70% based on age
                'expected_new_velocity': 0.5,  # Assume some movement after discount
                'days_to_clear': int(closing_stock / 0.5) if closing_stock > 0 else None,
                'action': 'Liquidation Needed - Dead Stock',
                'excess_units': int(closing_stock)
            }
        
        # Calculate required velocity increase to reach target DOI
        required_velocity = closing_stock / target_doi
        velocity_increase_needed = (required_velocity / daily_velocity) - 1
        velocity_increase_pct = velocity_increase_needed * 100
        
        # Calculate discount using elasticity
        # Higher elasticity = smaller discount needed for same velocity increase
        discount_pct = velocity_increase_pct / elasticity
        
        # Cap discount at reasonable levels
        discount_pct = min(70, max(5, discount_pct))
        
        # Round to nearest 5%
        discount_pct = round(discount_pct / 5) * 5
        
        # Estimate new velocity after discount
        expected_velocity_increase = (discount_pct * elasticity) / 100
        expected_new_velocity = daily_velocity * (1 + expected_velocity_increase)
        
        # Days to clear at new velocity
        days_to_clear = int(closing_stock / expected_new_velocity) if expected_new_velocity > 0 else None
        
        # Generate action recommendation
        if discount_pct >= 50:
            action = f"Heavy Discount ({int(discount_pct)}%)"
        elif discount_pct >= 30:
            action = f"Moderate Discount ({int(discount_pct)}%)"
        elif discount_pct >= 15:
            action = f"Light Discount ({int(discount_pct)}%)"
        else:
            action = f"Promotion ({int(discount_pct)}%)"
        
        return {
            'discount_pct': int(discount_pct),
            'expected_new_velocity': round(expected_new_velocity, 2),
            'days_to_clear': days_to_clear,
            'action': action,
            'excess_units': int(excess_units)
        }
        
    except Exception as e:
        return {
            'discount_pct': 0,
            'expected_new_velocity': 0,
            'days_to_clear': None,
            'action': f'Error: {str(e)}',
            'excess_units': 0
        }


def compute_historical_trends(current_df: pd.DataFrame, 
                               previous_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compare current month vs previous month metrics.
    
    Calculates:
    - Stock change (units and %)
    - Velocity change
    - DOI trend (improving/declining)
    - Growth classification
    
    Args:
        current_df: Current month metrics
        previous_df: Previous month metrics
    
    Returns:
        DataFrame with comparison metrics
    """
    if current_df.empty or previous_df.empty:
        return pd.DataFrame()
    
    try:
        # Merge on product identifier
        key_cols = ['channel', 'country', 'fnsku']
        
        # Select relevant columns from each
        current_cols = ['closing_stock', 'sold_units', 'daily_velocity', 'doi', 'display_name', 'returns', 'revenue']
        previous_cols = ['closing_stock', 'sold_units', 'daily_velocity', 'doi', 'returns', 'revenue']
        
        current_subset = current_df[key_cols + [c for c in current_cols if c in current_df.columns]].copy()
        previous_subset = previous_df[key_cols + [c for c in previous_cols if c in previous_df.columns]].copy()
        
        # Merge
        merged = current_subset.merge(
            previous_subset, 
            on=key_cols, 
            how='left',
            suffixes=('', '_prev')
        )
        
        # Calculate changes
        merged['stock_change'] = merged['closing_stock'] - merged['closing_stock_prev'].fillna(0)
        merged['stock_change_pct'] = np.where(
            merged['closing_stock_prev'] > 0,
            (merged['stock_change'] / merged['closing_stock_prev']) * 100,
            0
        )
        
        merged['velocity_change'] = merged['daily_velocity'] - merged['daily_velocity_prev'].fillna(0)
        merged['velocity_change_pct'] = np.where(
            merged['daily_velocity_prev'] > 0,
            (merged['velocity_change'] / merged['daily_velocity_prev']) * 100,
            0
        )
        
        merged['doi_change'] = merged['doi'] - merged['doi_prev'].fillna(0)
        
        # [NEW] Sold Units Calculation
        if 'sold_units' in merged.columns and 'sold_units_prev' in merged.columns:
            merged['sold_units_change'] = merged['sold_units'] - merged['sold_units_prev'].fillna(0)
            merged['sold_units_growth_pct'] = np.where(
                merged['sold_units_prev'] > 0,
                (merged['sold_units_change'] / merged['sold_units_prev']) * 100,
                0
            )

        # [NEW] Return Rate Calculation
        if 'returns' in merged.columns:
            merged['return_rate'] = np.where(
                merged['sold_units'] > 0,
                (merged['returns'] / merged['sold_units']) * 100,
                0
            )
            merged['return_rate'] = merged['return_rate'].fillna(0)
            
            if 'returns_prev' in merged.columns:
                merged['return_rate_prev'] = np.where(
                    merged['sold_units_prev'] > 0,
                    (merged['returns_prev'] / merged['sold_units_prev']) * 100,
                    0
                )
                merged['return_rate_prev'] = merged['return_rate_prev'].fillna(0)
                merged['return_rate_change'] = merged['return_rate'] - merged['return_rate_prev']
        
        # Classify trend
        def classify_trend(row):
            vel_change = row.get('velocity_change_pct', 0)
            doi_change = row.get('doi_change', 0)
            
            if vel_change > 20 and doi_change < 0:
                return '🚀 Strong Growth'
            elif vel_change > 10:
                return '📈 Growing'
            elif vel_change < -20:
                return '⚠️ Declining Fast'
            elif vel_change < -10:
                return '📉 Declining'
            elif doi_change > 30:
                return '📦 Building Stock'
            elif doi_change < -30:
                return '🔄 Clearing Stock'
            else:
                return '➡️ Stable'
        
        merged['trend'] = merged.apply(classify_trend, axis=1)
        
        # Round numeric columns
        for col in ['stock_change_pct', 'velocity_change_pct', 'doi_change', 'sold_units_growth_pct', 'return_rate', 'return_rate_change']:
            if col in merged.columns:
                merged[col] = merged[col].round(1)
        
        return merged
        
    except Exception as e:
        print(f"Error computing trends: {e}")
        return pd.DataFrame()




# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_session_display_name(session_info: Dict) -> str:
    """Format session info for display in dropdown."""
    name = session_info.get('session_name', 'Unknown')
    date = session_info.get('created_at', '')[:10]  # Just date part
    sku_count = session_info.get('sku_count', 0)
    return f"{name} ({date}) - {sku_count} SKUs"
