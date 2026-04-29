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

    # ---------------- 0x0 CONTEXTUAL ---------------- #

    def detect_next_after_00_contextual(self):

        logger.info("\n⏱️ ===== LIVE SCAN (0x0 CONTEXTUAL) =====")

        today = datetime.now().strftime("%Y-%m-%d")

        fixtures = self._get_api_data("fixtures", {
            "date": today,
            "timezone": "Europe/Lisbon"
        })

        if not fixtures:
            logger.info("❌ Nenhum jogo encontrado")
            return

        fixtures.sort(key=lambda x: x["fixture"]["timestamp"])

        total = 0
        zeros = 0
        alerts = 0

        for i in range(len(fixtures) - 1):

            current = fixtures[i]
            next_game = fixtures[i + 1]

            total += 1

            # só jogos terminados
            if current["fixture"]["status"]["short"] != "FT":
                continue

            g_home = current["goals"]["home"]
            g_away = current["goals"]["away"]

            # 🎯 encontrou 0x0
            if g_home == 0 and g_away == 0:

                zeros += 1

                next_status = next_game["fixture"]["status"]["short"]
                elapsed = next_game["fixture"]["status"].get("elapsed", 0)

                # 🔥 NOVA LÓGICA → aceita LIVE até 10'
                if not (
                    next_status in ["NS", "TBD"] or
                    (next_status == "1H" and elapsed is not None and elapsed <= 10)
                ):
                    logger.info("⚠️ Fora da janela (já passou minuto 10) → SKIP")
                    continue

                game_id = f"context_{next_game['fixture']['id']}"

                if game_id in self.sent_alerts:
                    continue

                self.sent_alerts.add(game_id)
                alerts += 1

                home = next_game["teams"]["home"]["name"]
                away = next_game["teams"]["away"]["name"]

                match_time = datetime.fromtimestamp(
                    next_game["fixture"]["timestamp"]
                ).strftime("%H:%M")

                logger.info(f"\n⚽ Próximo jogo: {home} vs {away}")
                logger.info(f"⏱️ Status: {next_status} | Minuto: {elapsed}")
                logger.info("📊 Contexto: jogo anterior terminou 0x0")
                logger.info("✅ ENTRADA SUGERIDA → Procurar GOL")

                msg = (
                    f"🚨 <b>0x0 → PRÓXIMO JOGO</b>\n\n"
                    f"⚽ {home} vs {away}\n"
                    f"🕒 {match_time}\n"
                    f"⏱️ Status: {next_status} ({elapsed} min)\n\n"
                    f"💡 Procurar GOL (Over / Lay 0x0)"
                )

                self._send_telegram(msg)

        # 📊 resumo final
        logger.info("\n📊 ===== RESUMO 0x0 =====")
        logger.info(f"Jogos analisados: {total}")
        logger.info(f"0x0 encontrados: {zeros}")
        logger.info(f"Alertas enviados: {alerts}")

    # ---------------- HANDICAP ---------------- #

    def scan_handicap_games(self):

        today = datetime.now().date()

        if self.last_handicap_date == today:
            logger.info("⏭️ Handicap já analisado hoje")
            return

        self.last_handicap_date = today

        logger.info("\n📊 ===== HANDICAP SCAN =====")

        fixtures = self._get_api_data("fixtures", {
            "date": str(today),
            "timezone": "Europe/Lisbon"
        })

        if not fixtures:
            logger.info("❌ Sem jogos hoje")
            return

        count = 0

        for game in fixtures[:10]:

            if game["fixture"]["status"]["short"] != "NS":
                continue

            fixture_id = game["fixture"]["id"]

            odds_data = self._get_api_data("odds", {"fixture": fixture_id})

            time.sleep(1.2)  # evitar 429

            if not odds_data:
                continue

            try:
                bookmakers = odds_data[0]["bookmakers"]

                odds_1x2 = None
                odds_ah = None

                for book in bookmakers:
                    for bet in book["bets"]:

                        if bet["name"] == "Match Winner":
                            odds_1x2 = {v["value"]: float(v["odd"]) for v in bet["values"]}

                        if bet["name"] == "Asian Handicap":
                            odds_ah = bet["values"]

                if not odds_1x2 or not odds_ah:
                    continue

                fav_odd = min(odds_1x2.values())

                ah_ok = False
                for line in odds_ah:
                    if "-1" in line["value"] and float(line["odd"]) >= 2.00:
                        ah_ok = True

                if 1.50 <= fav_odd <= 1.80 and ah_ok:

                    home = game["teams"]["home"]["name"]
                    away = game["teams"]["away"]["name"]

                    logger.info(f"\n⚽ {home} vs {away}")
                    logger.info(f"📊 Odd favorito: {fav_odd}")
                    logger.info("✅ Jogo qualificado (handicap forte)")

                    msg = (
                        f"🔥 <b>HANDICAP FORTE</b>\n\n"
                        f"{home} vs {away}\n\n"
                        f"📊 Favorito: {fav_odd}\n"
                        f"💡 Over 1.5 / Over 2.5"
                    )

                    self._send_telegram(msg)
                    count += 1

            except Exception as e:
                logger.error(f"Erro parsing odds: {e}")
                continue

        logger.info(f"\n📊 Jogos com valor handicap: {count}")
