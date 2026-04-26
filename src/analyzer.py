import os
import logging
import time
from datetime import datetime
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Analyzer:

    def __init__(self):
        self.api_url = "https://v3.football.api-sports.io"
        self.api_key = os.getenv("API_SPORTS_KEY")

        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "v3.football.api-sports.io"
        }

        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def _get_api_data(self, endpoint, params):
        try:
            r = requests.get(
                f"{self.api_url}/{endpoint}",
                headers=self.headers,
                params=params,
                timeout=15
            )
            r.raise_for_status()
            return r.json().get("response", [])
        except Exception as e:
            logger.error(f"Erro API: {e}")
            return []

    def _send_telegram(self, msg):
        if not self.telegram_token:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                data={
                    "chat_id": self.telegram_chat_id,
                    "text": msg,
                    "parse_mode": "HTML"
                },
                timeout=10
            )
        except Exception as e:
            logger.error(f"Erro Telegram: {e}")

    # 🔥 LÓGICA PRINCIPAL
    def detect_next_after_00(self):

        today = datetime.now().strftime("%Y-%m-%d")

        fixtures = self._get_api_data("fixtures", {
            "date": today,
            "timezone": "Europe/Lisbon"
        })

        if not fixtures:
            return

        # ordenar por horário
        fixtures.sort(key=lambda x: x["fixture"]["timestamp"])

        for i in range(len(fixtures) - 1):

            current = fixtures[i]
            next_game = fixtures[i + 1]

            status = current["fixture"]["status"]["short"]

            # só considerar jogos terminados
            if status != "FT":
                continue

            g_home = current["goals"]["home"]
            g_away = current["goals"]["away"]

            # 🎯 DETECTOU 0x0
            if g_home == 0 and g_away == 0:

                next_status = next_game["fixture"]["status"]["short"]

                # próximo jogo ainda não começou
                if next_status in ["NS", "TBD"]:

                    home = next_game["teams"]["home"]["name"]
                    away = next_game["teams"]["away"]["name"]

                    time_match = datetime.fromtimestamp(
                        next_game["fixture"]["timestamp"]
                    ).strftime("%H:%M")

                    msg = (
                        f"🚨 <b>ALERTA ESTRATÉGIA 0x0</b>\n\n"
                        f"📊 Jogo anterior terminou 0x0\n\n"
                        f"➡️ Próximo jogo:\n"
                        f"⚽ {home} vs {away}\n"
                        f"🕒 {time_match}\n\n"
                        f"💡 Estratégia: Procurar GOL (Over / Lay 0x0)"
                    )

                    logger.info(f"🔥 ALERTA: {home} vs {away}")
                    self._send_telegram(msg)

    def run(self):
        logger.info("🚀 Bot ativo (30 min)")

        while True:
            try:
                self.detect_next_after_00()
            except Exception as e:
                logger.error(f"Erro: {e}")

            time.sleep(1800)  # 30 min


if __name__ == "__main__":
    Analyzer().run()
