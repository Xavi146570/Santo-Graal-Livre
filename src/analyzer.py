import os
import logging
import time
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

    # ---------------- AGRUPAMENTO PRO ---------------- #

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

    # ---------------- 0x0 PRO ---------------- #

    def detect_next_after_00_contextual(self):

        logger.info("\n⏱️ ===== 0x0 PRO SCAN =====")

        today = datetime.now().strftime("%Y-%m-%d")

        fixtures = self._get_api_data("fixtures", {
            "date": today,
            "timezone": "Europe/Lisbon"
        })

        if not fixtures:
            logger.warning("Sem jogos")
            return

        groups = self._group_fixtures_precise(fixtures)

        total_00 = 0
        alerts = 0

        for key, games in groups.items():

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

                    # filtro sequência real
                    if (t2 - t1) > 21600:
                        continue

                    home_00 = current["teams"]["home"]["name"]
                    away_00 = current["teams"]["away"]["name"]

                    logger.info(f"⚽ 0x0 → {home_00} vs {away_00}")

                    next_status = next_game["fixture"]["status"]["short"]

                    if next_status not in ["NS", "TBD"]:
                        logger.info("⚠️ Próximo já começou → SKIP")
                        continue

                    game_id = f"00_{next_game['fixture']['id']}"

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

                    msg = (
                        f"🚨 0x0 → PRÓXIMO JOGO\n\n"
                        f"{home_00} vs {away_00} terminou 0x0\n\n"
                        f"➡️ {home} vs {away}\n"
                        f"🕒 {time_match}\n\n"
                        f"💡 Over / Lay 0x0"
                    )

                    self._send_telegram(msg)

        logger.info(f"\n📊 0x0 encontrados: {total_00}")
        logger.info(f"📊 Alertas enviados: {alerts}")

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

        except:
            return None

    def _is_strong_favorite(self, odds_1x2, odds_ah):

        if not odds_1x2 or not odds_ah:
            return False

        try:
            fav = min(odds_1x2.values())

            if not (1.50 <= fav <= 1.80):
                return False

            for line in odds_ah:
                if "-1" in line["value"] and float(line["odd"]) >= 2.00:
                    return True

        except:
            return False

        return False

    def scan_handicap_games(self):

        today = datetime.now().date()

        if self.last_handicap_date == today:
            logger.info("⏭️ Handicap já feito hoje")
            return

        self.last_handicap_date = today

        logger.info("\n📊 ===== HANDICAP SCAN =====")

        fixtures = self._get_api_data("fixtures", {
            "date": str(today),
            "timezone": "Europe/Lisbon"
        })

        found = 0

        for game in fixtures[:10]:

            if game["fixture"]["status"]["short"] != "NS":
                continue

            odds_data = self._get_match_odds(game["fixture"]["id"])

            time.sleep(1.2)

            if not odds_data:
                continue

            odds_1x2, odds_ah = odds_data

            if self._is_strong_favorite(odds_1x2, odds_ah):

                found += 1

                home = game["teams"]["home"]["name"]
                away = game["teams"]["away"]["name"]

                logger.info(f"🔥 HANDICAP: {home} vs {away}")

        logger.info(f"\n📊 Jogos com valor handicap: {found}")
