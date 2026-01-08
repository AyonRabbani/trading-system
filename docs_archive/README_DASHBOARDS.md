# Trading Dashboard Documentation

## Overview
Two separate dashboards for monitoring trading system activity:
- **local_dashboard.py**: Full-featured local dashboard with Alpaca API integration
- **public_dashboard.py**: Read-only public dashboard for Streamlit Cloud deployment

## Local Dashboard

### Features
- **Account Summary**: Real-time portfolio value, cash, buying power, daily P&L
- **Current Positions**: Live position table with P&L tracking
- **Market Scanner**: Latest scan results and top opportunities
- **Portfolio Manager Logs**: Recent trading automation logs
- **Profit Taker Logs**: Intraday profit taking activity
- **Recent Orders**: Order history and status

### Requirements
- Alpaca API keys in `.env` file
- Local filesystem access to log files
- Network access to Alpaca API

### Usage
```bash
# Start local dashboard
streamlit run local_dashboard.py

# Or use the helper script
./start_dashboard.sh
```

Access at: http://localhost:8501

### Configuration
Requires `.env` file with:
```
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
```

## Public Dashboard

### Features
- **System Status**: Shows which components are active
- **Activity Feed**: Sanitized event stream from trading system
- **Market Scanner**: Latest scan results
- **Portfolio Summary**: Latest strategy decisions

### Data Sources
- `public_events.json`: Sanitized event feed (no sensitive data)
- `scan_results.json`: Market scanner output

### Usage
```bash
# Test locally
streamlit run public_dashboard.py --server.port=8502

# Deploy to Streamlit Cloud
# Push to GitHub and connect via streamlit.io
```

### Deployment
1. Push code to GitHub
2. Go to share.streamlit.io
3. Connect repository
4. Set main file: `public_dashboard.py`
5. No secrets needed (reads from JSON files)

## Data Flow

### Local System
```
Trading Scripts → EventBroadcaster → public_events.json
                                   → WebSocket (optional)
```

### Public Sync
```
local: public_events.json → Git Push → GitHub
cloud: GitHub → Streamlit Cloud → public_dashboard.py
```

## Architecture

### Terminal-Style Design
- No charts or complex visualizations (avoiding client-side JS errors)
- Simple tables and metrics
- Text-based log display
- Minimal dependencies

### Security
- **Local Dashboard**: Never deploy publicly (contains API keys)
- **Public Dashboard**: Safe for public deployment (read-only, sanitized data)

## Monitoring Workflow

1. **Start Core Systems**:
   ```bash
   # Terminal 1: WebSocket server
   python log_broadcast_server.py
   
   # Terminal 2: Local dashboard
   streamlit run local_dashboard.py
   ```

2. **Run Trading Scripts**:
   ```bash
   # Terminal 3: Daily scan
   python daily_scanner.py --mode scan
   
   # Terminal 4: Trading automation
   python trading_automation.py --mode live
   
   # Terminal 5: Profit taker
   python intraday_profit_taker.py --mode moderate
   ```

3. **Sync to Public** (optional):
   ```bash
   # Terminal 6: Auto-sync
   ./sync_to_cloud.sh --watch
   ```

## Troubleshooting

### Local Dashboard Not Showing Data
- Check `.env` file exists and has valid API keys
- Verify internet connection to Alpaca
- Check log files exist (run trading scripts first)

### Public Dashboard Empty
- Run trading scripts locally first to generate events
- Check `public_events.json` exists and has data
- Run `./sync_to_cloud.sh` to push to GitHub
- Wait for Streamlit Cloud to redeploy

### Syntax Errors
Both dashboards use:
- No custom CSS injection
- No markdown with special characters
- No plotly charts
- Only native Streamlit components (st.write, st.caption, st.metric, st.dataframe)

This eliminates client-side JavaScript regex errors.

## Auto-Refresh
Both dashboards support optional auto-refresh:
- Enable in sidebar: "Auto-refresh (30s)"
- Dashboard reloads every 30 seconds
- Disable for manual control

## Files
- `local_dashboard.py`: Local full-featured dashboard
- `public_dashboard.py`: Public read-only dashboard
- `start_dashboard.sh`: Helper script to start local dashboard
- `event_broadcaster.py`: Dual-logs to WebSocket + JSON
- `public_event_exporter.py`: Sanitizes and exports events
