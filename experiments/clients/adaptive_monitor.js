const URL = "https://41osqgw03d.execute-api.ap-northeast-1.amazonaws.com/prod/hello";

async function checkLimit() {
    process.stdout.write("\n⏳ Waiting for window reset (12s)...");
    
    // Wait 12s to guarantee a fresh rate limit window
    await new Promise(r => setTimeout(r, 12000));
    
    console.log(`\n--- 🚀 FIRING REQUESTS ---`);
    let successCount = 0;
    const requests = [];

    // Launch 8 parallel requests
    for (let i = 0; i < 8; i++) {
        requests.push(fetch(URL).then(res => {
            if (res.status === 200) successCount++;
        }));
    }

    await Promise.all(requests);

    if (successCount >= 4) {
        console.log(`✅ NORMAL LOAD: ${successCount}/8 passed. (Limit ~5)`);
    } else if (successCount <= 3) {
        console.log(`⚠️ HIGH CPU DETECTED: ${successCount}/8 passed. (Limit dropped to ~2)`);
    }
    
    // Loop
    checkLimit();
}

checkLimit();
