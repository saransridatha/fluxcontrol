# Product Requirements Document: FluxControl

**Project Name:** FluxControl  
**Version:** 1.2  
**Date:** January 14, 2026  
**Status:** In Development  

## 1. Introduction

FluxControl is a cloud-native security middleware designed to protect backend Application Programming Interfaces (APIs) from excessive traffic and abuse. In modern web architecture, APIs are vulnerable to Distributed Denial of Service (DDoS) attacks and brute-force attempts. This project aims to solve this problem by implementing a serverless rate-limiting solution using AWS technologies.

The system acts as a "traffic warden," sitting between the public internet and the private backend servers. It enforces strict traffic policies, ensuring that no single user can overwhelm the system, while providing administrators with a dashboard to monitor and manage security threats.

## 2. Team Structure and Responsibilities

The project responsibilities are divided to simulate a professional software development lifecycle (SDLC).

| Member Name | Role | Responsibilities |
| :--- | :--- | :--- |
| **Saran Sri Datha Madhipati** | **Lead Architect & Core Logic** | Responsible for the entire AWS infrastructure setup (VPC, Subnets, Gateway Endpoints). He writes the core Python logic for the Rate Limiter Lambda and manages the Terraform Infrastructure as Code (IaC). |
| **Parijat Pal** | **Full Stack Developer** | Responsible for the User Experience (UX) and Administrative controls. He develops the `fluxcontrolAdmin` API and builds the frontend dashboard (React/Vue) to ensure the system is usable for non-technical operators. |
| **Sumit Joshi** | **Database Administrator** | Responsible for the design and maintenance of the DynamoDB tables (`RateLimitTable` and `IPReputationTable`). He also monitors system logs and creates CloudWatch dashboards to track database performance. |
| **Ritvij** | **Quality Assurance (QA) Lead** | Responsible for stress testing and validation. He uses the custom-built automation tool `httpTest` to simulate high-traffic scenarios and verify that the rate limiter blocks requests accurately. |
| **Kavya Rastogi** | **Documentation Lead** | Responsible for maintaining the project report, API specifications, and compliance documents. He ensures all technical decisions and architectural diagrams are properly recorded for the final presentation. |

## 3. Problem Statement

Our backend services, currently hosted on EC2 instances, are exposed to the public internet. Without a filtering layer, they are susceptible to:
1.  **Traffic Spikes:** Sudden surges in requests that crash the server.
2.  **Resource Exhaustion:** Malicious scripts consuming all CPU/RAM.
3.  **Lack of Visibility:** No easy way to see who is abusing the API or to ban them manually.

## 4. Proposed Solution

We propose a **Serverless Token Bucket variant** running on AWS Lambda. The system utilizes a "Check-then-Act" architecture supported by high-speed atomic counters in DynamoDB.

### Key Architectural Decisions:
* **VPC Isolation:** The logic runs inside a private VPC subnet for security.
* **Private Connectivity:** Communication with the backend occurs over private IP addresses (172.x.x.x), preventing outside access.
* **Atomic Counters:** We use DynamoDB atomic updates to handle concurrency, ensuring accurate counting even during parallel attacks.

## 5. Functional Requirements

### 5.1. Traffic Shaping (The Rate Limiter)
* **Windowing Logic:** The system must utilize a Clock-Aligned Fixed Window algorithm.
* **Threshold:** A limit of **5 requests per 10-second window** must be enforced per unique client IP address.
* **Response:**
    * *Under Limit:* Request is proxied to the private EC2 backend.
    * *Over Limit:* System returns `429 Too Many Requests` immediately.

### 5.2. Reputation Management (The Ban Hammer)
* **Violation Tracking:** Every time a user hits the rate limit (receives a 429), their "Violation Count" in the `IPReputationTable` must increment.
* **Permanent Ban:** If the violation count exceeds **50**, the IP address is flagged as "Banned."
* **Ban Duration:** A banned IP receives a `403 Forbidden` response for a duration of **24 hours**.

### 5.3. Administrative Dashboard
* **User Management:** Administrators must be able to view a paginated list of all IP addresses that have violated rules.
* **Manual Override:** The interface must allow administrators to manually "Ban" a suspicious IP or "Unban" a legitimate user who was blocked accidentally.
* **Usability:** The dashboard must provide visual cues (e.g., red highlighting for banned users) to improve operational efficiency.

## 6. Non-Functional Requirements

* **Latency:** The overhead introduced by the rate limiter logic should not exceed 100 milliseconds per request.
* **Scalability:** The system must handle bursts of traffic without manual intervention, leveraging AWS Lambda's auto-scaling capabilities.
* **Data Integrity:** The request counts must be consistent. Race conditions (two requests reading the same counter value) must be prevented using atomic database operations.

## 7. Testing Strategy

Testing will be conducted primarily using the **httpTest** tool developed in-house.

* **Tool Source:** [https://github.com/saransridatha/httpTest](https://github.com/saransridatha/httpTest)
* **Scope:**
    1.  **Functional Testing:** Verifying that the 6th request in a 10-second window fails.
    2.  **Concurrency Testing:** Simulating 50+ concurrent threads to ensure the database counters do not drift.
    3.  **End-to-End Testing:** Verifying that a valid request successfully retrieves data from the EC2 backend via the private network.

## 8. Future Scope

* **Geographic Blocking:** Adding logic to block traffic from specific countries based on IP geolocation.
* **User Authentication:** Integrating API Keys so that different users can have different rate limits (e.g., Premium users get 100 req/sec).
* **Machine Learning:** Implementing anomaly detection to identify attack patterns that are slower than the hard rate limit (e.g., "Low and Slow" attacks).