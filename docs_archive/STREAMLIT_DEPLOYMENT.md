# Streamlit Cloud Deployment Guide

## ✅ Your System is Ready!

The trading system is now configured to push data to GitHub every 30 seconds, and the public dashboard will automatically fetch the latest data from GitHub.

## 🚀 Deploy to Streamlit Cloud

### Step 1: Go to Streamlit Cloud
Visit: https://share.streamlit.io/

### Step 2: Sign in with GitHub
- Click "Sign in with GitHub"
- Authorize Streamlit Cloud to access your repos

### Step 3: Deploy New App
1. Click "New app" button
2. Fill in deployment details:
   - **Repository**: `AyonRabbani/trading-system`
   - **Branch**: `main`
   - **Main file path**: `public_dashboard.py`
   - **App URL** (custom): Choose your URL slug

### Step 4: Deploy!
- Click "Deploy!"
- Streamlit will install dependencies from `requirements.txt`
- First deployment takes 2-3 minutes

### Step 5: Share URL
Your dashboard will be at:
```
https://[your-chosen-slug].streamlit.app
```

Share this URL with your team and friends!

## 📊 How It Works

```
Local Trading System
    ↓ (Events broadcast)
WebSocket Server
    ↓ (Export to file)
public_events.json + scan_results.json
    ↓ (Git push every 30 seconds)
GitHub Repository (main branch)
    ↓ (HTTP fetch every 30 seconds)
Streamlit Cloud Dashboard
    ↓ (Display)
Your Team Sees Live Updates!
```

**Total Delay**: ~60-90 seconds from event to team visibility

## 🔄 Auto-Updates

The dashboard will automatically:
- ✅ Fetch latest data from GitHub every 30 seconds (cache refresh)
- ✅ Auto-refresh the page every 30 seconds (if toggle enabled)
- ✅ Show live position changes
- ✅ Display new orders as they're placed
- ✅ Update scanner recommendations
- ✅ Refresh profit taker status

## 📱 What Your Team Sees

### Real-Time Trading Activity
- Current positions with P&L
- Recent orders (BUY/SELL with quantities and prices)
- Account value and performance
- Strategy selection and reasoning

### Scanner Intelligence
- Top scoring tickers
- Rotation recommendations
- Market regime (RISK_ON/RISK_OFF)
- Hot/cold sectors

### Performance Metrics
- Strategy backtests (BUY_HOLD, TACTICAL, SPEC, ASYM)
- Portfolio Manager decisions
- Profit taker activity
- Win rates and returns

### Full Transparency
- ✅ Exact dollar amounts
- ✅ Share quantities
- ✅ Entry and exit prices
- ✅ Real P&L calculations
- ✅ All backtest results

## 🎯 Verify Deployment

### Check Data is Flowing
1. Open your Streamlit app URL
2. Look for:
   - Events count (should be ~45-200)
   - Recent timestamp (should be within last minute)
   - Data source shows: "GitHub (AyonRabbani/trading-system)"

### Test Auto-Refresh
1. Enable "🔄 Auto-refresh (30s)" toggle
2. Watch timestamp update every 30 seconds
3. New events should appear automatically

### Verify Live Updates
1. Place a trade locally (or let profit taker run)
2. Wait 30-60 seconds
3. Check Streamlit dashboard refreshes with new data

## 🐛 Troubleshooting

### Dashboard Shows Old Data
```bash
# Check sync is running locally
ps aux | grep sync_to_cloud

# Verify recent GitHub commits
git log --oneline -5

# Manual sync to force update
./sync_to_cloud.sh
```

### Dashboard Shows "Could not fetch from GitHub"
- Check your repo is public OR Streamlit has access to private repos
- Verify files exist: https://github.com/AyonRabbani/trading-system/blob/main/public_events.json
- Check GitHub is not rate-limiting (unlikely with 30s cache)

### Events Not Updating
```bash
# Check WebSocket server is exporting events
tail -f logs/broadcast_server.log | grep "public_events"

# Verify file is being updated
stat public_events.json

# Check sync is pushing
tail -f logs/cloud_sync.log
```

### Streamlit App Won't Deploy
- Check `requirements.txt` has all dependencies
- Verify `public_dashboard.py` has no syntax errors
- Check Streamlit Cloud logs for error details

## 🔐 Security Notes

### What's Public
Your Streamlit app URL will show:
- All trading activity (positions, orders, P&L)
- Account balance
- Strategy decisions
- Scanner recommendations

### What's Protected
- API keys (not in public files)
- AWS credentials (not in public files)
- Private code logic (only in GitHub)

### Sharing Best Practices
- Only share URL with trusted team/friends
- Consider password-protecting the Streamlit app (Streamlit Cloud feature)
- Monitor who has access
- Can revoke by taking down the app

## 📈 Next Steps

1. **Deploy the app** following steps above
2. **Share URL** with your team via Slack/Discord/Email
3. **Monitor together** during market hours
4. **Discuss trades** as they happen in real-time

Your team will have complete visibility into your trading system! 🎉

## 🛠️ Advanced Configuration

### Custom Domain (Streamlit Cloud Pro)
- Connect your own domain
- Example: `trading.yourdomain.com`

### Password Protection
- In Streamlit Cloud settings
- Add authentication layer
- Share credentials with team only

### Faster Updates
Edit `start_full_trading_system.sh` line 186:
```bash
./sync_to_cloud.sh --watch --interval 15  # 15 seconds instead of 30
```

Remember: Faster = more GitHub commits and API calls

## 📞 Support

If deployment doesn't work:
1. Check all services are running: `cat .trading_pids`
2. Verify data on GitHub: `curl https://raw.githubusercontent.com/AyonRabbani/trading-system/main/public_events.json`
3. Test locally first: `streamlit run public_dashboard.py`
4. Check Streamlit Cloud logs for errors

Happy team monitoring! 🚀
