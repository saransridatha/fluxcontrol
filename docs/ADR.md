# Architecture Decision Records (ADR) - FluxControl

**Project:** FluxControl Rate Limiter  
**Date:** January 14, 2026  
**Status:** In Development

---

## ADR 001: Adoption of Atomic Counters for Rate Limiting 
#### Author: Saran Sri Datha

### Context
Initially, the rate-limiting logic used a "Read-Modify-Write" pattern:
1.  Read the current count from the database.
2.  Increment the count in application memory.
3.  Write the new count back to the database.

**Problem:** During stress testing with high concurrency (simultaneous requests), a **Race Condition** occurred. Multiple instances of the Lambda function read the same initial value (e.g., `count=3`) before any of them could write the update. This allowed users to exceed the limit (e.g., 7 requests succeeding despite a limit of 5).

### Decision
We switched to **DynamoDB Atomic Counters** using the `ADD` UpdateExpression.

### Consequences
* **Positive:** The database handles the serialization of updates. The returned value is always the accurate, post-increment count. This eliminated the race condition entirely.
* **Negative:** We cannot "read" the value without incrementing it in a single step, which slightly changes the logic flow (we increment first, then check if we crossed the line).

---

## ADR 002: Clock-Aligned Fixed Window Strategy
#### Author: Saran Sri Datha, Sumit Joshi

### Context
The initial implementation used a "sliding expiration" where every new request from a blocked user would reset the expiration timer.
**Problem:** A user who continued to spam the API after being blocked would effectively keep themselves blocked forever (the "Penalty Box" effect), rather than being released after the window passed.

### Decision
We implemented a **Clock-Aligned Fixed Window** algorithm.
* The time window is determined by the server clock (e.g., `12:00:00` to `12:00:10`).
* The database key is constructed as `{IP}-{WindowTimestamp}`.

### Consequences
* **Positive:** The system is strictly deterministic. At `XX:XX:10`, the key changes, and the count automatically resets to 0, regardless of user behavior.
* **Positive:** Simplifies the database TTL (Time To Live) logic, as keys naturally expire.

---

## ADR 003: VPC Integration for Backend Security
#### Author: Saran Sri Datha, Ritvij

### Context
The backend API is hosted on an AWS EC2 instance. For security reasons, this instance is deployed in a private network configuration with no public IP address exposed for the API port (8000).
**Problem:** The AWS Lambda function (running in the public AWS zone by default) could not establish a connection to the private IP (`172.x.x.x`) of the EC2 instance, resulting in timeouts.

### Decision
We configured the Lambda function to run **inside the Virtual Private Cloud (VPC)**, attached to the private subnets.

### Consequences
* **Positive:** The Lambda can communicate directly with the backend over the private network, reducing latency and exposure.
* **Negative:** Lambda functions inside a VPC lose default access to the public internet. This broke connectivity to AWS services like DynamoDB. (See ADR 005).

---

## ADR 004: Microservices Separation for Administration
#### Author: Parijat Pal, Saran Sri Datha

### Context
The system requires both high-speed traffic processing (Rate Limiting) and state management (Banning/Unbanning IPs).
**Problem:** Combining administrative logic (scanning tables, manual edits) into the main proxy Lambda would increase the deployment package size and risk impacting the latency of critical traffic.

### Decision
We adopted a **Microservices pattern**, creating two distinct Lambda functions:
1.  `RateLimiterLogic`: Optimized for speed, handles only traffic filtering.
2.  `fluxcontrolAdmin`: Optimized for functionality, handles the dashboard API.

### Consequences
* **Positive:** Decoupling allows us to update the Admin API without redeploying or risking the stability of the core traffic proxy.
* **Positive:** Separate IAM roles allow for granular permission control (e.g., only the Admin Lambda needs `Scan` permissions).

---

## ADR 005: Cost Optimization via VPC Gateway Endpoints
#### Author: Saran Sri Datha, Parijat Pal

### Context
After moving the Lambda to the VPC (ADR 003), it lost access to DynamoDB. The standard solution is to use a **NAT Gateway** to route traffic to the internet.
**Problem:** A NAT Gateway costs approximately **$0.045/hour (~$32/month)**, which exceeds the budget for this project.

### Decision
We implemented a **VPC Gateway Endpoint** for DynamoDB.

### Consequences
* **Positive:** This service is provided by AWS at **no cost**.
* **Positive:** It provides a secure, private tunnel from the VPC to DynamoDB without traversing the public internet.
* **Negative:** The Lambda remains isolated from the wider internet (cannot access 3rd party APIs), but this aligns with our security requirements ("Egress Filtering").

---

## ADR 006: Background Service Management (Systemd)
#### Author: Saran Sri Datha

### Context
During development, the backend API was run manually via SSH sessions (`python main.py`).
**Problem:** The API would crash or terminate whenever the SSH session timed out or network connectivity was interrupted, causing "502 Bad Gateway" errors.

### Decision
We created a **Systemd Service** (`fluxapi.service`) to manage the backend process.

### Consequences
* **Positive:** The application starts automatically on server boot.
* **Positive:** The `Restart=always` configuration ensures the API automatically recovers from crashes within 3 seconds, significantly improving system availability.

---

## ADR 007: CI/CD with GitHub Actions
#### Author: Saran Sri Datha

### Context
Previously, deploying the Lambda functions was a manual process involving zipping the files and uploading them through the AWS console.
**Problem:** This manual process is error-prone, time-consuming, and not easily repeatable. It also makes it difficult to track changes and roll back to previous versions.

### Decision
We implemented a **CI/CD pipeline using GitHub Actions**.

### Consequences
* **Positive:** Deployments are now automated. Any push to the `main` branch with changes in the `src` directory triggers a deployment.
* **Positive:** The process is now consistent and repeatable.
* **Positive:** We can now track the history of deployments in the GitHub Actions tab.
* **Negative:** The deployment process is now dependent on GitHub Actions. If GitHub Actions is down, we cannot deploy.