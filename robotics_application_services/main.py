from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from uvicorn import run
import argparse

from routers import format

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On launch
    yield
    # On end


app = FastAPI(lifespan=lifespan)

app.include_router(format.router)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


if __name__ == "__main__":
    run(app, host="0.0.0.0", port=8000)
