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
We need three tables in the **ap-northeast-1** (Tokyo) region.

1.  **Table 1: RateLimitTable**
    * **Partition Key:** `client_id` (String)
    * **Capacity Mode:** On-Demand
    * **TTL Setting:** Enable TTL on attribute `expires_at`.

2.  **Table 2: IPReputationTable**
    * **Partition Key:** `ip_address` (String)
    * **Capacity Mode:** On-Demand

3.  **Table 3: FluxConfig**
    * **Partition Key:** `config_key` (String)
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

## 3. Deployment

### CI/CD Automation
This project uses GitHub Actions for continuous integration and continuous deployment. The deployment is divided into two workflows:

*   **Lambda Deployment (`.github/workflows/deploy.yml`):** On every push to the `main` branch with changes in the `src/lambda` directory, the workflow will automatically deploy the AWS Lambda functions.
*   **EC2 Backend Deployment (`.github/workflows/deploy-backend.yml`):** On every push to the `main` branch with changes in the `src/backend` directory, the workflow will automatically deploy the EC2 backend.

**Secrets:**
The deployment requires the following secrets to be configured in the GitHub repository:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`
- `EC2_HOST`
- `EC2_SSH_KEY`

### Manual Deployment (for emergencies)
The following steps are for manual deployment and should only be used if the CI/CD pipeline is unavailable.

<details>
<summary>Click to expand for manual deployment instructions</summary>

### Backend Deployment (EC2)

#### Step 3.1: Launch Instance
1.  **OS:** Ubuntu 24.04 LTS or Amazon Linux 2023.
2.  **Instance Type:** t2.micro (Free Tier).
3.  **Key Pair:** Create/Select `test`.
4.  **Network:** Default VPC, Public Subnet (Auto-assign Public IP: Enable).

#### Step 3.2: Configure Firewall (Security Group)
*This allows the Lambda to talk to the EC2.*

1.  Go to **Security Groups** > Select the EC2 SG.
2.  **Inbound Rules:**
    * **Type:** Custom TCP
    * **Port:** `8000`
    * **Source:** `172.31.0.0/16` (Allows internal VPC traffic).
    * **Type:** SSH (22) -> Source: My IP / Anywhere IPv4. (For management)

#### Step 3.3: Initial Code Setup & Service Configuration
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
sudo nano /etc/systemd/system/fluxapi.service
# Paste into fluxapi.service:

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

sudo systemctl daemon-reload
sudo systemctl enable fluxapi
sudo systemctl start fluxapi
```
### Lambda Deployment (The Core)

#### Step 4.1: RateLimiterLogic
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

#### Step 4.2: fluxcontrolAdmin
Create a new Lambda function with the following settings:
*   **Function Name:** `fluxcontrolAdmin`
*   **Runtime:** Python 3.12

**Permissions (IAM Role):**
Create a new role with the `AmazonDynamoDBFullAccess` policy.

**Code:**
*   Zip the `src/lambda/fluxcontrolAdmin.py` file and upload it as the function's code.

### API Gateway Setup
#### Step 5.1: Create API
Type: REST API.

Name: `fluxcontrolAPI`.

#### Step 5.2: Configure Routes
**Resource: `/proxy`**

Method: GET (or ANY).

Integration: Lambda Function -> `RateLimiterLogic`.

Use Proxy Integration: YES (Check the box).

**Resource: `/admin`**

Method: GET & POST.

Integration: Lambda Function -> `fluxcontrolAdmin`.

Use Proxy Integration: YES.

Enable CORS: Select "Enable CORS" on the `/admin` resource.

#### Step 5.3: Deploy
Click Actions > Deploy API.

Stage Name: `dev`.

Copy the Invoke URL.
</details>

---

## 4. Local Development Setup

### Backend
1.  Navigate to the `src/backend` directory.
2.  Install the dependencies: `pip install -r requirements.txt`
3.  Run the FastAPI server: `uvicorn main:app --reload`
The backend will be available at `http://127.0.0.1:8000`.

### Lambda Functions
Testing the Lambda functions locally is complex. It's recommended to deploy them to a development environment in AWS for testing. The `experiments/clients` directory contains scripts to test the deployed functions.

---

## 5. Verification Checklist
[ ] **Local Backend:** Run `curl http://localhost:8000` locally. Should return `200 OK`.
[ ] **Deployed Backend:** Run `curl http://{EC2_PUBLIC_IP}:8000` (if you have a public IP). Should return `200 OK`.
[ ] **VPC Link:** Run `curl https://{api_id}.../dev/proxy`. Should return `200 OK`.
[ ] **Rate Limit:** Run the `experiments/clients/adaptive_monitor.js` script. Should see `429` errors.
[ ] **Shield Mode:** Run the `experiments/clients/smart_client.js` script. Should see the puzzle challenge and solution.
[ ] **Admin Panel:** Make a `GET` request to `https://{api_id}.../dev/admin`. Should return a list of IPs.

---

## 6. Troubleshooting Guide

*   **Issue:** `502 Bad Gateway` from the `/proxy` endpoint.
    *   **Cause:** The Lambda function cannot reach the backend EC2 instance.
    *   **Solution:**
        1.  Verify the EC2 instance is running.
        2.  Check the EC2 security group allows inbound traffic from the Lambda's security group on port 8000.
        3.  Ensure the `TARGET_IP` in `src/lambda/RateLimiterLogic.py` is correct.

*   **Issue:** Lambda function times out.
    *   **Cause:** The Lambda function cannot access DynamoDB or the backend.
    *   **Solution:**
        1.  Verify the VPC Gateway Endpoint for DynamoDB is configured correctly.
        2.  Check the Lambda's VPC and subnet settings.
        3.  Increase the Lambda function's timeout setting.

*   **Issue:** `403 Forbidden` for all requests.
    *   **Cause:** Your IP address has been banned.
    *   **Solution:** Use the Admin API to unban your IP or wait for the 24-hour ban to expire.

---

## 7. Emergency Commands
**Unlock a User Manually (CLI):**

```bash
curl -X POST https://{api_id}.execute-api.ap-northeast-1.amazonaws.com/dev/admin \
   -H "Content-Type: application/json" \
   -d '{"ip": "1.2.3.4", "action": "unban"}'
```

**Update System Configuration (CLI):**
```bash
curl -X POST https://{api_id}.execute-api.ap-northeast-1.amazonaws.com/dev/admin \
   -H "Content-Type: application/json" \
   -d '{"action": "config", "mode": "shield", "difficulty": 4, "cpu_threshold": 80}'
```

**Restart Backend:**

```bash
sudo systemctl restart fluxapi
```
**View Logs:**

Lambda: CloudWatch > Log Groups > `/aws/lambda/RateLimiterLogic`

Backend: `journalctl -u fluxapi -f`
