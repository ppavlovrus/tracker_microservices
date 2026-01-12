from fastapi import FastAPI

app = FastAPI(
    title="Task Manager",
    description="Gaateway for Tak manager",
    version="0.1.0",
    lifespan=""
)

# Application entry point
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)