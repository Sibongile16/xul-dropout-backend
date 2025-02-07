from fastapi import FastAPI

app = FastAPI(title="School Dropout", version="1.0.0")

@app.get("/")
async def root():
    return {"message":"hello there"}