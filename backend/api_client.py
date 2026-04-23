import os
from dotenv import load_dotenv
import requests

from database import SessionLocal
from model import Coach, League, Player, PlayerStatistics, Team, TeamStatistics

load_dotenv()


class baseApiClient:
    def __init__(self):
        self.api_key = os.getenv("FOOTBALL_API_KEY")
        self.api_endpoint = os.getenv("APIENDPOINT")
        self.headers = {
            "x-apisports-key": self.api_key,
            "Content-Type": "application/json"}
        
    def request(self,url):
        response=requests.get(url,headers=self.headers)
        if response.status_code==200:
            return response.json()
        else:
            return {"error":f"Request failed with status code {response.status_code}"}

class playerDataFetch(baseApiClient):
    def __init__(self):
        super().__init__()
    def get_player_data(self,team_id,season):
        url=f"{self.api_endpoint}/players?team={team_id}&season={season}"
        response=self.request(url)
        datas_players=[]
        for i in response.get("response", []):
            stats_list = i.get("statistics") or []
            if not stats_list:
                continue
            st0 = stats_list[0]
            datas_players.append({
                "id": i.get("player", {}).get("id"),
                "team_id": st0.get("team", {}).get("id"),
                "firstname": i.get("player", {}).get("firstname"),
                "lastname": i.get("player", {}).get("lastname"),
                "age": i.get("player", {}).get("age"),
                "nationality": i.get("nationality"),
                "position": st0.get("games", {}).get("position"),
            })
        return datas_players

class teamDataFetch(baseApiClient):
    def __init__(self):
        super().__init__()
    def get_team_data(self,league_id,season):
        url=f"{self.api_endpoint}/teams?league={league_id}&season={season}"
        response =self.request(url)
        datas_teams=[]
        for i in response.get("response",[]):
            datas_teams.append({
               "id" : i.get("team",{}).get("id"),
               "league_id" : league_id,
               "name" : i.get("team",{}).get("name"),
               "country" : i.get("team",{}).get("country")
            })
        return datas_teams

class coachDataFetch(baseApiClient):
    def __init__(self):
        super().__init__()
    def get_coach_data(self,team_id):
        url=f"{self.api_endpoint}/coachs?team={team_id}"
        response=self.request(url)
        datas_coachs=[]
        for i in response.get("response",[]):
            firstname=i.get("firstname",[])
            lastname=i.get("lastname",[])
            if firstname and lastname:
                datas_coachs.append({
                    "team_id" : team_id,
                    "firstname" : i.get("firstname",[]),
                    "lastname" : i.get("lastname",[]),
                    "id" : i.get("id",[]),
                    "age" : i.get("age",[]),
                    "nationality" : i.get("nationality")
                })
        return datas_coachs

class leagueDataFetch(baseApiClient):
    def __init__(self):
        super().__init__()
    def get_league_data(self,season):
        url=f"{self.api_endpoint}/leagues?season={season}"
        response=self.request(url)
        datas_leagues=[]
        for i in response.get("response",[]):
            datas_leagues.append({
                "id" : i.get("league",{}).get("id"),
                "name" : i.get("league",{}).get("name"),
                "country" : i.get("country",{}).get("name"),
                "season" : i.get("seasons",[])[0].get("year")
            })
        return datas_leagues
    
class teamStatisticsDataFetch(baseApiClient):
    def __init__(self):
        super().__init__()
    def get_team_statistics_data(self,team_id,season,league_id):
        url=f"{self.api_endpoint}/teams/statistics?team={team_id}&season={season}&league={league_id}"
        data=self.request(url)
        stats=data.get("response",{})
        response={
                "team_id" : team_id,
                "team_name" : stats.get("team",{}).get("name"),
                "goals_for" : stats.get("goals",{}).get("for",{}),
                "goals_against" : stats.get("goals",{}).get("against",{}),
                "fixtures": stats.get("fixtures",{}),
                "failed_to_score": stats.get("biggest",{}).get("failed_to_score",{}),
                "linesups": stats.get("lineups",[]),
                "cards_yellow": stats.get("cards",{}).get("yellow",{}),
                "cards_red": stats.get("cards",{}).get("red",{})
                
        }
        
        return response
    
class playerStatisticsDataFetch(baseApiClient):
    def __init__(self):
        super().__init__()
    
    def get_player_statistics_data(self,season,team_id):
        url=f"{self.api_endpoint}/players?team={team_id}&season={season}"
        response=self.request(url)
        datas_players_statistics=[]
        for i in response.get("response", []):
            stats_list = i.get("statistics") or []
            statistics = stats_list[0] if stats_list else {}
            datas_players_statistics.append({
                "player_id": i.get("player", {}).get("id"),
                "team_id": statistics.get("team", {}).get("id"),
                "height": i.get("player", {}).get("height"),
                "weight": i.get("player", {}).get("weight"),
                "injured": i.get("player", {}).get("injured"),
                "games": statistics.get("games", {}),
                "substitutes": statistics.get("substitutes", {}),
                "shooting": statistics.get("shots", {}),
                "passing": statistics.get("passes", {}),
                "tackles": statistics.get("tackles", {}),
                "duels": statistics.get("duels", {}),
                "dribbles": statistics.get("dribbles", {}),
                "fouls": statistics.get("fouls", {}),
                "cards": statistics.get("cards", {}),
                "penalty": statistics.get("penalty", {}),
                "goals": statistics.get("goals", {}).get("total"),
            })
        return datas_players_statistics


class fetchDBdataClient:
    """
    Koç LLM'lerinin kullandığı PostgreSQL okuyucusu.
    `format_stats_for_llm` ile uyumlu tuple satırları üretir.
    """

    def fetch_team_formation(self, team_id: int) -> str | None:
        db = SessionLocal()
        try:
            ts = db.query(TeamStatistics).filter(TeamStatistics.team_id == team_id).first()
            if not ts or not ts.lineups:
                return None
            lineups = ts.lineups
            if isinstance(lineups, list) and lineups:
                best_form, best_n = None, -1
                for item in lineups:
                    if not isinstance(item, dict):
                        continue
                    f = item.get("formation")
                    if not f:
                        continue
                    n = item.get("played", 0) or 0
                    if n >= best_n:
                        best_n = n
                        best_form = f
                return best_form or (
                    lineups[0].get("formation")
                    if isinstance(lineups[0], dict)
                    else None
                )
            if isinstance(lineups, dict):
                return lineups.get("formation")
            return None
        finally:
            db.close()

    def fetch_player_statistics_by_positions(self, team_id: int, positions: list[str]) -> list:
        """Birden fazla pozisyon için tek sorgu (örn. ['Goalkeeper','Defender'])."""
        if not positions:
            return []
        db = SessionLocal()
        try:
            rows = (
                db.query(Player, PlayerStatistics)
                .join(PlayerStatistics, Player.id == PlayerStatistics.player_id)
                .filter(Player.team_id == team_id)
                .filter(Player.position.in_(positions))
                .all()
            )
            out = []
            for player, stats in rows:
                name = f"{player.firstname or ''} {player.lastname or ''}".strip()
                base = (
                    stats.id,
                    player.id,
                    stats.height,
                    stats.weight,
                    bool(stats.injured),
                    stats.games or {},
                    stats.substitutes or {},
                    stats.shooting or {},
                    stats.passing or {},
                    stats.goals or {},
                    stats.tackles or {},
                    stats.duels or {},
                    stats.dribbles or {},
                    stats.fouls or {},
                    stats.cards or {},
                    stats.penalty or {},
                    name,
                    player.position or "",
                )
                if player.description:
                    out.append(base + (player.description,))
                else:
                    out.append(base)
            return out
        finally:
            db.close()

    def fetch_player_statistics_by_filter(self, team_id: int, position_filter: str) -> list:
        return self.fetch_player_statistics_by_positions(team_id, [position_filter])


def _as_int(val):
    if val is None:
        return None
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    try:
        s = str(val).replace(" cm", "").replace(" kg", "").strip()
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _goals_json(row: dict):
    g = row.get("goals")
    if g is None:
        return None
    if isinstance(g, dict):
        return g
    return {"total": g}


class DataService:
    """Harici futbol API → PostgreSQL upsert (app.py fetch_and_upsert uçları)."""

    def __init__(self, db):
        self.db = db

    def fetch_all_leagues(self, season: int) -> None:
        ld = leagueDataFetch()
        rows = ld.get_league_data(season)
        if isinstance(rows, dict) and rows.get("error"):
            raise RuntimeError(rows.get("error", "API hatası"))
        for row in rows or []:
            lid = row.get("id")
            if lid is None:
                continue
            year = row.get("season")
            season_str = str(year) if year is not None else str(season)
            ex = self.db.query(League).filter(League.id == lid).first()
            if ex:
                if row.get("name"):
                    ex.name = row["name"]
                ex.country = row.get("country")
                ex.season = season_str
            else:
                self.db.add(
                    League(
                        id=lid,
                        name=row.get("name") or f"League-{lid}",
                        country=row.get("country"),
                        season=season_str,
                    )
                )
        self.db.commit()

    def fetch_all_teams(self, league_id: int, season: int) -> None:
        td = teamDataFetch()
        rows = td.get_team_data(league_id, season)
        if isinstance(rows, dict) and rows.get("error"):
            raise RuntimeError(rows.get("error", "API hatası"))
        for row in rows or []:
            tid = row.get("id")
            if tid is None:
                continue
            ex = self.db.query(Team).filter(Team.id == tid).first()
            if ex:
                ex.league_id = row.get("league_id", league_id)
                if row.get("name"):
                    ex.name = row["name"]
                ex.country = row.get("country")
            else:
                self.db.add(
                    Team(
                        id=tid,
                        league_id=row.get("league_id", league_id),
                        name=row.get("name") or f"Team-{tid}",
                        country=row.get("country"),
                    )
                )
        self.db.commit()

    def fetch_all_players(self, team_id: int, season: int) -> None:
        pd = playerDataFetch()
        rows = pd.get_player_data(team_id, season)
        if isinstance(rows, dict) and rows.get("error"):
            raise RuntimeError(rows.get("error", "API hatası"))
        for row in rows or []:
            pid = row.get("id")
            if pid is None:
                continue
            ex = self.db.query(Player).filter(Player.id == pid).first()
            tid = row.get("team_id") or team_id
            if ex:
                ex.team_id = tid
                if row.get("firstname") is not None:
                    ex.firstname = row["firstname"]
                if row.get("lastname") is not None:
                    ex.lastname = row["lastname"]
                ex.age = _as_int(row.get("age"))
                ex.nationality = row.get("nationality")
                if row.get("position"):
                    ex.position = row["position"]
            else:
                self.db.add(
                    Player(
                        id=pid,
                        team_id=tid,
                        firstname=row.get("firstname") or "",
                        lastname=row.get("lastname") or "",
                        age=_as_int(row.get("age")),
                        nationality=row.get("nationality"),
                        position=row.get("position") or "",
                        description=None,
                    )
                )
        self.db.commit()

    def fetch_all_coachs(self, team_id: int, season: int) -> None:
        _ = season  # API imzası ile uyum
        cd = coachDataFetch()
        rows = cd.get_coach_data(team_id)
        if isinstance(rows, dict) and rows.get("error"):
            raise RuntimeError(rows.get("error", "API hatası"))
        for row in rows or []:
            cid = row.get("id")
            if cid is None:
                continue
            ex = self.db.query(Coach).filter(Coach.team_id == team_id).first()
            if ex:
                ex.firstname = row.get("firstname") or ex.firstname
                ex.lastname = row.get("lastname") or ex.lastname
                ex.age = _as_int(row.get("age"))
                ex.nationality = row.get("nationality")
            else:
                self.db.add(
                    Coach(
                        id=cid,
                        team_id=team_id,
                        firstname=row.get("firstname") or "",
                        lastname=row.get("lastname") or "",
                        age=_as_int(row.get("age")),
                        nationality=row.get("nationality"),
                        description=None,
                    )
                )
            break
        self.db.commit()

    def fetch_team_statistics(self, team_id: int, season: int, league_id: int) -> None:
        tsf = teamStatisticsDataFetch()
        data = tsf.get_team_statistics_data(team_id, season, league_id)
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(data.get("error", "API hatası"))
        ex = self.db.query(TeamStatistics).filter(TeamStatistics.team_id == team_id).first()
        lineups = data.get("linesups", data.get("lineups"))
        payload = {
            "fixtures": data.get("fixtures"),
            "goals_for": data.get("goals_for"),
            "goals_against": data.get("goals_against"),
            "failed_to_score": data.get("failed_to_score"),
            "lineups": lineups,
            "cards_yellow": data.get("cards_yellow"),
            "cards_red": data.get("cards_red"),
        }
        if ex:
            for k, v in payload.items():
                if v is not None:
                    setattr(ex, k, v)
        else:
            self.db.add(
                TeamStatistics(
                    team_id=team_id,
                    fixtures=payload["fixtures"],
                    goals_for=payload["goals_for"],
                    goals_against=payload["goals_against"],
                    failed_to_score=payload["failed_to_score"],
                    lineups=payload["lineups"],
                    cards_yellow=payload["cards_yellow"],
                    cards_red=payload["cards_red"],
                )
            )
        self.db.commit()

    def fetch_all_player_statistics(self, season: int, team_id: int) -> None:
        psf = playerStatisticsDataFetch()
        rows = psf.get_player_statistics_data(season, team_id)
        if isinstance(rows, dict) and rows.get("error"):
            raise RuntimeError(rows.get("error", "API hatası"))
        for row in rows or []:
            pid = row.get("player_id")
            if pid is None:
                continue
            ex = self.db.query(PlayerStatistics).filter(PlayerStatistics.player_id == pid).first()
            goals_j = _goals_json(row)
            fields = {
                "height": _as_int(row.get("height")),
                "weight": _as_int(row.get("weight")),
                "injured": bool(row.get("injured")) if row.get("injured") is not None else None,
                "games": row.get("games"),
                "substitutes": row.get("substitutes"),
                "shooting": row.get("shooting"),
                "passing": row.get("passing"),
                "goals": goals_j,
                "tackles": row.get("tackles"),
                "duels": row.get("duels"),
                "dribbles": row.get("dribbles"),
                "fouls": row.get("fouls"),
                "cards": row.get("cards"),
                "penalty": row.get("penalty"),
            }
            if ex:
                for k, v in fields.items():
                    if v is not None:
                        setattr(ex, k, v)
            else:
                self.db.add(
                    PlayerStatistics(
                        player_id=pid,
                        height=fields["height"],
                        weight=fields["weight"],
                        injured=fields["injured"] if fields["injured"] is not None else False,
                        games=fields["games"],
                        substitutes=fields["substitutes"],
                        shooting=fields["shooting"],
                        passing=fields["passing"],
                        goals=fields["goals"],
                        tackles=fields["tackles"],
                        duels=fields["duels"],
                        dribbles=fields["dribbles"],
                        fouls=fields["fouls"],
                        cards=fields["cards"],
                        penalty=fields["penalty"],
                    )
                )
        self.db.commit()