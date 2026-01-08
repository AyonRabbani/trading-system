# Trading Dashboard Deployment Guide

This guide covers multiple deployment options for the Streamlit trading dashboard.

---

## 🚀 Quick Start Options

### Option 1: Local Development (Already Running)
```bash
streamlit run trading_dashboard.py
```
Access at: http://localhost:8501

---

## 🐳 Docker Deployment (Recommended for Production)

### Build and Run
```bash
# Build the Docker image
docker build -t trading-dashboard .

# Run the container
docker run -p 8501:8501 \
  -e ALPACA_API_KEY="your_api_key" \
  -e ALPACA_API_SECRET="your_api_secret" \
  -e POLYGON_API_KEY="your_polygon_key" \
  trading-dashboard
```

### Run with Docker Compose
Create `docker-compose.yml`:
```yaml
version: '3.8'
services:
  dashboard:
    build: .
    ports:
      - "8501:8501"
    environment:
      - ALPACA_API_KEY=${ALPACA_API_KEY}
      - ALPACA_API_SECRET=${ALPACA_API_SECRET}
      - POLYGON_API_KEY=${POLYGON_API_KEY}
    volumes:
      - ./logs:/app/logs
      - ./scan_results.json:/app/scan_results.json
    restart: unless-stopped
```

Run with:
```bash
docker-compose up -d
```

---

## ☁️ Cloud Deployment Options

### 1. Streamlit Cloud (Free Tier Available)

**Steps:**
1. Push code to GitHub repository
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub account
4. Select repository and branch
5. Add secrets in "Advanced settings":
   ```toml
   ALPACA_API_KEY = "your_key"
   ALPACA_API_SECRET = "your_secret"
   POLYGON_API_KEY = "your_key"
   ```
6. Deploy!

**Pros:** Free, auto-deploys on git push, SSL included
**Cons:** Public by default, limited resources on free tier

---

### 2. AWS EC2 Deployment

**Launch EC2 Instance:**
```bash
# SSH into your EC2 instance
ssh -i your-key.pem ec2-user@your-instance-ip

# Install Docker
sudo yum update -y
sudo yum install docker -y
sudo service docker start
sudo usermod -a -G docker ec2-user

# Clone your repository
git clone your-repo-url
cd your-repo

# Build and run
docker build -t trading-dashboard .
docker run -d -p 8501:8501 \
  -e ALPACA_API_KEY="your_key" \
  -e ALPACA_API_SECRET="your_secret" \
  -e POLYGON_API_KEY="your_key" \
  --restart always \
  trading-dashboard
```

**Security Group Settings:**
- Allow inbound TCP on port 8501 from your IP only
- Allow SSH (port 22) from your IP only

---

### 3. Google Cloud Run

**Deploy serverless container:**
```bash
# Install gcloud CLI and authenticate
gcloud auth login

# Build and push to Container Registry
gcloud builds submit --tag gcr.io/your-project-id/trading-dashboard

# Deploy to Cloud Run
gcloud run deploy trading-dashboard \
  --image gcr.io/your-project-id/trading-dashboard \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars ALPACA_API_KEY=your_key,ALPACA_API_SECRET=your_secret,POLYGON_API_KEY=your_key
```

**Pros:** Auto-scaling, pay-per-use, serverless
**Cons:** Cold starts, session state may reset

---

### 4. DigitalOcean Droplet

**Quick Setup:**
```bash
# Create droplet with Docker pre-installed
# SSH into droplet
ssh root@your-droplet-ip

# Clone and run
git clone your-repo-url
cd your-repo
docker build -t trading-dashboard .
docker run -d -p 8501:8501 \
  -e ALPACA_API_KEY="your_key" \
  -e ALPACA_API_SECRET="your_secret" \
  -e POLYGON_API_KEY="your_key" \
  --restart always \
  trading-dashboard
```

**Setup Nginx reverse proxy (optional):**
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

---

## 🔒 Security Best Practices

### Environment Variables
Never hardcode API keys. Use environment variables:

**Create `.env` file (don't commit!):**
```bash
ALPACA_API_KEY=your_key_here
ALPACA_API_SECRET=your_secret_here
POLYGON_API_KEY=your_key_here
```

**Update dashboard to read from env:**
```python
import os
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY', 'fallback_key')
ALPACA_API_SECRET = os.getenv('ALPACA_API_SECRET', 'fallback_secret')
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY', 'fallback_key')
```

### Add Authentication
For production, add password protection:

**Create `.streamlit/secrets.toml`:**
```toml
password = "your_secure_password"
```

**Add to dashboard:**
```python
import streamlit as st

def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Password incorrect")
        return False
    else:
        return True

if not check_password():
    st.stop()
```

### Firewall Rules
```bash
# Allow only your IP to access dashboard
sudo ufw allow from your.ip.address to any port 8501
sudo ufw enable
```

---

## 🔧 Configuration

### Update API Endpoints
For paper trading (testing):
```python
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
```

For live trading:
```python
ALPACA_BASE_URL = "https://api.alpaca.markets"
```

### Adjust Auto-Refresh
In `trading_dashboard.py`, modify:
```python
auto_refresh = st.sidebar.checkbox("Auto-refresh (10s)", value=True)
if auto_refresh:
    time.sleep(10)  # Change to desired interval
    st.rerun()
```

---

## 📊 Monitoring & Logs

### View Docker Logs
```bash
docker logs -f container-name
```

### Log Rotation
Add to `docker-compose.yml`:
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### Health Checks
```bash
# Check if container is healthy
docker ps

# Manual health check
curl http://localhost:8501/_stcore/health
```

---

## 🚨 Troubleshooting

### Container won't start
```bash
# Check logs
docker logs container-name

# Check if port is in use
lsof -i :8501

# Rebuild without cache
docker build --no-cache -t trading-dashboard .
```

### Process management not working
- Ensure scripts (scanner, trading, profit_taker) are in same directory
- Check file permissions: `chmod +x *.py`
- Verify Python path in subprocess calls

### API connection issues
- Verify API keys are set correctly
- Check network connectivity from container
- Ensure using correct API endpoints (paper vs live)

---

## 📈 Performance Optimization

### Increase cache TTL for stable data
```python
@st.cache_data(ttl=300)  # 5 minutes
def get_portfolio_history():
    # ...
```

### Reduce auto-refresh frequency
```python
time.sleep(30)  # Refresh every 30 seconds instead of 10
```

### Use connection pooling
```python
import requests
session = requests.Session()
# Use session.get() instead of requests.get()
```

---

## 🔄 CI/CD Pipeline (GitHub Actions)

Create `.github/workflows/deploy.yml`:
```yaml
name: Deploy Dashboard

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build and push Docker image
        run: |
          docker build -t your-registry/trading-dashboard .
          docker push your-registry/trading-dashboard
      
      - name: Deploy to server
        run: |
          ssh user@your-server 'docker pull your-registry/trading-dashboard && docker-compose up -d'
```

---

## 📝 Maintenance

### Backup Data
```bash
# Backup scan results and logs
docker cp container-name:/app/logs ./backup/logs
docker cp container-name:/app/scan_results.json ./backup/
```

### Update Dashboard
```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d
```

---

## 🎯 Recommended Setup

**For Testing:**
- Local: `streamlit run trading_dashboard.py`
- Use paper trading API endpoints

**For Personal Use:**
- Docker on home server or DigitalOcean droplet ($6/month)
- Add password authentication
- Restrict access by IP

**For Team Use:**
- Streamlit Cloud with GitHub auth
- Or AWS EC2 with load balancer
- Add user management

---

## 💡 Next Steps

1. Test dashboard locally with paper trading
2. Choose deployment method based on needs
3. Set up monitoring and alerts
4. Configure backup strategy
5. Document your specific setup

---

## 🆘 Support

If you encounter issues:
1. Check troubleshooting section above
2. Review Docker/Streamlit logs
3. Verify API keys and network connectivity
4. Test individual scripts (scanner, trading, profit_taker) separately

**Useful Commands:**
```bash
# Container shell access
docker exec -it container-name /bin/bash

# View all processes
docker ps -a

# Remove old containers
docker system prune -a
```

---

**Happy Trading! 📈**
