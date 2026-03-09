from contextlib import asynccontextmanager
from fastapi import FastAPI
from .database import engine
from .models import Base
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="Curator Radar", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "curator-radar"}
