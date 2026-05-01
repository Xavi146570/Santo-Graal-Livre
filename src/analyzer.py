import os
import logging
from datetime import datetime, timedelta
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

        self.sent_alerts = set()

    # ---------------- API ---------------- #

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

    # ---------------- CORE ENGINE ---------------- #

    def _group_fixtures_precise(self, fixtures):

        groups = {}

        for f in fixtures:
            league = f["league"]

            key = (
                league["id"],
                league.get("season"),
                league.get("round"),
                league.get("type")
            )

            groups.setdefault(key, []).append(f)

        return groups

    # ---------------- 0x0 DETECTOR PRO ---------------- #

    def detect_next_after_00_pro(self, days_back=0):

        logger.info("\n⏱️ ===== 0x0 PRO SCAN =====")

        target_date = datetime.now() - timedelta(days=days_back)
        date_str = target_date.strftime("%Y-%m-%d")

        fixtures = self._get_api_data("fixtures", {
            "date": date_str,
            "timezone": "Europe/Lisbon"
        })

        if not fixtures:
            logger.warning("Sem jogos")
            return

        groups = self._group_fixtures_precise(fixtures)

        total_00 = 0
        alerts = 0

        logger.info("\n📋 LISTA REAL DE 0x0:")

        for key, games in groups.items():

            # ordenar cronologicamente
            games.sort(key=lambda x: x["fixture"]["timestamp"])

            for i in range(len(games) - 1):

                current = games[i]
                next_game = games[i + 1]

                if current["fixture"]["status"]["short"] != "FT":
                    continue

                if current["goals"]["home"] == 0 and current["goals"]["away"] == 0:

                    total_00 += 1

                    t1 = current["fixture"]["timestamp"]
                    t2 = next_game["fixture"]["timestamp"]

                    # 🔥 FILTRO CRÍTICO: sequência real
                    if (t2 - t1) > 21600:  # 6 horas
                        continue

                    home_00 = current["teams"]["home"]["name"]
                    away_00 = current["teams"]["away"]["name"]

                    logger.info(f"⚽ 0x0 → {home_00} vs {away_00}")

                    next_status = next_game["fixture"]["status"]["short"]

                    if next_status not in ["NS", "TBD"]:
                        logger.info("⚠️ Próximo já começou → SKIP")
                        continue

                    game_id = f"pro_{next_game['fixture']['id']}"

                    if game_id in self.sent_alerts:
                        continue

                    self.sent_alerts.add(game_id)
                    alerts += 1

                    home = next_game["teams"]["home"]["name"]
                    away = next_game["teams"]["away"]["name"]

                    time_match = datetime.fromtimestamp(
                        next_game["fixture"]["timestamp"]
                    ).strftime("%H:%M")

                    logger.info(f"➡️ Próximo: {home} vs {away}")
                    logger.info("✅ ENTRADA: PROCURAR GOL\n")

                    msg = (
                        f"🚨 <b>0x0 → SEQUÊNCIA REAL</b>\n\n"
                        f"{home_00} vs {away_00} = 0x0\n\n"
                        f"➡️ {home} vs {away}\n"
                        f"🕒 {time_match}\n\n"
                        f"💡 Over / Lay 0x0"
                    )

                    self._send_telegram(msg)

        logger.info("\n📊 ===== RESUMO =====")
        logger.info(f"0x0 reais: {total_00}")
        logger.info(f"Entradas válidas: {alerts}")
