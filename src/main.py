import os
import asyncio
import logging
from datetime import datetime
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

# Inicializa Analyzer
analyzer = Analyzer()

# ---------------- EXECUÇÃO ---------------- #

async def run_analysis_async():
    try:
        logger.info("🚀 Executando análise...")
        await asyncio.to_thread(analyzer.detect_next_after_00)
        logger.info("✅ Análise concluída.")
    except Exception as e:
        logger.error(f"❌ Erro na análise: {e}")

# ---------------- SCHEDULER 30 MIN ---------------- #

async def scheduler_30min():
    logger.info("⏳ Scheduler 30 minutos iniciado")

    while True:
        await run_analysis_async()
        logger.info("⏱️ Próxima execução em 30 minutos...\n")
        await asyncio.sleep(1800)

# ---------------- STARTUP ---------------- #

@app.on_event("startup")
async def on_startup():
    logger.info("🔥 Aplicação iniciada")

    # roda imediatamente
    asyncio.create_task(run_analysis_async())

    # inicia loop de 30 min
    asyncio.create_task(scheduler_30min())

# ---------------- ROTAS ---------------- #

@app.get("/")
def health_check():
    return {"status": "online", "time": datetime.now().isoformat()}

@app.get("/run")
async def run_manual(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_analysis_async)
    return {"status": "ok", "message": "Análise manual iniciada"}

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
