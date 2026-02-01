from fastapi import FastAPI
import psutil
import os

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Welcome to the Flux Protected Backend!"}

@app.get("/health")
def health_check():
    cpu_usage = psutil.cpu_percent(interval=0.1)
    return {"status": "alive", "cpu": cpu_usage}