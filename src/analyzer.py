import os
import logging
import time
from datetime import datetime
import requests

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Analyzer:

    VIP_LEAGUES = [
        39, 140, 61, 78, 135, 94, 88, 71, 179, 144,
        141, 40, 262, 301, 235, 253, 556, 128, 569, 307
    ]

    def __init__(self):
        self.api_url = "https://v3.football.api-sports.io"
        self.api_key = os.getenv("API_SPORTS_KEY")

        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "v3.football.api-sports.io"
        }

        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

        leagues_env = os.getenv("LEAGUE_IDS", "")
        if leagues_env:
            try:
                parsed = [int(x.strip()) for x in leagues_env.split(",") if x.strip().isdigit()]
                self.vip_leagues = sorted(list(set(parsed)))
            except:
                self.vip_leagues = self.VIP_LEAGUES
        else:
            self.vip_leagues = self.VIP_LEAGUES

    # ---------------- API ---------------- #

    def _get_api_data(self, endpoint, params):
        url = f"{self.api_url}/{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            if data.get("errors"):
                logger.warning(f"⚠️ API Info: {data['errors']}")
                return None

            return data.get("response", [])

        except Exception as e:
            logger.error(f"❌ Erro API ({endpoint}): {e}")
            return None

    def _get_last_fixture(self, team_id):
        params = {"team": team_id, "last": 1, "status": "FT-AET-PEN"}
        fixtures = self._get_api_data("fixtures", params)
        return fixtures[0] if fixtures else None

    # ---------------- TELEGRAM ---------------- #

    def _send_telegram_message(self, message):
        if not self.telegram_token or not self.telegram_chat_id:
            return

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"

        try:
            requests.post(url, data={
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }, timeout=10)

        except Exception as e:
            logger.error(f"Erro Telegram: {e}")

    # ---------------- CORE ---------------- #

    def run_analysis(self):
        today = datetime.now().strftime("%Y-%m-%d")
        logger.info(f"🔎 Scan iniciado: {today}")

        params = {"date": today, "timezone": "Europe/Lisbon"}
        fixtures = self._get_api_data("fixtures", params) or []

        if not fixtures:
            logger.warning("❌ Nenhum jogo hoje")
            return

        logger.info(f"📊 Jogos encontrados: {len(fixtures)}")

        checked = 0

        for fixture in fixtures:

            # Apenas jogos futuros
            if fixture['fixture']['status']['short'] not in ['NS', 'TBD']:
                continue

            league_id = fixture['league']['id']
            league_name = fixture['league']['name']
            is_vip = league_id in self.vip_leagues

            home = fixture["teams"]["home"]
            away = fixture["teams"]["away"]

            checked += 1

            for team, side in [(home, "Casa"), (away, "Fora")]:

                last_match = self._get_last_fixture(team['id'])
                if not last_match:
                    continue

                goals = last_match.get("goals", {})

                # 🎯 DETECÇÃO PRINCIPAL
                if goals.get("home") == 0 and goals.get("away") == 0:

                    match_time = datetime.fromtimestamp(
                        fixture['fixture']['timestamp']
                    ).strftime('%H:%M')

                    msg = (
                        f"🚨 <b>PADRÃO DETECTADO</b>\n\n"
                        f"🏆 {league_name}\n"
                        f"⚽ {home['name']} vs {away['name']}\n"
                        f"🕒 {match_time}\n\n"
                        f"⚠️ {team['name']} ({side}) vem de <b>0x0</b>\n"
                        f"💡 Procurar OVER no próximo jogo\n"
                    )

                    if is_vip:
                        self._send_telegram_message(msg)
                        logger.info(f"📲 ALERTA VIP: {team['name']}")
                    else:
                        logger.info(f"👀 {team['name']} 0x0 (não VIP)")

        logger.info(f"✅ Scan terminado. Jogos analisados: {checked}")

    # ---------------- LOOP ---------------- #

    def run_forever(self):
        logger.info("🚀 BOT iniciado (intervalo 30 min)")

        while True:
            try:
                self.run_analysis()
            except Exception as e:
                logger.error(f"Erro geral: {e}")

            logger.info("⏳ A aguardar 30 minutos...\n")
            time.sleep(1800)  # 30 minutos


# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    bot = Analyzer()
    bot.run_forever()
