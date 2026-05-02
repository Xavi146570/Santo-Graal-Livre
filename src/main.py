import os
import asyncio
import logging
from contextlib import asynccontextmanager
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


# ---------------- 0x0 (10 MIN) ---------------- #

async def scheduler_10min(analyzer: "Analyzer"):
    logger.info("⏳ Scheduler 10 minutos (0x0) iniciado")

    while True:
        try:
            await asyncio.to_thread(analyzer.detect_next_after_00_contextual)
        except Exception as e:
            logger.error(f"Erro 0x0: {e}")

        logger.info("⏱️ Próxima execução em 10 minutos...\n")
        await asyncio.sleep(600)


# ---------------- HANDICAP (DIÁRIO) ---------------- #

async def scheduler_daily_handicap(analyzer: "Analyzer"):
    logger.info("📅 Scheduler diário (handicap) iniciado")

    while True:
        now = datetime.now()
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)

        if now >= target:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        logger.info(f"⏰ Próxima análise handicap: {target.strftime('%Y-%m-%d %H:%M:%S')}")
        await asyncio.sleep(wait_seconds)

        try:
            await asyncio.to_thread(analyzer.scan_handicap_games)
        except Exception as e:
            logger.error(f"Erro handicap: {e}")


# ---------------- LIFESPAN (substitui on_event deprecated) ---------------- #

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔥 Aplicação iniciada")

    analyzer = Analyzer()

    # Guarda no state para acesso nas rotas
    app.state.analyzer = analyzer

    # 🔥 Roda handicap UMA VEZ ao iniciar
    asyncio.create_task(asyncio.to_thread(analyzer.scan_handicap_games))

    # Schedulers em background
    asyncio.create_task(scheduler_daily_handicap(analyzer))
    asyncio.create_task(scheduler_10min(analyzer))

    yield

    logger.info("🛑 Aplicação encerrada")


app = FastAPI(lifespan=lifespan)


# ---------------- ROTAS ---------------- #

@app.get("/")
def health_check():
    return {"status": "online", "time": datetime.now().isoformat()}


@app.get("/run")
async def run_manual(background_tasks: BackgroundTasks):
    analyzer = app.state.analyzer
    background_tasks.add_task(analyzer.detect_next_after_00_contextual)
    return {"status": "ok", "message": "0x0 scan manual iniciado"}


@app.get("/run-handicap")
async def run_handicap_manual(background_tasks: BackgroundTasks):
    """Força nova análise de handicap (ignora cache do dia)"""
    analyzer = app.state.analyzer
    analyzer.last_handicap_date = None  # reset para forçar re-análise
    background_tasks.add_task(analyzer.scan_handicap_games)
    return {"status": "ok", "message": "Handicap scan manual iniciado"}


# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
