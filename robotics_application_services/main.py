from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from uvicorn import run
import argparse

from .routers import ssh

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On launch
    yield
    # On end


app = FastAPI(lifespan=lifespan)

app.include_router(ssh.router)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "host", type=str, help="Host to listen to (0.0.0.0 or all hosts)"
    )
    parser.add_argument("port", type=int, help="Port to listen to")
    args = parser.parse_args()
    project = args.project

    run(app, host="0.0.0.0", port=8000)
