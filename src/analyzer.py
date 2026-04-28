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

    def detect_next_after_00(self):

        logger.info("\n⏱️ ===== LIVE SCAN (0x0 CONTEXTUAL) =====\n")

        today = datetime.now().strftime("%Y-%m-%d")

        fixtures = self._get_api_data("fixtures", {
            "date": today,
            "timezone": "Europe/Lisbon"
        })

        if not fixtures:
            logger.info("❌ Sem jogos\n")
            return

        fixtures.sort(key=lambda x: x["fixture"]["timestamp"])

        total_games = len(fixtures)
        zero_zero_found = 0
        alerts_sent = 0

        for i in range(len(fixtures) - 1):

            current = fixtures[i]
            next_game = fixtures[i + 1]

            if current["fixture"]["status"]["short"] != "FT":
                continue

            if current["goals"]["home"] != 0 or current["goals"]["away"] != 0:
                continue

            zero_zero_found += 1

            if current["league"]["id"] != next_game["league"]["id"]:
                continue

            time_diff = next_game["fixture"]["timestamp"] - current["fixture"]["timestamp"]

            if time_diff > 10800:
                continue

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

            alerts_sent += 1

        logger.info("\n📊 ===== RESUMO 0x0 =====")
        logger.info(f"Jogos analisados: {total_games}")
        logger.info(f"0x0 encontrados: {zero_zero_found}")
        logger.info(f"Alertas enviados: {alerts_sent}")
        logger.info("⏱️ Próxima execução em 30 minutos...\n")

    # ---------------- HANDICAP ---------------- #

    def _get_match_odds(self, fixture_id):

        data = self._get_api_data("odds", {"fixture": fixture_id})

        if not data:
            return None

        try:
            bookmakers = data[0]["bookmakers"]

            odds_1x2 = None
            odds_ah = None

            for book in bookmakers:
                for bet in book["bets"]:

                    if bet["name"] == "Match Winner":
                        odds_1x2 = {
                            v["value"]: float(v["odd"])
                            for v in bet["values"]
                        }

                    if bet["name"] == "Asian Handicap":
                        odds_ah = bet["values"]

            return odds_1x2, odds_ah

        except Exception as e:
            logger.error(f"Erro odds: {e}")
            return None

    def _is_strong_favorite(self, odds_1x2, odds_ah):

        if not odds_1x2 or not odds_ah:
            return False

        try:
            fav_odd = min(odds_1x2.values())

            if not (1.50 <= fav_odd <= 1.80):
                return False

            for line in odds_ah:
                if "-1" in line["value"]:
                    if float(line["odd"]) >= 2.00:
                        return True

        except:
            return False

        return False

    def scan_handicap_games(self):

        today = datetime.now().date()

        if self.last_handicap_date == today:
            logger.info("⏭️ Handicap já feito hoje\n")
            return

        self.last_handicap_date = today

        logger.info("\n📊 ===== HANDICAP SCAN =====\n")

        fixtures = self._get_api_data("fixtures", {
            "date": str(today),
            "timezone": "Europe/Lisbon"
        })

        total_games = 0
        checked_games = 0
        qualified_games = 0

        max_games = 10

        for game in fixtures[:max_games]:

            total_games += 1

            if game["fixture"]["status"]["short"] != "NS":
                continue

            checked_games += 1

            home = game["teams"]["home"]["name"]
            away = game["teams"]["away"]["name"]

            fixture_id = game["fixture"]["id"]

            odds_data = self._get_match_odds(fixture_id)

            time.sleep(1.2)

            if not odds_data:
                logger.info(f"⚠️ {home} vs {away} → sem odds")
                continue

            odds_1x2, odds_ah = odds_data

            try:
                fav_odd = min(odds_1x2.values())
            except:
                logger.info(f"⚠️ {home} vs {away} → erro odds")
                continue

            ah_value = None

            for line in odds_ah:
                if "-1" in line["value"]:
                    ah_value = float(line["odd"])
                    break

            if not ah_value:
                logger.info(f"❌ {home} vs {away} → sem AH -1")
                continue

            ratio = (1 / fav_odd) * 100

            logger.info(f"\n⚽ {home} vs {away}")
            logger.info(f"📊 1X2: {fav_odd:.2f} | AH -1: {ah_value:.2f}")
            logger.info(f"📈 Ratio: {ratio:.1f}%")

            if self._is_strong_favorite(odds_1x2, odds_ah):

                qualified_games += 1

                logger.info("✅ QUALIFICADO")
                logger.info("🎯 Sugestão: Over 1.5 / Over 2.5")

                msg = (
                    f"🔥 <b>HANDICAP FORTE</b>\n\n"
                    f"⚽ {home} vs {away}\n\n"
                    f"📊 Odd: {fav_odd:.2f}\n"
                    f"📊 AH -1: {ah_value:.2f}\n"
                    f"📈 Ratio: {ratio:.1f}%\n\n"
                    f"💡 Over 1.5 / Over 2.5"
                )

                self._send_telegram(msg)

            else:
                logger.info("❌ NÃO QUALIFICADO")

        logger.info("\n📊 ===== RESUMO HANDICAP =====")
        logger.info(f"Jogos lidos: {total_games}")
        logger.info(f"Jogos analisados: {checked_games}")
        logger.info(f"Jogos qualificados: {qualified_games}\n")
