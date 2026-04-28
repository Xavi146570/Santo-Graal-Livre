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

        self.sent_alerts = set()
        self.last_handicap_date = None

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

    # ---------------- HANDICAP ---------------- #

    def _get_match_odds(self, fixture_id):
        data = self._get_api_data("odds", {"fixture": fixture_id})

        if not data:
            return None

        try:
            bookmakers = data[0]["bookmakers"]

            odds_1x2 = None
            ah_odd = None

            for book in bookmakers:
                for bet in book["bets"]:

                    if bet["name"] == "Match Winner":
                        odds_1x2 = {
                            v["value"]: float(v["odd"])
                            for v in bet["values"]
                        }

                    if bet["name"] == "Asian Handicap":
                        for v in bet["values"]:
                            if "-1" in v["value"]:
                                ah_odd = float(v["odd"])

            return odds_1x2, ah_odd

        except:
            return None

    def scan_handicap_games(self):

        today = datetime.now().date()

        if self.last_handicap_date == today:
            logger.info("⏭️ Handicap já analisado hoje\n")
            return

        self.last_handicap_date = today

        logger.info("\n📊 ===== HANDICAP SCAN =====\n")

        fixtures = self._get_api_data("fixtures", {
            "date": str(today),
            "timezone": "Europe/Lisbon"
        })

        max_games = 10

        for game in fixtures[:max_games]:

            if game["fixture"]["status"]["short"] != "NS":
                continue

            fixture_id = game["fixture"]["id"]

            odds_data = self._get_match_odds(fixture_id)
            time.sleep(1.2)

            if not odds_data:
                continue

            odds_1x2, ah_odd = odds_data

            if not odds_1x2 or not ah_odd:
                continue

            fav_odd = min(odds_1x2.values())
            ratio = (1 / fav_odd) * 100

            home = game["teams"]["home"]["name"]
            away = game["teams"]["away"]["name"]

            logger.info(f"⚽ {home} vs {away}")
            logger.info(f"📊 Odd Fav: {fav_odd:.2f} | AH -1: {ah_odd:.2f}")
            logger.info(f"📈 Ratio: {ratio:.1f}%")

            # DECISÃO
            if 1.50 <= fav_odd <= 1.80 and ah_odd >= 2.00 and ratio >= 60:

                logger.info("✅ QUALIFICADO")
                logger.info("🎯 Sugestão: Over 1.5 / Over 2.5\n")

                msg = (
                    f"🔥 HANDICAP FORTE\n\n"
                    f"{home} vs {away}\n"
                    f"Odd: {fav_odd:.2f} | AH: {ah_odd:.2f}\n"
                    f"Ratio: {ratio:.0f}%\n\n"
                    f"👉 Over 1.5 / Over 2.5"
                )

                self._send_telegram(msg)

            else:
                logger.info("❌ SKIP (sem valor)\n")

    # ---------------- 0x0 ---------------- #

    def detect_next_after_00(self):

    logger.info("\n⏱️ ===== LIVE SCAN (0x0 CONTEXTUAL) =====\n")

    today = datetime.now().strftime("%Y-%m-%d")

    fixtures = self._get_api_data("fixtures", {
        "date": today,
        "timezone": "Europe/Lisbon"
    })

    if not fixtures:
        logger.info("❌ Sem jogos")
        return

    # ordenar por tempo
    fixtures.sort(key=lambda x: x["fixture"]["timestamp"])

    for i in range(len(fixtures) - 1):

        current = fixtures[i]
        next_game = fixtures[i + 1]

        # 🔹 condição 1 → jogo terminou
        if current["fixture"]["status"]["short"] != "FT":
            continue

        # 🔹 condição 2 → foi 0x0
        if current["goals"]["home"] != 0 or current["goals"]["away"] != 0:
            continue

        # 🔹 condição 3 → mesma liga
        if current["league"]["id"] != next_game["league"]["id"]:
            continue

        # 🔹 condição 4 → intervalo máximo (ex: 3 horas)
        time_diff = next_game["fixture"]["timestamp"] - current["fixture"]["timestamp"]

        if time_diff > 10800:  # 3 horas
            continue

        # 🔹 condição 5 → próximo jogo ainda não começou
        if next_game["fixture"]["status"]["short"] not in ["NS", "TBD"]:
            continue

        game_id = f"00_{next_game['fixture']['id']}"

        if game_id in self.sent_alerts:
            continue

        self.sent_alerts.add(game_id)

        home = next_game["teams"]["home"]["name"]
        away = next_game["teams"]["away"]["name"]

        match_time = datetime.fromtimestamp(
            next_game["fixture"]["timestamp"]
        ).strftime("%H:%M")

        logger.info(f"⚽ {home} vs {away}")
        logger.info(f"🏆 Liga: {current['league']['name']}")
        logger.info(f"⏱️ Intervalo: {int(time_diff/60)} min")
        logger.info("📊 Contexto: 0x0 anterior (mesma liga)")
        logger.info("✅ ENTRADA SUGERIDA\n")

        msg = (
            f"🚨 <b>0x0 → SEQUÊNCIA REAL</b>\n\n"
            f"🏆 {current['league']['name']}\n"
            f"➡️ {home} vs {away}\n"
            f"🕒 {match_time}\n\n"
            f"⏱️ Intervalo: {int(time_diff/60)} min\n"
            f"💡 Procurar GOL"
        )

        self._send_telegram(msg)
