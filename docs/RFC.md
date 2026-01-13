# RFC 001: FluxControl Rate Limiting Architecture

| Metadata | Details |
| :--- | :--- |
| **Title** | FluxControl: Scalable Serverless Rate Limiting System |
| **Authors** | Saran Sri Datha Madhipati, Parijat Pal, Sumit Joshi |
| **Status** | Implementation Phase |
| **Date** | January 14, 2026 |
| **Version** | 1.0 |

## 1. Abstract

This document proposes the technical design for **FluxControl**, a middleware solution intended to throttle incoming HTTP requests to backend services. The system utilizes a serverless architecture on AWS, leveraging Lambda for compute and DynamoDB for state management. The core mechanism involves a distributed atomic counter with a clock-aligned fixed window algorithm to ensure strict traffic shaping (5 requests/10 seconds) and long-term offender banning (24 hours after 50 violations).

## 2. Motivation

Our current backend infrastructure is hosted on a standalone EC2 instance. It handles requests synchronously and lacks an inherent queuing or filtering mechanism. This makes the application trivial to crash using simple flooding scripts or the `httpTest` tool.

We require a solution that:
1.  **Decouples Security from Logic:** The backend developers should not write security code inside the business API.
2.  **Scales independently:** The security layer must absorb traffic spikes without consuming backend CPU resources.
3.  **Preserves State:** Traffic counts must be consistent across distributed execution environments.

## 3. Proposed Architecture

The system follows the **"VPC-Walled Garden"** pattern to ensure maximum security.

### 3.1. High-Level Design



1.  **Ingress:** Traffic enters via **Amazon API Gateway**, which handles SSL termination and standard request validation.
2.  **Processing:** The request is passed to the **RateLimiterLogic Lambda**. This function resides inside a private VPC Subnet.
3.  **State Check:** The Lambda communicates with **Amazon DynamoDB** via a VPC Gateway Endpoint (avoiding public internet traversal) to check the user's current usage count.
4.  **Routing:**
    * If allowed, the Lambda proxies the request to the **EC2 Backend** using its Private IPv4 address.
    * If blocked, the Lambda returns a `429` status code immediately.

### 3.2. Network Security

Unlike standard setups, we do not use a NAT Gateway to save costs.
* **Inbound:** API Gateway triggers Lambda.
* **Outbound:** Lambda has **NO** internet access. It can only talk to:
    * Internal EC2 (via Local VPC Route).
    * DynamoDB (via VPC Endpoint `vpce-xxxx`).

## 4. Data Design

We utilize two distinct DynamoDB tables to separate high-velocity ephemeral data from low-velocity persistent data.

### 4.1. Table 1: `RateLimitTable`
Stores the temporary request counts. This table experiences heavy write throughput.

* **Partition Key:** `client_id` (String).
    * *Format:* `{IP_ADDRESS}-{WINDOW_TIMESTAMP}`
    * *Example:* `192.168.1.5-1705234000`
* **Attribute:** `request_count` (Number).
* **TTL Attribute:** `expires_at` (Epoch Timestamp).
    * *Policy:* Records are automatically deleted by AWS 60 seconds after creation to manage storage costs.

### 4.2. Table 2: `IPReputationTable`
Stores the long-term history of offenders.

* **Partition Key:** `ip_address` (String).
* **Attributes:**
    * `violation_count` (Number): Cumulative number of 429 errors received.
    * `is_banned` (Boolean): Master flag to block access.
    * `ban_expiry` (Number): Epoch timestamp when the ban lifts.



## 5. Algorithmic Implementation

### 5.1. The Race Condition Problem
In a distributed system, a standard "Read-Increment-Write" logic fails under load (e.g., during an `httpTest` flood). Two requests reading `count=4` simultaneously will both write `count=5`, allowing 6 requests through.

### 5.2. The Atomic Solution
We utilize DynamoDB's `UpdateItem` API with the `ADD` expression.
```python
response = table.update_item(
    Key={'client_id': key},
    UpdateExpression="ADD request_count :inc",
    ExpressionAttributeValues={':inc': 1},
    ReturnValues="UPDATED_NEW"
)
```