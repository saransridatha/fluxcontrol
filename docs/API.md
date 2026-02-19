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
    *   **Request Body:** `{"action": "config", "mode": "shield", "difficulty": 4, "cpu_threshold": 80}`
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

For the adaptive rate limiting to work, your backend service must expose a `/health` endpoint. This endpoint is part of the backend service itself, not the FluxControl API.

*   **Method:** `GET`
*   **Endpoint:** `/health`
*   **Response Body:** A JSON object with the current CPU usage of the backend server.
    ```json
    {
        "status": "alive",
        "cpu": 75.5
    }
    ```

---

## Configuration

The system is configured via the `FluxConfig` table in DynamoDB. The `config` action of the `POST /admin` endpoint can be used to update these settings.

| Parameter | Type | Description | Default |
| :--- | :--- | :--- | :--- |
| `mode` | String | The system mode. Can be `normal` or `shield`. | `normal` |
| `difficulty`| Number | The difficulty of the proof-of-work puzzle in `shield` mode. | `4` |
| `cpu_threshold`| Number | The CPU usage threshold for adaptive rate limiting. | `80` |

---

## Error Codes

The proxy API can return the following error codes:

| Code | Status | Description | Response Body |
| :--- | :--- | :--- | :--- |
| `401` | Unauthorized | **Shield Mode is active.** The client must solve a proof-of-work puzzle. The `challenge` and `difficulty` are provided in the response body. | `{"error": "Shield Active. Solve Puzzle.", "challenge": "...", "difficulty": 4}` |
| `403` | Forbidden | The client's IP address is **banned**. | `{"error": "Access Denied", "message": "You are banned."}` |
| `429` | Too Many Requests | The client has **exceeded the rate limit**. | `{"error": "Too Many Requests", "limit": 5}` |
| `500` | Internal Server Error | An unexpected error occurred in the rate limiter logic. | `{"error": "Internal Logic Error", "details": "..."}` |
| `502` | Bad Gateway | The backend service is down or unreachable. | N/A |

---

## Shield Mode (Proof-of-Work)

When the system is in "shield" mode, the rate limiter will block all requests that don't include a valid puzzle solution in the `X-Puzzle-Solution` header. This is a defense mechanism against DDoS attacks.

**How it works:**

1.  A client makes a request to `/proxy` without a solution.
2.  The API responds with a `401 Unauthorized` and a JSON body containing a `challenge` string and a `difficulty` number.
3.  The client needs to find a `solution` (a number, or "nonce") such that the SHA-256 hash of the string `challenge + solution` starts with `difficulty` number of zeros.
4.  The client then retries the request with the solution in the `X-Puzzle-Solution` header.

**Example Client-Side Implementation (JavaScript):**

```javascript
const crypto = require('crypto');

async function solvePuzzleAndFetch(url) {
    try {
        const initialResponse = await fetch(url);

        if (initialResponse.status === 401) {
            console.log("Shield mode is active. Solving puzzle...");
            const { challenge, difficulty } = await initialResponse.json();
            
            let solution = 0;
            const prefix = '0'.repeat(difficulty);
            
            while (true) {
                const attempt = challenge + solution;
                const hash = crypto.createHash('sha256').update(attempt).digest('hex');
                
                if (hash.startsWith(prefix)) {
                    console.log(`Puzzle solved! Nonce: ${solution}`);
                    
                    const retryResponse = await fetch(url, {
                        headers: {
                            'X-Puzzle-Solution': solution.toString()
                        }
                    });

                    return retryResponse;
                }
                solution++;
            }
        } else {
            return initialResponse;
        }
    } catch (error) {
        console.error("Error during fetch:", error);
        throw error;
    }
}

// Usage
const apiUrl = 'https://{api_id}.execute-api.ap-northeast-1.amazonaws.com/dev/proxy';

solvePuzzleAndFetch(apiUrl)
    .then(response => response.json())
    .then(data => console.log("Success:", data))
    .catch(error => console.error("Error:", error));
```
