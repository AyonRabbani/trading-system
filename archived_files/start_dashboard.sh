#!/bin/bash
"""
Start Scripts for Trading Dashboards
"""

# Local Dashboard (with API keys)
echo "🚀 Starting Local Dashboard on port 8501..."
echo "   View at: http://localhost:8501"
streamlit run local_dashboard.py --server.port=8501

# Public Dashboard (for deployment)
# streamlit run public_dashboard.py --server.port=8502
