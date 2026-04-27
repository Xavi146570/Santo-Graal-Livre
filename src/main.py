import os
import asyncio
import logging
from datetime import datetime, timedelta
from fastapi import FastAPI, BackgroundTasks
import uvicorn

# Import flexível
try:
    from src.analyzer import Analyzer
except ImportError:
    try:
        from .analyzer import Analyzer
    except ImportError:
        from analyzer import Analyzer

# Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI()

analyzer = Analyzer()

# ---------------- 0x0 (30 MIN) ---------------- #

async def scheduler_30min():
    logger.info("⏳ Scheduler 30 minutos (0x0) iniciado")

    while True:
        try:
            await asyncio.to_thread(analyzer.detect_next_after_00)
        except Exception as e:
            logger.error(f"Erro 0x0: {e}")

        logger.info("⏱️ Próxima execução em 30 minutos...\n")
        await asyncio.sleep(1800)

# ---------------- HANDICAP (DIÁRIO) ---------------- #

async def scheduler_daily_handicap():
    logger.info("📅 Scheduler diário (handicap) iniciado")

    while True:
        now = datetime.now()
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)

        if now >= target:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()

        logger.info(f"⏰ Próxima análise handicap: {target}")
        await asyncio.sleep(wait_seconds)

        try:
            await asyncio.to_thread(analyzer.scan_handicap_games)
        except Exception as e:
            logger.error(f"Erro handicap: {e}")

# ---------------- STARTUP ---------------- #

@app.on_event("startup")
async def on_startup():
    logger.info("🔥 Aplicação iniciada")

    # 🔥 roda handicap UMA VEZ ao iniciar
    asyncio.create_task(asyncio.to_thread(analyzer.scan_handicap_games))

    # schedulers
    asyncio.create_task(scheduler_daily_handicap())
    asyncio.create_task(scheduler_30min())

# ---------------- ROTAS ---------------- #

@app.get("/")
def health_check():
    return {"status": "online", "time": datetime.now().isoformat()}

@app.get("/run")
async def run_manual(background_tasks: BackgroundTasks):
    background_tasks.add_task(analyzer.detect_next_after_00)
    return {"status": "ok", "message": "0x0 scan manual iniciado"}

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
