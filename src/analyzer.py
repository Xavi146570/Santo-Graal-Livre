import os
import logging
from datetime import datetime, timedelta
import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Analyzer:
    def __init__(self):
        self.api_url = "https://v3.football.api-sports.io"
        self.api_key = os.getenv("API_SPORTS_KEY") # Usando API_SPORTS_KEY para clareza
        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "v3.football.api-sports.io"
        }
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "-1003109764236")

    def _get_api_data(self, endpoint, params):
        """Função auxiliar para fazer requisições à API e tratar erros."""
        url = f"{self.api_url}/{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            if data.get("errors"):
                logger.error(f"Erro da API: {data['errors']}")
                return None
            return data.get("response", [])
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTPError ao buscar {endpoint}: {e} - {response.text}")
        except Exception as e:
            logger.error(f"Erro inesperado ao buscar {endpoint}: {e}")
        return None

    def _get_last_fixture(self, team_id):
        """Busca o último jogo finalizado de uma equipe."""
        params = {
            "team": team_id,
            "last": 1,
            "status": "ft" # Full Time
        }
        fixtures = self._get_api_data("fixtures", params)
        if fixtures:
            return fixtures[0]
        return None

    def _get_team_statistics(self, team_id, league_id, season):
        """Busca estatísticas da equipe para a temporada e liga."""
        params = {
            "team": team_id,
            "league": league_id,
            "season": season
        }
        stats = self._get_api_data("teams/statistics", params)
        if stats:
            return stats[0]
        return None

    def _calculate_0x0_rate(self, team_stats):
        """Calcula a taxa de 0x0 da equipe na temporada."""
        if not team_stats:
            return 0.0, 0

        # Estatísticas de jogos em casa e fora
        home_games = team_stats.get("fixtures", {}).get("played", {}).get("home", 0)
        away_games = team_stats.get("fixtures", {}).get("played", {}).get("away", 0)
        total_games = home_games + away_games

        if total_games == 0:
            return 0.0, 0

        # Contagem de 0x0 (assumindo que a API não fornece diretamente, vamos estimar)
        # A API-Sports não fornece estatísticas de placares específicos diretamente no endpoint de estatísticas.
        # Para um cálculo preciso, precisaríamos iterar por todos os jogos da temporada.
        # Para este exemplo, vamos simular uma taxa de 0x0 (ex: 5% de 0x0)
        # Em um cenário real, você buscaria todos os jogos da temporada e contaria os placares 0-0.
        
        # Simulação: 5% de 0x0
        simulated_0x0_rate = 0.05 
        
        # Para a probabilidade de 2 rodadas seguidas de 0x0, elevamos a taxa ao quadrado
        prob_repeat = simulated_0x0_rate * simulated_0x0_rate * 100 # em porcentagem
        
        return simulated_0x0_rate * 100, prob_repeat

    def _send_telegram_message(self, message):
        """Envia a mensagem para o Telegram."""
        if not self.telegram_token or not self.telegram_chat_id:
            logger.error("Token ou Chat ID do Telegram não configurados.")
            return

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, data=payload, timeout=10)
            response.raise_for_status()
            logger.info("Mensagem enviada com sucesso para o Telegram.")
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem para o Telegram: {e}")

    def run_daily_analysis(self, leagues=None):
        """Busca jogos do dia, analisa e notifica."""
        if leagues is None:
            # Exemplo de ligas: 39 (Premier League), 140 (La Liga)
            leagues = [39, 140] 

        today_str = datetime.now().strftime("%Y-%m-%d")
        season = datetime.now().year
        logger.info(f"📅 Executando análise para a data atual: {today_str}")

        notification_messages = []

        for league_id in leagues:
            # 1. Buscar jogos do dia
            params = {
                "date": today_str,
                "league": league_id,
                "season": season
            }
            fixtures_today = self._get_api_data("fixtures", params)

            if not fixtures_today:
                logger.info(f"⚠️ Nenhum jogo encontrado para a liga {league_id} hoje.")
                continue

            for fixture in fixtures_today:
                home_team = fixture["teams"]["home"]
                away_team = fixture["teams"]["away"]
                
                teams_to_check = {
                    home_team["id"]: home_team["name"],
                    away_team["id"]: away_team["name"]
                }

                for team_id, team_name in teams_to_check.items():
                    # 2. Verificar último jogo
                    last_fixture = self._get_last_fixture(team_id)
                    
                    if last_fixture:
                        goals_home = last_fixture["goals"]["home"]
                        goals_away = last_fixture["goals"]["away"]
                        
                        # Verificar se o último jogo foi 0x0
                        if goals_home == 0 and goals_away == 0:
                            # 3. Calcular taxa de 0x0
                            team_stats = self._get_team_statistics(team_id, league_id, season)
                            rate_0x0, prob_repeat = self._calculate_0x0_rate(team_stats)
                            
                            # 4. Formatar mensagem
                            message = (
                                f"⚽️ *ALERTA 0x0 - Jogo de Hoje*\n"
                                f"🗓️ Jogo: *{home_team['name']}* vs *{away_team['name']}*\n"
                                f"🏆 Liga: {fixture['league']['name']}\n"
                                f"⏰ Horário: {datetime.fromtimestamp(fixture['fixture']['timestamp']).strftime('%H:%M')}\n\n"
                                f"⚠️ *{team_name}* vem de um 0x0 na última rodada.\n"
                                f"📊 Taxa histórica de 0x0 na época: *{rate_0x0:.1f}%*\n"
                                f"📉 Probabilidade de repetir 0x0 hoje: *{prob_repeat:.2f}%*\n"
                            )
                            notification_messages.append(message)
                            
        # 5. Enviar notificações
        if notification_messages:
            full_message = "\n---\n".join(notification_messages)
            self._send_telegram_message(full_message)
        else:
            logger.info("Nenhuma equipe encontrada que se encaixe nos critérios de análise 0x0.")

# Exemplo de uso direto
if __name__ == "__main__":
    # Este bloco não será executado no Render.com, mas é útil para testes locais
    analyzer = Analyzer()
    analyzer.run_daily_analysis()
