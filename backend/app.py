import os
import json
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from database import SessionLocal
from pydantic import BaseModel, field_validator

from redis_orchestrator import FootballLLMOrchestrator, LLMAnswerStatus
from sqlalchemy import cast, or_, String, func
from sqlalchemy.orm import Session
from typing import Optional

from model import League, Team, Player, PlayerStatistics, TacticalSimulation, MatchAnalysis

from api_client import DataService

def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()


_embedded_llm_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Koç endpoint'leri Redis kuyruğuna yazar; worker'lar kuyruğu dinleyip
    `response:{task_id}` üzerinden cevabı üretir.

    Varsayılan: worker'lar bu uvicorn sürecinde arka planda çalışır (Postman tek sunucu yeter).
    Ölçekleme: DISABLE_EMBEDDED_LLM_WORKERS=1 ile kapatıp ayrı süreçte `python llm_models.py` çalıştır.
    """
    global _embedded_llm_tasks
    disable = os.getenv("DISABLE_EMBEDDED_LLM_WORKERS", "").lower() in ("1", "true", "yes")
    if not disable:
        from llm_models import HeadCoachAI, TacticalAIHub

        coach = HeadCoachAI()
        hub = TacticalAIHub()
        _embedded_llm_tasks = [
            asyncio.create_task(coach.run_worker(), name="head_coach_worker"),
            asyncio.create_task(hub.run_worker(), name="tactical_hub_worker"),
        ]
        print("🤖 Gömülü LLM worker'ları başladı (head_coach_queue + diğer koç kuyrukları).")
    else:
        print(
            "ℹ️  Gömülü LLM worker kapalı. Cevap için ayrı terminal: "
            "cd backend && python llm_models.py"
        )

    yield

    for t in _embedded_llm_tasks:
        t.cancel()
    if _embedded_llm_tasks:
        await asyncio.gather(*_embedded_llm_tasks, return_exceptions=True)
    _embedded_llm_tasks.clear()


app = FastAPI(lifespan=lifespan)

_cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
_cors_raw = _cors_raw.strip().strip("[]")
_cors_origins = [
    o.strip().strip("'\"")
    for o in _cors_raw.split(",")
    if o.strip().strip("'\"")
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/players/fetch_and_upsert")
def fetch_and_upsert_players(
    team_id:int,
    season:int,
    db:SessionLocal=Depends(get_db)
    ):
    service=DataService(db)
    try:
        service.fetch_all_players(team_id,season)
    except Exception as e:
        return {
            "status":"error",
            "message":str(e)
        }
    return {
        "status":"success",
        "team_id":team_id,
        "season":season,
        "message":"Player data fetched and upserted successfully."
    }
    
@app.get("/teams/fetch_and_upsert")
def fetch_and_upsert_teams(
    league_id:int,
    season:int,
    db:SessionLocal=Depends(get_db)
    ):
    service=DataService(db)
    try:
        service.fetch_all_teams(league_id,season)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "status":"success",
        "league_id":league_id,
        "season":season,
        "message":"Team data fetched and upserted successfully."
    }

@app.get("/coachs/fetch_and_upsert")
def fetch_and_upsert_coachs(
    team_id:int,
    season:int,
    db:SessionLocal=Depends(get_db)
    ):
    service=DataService(db)
    try:
        service.fetch_all_coachs(team_id,season)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "status":"success",
        "team_id":team_id,
        "season":season,
        "message":"Coach data fetched and upserted successfully."
    }

@app.get("/leagues/fetch_and_upsert")
def fetch_and_upsert_leagues(
    season:int,
    db:SessionLocal=Depends(get_db)
    ):
    service=DataService(db)
    try:
        service.fetch_all_leagues(season)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "status":"success",
        "season":season,
        "message":"League data fetched and upserted successfully."
    }

@app.get("/teamstats/fetch_and_upsert")
def fetch_team_statistics(
    team_id:int,
    season:int,
    league_id:int,
    db:SessionLocal=Depends(get_db)
    ):
    service=DataService(db)
    try:
        service.fetch_team_statistics(team_id,season,league_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "status":"success",
        "team_id":team_id,
        "season":season,
        "league_id":league_id,
        "message":"Team statistics data fetched and upserted successfully."
    }

@app.get("/playerstats/fetch_and_upsert")
def fetch_all_player_statistics(
    team_id:int,
    season:int,
    league_id:int,
    db:SessionLocal=Depends(get_db)
    ):
    service=DataService(db)
    try:
        service.fetch_all_player_statistics(season,team_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "status":"success",
        "team_id":team_id,
        "season":season,
        "league_id":league_id,
        "message":"Player statistics data fetched and upserted successfully."
    }



# app.py içindeki mevcut class'ı bu şekilde güncelle
# app.py

class MatchStrategyRequest(BaseModel):
    match_id: int
    home_id: int
    away_id: int
    my_team_id: int
    # Opsiyonel: maç tarihi/saat (UI'dan gönderilebilir; sim başlıklarında kullanılır)
    match_date: str | None = None
    # Opsiyonel: aynı maçta kısa sohbet için oturum (head-coach sonrası Redis'te bağlam)
    session_id: str | None = None
    # Teknik direktörden gelen özel not/talimat (Opsiyonel)
    coach_instruction: str | None = None
    # Panelden düzenlenen oyuncu/istatistik özet metni (LLM'e ek bağlam)
    analysis_notes: str | None = None

class CustomSimulationRequest(BaseModel):
    home_id: int
    away_id: int
    my_team_id: int
    sim_type: str = "attack_organization"
    count: int = 1
    coach_instruction: Optional[str] = None

class MatchChatRequest(BaseModel):
    session_id: str
    message: str


async def process_coach_request(task_type: LLMAnswerStatus, request_data: MatchStrategyRequest):
    """
    Tüm koçluk isteklerini işleyen genel fonksiyon.
    Redis'e bağlanır, görevi ilgili kuyruğa atar ve cevabı bekler.
    """
    orchestrator = FootballLLMOrchestrator()
    await orchestrator.connect()
    
    try:
        # Request body'den gelen verileri dict'e çevir
        task_params = request_data.model_dump()
        task_params.pop("session_id", None)
        notes = task_params.pop("analysis_notes", None)
        if notes:
            ci = task_params.get("coach_instruction") or ""
            task_params["coach_instruction"] = (
                f"{ci}\n\n--- Maç analiz paneli (düzenlenen veri) ---\n{notes}"
            )

        # Görevi Orchestrator üzerinden gönder
        task_id = await orchestrator.submit_task(task_type, task_params)
        
        if not task_id:
            raise HTTPException(status_code=500, detail="Görev Redis kuyruğuna iletilemedi.")
            
        # Cevabı Bekle (Timeout: 120 saniye yeterli olacaktır tekil görevler için)
        response_key = f"response:{task_id}"
        response_raw = await orchestrator.redis_client.blpop(response_key, timeout=120)
        
        if response_raw:
            _, response_data = response_raw
            response_json = json.loads(response_data)
            
            return {
                "status": "success",
                "task_id": task_id,
                "task_type": task_type.value,
                "result": response_json.get("result")
            }
        else:
            raise HTTPException(status_code=504, detail="AI Coach yanıt vermedi (Zaman Aşımı).")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sistem Hatası: {str(e)}")
        
    finally:
        await orchestrator.disconnect()


# ─── SİMÜLASYON ARKA PLAN GÖREVİ ──────────────────────────────────────────

def _bg_generate_simulations(match_params: dict, coach_report: str):
    """BackgroundTasks tarafından çağrılır; LLM ile tüm sim tiplerini üretip DB'ye yazar."""
    from llm_models import generate_all_simulations

    print(f"🎬 Simülasyon üretimi başladı  match_id={match_params.get('match_id')}")
    sims = generate_all_simulations(match_params, coach_report)

    if not sims:
        print("⚠️  Hiçbir simülasyon üretilemedi.")
        return

    db = SessionLocal()
    try:
        for s in sims:
            db.add(TacticalSimulation(
                match_id=match_params["match_id"],
                home_id=match_params.get("home_id"),
                away_id=match_params.get("away_id"),
                my_team_id=match_params.get("my_team_id"),
                sim_type=s["sim_type"],
                title=s["title"],
                description=s["description"],
                frames=s["frames"],
            ))
        db.commit()
        print(f"✅ {len(sims)} simülasyon DB'ye kaydedildi  match_id={match_params['match_id']}")
    except Exception as exc:
        db.rollback()
        print(f"❌ Simülasyon DB kayıt hatası: {exc}")
    finally:
        db.close()


def _team_names_for_ids(db: Session, home_id: int | None, away_id: int | None) -> tuple[str | None, str | None]:
    hn, an = None, None
    if home_id is not None:
        t = db.query(Team).filter(Team.id == home_id).first()
        hn = t.name if t else None
    if away_id is not None:
        t = db.query(Team).filter(Team.id == away_id).first()
        an = t.name if t else None
    return hn, an

def _bg_generate_custom_simulations(sim_params: dict):
    from llm_models import generate_custom_simulations_task
    from database import SessionLocal
    from model import TacticalSimulation, MatchAnalysis
    import json
    
    try:
        db = SessionLocal()
        coach_report = ""
        try:
            # Eğer match_id 999 veya dummy bir şeyse, son analizi bulmaya çalış ya da yenisini üret
            latest_analysis = db.query(MatchAnalysis).filter(MatchAnalysis.match_id == sim_params["match_id"]).order_by(MatchAnalysis.id.desc()).first()
            if latest_analysis:
                coach_report = latest_analysis.result_text
        finally:
            db.close()

        sims = generate_custom_simulations_task(sim_params, coach_report=coach_report)
        if hasattr(sims, '__await__'):
           import asyncio
           sims = asyncio.run(sims)
        if not sims:
            return
            
        db = SessionLocal()
        try:
            for s in sims:
                sim_model = TacticalSimulation(
                    match_id=sim_params["match_id"],
                    home_id=sim_params.get("home_id"),
                    away_id=sim_params.get("away_id"),
                    my_team_id=sim_params.get("my_team_id"),
                    sim_type=s["sim_type"],
                    title=s["title"],
                    description=s["description"],
                    frames=s["frames"]
                )
                db.add(sim_model)
            db.commit()
            print(f"🎬 [Custom] {len(sims)} simülasyon DB'ye kaydedildi")
        except Exception as exc:
            db.rollback()
            print(f"❌ [Custom] Simülasyon DB kayıt hatası: {exc}")
        finally:
            db.close()
    except Exception as e:
        print(f"❌ Custom simülasyon görev hatası: {e}")

def _bg_save_match_analysis(
    match_params: dict,
    coach_report: str,
    task_id: str | None,
    session_id: str | None,
):
    """Head coach çıktısını PostgreSQL'de maç ID ile saklar (sayfa yenilemede geçmiş)."""
    if not coach_report:
        return
    db = SessionLocal()
    try:
        mid = int(match_params.get("match_id") or 0)
        if mid == 0:
            # En son kullanılan match_id'yi bulup 1 artırıyoruz (otomatik belirleme)
            from sqlalchemy import func
            max_id = db.query(func.max(MatchAnalysis.match_id)).scalar() or 1000
            mid = max_id + 1

        hid = match_params.get("home_id")
        aid = match_params.get("away_id")
        hn, an = _team_names_for_ids(db, hid, aid)
        row = MatchAnalysis(
            match_id=mid,
            home_id=hid,
            away_id=aid,
            my_team_id=match_params.get("my_team_id"),
            home_name=hn,
            away_name=an,
            match_date=(match_params.get("match_date") or None),
            session_id=(session_id or "")[:80] or None,
            task_id=(task_id[:80] if task_id else None),
            result_text=coach_report,
        )
        db.add(row)
        db.commit()
        print(f"📝 Maç analizi kaydedildi  match_id={row.match_id} id={row.id}")
    except Exception as exc:
        db.rollback()
        print(f"❌ Maç analizi DB kayıt hatası: {exc}")
    finally:
        db.close()


def _persist_coach_session(session_id: str, params: dict, analysis_text: str):
    """Head coach çıktısını Redis'te tutar; /coach/match-chat tekrar tüm veriyi göndermez."""
    from coach_session import save_analysis_snapshot

    clean = {
        k: v
        for k, v in params.items()
        if k not in ("session_id", "analysis_notes")
    }
    save_analysis_snapshot(session_id, clean, analysis_text)


# --- MEVCUT HEAD COACH (BÜTÜNSEL) ---
@app.post("/coach/head-coach")
async def get_holistic_strategy(
    request: MatchStrategyRequest,
    background_tasks: BackgroundTasks,
):
    result = await process_coach_request(LLMAnswerStatus.HOLISTIC_MATCH_STRATEGY, request)

    coach_report = ""
    if isinstance(result, dict):
        coach_report = str(result.get("result", ""))

    sid = (request.session_id or "").strip()
    if sid and coach_report:
        background_tasks.add_task(
            _persist_coach_session,
            sid,
            request.model_dump(exclude_none=True),
            coach_report,
        )

    sim_params = {k: v for k, v in request.model_dump().items() if k != "session_id"}

    task_id_val = result.get("task_id") if isinstance(result, dict) else None
    if coach_report:
        background_tasks.add_task(
            _bg_save_match_analysis,
            sim_params,
            coach_report,
            str(task_id_val) if task_id_val else None,
            sid or None,
        )

    out = {**result} if isinstance(result, dict) else {"result": result}
    if sid:
        out["session_id"] = sid
    return out


@app.post("/coach/match-chat")
async def coach_match_chat(req: MatchChatRequest):
    """
    Aynı maç oturumunda kısa takip soruları. Bağlam Redis'te (analiz özeti + son mesajlar).
    """
    from coach_session import append_chat_turn, get_chat_history, load_match_context
    from llm_models import run_coach_match_chat

    sid = (req.session_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id gerekli")
    msg = (req.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message gerekli")

    ctx = load_match_context(sid)
    if not ctx:
        raise HTTPException(
            status_code=404,
            detail="Oturum bulunamadı. Önce head-coach analizi yapıp aynı session_id ile kaydedin.",
        )

    hist = get_chat_history(sid)
    reply = run_coach_match_chat(msg, hist, ctx)
    append_chat_turn(sid, msg, reply)
    return {"status": "success", "session_id": sid, "reply": reply}

@app.post("/coach/generate-simulations/{match_id}")
async def generate_simulations_for_match(match_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    analysis = db.query(MatchAnalysis).filter(MatchAnalysis.match_id == match_id).order_by(MatchAnalysis.id.desc()).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Maç analizi bulunamadı. Önce analiz yaptırmanız gerekiyor.")
        
    sim_params = {
        "match_id": match_id,
        "home_id": analysis.home_id,
        "away_id": analysis.away_id,
        "my_team_id": analysis.my_team_id,
        "match_date": analysis.match_date
    }
    
    background_tasks.add_task(
        _bg_generate_simulations,
        sim_params,
        analysis.result_text
    )
    
    return {"status": "success", "message": "Simülasyon üretimi arka planda başlatıldı."}


@app.post("/coach/generate-custom-simulations/{match_id}")
async def generate_custom_simulations_route(
    match_id: int, 
    request: CustomSimulationRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    actual_match_id = match_id
    
    # Eğer match_id belirtilmemişse (0 gelirse) veya yeni bir dummy lazımsa
    if actual_match_id == 0:
        # En yüksek match_id'yi bul
        max_id = db.query(func.max(MatchAnalysis.match_id)).scalar() or 9999
        actual_match_id = max_id + 1

    # MatchAnalysis tablosunda bu ID yoksa (veya 9999+ dummy ise) liste için bir kayıt oluştur
    exists = db.query(MatchAnalysis).filter(MatchAnalysis.match_id == actual_match_id).first()
    if not exists:
        hn, an = _team_names_for_ids(db, request.home_id, request.away_id)
        new_analysis = MatchAnalysis(
            match_id=actual_match_id,
            home_id=request.home_id,
            away_id=request.away_id,
            my_team_id=request.my_team_id or request.home_id,
            home_name=hn or "Ev Sahibi",
            away_name=an or "Deplasman",
            match_date="Özel Üretim",
            result_text="Bu analiz özel üretim simülasyonu için manuel olarak başlatıldı."
        )
        db.add(new_analysis)
        db.commit()

    sim_params = {
        "match_id": actual_match_id,
        "home_id": request.home_id,
        "away_id": request.away_id,
        "my_team_id": request.my_team_id,
        "sim_type": request.sim_type,
        "count": request.count,
        "coach_instruction": request.coach_instruction
    }
    
    background_tasks.add_task(
        _bg_generate_custom_simulations,
        sim_params
    )
    
    return {
        "status": "success", 
        "match_id": actual_match_id,
        "message": f"{request.count} adet {request.sim_type} simülasyon üretimi (#{actual_match_id}) için başlatıldı."
    }

# --- 1. SAVUNMA KOÇU ---
@app.post("/coach/defense")
async def get_defense_tactic(request: MatchStrategyRequest):
    """Sadece savunma kurgusu ve eşleşme önerisi verir."""
    return await process_coach_request(LLMAnswerStatus.DEFENSE_TACTIC_SUGGESTION, request)


# --- 2. HÜCUM KOÇU ---
@app.post("/coach/offense")
async def get_offense_tactic(request: MatchStrategyRequest):
    """Sadece hücum setleri ve zayıf yön analizi verir."""
    return await process_coach_request(LLMAnswerStatus.OFFENSE_TACTIC_SUGGESTION, request)


# --- 3. DURAN TOP UZMANI ---
@app.post("/coach/set-piece")
async def get_set_piece_tactic(request: MatchStrategyRequest):
    """Korner ve frikik organizasyonları verir."""
    return await process_coach_request(LLMAnswerStatus.SET_PIECE_SUGGESTION, request)


# --- 4. POZİSYON ANALİSTİ ---
@app.post("/coach/positioning")
async def get_player_positioning(request: MatchStrategyRequest):
    """Oyuncuların saha içi yerleşimi ve rolleri hakkında tavsiye verir."""
    return await process_coach_request(LLMAnswerStatus.PLAYER_POSITIONING_SUGGESTION, request)


# --- 5. MAÇ HAZIRLIK UZMANI ---
@app.post("/coach/preparation")
async def get_match_preparation(request: MatchStrategyRequest):
    """Maç öncesi mental ve taktiksel hazırlık tavsiyeleri verir."""
    return await process_coach_request(LLMAnswerStatus.MATCH_PREPARATION_SUGGESTION, request)


# --- 6. ANTRENMAN DRİLİ ---
@app.post("/coach/training")
async def get_training_drill(request: MatchStrategyRequest):
    """
    Maç eksiğine göre antrenman drili önerir.
    'focus_area' parametresi gönderilirse ona odaklanır.
    """
    return await process_coach_request(LLMAnswerStatus.TRAINING_DRILL_SUGGESTION, request)


# ─────────────────────────────────────────────────────────────────────────────
# RAG TAKTİKSEL SORGU ENDPOINTLERİ
# ─────────────────────────────────────────────────────────────────────────────

class TacticalQueryRequest(BaseModel):
    question: str
    verbose: Optional[bool] = False


class IngestRequest(BaseModel):
    team_name: Optional[str] = ""
    file_path: Optional[str] = None  # None → RAG_DOCUMENTS_PATH klasörünü tara


@app.get("/rag/stats")
async def rag_chroma_stats():
    """
    ChromaDB'de kaç kayıt olduğunu döndürür (ingest başarılı mı kontrolü).
    tactical_documents / tactical_sections / tactical_facts sayıları.
    """
    from rag_ingest import get_chroma_stats
    return await asyncio.get_event_loop().run_in_executor(None, get_chroma_stats)


@app.post("/rag/query")
async def rag_tactical_query(request: TacticalQueryRequest):
    """
    Taktiksel RAG sorgulama endpoint'i.

    Kullanım örnekleri:
      - "4-3-3 formasyonunda savunmaya geçiş prensipleri nelerdir?"
      - "Son iki maçta sol kanattaki pres performansı nasıldı?"
      - "MD-2 günü için antrenman planı öner"
      - "xG ve PPDA metriklerini nasıl yorumlamalıyım?"
    """
    try:
        from llm_models import tactical_rag_query
        answer = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: tactical_rag_query(request.question, verbose=request.verbose),
        )
        return {
            "status":   "success",
            "question": request.question,
            "answer":   answer,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG Sorgu Hatası: {str(e)}")


@app.post("/rag/ingest")
async def rag_ingest_documents(request: IngestRequest, background_tasks: BackgroundTasks):
    """
    RAG_DOCUMENTS_PATH (veya verilen file_path) altındaki dokümanları ChromaDB'ye indeksler.
    İşlem arka planda çalışır; uzun sürebilir (PDF boyutuna göre 1-5 dakika).
    """
    def _run_ingest():
        from rag_ingest import ingest_file, ingest_directory
        if request.file_path:
            ingest_file(request.file_path, team_name=request.team_name or "")
        else:
            ingest_directory(team_name=request.team_name or "")

    background_tasks.add_task(_run_ingest)
    return {
        "status":  "accepted",
        "message": "İndeksleme arka planda başlatıldı. Sunucu loglarından durumu takip edebilirsiniz.",
        "target":  request.file_path or "RAG_DOCUMENTS_PATH klasörü",
    }


# ═══════════════════════════════════════════════════════════════════════════
# REST — Dashboard (liste / CRUD). Frontend `NEXT_PUBLIC_API_URL` ile çağırır.
# ═══════════════════════════════════════════════════════════════════════════


class LeagueRow(BaseModel):
    id: int
    name: str
    country: Optional[str] = None
    season: Optional[str] = None


class LeaguePatch(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None
    season: Optional[str] = None


class TeamRow(BaseModel):
    id: int
    league_id: int
    name: str
    country: Optional[str] = None


class TeamPatch(BaseModel):
    name: Optional[str] = None
    country: Optional[str] = None
    league_id: Optional[int] = None


class PlayerRow(BaseModel):
    id: int
    team_id: int
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    age: Optional[int] = None
    nationality: Optional[str] = None
    position: Optional[str] = None
    description: Optional[str] = None
    height: Optional[int] = None
    weight: Optional[int] = None
    injured: Optional[bool] = None
    games: Optional[dict] = None


class PlayerPatch(BaseModel):
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    age: Optional[int] = None
    nationality: Optional[str] = None
    position: Optional[str] = None
    description: Optional[str] = None


class PlayerStatsPatch(BaseModel):
    height: Optional[int] = None
    weight: Optional[int] = None
    injured: Optional[bool] = None
    games: Optional[dict] = None
    shooting: Optional[dict] = None
    passing: Optional[dict] = None
    goals: Optional[dict] = None
    tackles: Optional[dict] = None


class PaginatedLeagues(BaseModel):
    items: list[LeagueRow]
    total: int
    page: int
    page_size: int


class PaginatedTeams(BaseModel):
    items: list[TeamRow]
    total: int
    page: int
    page_size: int


def _clamp_page_size(page_size: int, default: int = 50, max_size: int = 100) -> int:
    if page_size < 1:
        return default
    return min(page_size, max_size)


@app.get("/rest/leagues", response_model=PaginatedLeagues)
def rest_list_leagues(
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    base = db.query(League)
    if q and q.strip():
        term = f"%{q.strip()}%"
        id_filter = None
        if q.strip().isdigit():
            id_filter = League.id == int(q.strip())
        text_filter = or_(
            League.name.ilike(term),
            League.country.ilike(term),
            League.season.ilike(term),
            cast(League.id, String).ilike(term),
        )
        base = base.filter(or_(text_filter, id_filter) if id_filter is not None else text_filter)
    total = base.count()
    ps = _clamp_page_size(page_size)
    p = max(page, 1)
    rows = (
        base.order_by(League.name)
        .offset((p - 1) * ps)
        .limit(ps)
        .all()
    )
    return PaginatedLeagues(
        items=[
            LeagueRow(
                id=r.id,
                name=r.name or "",
                country=r.country,
                season=r.season,
            )
            for r in rows
        ],
        total=total,
        page=p,
        page_size=ps,
    )


@app.patch("/rest/leagues/{league_id}")
def rest_patch_league(league_id: int, body: LeaguePatch, db: Session = Depends(get_db)):
    row = db.query(League).filter(League.id == league_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Lig bulunamadı")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    return {"status": "success", "id": league_id}


@app.delete("/rest/leagues/{league_id}")
def rest_delete_league(league_id: int, db: Session = Depends(get_db)):
    n_teams = db.query(Team).filter(Team.league_id == league_id).count()
    if n_teams:
        raise HTTPException(
            status_code=409,
            detail=f"Ligde {n_teams} takım var; önce takımları silin veya taşıyın.",
        )
    row = db.query(League).filter(League.id == league_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Lig bulunamadı")
    db.delete(row)
    db.commit()
    return {"status": "success", "id": league_id}


@app.get("/rest/teams", response_model=PaginatedTeams)
def rest_list_teams(
    league_id: Optional[int] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    base = db.query(Team)
    if league_id is not None:
        base = base.filter(Team.league_id == league_id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        id_filter = None
        league_id_filter = None
        if q.strip().isdigit():
            id_filter = Team.id == int(q.strip())
            league_id_filter = Team.league_id == int(q.strip())
        text_filter = or_(
            Team.name.ilike(term),
            Team.country.ilike(term),
            cast(Team.id, String).ilike(term),
            cast(Team.league_id, String).ilike(term),
        )
        if id_filter is not None:
            base = base.filter(or_(text_filter, id_filter, league_id_filter))
        else:
            base = base.filter(text_filter)
    total = base.count()
    ps = _clamp_page_size(page_size)
    p = max(page, 1)
    rows = (
        base.order_by(Team.name)
        .offset((p - 1) * ps)
        .limit(ps)
        .all()
    )
    return PaginatedTeams(
        items=[
            TeamRow(
                id=r.id,
                league_id=r.league_id,
                name=r.name or "",
                country=r.country,
            )
            for r in rows
        ],
        total=total,
        page=p,
        page_size=ps,
    )


@app.patch("/rest/teams/{team_id}")
def rest_patch_team(team_id: int, body: TeamPatch, db: Session = Depends(get_db)):
    row = db.query(Team).filter(Team.id == team_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Takım bulunamadı")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    return {"status": "success", "id": team_id}


@app.delete("/rest/teams/{team_id}")
def rest_delete_team(team_id: int, db: Session = Depends(get_db)):
    n_players = db.query(Player).filter(Player.team_id == team_id).count()
    if n_players:
        raise HTTPException(
            status_code=409,
            detail=f"Takımda {n_players} oyuncu var; önce oyuncuları silin.",
        )
    row = db.query(Team).filter(Team.id == team_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Takım bulunamadı")
    db.delete(row)
    db.commit()
    return {"status": "success", "id": team_id}


@app.get("/rest/players", response_model=list[PlayerRow])
def rest_list_players(team_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(Player)
        .filter(Player.team_id == team_id)
        .order_by(Player.lastname, Player.firstname)
        .all()
    )
    out: list[PlayerRow] = []
    for p in rows:
        st = p.statistics
        out.append(
            PlayerRow(
                id=p.id,
                team_id=p.team_id,
                firstname=p.firstname,
                lastname=p.lastname,
                age=p.age,
                nationality=p.nationality,
                position=p.position,
                description=p.description,
                height=st.height if st else None,
                weight=st.weight if st else None,
                injured=st.injured if st else None,
                games=st.games if st else None,
            )
        )
    return out


@app.patch("/rest/players/{player_id}")
def rest_patch_player(player_id: int, body: PlayerPatch, db: Session = Depends(get_db)):
    row = db.query(Player).filter(Player.id == player_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    return {"status": "success", "id": player_id}


@app.patch("/rest/players/{player_id}/statistics")
def rest_patch_player_stats(
    player_id: int, body: PlayerStatsPatch, db: Session = Depends(get_db)
):
    row = db.query(Player).filter(Player.id == player_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")
    st = row.statistics
    if not st:
        st = PlayerStatistics(player_id=player_id)
        db.add(st)
        db.flush()
    data = body.model_dump(exclude_unset=True)
    if "games" in data and data["games"] is not None:
        gnew = data.pop("games")
        if isinstance(st.games, dict) and isinstance(gnew, dict):
            st.games = {**st.games, **gnew}
        else:
            st.games = gnew
    for k, v in data.items():
        setattr(st, k, v)
    db.commit()
    return {"status": "success", "player_id": player_id}


@app.delete("/rest/players/{player_id}")
def rest_delete_player(player_id: int, db: Session = Depends(get_db)):
    row = db.query(Player).filter(Player.id == player_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Oyuncu bulunamadı")
    if row.statistics:
        db.delete(row.statistics)
    db.delete(row)
    db.commit()
    return {"status": "success", "id": player_id}


# ═══════════════════════════════════════════════════════════════════════════
# REST — Maç analizi geçmişi (Head Coach)
# ═══════════════════════════════════════════════════════════════════════════


class MatchAnalysisMeta(BaseModel):
    id: int
    match_id: int
    home_id: Optional[int] = None
    away_id: Optional[int] = None
    my_team_id: Optional[int] = None
    home_name: Optional[str] = None
    away_name: Optional[str] = None
    match_date: Optional[str] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    created_at: Optional[str] = None


class MatchAnalysisRow(MatchAnalysisMeta):
    result_text: str


class MatchAnalysisPaginated(BaseModel):
    items: list[MatchAnalysisMeta]
    total: int
    page: int
    page_size: int


@app.get("/rest/match-analyses")
def rest_list_match_analyses(
    match_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """Tüm ya da belirli bir maça ait analiz listesi (sayfalama desteği ile)."""
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)
    
    # Sadece analiz tablosunu değil, simülasyon tablosundaki benzersiz match_id'leri de gösterebilmek için:
    # (Opsiyonel: Daha karmaşık bir join yerine, MatchAnalysis'i ana tablo tutup eksik olanları stub olarak ekleyelim/listeleyelim)
    
    q = db.query(MatchAnalysis)
    if match_id is not None:
        q = q.filter(MatchAnalysis.match_id == match_id)
    
    total = q.count()
    rows = (
        q.order_by(MatchAnalysis.created_at.desc(), MatchAnalysis.id.desc())
         .offset((page - 1) * page_size)
         .limit(page_size)
         .all()
    )

    # Eğer sayfa boşsa ve henüz hiç analiz yoksa ama simülasyonlar varsa, 
    # simülasyon tablosundan match_id'leri çekip sanal analizler gösterelim (ilk kurulum/debug geçişi için)
    if total == 0 and match_id is None:
        sim_match_ids = db.query(TacticalSimulation.match_id).distinct().all()
        for (smid,) in sim_match_ids:
            # Gerçekten yoksa sanal bir tane ekleyelim (stub)
            already = db.query(MatchAnalysis).filter(MatchAnalysis.match_id == smid).first()
            if not already:
                hn, an = _team_names_for_ids(db, None, None) # IDs for sims are often stored in its row, but we can't easily bulk-get here
                # En azından ilk simülasyon satırından isimleri alalım
                sample = db.query(TacticalSimulation).filter(TacticalSimulation.match_id == smid).first()
                new_stub = MatchAnalysis(
                    match_id=smid,
                    home_id=sample.home_id,
                    away_id=sample.away_id,
                    home_name="Maç #" + str(smid),
                    away_name="Simülasyon Aktif",
                    match_date=str(sample.created_at.date()) if sample.created_at else "Geçmiş",
                    result_text="Bu maç için henüz detaylı bir analiz raporu üretilmemiş, ancak taktik simülasyon verileri mevcut."
                )
                db.add(new_stub)
        db.commit()
        # Yeniden sorgula
        q = db.query(MatchAnalysis)
        total = q.count()
        rows = q.order_by(MatchAnalysis.created_at.desc(), MatchAnalysis.id.desc()).offset((page-1)*page_size).limit(page_size).all()

    items = [
        MatchAnalysisMeta(
            id=r.id,
            match_id=r.match_id,
            home_id=r.home_id,
            away_id=r.away_id,
            my_team_id=r.my_team_id,
            home_name=r.home_name,
            away_name=r.away_name,
            match_date=r.match_date,
            session_id=r.session_id,
            task_id=r.task_id,
            created_at=str(r.created_at) if r.created_at else None,
        )
        for r in rows
    ]
    
    # Eski istemciler (match_id var) için sadece list dön, yeni istemciler (sayfa destekli) obj dön
    if match_id is not None and page == 1 and page_size == 20:
        # frontend eski api-client (list) çağrısı ile uyumlu
        return items
    
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.get("/rest/match-analyses/{analysis_id}", response_model=MatchAnalysisRow)
def rest_get_match_analysis(analysis_id: int, db: Session = Depends(get_db)):
    row = db.query(MatchAnalysis).filter(MatchAnalysis.id == analysis_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Analiz bulunamadı")
    return MatchAnalysisRow(
        id=row.id,
        match_id=row.match_id,
        home_id=row.home_id,
        away_id=row.away_id,
        my_team_id=row.my_team_id,
        home_name=row.home_name,
        away_name=row.away_name,
        match_date=row.match_date,
        session_id=row.session_id,
        task_id=row.task_id,
        created_at=str(row.created_at) if row.created_at else None,
        result_text=row.result_text or "",
    )


@app.delete("/rest/match-analyses/{analysis_id}")
def rest_delete_match_analysis(analysis_id: int, db: Session = Depends(get_db)):
    row = db.query(MatchAnalysis).filter(MatchAnalysis.id == analysis_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Analiz bulunamadı")
    db.delete(row)
    db.commit()
    return {"status": "success", "id": analysis_id}


# ═══════════════════════════════════════════════════════════════════════════
# REST — Taktik Simülasyonlar
# ═══════════════════════════════════════════════════════════════════════════

class SimulationRow(BaseModel):
    id: int
    match_id: int
    home_id: Optional[int] = None
    away_id: Optional[int] = None
    my_team_id: Optional[int] = None
    home_name: Optional[str] = None
    away_name: Optional[str] = None
    sim_type: str
    title: Optional[str] = None
    description: Optional[str] = None
    frames: list
    created_at: Optional[str] = None

    @field_validator("frames", mode="before")
    @classmethod
    def parse_frames(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v

class SimulationMeta(BaseModel):
    id: int
    match_id: int
    home_id: Optional[int] = None
    away_id: Optional[int] = None
    my_team_id: Optional[int] = None
    home_name: Optional[str] = None
    away_name: Optional[str] = None
    sim_type: str
    title: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[str] = None


@app.get("/rest/simulations", response_model=list[SimulationMeta])
def rest_list_simulations(
    match_id: int,
    db: Session = Depends(get_db),
):
    """Belirli bir maç için tüm simülasyonları listeler (frames hariç, hafif)."""
    rows = (
        db.query(TacticalSimulation)
        .filter(TacticalSimulation.match_id == match_id)
        .order_by(TacticalSimulation.created_at.desc(), TacticalSimulation.id)
        .all()
    )
    out = []
    for r in rows:
        hn, an = _team_names_for_ids(db, r.home_id, r.away_id)
        out.append(
            SimulationMeta(
                id=r.id,
                match_id=r.match_id,
                home_id=r.home_id,
                away_id=r.away_id,
                my_team_id=r.my_team_id,
                home_name=hn,
                away_name=an,
                sim_type=r.sim_type,
                title=r.title,
                description=r.description,
                created_at=str(r.created_at) if r.created_at else None,
            )
        )
    return out


@app.get("/rest/simulations/{sim_id}", response_model=SimulationRow)
def rest_get_simulation(sim_id: int, db: Session = Depends(get_db)):
    """Tek bir simülasyonun tüm detayını (frames dahil) döndürür."""
    row = db.query(TacticalSimulation).filter(TacticalSimulation.id == sim_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Simülasyon bulunamadı")
    hn, an = _team_names_for_ids(db, row.home_id, row.away_id)
    return SimulationRow(
        id=row.id,
        match_id=row.match_id,
        home_id=row.home_id,
        away_id=row.away_id,
        my_team_id=row.my_team_id,
        home_name=hn,
        away_name=an,
        sim_type=row.sim_type,
        title=row.title,
        description=row.description,
        frames=row.frames,
        created_at=str(row.created_at) if row.created_at else None,
    )


@app.delete("/rest/simulations/{sim_id}")
def rest_delete_simulation(sim_id: int, db: Session = Depends(get_db)):
    row = db.query(TacticalSimulation).filter(TacticalSimulation.id == sim_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Simülasyon bulunamadı")
    db.delete(row)
    db.commit()
    return {"status": "success", "id": sim_id}


@app.get("/rest/simulations/status/{match_id}")
def rest_sim_generation_status(match_id: int, db: Session = Depends(get_db)):
    """Simülasyon üretimi tamamlandı mı kontrolü (polling için)."""
    count = (
        db.query(TacticalSimulation)
        .filter(TacticalSimulation.match_id == match_id)
        .count()
    )
    return {"match_id": match_id, "count": count, "ready": count > 0}