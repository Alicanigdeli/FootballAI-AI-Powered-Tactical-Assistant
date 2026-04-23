from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Boolean, JSON, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)

    firstname = Column(String, index=True)
    lastname = Column(String, index=True)
    age = Column(Integer, index=True)
    nationality = Column(String)
    position = Column(String, index=True)
    description = Column(String)
    statistics = relationship("PlayerStatistics", back_populates="player", uselist=False)
    team = relationship("Team", back_populates="players")
    def __repr__(self):
        return f"<Player id={self.id} name={self.firstname} {self.lastname}>"
    
class PlayerStatistics(Base):
    __tablename__ = "player_statistics"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), unique=True, index=True)

    height = Column(Integer)
    weight = Column(Integer)
    injured = Column(Boolean, default=False)
    games = Column(JSON)
    substitutes = Column(JSON)
    shooting = Column(JSON)
    passing = Column(JSON)
    goals = Column(JSON)
    tackles = Column(JSON)
    duels = Column(JSON)
    dribbles = Column(JSON)
    fouls = Column(JSON)
    cards = Column(JSON)
    penalty = Column(JSON)

    player = relationship("Player", back_populates="statistics")
    def __repr__(self):
        return f"<PlayerStatistics id={self.id} player_id={self.player_id}>"

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey("leagues.id"), index=True) 
    name = Column(String, index=True)
    country = Column(String)
    players = relationship("Player", back_populates="team")
    coach = relationship("Coach", back_populates="team", uselist=False)
    # Relations
    league_rel = relationship("League", back_populates="teams")
    statistics = relationship("TeamStatistics", back_populates="team", uselist=False)

    def __repr__(self):
        return f"<Team id={self.id} name={self.name}>"

    
# burada lige göre veri çekmeyi bulup veriler incenecek yarın bak. amaç team istatiskleri laıancka ama türkiye ligi için alırsın sonra bakılacak sadece takım alnıyor mu diye.
class TeamStatistics(Base):
    __tablename__ = "team_statistics"
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), unique=True, index=True)
    fixtures = Column(JSON)
    goals_for = Column(JSON)
    goals_against = Column(JSON)
    failed_to_score = Column(JSON)
    lineups = Column(JSON)
    cards_yellow = Column(JSON)
    cards_red = Column(JSON)
    team = relationship("Team", back_populates="statistics")
    def __repr__(self):
        return f"<TeamStatistics id={self.id} team_name={self.team_name}>"

class Coach(Base):
    __tablename__ = "coaches"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"),unique=True,index=True)
    firstname = Column(String)
    lastname = Column(String)
    age = Column(Integer)
    nationality = Column(String)
    description = Column(String)
    team = relationship("Team", back_populates="coach")


    def __repr__(self):
        return f"<Coach id={self.id} name={self.firstname}>"
    
class League(Base):
    """Futbol ligi bilgilerini tutar."""
    __tablename__ = "leagues"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    country = Column(String, index=True)
    season = Column(String, index=True) # Örn: "2024/2025"

    teams = relationship("Team", back_populates="league_rel") # teams ilişkisi zaten tanımlı
    
    def __repr__(self):
        return f"<League id={self.id} name={self.name}>"


class TacticalSimulation(Base):
    __tablename__ = "tactical_simulations"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, index=True, nullable=False)
    home_id = Column(Integer)
    away_id = Column(Integer)
    my_team_id = Column(Integer)
    sim_type = Column(String(64), index=True, nullable=False)
    title = Column(String(256))
    description = Column(String)
    frames = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<TacticalSimulation id={self.id} match={self.match_id} type={self.sim_type}>"


class MatchAnalysis(Base):
    """Head coach (bütünsel) analiz geçmişi — maç ID ile listelenir."""

    __tablename__ = "match_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, index=True, nullable=False)
    home_id = Column(Integer, index=True)
    away_id = Column(Integer, index=True)
    my_team_id = Column(Integer, index=True)
    home_name = Column(String(256))
    away_name = Column(String(256))
    match_date = Column(String(128))
    session_id = Column(String(80), index=True)
    task_id = Column(String(80))
    result_text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<MatchAnalysis id={self.id} match={self.match_id}>"
