import os
import asyncio
import logging
from datetime import datetime, timedelta
from fastapi import FastAPI, BackgroundTasks
import uvicorn

# Imports flexíveis
try:
    from src.analyzer import Analyzer
except ImportError:
    try:
        from .analyzer import Analyzer
    except ImportError:
        from analyzer import Analyzer

# Configuração de logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Inicializa Analyzer
try:
    analyzer = Analyzer()
except Exception as e:
    logger.error(f"Erro crítico ao inicializar Analyzer: {e}")
    analyzer = None

async def run_analysis_async():
    if analyzer:
        logger.info("🚀 Iniciando análise IMEDIATA (Post-Deploy)...")
        # Corre numa thread separada para não bloquear
        await asyncio.to_thread(analyzer.detect_next_after_00)
        logger.info("✅ Análise concluída.")
    else:
        logger.error("❌ Analyzer não inicializado.")

async def scheduler_30min():
    logger.info("⏳ Scheduler 30 minutos ativado.")

    while True:
        try:
            await run_analysis_async()
        except Exception as e:
            logger.error(f"Erro no scheduler: {e}")

        logger.info("⏱️ Próxima execução em 30 minutos...\n")
        await asyncio.sleep(1800)  # 30 min

# ------------------------------------------------------------------
# ⚡ O PONTO CHAVE: Executar logo ao ligar o servidor
# ------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    asyncio.create_task(scheduler_30min())
    asyncio.create_task(run_analysis_async())
    
    # ⚡ FORÇA A EXECUÇÃO IMEDIATA (Para veres logo os logs no deploy)
   asyncio.create_task(scheduler_30min())

@app.get("/run")
async def run_analysis_manual(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_analysis_async)
    return {"status": "success", "message": "Análise iniciada manualmente."}

@app.get("/")
def health_check():
    return {"status": "online", "time": datetime.now().isoformat()}

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
