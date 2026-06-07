from fastapi import FastAPI

app = FastAPI(title="Marvel Business Shop Bot")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
