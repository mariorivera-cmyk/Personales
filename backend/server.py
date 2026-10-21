from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

import os
import asyncio
import logging
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from core import client
from routes_extra import r as extra_router
from routes_saas import r as saas_router
from routes_ops import r as ops_router
from routes_wa import r as wa_router
from rules import r as rules_router
from wa_cloud import r as wa_cloud_router
from packages import r as packages_router, package_notices
from seed import seed_all
from engine import run_reminders, release_unpaid
from billing import run_billing, trial_notices

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="SalonFlow SaaS API", description="API multiempresa para gestión de citas de salones de belleza",
              docs_url="/api/docs", openapi_url="/api/openapi.json")
for router in (extra_router, saas_router, ops_router, wa_router, rules_router, wa_cloud_router, packages_router):
    app.include_router(router)


@app.get("/api/health")
async def health():
    return {"ok": True}


app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


async def scheduler():
    ticks = 0
    while True:
        try:
            await run_reminders()
            await release_unpaid()
            if ticks % 72 == 0:
                await run_billing()
                await trial_notices()
                await package_notices()
        except Exception as e:
            logger.error(f"scheduler error: {e}")
        ticks += 1
        await asyncio.sleep(300)


@app.on_event("startup")
async def startup():
    await seed_all()
    from routes_extra import setup_steps
    from core import db
    for co in await db.companies.find({"setup_complete": {"$exists": False}}, {"_id": 0}).to_list(1000):
        await setup_steps(co)
    asyncio.create_task(scheduler())


@app.on_event("shutdown")
async def shutdown():
    client.close()
