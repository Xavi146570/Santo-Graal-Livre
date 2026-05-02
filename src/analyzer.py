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

        # Alertas já enviados (evita duplicados enquanto o processo estiver vivo)
        self.sent_alerts = set()
        self.last_handicap_date = None

        # 🔥 TOP LIGAS (baixo 0x0)
        self.top_leagues = [
            39,   # Premier League
            140,  # La Liga
            135,  # Serie A
            78,   # Bundesliga
            61,   # Ligue 1
            94,   # Primeira Liga
            88,   # Eredivisie
            71,   # Brasileirão
            253,  # MLS
            144,  # Jupiler Pro League
            179,  # Allsvenskan
            203,  # Süper Lig
            262,  # Liga MX
            40,   # Championship
            141,  # Segunda Espanha
            307,  # Saudi League
            235,  # Argentina
            128,  # Superliga Dinamarca
            556,  # Noruega
            566   # Japão
        ]

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
            logger.error(f"Erro API [{endpoint}]: {e}")
            return []

    def _send_telegram(self, msg):
        if not self.telegram_token or not self.telegram_chat_id:
            logger.warning("⚠️ Telegram não configurado (token ou chat_id em falta)")
            return

        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                data={
                    "chat_id": self.telegram_chat_id,
                    "text": msg,
                    "parse_mode": "HTML"
                },
                timeout=10
            )
            if not resp.ok:
                logger.error(f"Telegram erro HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Erro Telegram: {e}")

    # ---------------- 0x0 CONTEXTUAL ---------------- #

    def detect_next_after_00_contextual(self):
        """
        Varre jogos de hoje por liga.
        Se um jogo terminou 0x0, alerta para o PRÓXIMO jogo ainda não iniciado
        da mesma liga (por ordem de timestamp).
        """
        logger.info("\n⏱️ ===== LIVE SCAN (0x0 CONTEXTUAL) =====")

        today = datetime.now().strftime("%Y-%m-%d")

        fixtures = self._get_api_data("fixtures", {
            "date": today,
            "timezone": "Europe/Lisbon"
        })

        if not fixtures:
            logger.info("⚠️ Sem jogos hoje")
            return

        # Filtrar só ligas da lista
        fixtures = [f for f in fixtures if f["league"]["id"] in self.top_leagues]

        # Agrupar por liga
        leagues: dict[int, list] = {}
        for f in fixtures:
            lid = f["league"]["id"]
            leagues.setdefault(lid, []).append(f)

        total_checked = 0
        total_00 = 0
        alerts = 0

        for league_id, games in leagues.items():

            # Ordenar por hora (sequência real da rodada)
            games.sort(key=lambda x: x["fixture"]["timestamp"])

            for i, current in enumerate(games):

                total_checked += 1

                # Só processar jogos já terminados
                if current["fixture"]["status"]["short"] != "FT":
                    continue

                home = current["teams"]["home"]["name"]
                away = current["teams"]["away"]["name"]
                g_home = current["goals"]["home"]
                g_away = current["goals"]["away"]

                # 🎯 Detectou 0x0
                if g_home != 0 or g_away != 0:
                    continue

                total_00 += 1
                logger.info(f"🧊 0x0 DETECTADO: {home} vs {away}")

                # Procurar o próximo jogo NS/TBD a seguir na mesma liga
                # (pode haver mais de um jogo entre o 0x0 e o próximo NS)
                next_game = None
                for j in range(i + 1, len(games)):
                    candidate = games[j]
                    if candidate["fixture"]["status"]["short"] in ["NS", "TBD"]:
                        next_game = candidate
                        break

                if next_game is None:
                    logger.info("⚠️ Sem próximo jogo NS nesta liga hoje → SKIP")
                    continue

                game_id = f"context_{next_game['fixture']['id']}"

                if game_id in self.sent_alerts:
                    logger.info(f"⏭️ Alerta já enviado para fixture {next_game['fixture']['id']}")
                    continue

                self.sent_alerts.add(game_id)

                n_home = next_game["teams"]["home"]["name"]
                n_away = next_game["teams"]["away"]["name"]
                league_name = next_game["league"]["name"]

                match_time = datetime.fromtimestamp(
                    next_game["fixture"]["timestamp"]
                ).strftime("%H:%M")

                msg = (
                    f"🚨 <b>0x0 → PRÓXIMO JOGO (MESMA LIGA)</b>\n\n"
                    f"🏆 {league_name}\n\n"
                    f"⚽ {home} vs {away} terminou <b>0x0</b>\n\n"
                    f"➡️ <b>Próximo jogo:</b>\n"
                    f"{n_home} vs {n_away}\n"
                    f"🕒 {match_time}\n\n"
                    f"💡 <i>Tip: Over / Lay 0x0</i>"
                )

                logger.info(f"🔥 ALERTA ENVIADO: {n_home} vs {n_away} ({match_time})")
                self._send_telegram(msg)
                alerts += 1

        logger.info("\n📊 ===== RESUMO 0x0 =====")
        logger.info(f"Jogos analisados : {total_checked}")
        logger.info(f"0x0 encontrados  : {total_00}")
        logger.info(f"Alertas enviados : {alerts}")

    # ---------------- HANDICAP ---------------- #

    def _get_match_odds(self, fixture_id):
        """
        Retorna (odds_1x2, odds_ah) para um fixture.
        odds_1x2: dict {"Home": float, "Draw": float, "Away": float}
        odds_ah : list de {"value": str, "odd": str}
        """
        data = self._get_api_data("odds", {"fixture": fixture_id})

        if not data:
            return None, None

        try:
            bookmakers = data[0].get("bookmakers", [])

            odds_1x2 = None
            odds_ah = None

            for book in bookmakers:
                for bet in book.get("bets", []):

                    if bet["name"] == "Match Winner" and odds_1x2 is None:
                        odds_1x2 = {
                            v["value"]: float(v["odd"])
                            for v in bet["values"]
                        }

                    if bet["name"] == "Asian Handicap" and odds_ah is None:
                        odds_ah = bet["values"]

                # Parar assim que tiver os dois (primeiro bookmaker com dados)
                if odds_1x2 and odds_ah:
                    break

            return odds_1x2, odds_ah

        except Exception as e:
            logger.error(f"Erro ao processar odds fixture {fixture_id}: {e}")
            return None, None

    def _is_strong_favorite(self, odds_1x2, odds_ah):
        """
        Critério:
        - Odd do favorito (1x2) entre 1.50 e 1.80
        - Existe linha de AH exatamente -1 (inteiro) com odd >= 2.00
          (linhas como -1.25 ou -1.5 são excluídas)
        Retorna (bool, detalhes_dict)
        """
        if not odds_1x2 or not odds_ah:
            return False, {}

        try:
            fav_odd = min(odds_1x2.values())

            if not (1.50 <= fav_odd <= 1.80):
                return False, {}

            for line in odds_ah:
                value_str = line["value"].strip()
                odd_val = float(line["odd"])

                # Verificação exacta: o value tem que ser "-1" ou "Home -1" / "Away -1"
                # Remove prefixos "Home " / "Away " antes de comparar
                clean = value_str.replace("Home", "").replace("Away", "").strip()

                if clean == "-1" and odd_val >= 2.00:
                    return True, {
                        "fav_odd": fav_odd,
                        "ah_value": value_str,
                        "ah_odd": odd_val
                    }

        except Exception as e:
            logger.error(f"Erro _is_strong_favorite: {e}")

        return False, {}

    def scan_handicap_games(self):
        """
        Scan diário: procura jogos ainda não iniciados (NS) nas top ligas
        com favorito claro (1.50–1.80) e handicap -1 com valor >= 2.00.
        """
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

        # Filtrar ligas e só jogos NS (não iniciados)
        fixtures = [
            f for f in fixtures
            if f["league"]["id"] in self.top_leagues
            and f["fixture"]["status"]["short"] == "NS"
        ]

        logger.info(f"Jogos NS nas top ligas: {len(fixtures)}")

        qualified = 0

        for game in fixtures:

            fixture_id = game["fixture"]["id"]
            home = game["teams"]["home"]["name"]
            away = game["teams"]["away"]["name"]
            league_name = game["league"]["name"]

            match_time = datetime.fromtimestamp(
                game["fixture"]["timestamp"]
            ).strftime("%H:%M")

            odds_1x2, odds_ah = self._get_match_odds(fixture_id)

            # Respeitar rate limit da API (1 req/seg)
            time.sleep(1.2)

            is_value, details = self._is_strong_favorite(odds_1x2, odds_ah)

            if not is_value:
                continue

            logger.info(
                f"🔥 HANDICAP OK: {home} vs {away} "
                f"| Fav: {details['fav_odd']} | AH: {details['ah_value']} @ {details['ah_odd']}"
            )

            msg = (
                f"🔥 <b>HANDICAP -1 COM VALOR</b>\n\n"
                f"🏆 {league_name}\n\n"
                f"⚽ {home} vs {away}\n"
                f"🕒 {match_time}\n\n"
                f"📊 Odd favorito (1x2): <b>{details['fav_odd']}</b>\n"
                f"📊 AH {details['ah_value']}: <b>{details['ah_odd']}</b>\n\n"
                f"💡 <i>Tip: Handicap -1 / Over 1.5</i>"
            )

            self._send_telegram(msg)
            qualified += 1

        logger.info(f"\n📊 Jogos com valor handicap: {qualified}")
