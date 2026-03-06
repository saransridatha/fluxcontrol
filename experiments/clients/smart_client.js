const crypto = require('crypto'); // Standard Node.js library

// YOUR PROD URL (Hardcoded for convenience)
const URL = "https://41osqgw03d.execute-api.ap-northeast-1.amazonaws.com/prod/hello";

async function main() {
    console.log(`\n---  STARTING CLIENT TEST ---`);
    console.log(`Target: ${URL}`);
    console.log("1. Sending initial request...");

    // Step 1: Try to access the API
    const res = await fetch(URL);
    
    // Case A: Shield Mode is OFF (Direct Access)
    if (res.status === 200) {
        console.log(" ACCESS GRANTED (Shield is OFF)");
        console.log("Response:", await res.text());
        return;
    }

    // Case B: Shield Mode is ON (401 Unauthorized)
    if (res.status === 401) {
        const data = await res.json();
        console.log(`\n SHIELD ACTIVE! Access Denied.`);
        console.log(` Challenge Received: "${data.challenge}"`);
        console.log(` Difficulty Level: ${data.difficulty}`);
        
        // Step 2: Solve the Puzzle (Proof of Work)
        const prefix = "0".repeat(data.difficulty);
        let nonce = 0;
        const start = Date.now();
        
        process.stdout.write("\n2. Solving Puzzle");
        
        while (true) {
            const str = data.challenge + nonce;
            // SHA256 Hash
            const hash = crypto.createHash('sha256').update(str).digest('hex');
            
            if (hash.startsWith(prefix)) {
                const timeTaken = Date.now() - start;
                console.log(`\n\n PUZZLE SOLVED in ${timeTaken}ms`);
                console.log(` Solution (Nonce): ${nonce}`);
                console.log(` Hash: ${hash}`);
                
                // Step 3: Retry with Solution
                console.log("\n3. Resending request with Solution...");
                const secureRes = await fetch(URL, {
                    headers: { 'X-Puzzle-Solution': nonce.toString() }
                });
                
                if (secureRes.status === 200) {
                    const finalText = await secureRes.text();
                    console.log(`\n SUCCESS! Access Granted.`);
                    console.log(` Server Response: ${finalText}`);
                } else {
                    console.log(` FAILED. Status: ${secureRes.status}`);
                    console.log(await secureRes.text());
                }
                break;
            }
            
            nonce++;
            // Show a dot every 50k attempts so you know it's working
            if (nonce % 50000 === 0) process.stdout.write(".");
        }
    } else {
        console.log("Unexpected Status:", res.status);
        console.log(await res.text());
    }
}

main();
