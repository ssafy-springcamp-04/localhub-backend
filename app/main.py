from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root():
    return {"message": "LocalHub API 서버입니다."}


@app.get("/api/health")
def health():
    return {"status": "ok"}