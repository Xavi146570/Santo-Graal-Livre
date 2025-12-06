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
        await asyncio.to_thread(analyzer.run_daily_analysis)
        logger.info("✅ Análise concluída.")
    else:
        logger.error("❌ Analyzer não inicializado.")

async def daily_scheduler():
    # Espera 1 minuto antes de entrar no loop normal para dar tempo ao 'run_analysis_async' inicial
    await asyncio.sleep(60) 
    logger.info("⏳ Scheduler diário ativado.")

    while True:
        now = datetime.now()
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)

        if now >= target:
            target = target + timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        logger.info(f"⏰ Próxima análise agendada: {target}")

        await asyncio.sleep(wait_seconds)

        try:
            await run_analysis_async()
        except Exception as e:
            logger.error(f"Erro no scheduler: {e}")
            await asyncio.sleep(60)

# ------------------------------------------------------------------
# ⚡ O PONTO CHAVE: Executar logo ao ligar o servidor
# ------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    # Inicia o agendamento
    asyncio.create_task(daily_scheduler())
    
    # ⚡ FORÇA A EXECUÇÃO IMEDIATA (Para veres logo os logs no deploy)
    asyncio.create_task(run_analysis_async())

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
