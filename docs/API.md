# FluxControl API Documentation

This document provides detailed information about the FluxControl API. It's intended for frontend developers who are building a management dashboard and for anyone who wants to interact with the FluxControl system programmatically.

## Base URL

The base URL for the API is provided by the AWS API Gateway deployment. It will look something like this:

`https://{api_id}.execute-api.{region}.amazonaws.com/{stage}`

For this project, the stage is typically `prod`.

**Note:** The example client scripts in the `experiments/clients` directory have a hardcoded URL. You will need to replace this with the invoke URL of your deployed API Gateway.

## Authentication

Currently, the API does not require any authentication. This is a planned future enhancement.

---

## Endpoints

### Admin API

The admin API provides endpoints for monitoring and managing the rate limiter.

#### `GET /admin`

Retrieves a list of all IP addresses that have interacted with the rate limiter, along with their reputation.

*   **Method:** `GET`
*   **Endpoint:** `/admin`
*   **Request:** No body or parameters required.
*   **Success Response:**
    *   **Code:** `200 OK`
    *   **Body:** A JSON array of IP reputation objects. Each object has the following structure:
        ```json
        [
            {
                "ip_address": "1.2.3.4",
                "violation_count": 10,
                "is_banned": false,
                "ban_expiry": 0,
                "is_seamless": true,
                "seamless_expiry": 1705318800,
                "last_seen": 1705232400
            }
        ]
        ```
*   **Error Response:**
    *   **Code:** `500 Internal Server Error`
    *   **Body:** `{"error": "Database error message"}`

#### `POST /admin`

Performs various administrative actions.

*   **Method:** `POST`
*   **Endpoint:** `/admin`
*   **Request Body:** A JSON object specifying the action to perform.

##### Actions

1.  **`ban`**: Manually ban an IP address.
    *   **Request Body:** `{"action": "ban", "ip": "1.2.3.4"}`
    *   **Response:** `{"message": "User 1.2.3.4 BANNED."}`

2.  **`unban`**: Manually unban an IP address.
    *   **Request Body:** `{"action": "unban", "ip": "1.2.3.4"}`
    *   **Response:** `{"message": "User 1.2.3.4 UNBANNED."}`

3.  **`seamless`**: Put an IP address in "seamless" (VIP) mode, bypassing rate limiting.
    *   **Request Body:** `{"action": "seamless", "ip": "1.2.3.4"}`
    *   **Response:** `{"message": "User 1.2.3.4 is in SEAMLESS MODE."}`

4.  **`unseamless`**: Revoke seamless mode for an IP address.
    *   **Request Body:** `{"action": "unseamless", "ip": "1.2.3.4"}`
    *   **Response:** `{"message": "User 1.2.3.4 VIP status REVOKED."}`

5.  **`config`**: Update the global configuration of the rate limiter.
    *   **Request Body:** `{"action": "config", "mode": "shield"}`
        *   `mode` can be `normal` or `shield`.
    *   **Response:** `{"message": "System Mode set to: shield"}`

---

### Proxy API

The proxy API is the main entry point for your backend services. It's protected by the rate limiter.

#### `GET /proxy`

Proxies requests to the backend service if the rate limit is not exceeded.

*   **Method:** `GET` (or any other method your backend supports)
*   **Endpoint:** `/proxy`
*   **Success Response:**
    *   **Code:** The status code from your backend service (e.g., `200 OK`).
    *   **Body:** The response body from your backend service.
*   **Error Responses:** See the [Error Codes](#error-codes) section below.

---

## Backend Health Endpoint

For the adaptive rate limiting to work, your backend service must expose a `/health` endpoint.

*   **Method:** `GET`
*   **Endpoint:** `/health`
*   **Response Body:** A JSON object with the current CPU usage of the backend server.
    ```json
    {
        "cpu": 75.5
    }
    ```

---

## Error Codes

The proxy API can return the following error codes:

| Code | Status | Description | Response Body |
| :--- | :--- | :--- | :--- |
| `401` | Unauthorized | **Shield Mode is active.** The client must solve a proof-of-work puzzle. | `{"error": "Shield Active. Solve Puzzle.", "challenge": "...", "difficulty": 4}` |
| `403` | Forbidden | The client's IP address is **banned**. | `{"error": "Access Denied", "message": "You are banned."}` |
| `429` | Too Many Requests | The client has **exceeded the rate limit**. | `{"error": "Too Many Requests", "limit": 5}` |
| `500` | Internal Server Error | An unexpected error occurred in the rate limiter logic. | `{"error": "Internal Logic Error", "details": "..."}` |

---

## Shield Mode (Proof-of-Work)

When the system is in "shield" mode, the rate limiter will block all requests that don't include a valid puzzle solution in the headers. This is a defense mechanism against DDoS attacks.

**How it works:**

1.  A client makes a request to `/proxy` without a solution.
2.  The API responds with a `401 Unauthorized` and a JSON body containing a `challenge` (the client's IP address) and a `difficulty` (number of leading zeros).
3.  The client needs to find a `solution` string such that `sha256(challenge + solution)` starts with the required number of zeros.
4.  The client then retries the request with the solution in the `X-Puzzle-Solution` header.

**Example (JavaScript):**

```javascript
async function solvePuzzle(challenge, difficulty) {
    let solution = 0;
    const prefix = '0'.repeat(difficulty);
    while (true) {
        const attempt = challenge + solution;
        const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(attempt));
        const hashHex = Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, '0')).join('');
        if (hashHex.startsWith(prefix)) {
            return solution;
        }
        solution++;
    }
}

// ... in your API call ...
const response = await fetch('/proxy');
if (response.status === 401) {
    const { challenge, difficulty } = await response.json();
    const solution = await solvePuzzle(challenge, difficulty);
    const retryResponse = await fetch('/proxy', {
        headers: {
            'X-Puzzle-Solution': solution
        }
    });
    // ... handle retryResponse
}
```
