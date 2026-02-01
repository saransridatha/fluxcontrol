# RUNBOOK: FluxControl System Setup & Recovery

**System:** FluxControl Rate Limiter    
**Last Updated:** January 14, 2026

---

## 1. Prerequisites
* AWS Account with Administrator Access.
* Python 3.9+ installed locally.
* AWS CLI configured.

---

## 2. Infrastructure Setup (Database & Network)

### Step 2.1: Create DynamoDB Tables
We need two tables in the **ap-northeast-1** (Tokyo) region.

1.  **Table 1: RateLimitTable**
    * **Partition Key:** `client_id` (String)
    * **Capacity Mode:** On-Demand
    * **TTL Setting:** Enable TTL on attribute `expires_at`.

2.  **Table 2: IPReputationTable**
    * **Partition Key:** `ip_address` (String)
    * **Capacity Mode:** On-Demand

### Step 2.2: VPC Gateway Endpoint (CRITICAL)
*Without this, the Lambda cannot talk to the Database.*

1.  Go to **VPC Console** > **Endpoints**.
2.  Click **Create Endpoint**.
3.  **Service Name:** `com.amazonaws.ap-northeast-1.dynamodb` (Type: Gateway).
4.  **VPC:** Select the Default VPC.
5.  **Route Tables:** Check the box for the **Main Route Table** (associated with your subnets).
6.  Click **Create**.

---

## 3. Backend Deployment (EC2)

***

**NOTE:** The deployment of the EC2 backend code is now automated through a CI/CD pipeline using GitHub Actions. Any push to the `main` branch with changes in the `src/backend` directory will automatically deploy the new code to the EC2 instance. The steps below are for the **initial setup** of a new EC2 instance and are preserved for reference.

***

### Step 3.1: Launch Instance
1.  **OS:** Ubuntu 24.04 LTS or Amazon Linux 2023.
2.  **Instance Type:** t2.micro (Free Tier).
3.  **Key Pair:** Create/Select `test`.
4.  **Network:** Default VPC, Public Subnet (Auto-assign Public IP: Enable).

### Step 3.2: Configure Firewall (Security Group)
*This allows the Lambda to talk to the EC2.*

1.  Go to **Security Groups** > Select the EC2 SG.
2.  **Inbound Rules:**
    * **Type:** Custom TCP
    * **Port:** `8000`
    * **Source:** `172.31.0.0/16` (Allows internal VPC traffic).
    * **Type:** SSH (22) -> Source: My IP / Anywhere IPv4. (For management)

### Step 3.3: Initial Code Setup & Service Configuration
SSH into the instance and run:

```bash
# 1. Install Dependencies
sudo apt update && sudo apt install python3-pip git -y

# 2. Clone the repository
git clone https://github.com/saransridatha/fluxcontrol.git
cd fluxcontrol

# 3. Install Python dependencies
pip3 install -r src/backend/requirements.txt

# 4. Create Systemd Service (For auto-restart)
# The backend service must implement a /health endpoint for the adaptive rate limiting to work.
# See src/backend/main.py for an example.
sudo nano /etc/systemd/system/fluxapi.service
# Paste into fluxapi.service:

# Ini, TOML

[Unit]
Description=FluxControl Backend API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/fluxcontrol
ExecStart=/usr/bin/python3 -m uvicorn src.backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
# Start the Service:

# Bash

sudo systemctl daemon-reload
sudo systemctl enable fluxapi
sudo systemctl start fluxapi
```
## 4. Lambda Deployment (The Core)

***

**NOTE:** The deployment of the Lambda functions is now automated through a CI/CD pipeline using GitHub Actions. Any push to the `main` branch with changes in the `src/lambda` directory will automatically deploy the functions. The steps below are for manual deployment and are preserved for reference or emergency use.

***
### Step 4.1: RateLimiterLogic 
Create a new Lambda function with the following settings:
*   **Function Name:** `RateLimiterLogic`
*   **Runtime:** Python 3.12

**Permissions (IAM Role):**
Create a new role with the following policies:
*   `AmazonDynamoDBFullAccess`
*   `AWSLambdaVPCAccessExecutionRole` (Crucial for VPC support)

**Network Configuration (VPC):**
*   **VPC:** Select your Default VPC.
*   **Subnets:** Select at least two private subnets.
*   **Security Group:** Select the Default Security Group.

**General Configuration:**
*   **Timeout:** Increase to `15` seconds.

**CRITICAL: Update Backend IP Address**
Before deploying, the private IP address of your EC2 backend **must be hardcoded** into the source code.

1.  Open `src/lambda/RateLimiterLogic.py`.
2.  Find the line `TARGET_IP = "http://172.31.34.253:8000"`.
3.  Replace the IP address with the private IP of your EC2 instance.

**Code:**
*   Create a deployment package by zipping the contents of `src/lambda`. Make sure to include the `requests` library.
*   Upload the zip file as the function's code.

### Step 4.2: fluxcontrolAdmin 
Create a new Lambda function with the following settings:
*   **Function Name:** `fluxcontrolAdmin`
*   **Runtime:** Python 3.12

**Permissions (IAM Role):**
Create a new role with the `AmazonDynamoDBFullAccess` policy.

**Code:**
*   Zip the `src/lambda/fluxcontrolAdmin.py` file and upload it as the function's code.

## 5. API Gateway Setup
### Step 5.1: Create API
Type: REST API.

Name: `fluxcontrolAPI`.

### Step 5.2: Configure Routes
**Resource: `/proxy`**

Method: GET (or ANY).

Integration: Lambda Function -> `RateLimiterLogic`.

Use Proxy Integration: YES (Check the box).

**Resource: `/admin`**

Method: GET & POST.

Integration: Lambda Function -> `fluxcontrolAdmin`.

Use Proxy Integration: YES.

Enable CORS: Select "Enable CORS" on the `/admin` resource.

### Step 5.3: Deploy
Click Actions > Deploy API.

Stage Name: `dev`.

Copy the Invoke URL.

## 6. Verification Checklist
[ ] Backend Status: Run `curl http://localhost:8000` inside EC2. Should return `200 OK`.

[ ] VPC Link: Run `curl https://{api_id}.../dev/proxy`. Should return `200 OK`.

[ ] Rate Limit: Run the attack script (10 fast requests). Should see `429` errors.

[ ] Admin Panel: Open `admin.html` and verify it loads the user list.

## 7. Emergency Commands
**Unlock a User Manually (CLI):**

```bash
curl -X POST https://{api_id}.execute-api.ap-northeast-1.amazonaws.com/dev/admin \
   -H "Content-Type: application/json" \
   -d '{"ip": "1.2.3.4", "action": "unban"}'
```
**Restart Backend:**

```bash
sudo systemctl restart fluxapi
```
**View Logs:**

Lambda: CloudWatch > Log Groups > `/aws/lambda/RateLimiterLogic`

Backend: `journalctl -u fluxapi -f`
