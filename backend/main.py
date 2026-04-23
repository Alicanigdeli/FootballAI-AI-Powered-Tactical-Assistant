from database import engine, Base
from model import (
    Player,
    Team,
    Coach,
    League,
    PlayerStatistics,
    TeamStatistics,
    TacticalSimulation,
    MatchAnalysis,
)


def init_db():
    Base.metadata.create_all(bind=engine)
    

if __name__ == "__main__":
    init_db()
    print("DB initialized!")
