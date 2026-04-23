import asyncio
import json
import os
import redis.asyncio as redis
from dotenv import load_dotenv

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from api_client import fetchDBdataClient
from llm_client import get_langchain_model, LLMModelType
from redis_orchestrator import LLMAnswerStatus
from rag_ingest import retrieve_context

load_dotenv()

# --- LLM CALL LOGGING (TAKİP) ---
_LLM_CALL_STATS = {"count": 0}

def _log_llm(reason: str):
    _LLM_CALL_STATS["count"] += 1
    print(f"\n🚀 [LLM ÇAĞRISI #{_LLM_CALL_STATS['count']}]")
    print(f"   SEBEP: {reason}")
    print(f"   DURUM: İşlem yapılıyor...\n", flush=True)

# Tüm alt koçlara ortak davranış kuralları (tutarlı, eyleme dönük çıktı)
_COACH_SHARED_RULES = """
GENEL KURALLAR (ZORUNLU):
- Dil: Türkçe, profesyonel futbol koçluğu dili; abartılı metafor yok.
- Öncelik sırası: (1) Aşağıdaki oyuncu/istatistik verileri (2) Taktiksel bilgi tabanı (3) Genel taktik bilgin.
- Bilgi tabanı "yüklenmemiş" veya çok kısaysa bunu tek cümleyle belirt; veriye dayalı öneri ver, uydurma metrik veya hayali oyuncu ekleme.
- Veride geçen oyuncu isimlerini mümkün olduğunca doğrudan kullan; isim yoksa pozisyon + rol ile yaz.
- Somut ol: "baskı kuralım" yerine tetikleyici (ör. rakip kaleci topa bastığında), hat yüksekliği, kaç oyuncu önde gibi netlik.
- Her raporda en az 3 numaralı, uygulanabilir madde (maç günü sahada yapılacak net davranış).
"""

_MASTER_SYNTHESIS_RULES = """
SENTEZ KURALLARI (TEKNİK DİREKTÖR):
- Beş alt raporu ve bilgi tabanını tek bir tutarlı maç felsefesinde birleştir; çelişki varsa hangi seçeneği seçtiğini ve nedenini yaz.
- Soyunma odasından anlaşılır dil: önce ana fikir (1 paragraf), sonra detay.
- Her bölümde sahaya indirilebilir, ölçülebilir veya gözlemlenebilir ifadeler kullan (ör. pres tetikleyicisi, hat yüksekliği, koridor tercihi).
- Alt raporlarda isim geçen oyuncuları nihai planda koru; yeni hayali oyuncu ekleme.
- Maç içi yönetim: skor senaryolarına göre Plan B ve oyuncu değişikliği tetikleyicileri mutlaka olsun.
"""


# 1. ALT BİRİM: SAVUNMA KOORDİNATÖRÜ
class DefenderLLMModel:
    def __init__(self, db_client):
        self.db = db_client
        self.llm = get_langchain_model(LLMModelType.GEMINI, temperature=0.3)
        self.prompt = PromptTemplate(
            input_variables=["opp_attackers", "my_defenders", "opp_form", "my_form", "tactical_knowledge"],
            template="""
            Sen UEFA Pro düzeyinde Savunma Koordinatörüsün.
            GÖREV: Rakip hücum hattını etkisiz kılmak ve savunmaya geçişi organize etmek.

            """ + _COACH_SHARED_RULES + """

            📚 TAKTİKSEL BİLGİ TABANI (öncelikli referans; veriyle çelişirse veriyi açıkla):
            {tactical_knowledge}

            VERİLER:
            Rakip Hücumcular: {opp_attackers}
            Bizim Savunmacılar: {my_defenders}
            Formasyonlar — Rakip: {opp_form} | Biz: {my_form}

            DERİNLEMESİNE ANALİZ (içsel düşün, çıktıda özetle):
            • Savunma bloğu: hat derinliği, merkez/kanat dengesi, son adam ve yarı alan koruması.
            • Pres: ne zaman, nerede, kim tetikler; geri dönüş yolları (rest savunma).
            • Eşleşmeler: rakip en tehlikeli hücumcuya adam/alan kararı; fizik ve hız verisine dayan.
            • Savunmaya geçiş: top kaybından sonraki 5–8 saniye (yakın baskı, geri koşu kanalları).
            • Duran top savunması: kısa not (bölge/adam, ön direk rolleri).

            ÇIKTI FORMATI (başlıkları aynen kullan):

            ## Savunma Özeti
            (2–4 cümle: ana fikir + rakibe özel tehdit)

            ## Öncelikli Savunma Aksiyonları
            1. ...
            2. ...
            3. ...

            ## Eşleşme ve Özel Görevler
            (İsim veya pozisyon bazlı net görevler)

            ## Riskler ve Kontrol Soruları
            (En az 2 madde: ne olursa plan B?)
            """
        )
        self.chain = self.prompt | self.llm | StrOutputParser()

    async def analyze(self, inputs):
        _log_llm("Savunma Koordinatörü Analizi")
        return await self.chain.ainvoke(inputs)


def format_stats_for_llm(player_list: list) -> str:
    """
    Oyuncu istatistiklerini LLM için okunabilir formata çevirir.

    Tuple yapısı:
    (id, player_id, height, weight, injured, games, substitutes,
     shooting, passing, goals, tackles, duels, dribbles, fouls, cards, penalty, name, position)
    """
    if not player_list:
        return "Veri Yok."
    
    summary_text = "=== OYUNCU İSTATİSTİKLERİ ===\n\n"
    
    for idx, p in enumerate(player_list, 1):
        # Tuple kontrolü
        if not isinstance(p, tuple) or len(p) < 18:
            continue
            
        # Tuple indexleri (başlıklarına göre)
        id_val = p[0]
        player_id = p[1]
        height = p[2]
        weight = p[3]
        injured = p[4]
        games = p[5]          # dict
        substitutes = p[6]    # dict
        shooting = p[7]       # dict
        passing = p[8]        # dict
        goals = p[9]          # dict
        tackles = p[10]       # dict
        duels = p[11]         # dict
        dribbles = p[12]      # dict
        fouls = p[13]         # dict
        cards = p[14]         # dict
        penalty = p[15]       # dict
        name = p[16]
        position = p[17]
        description = p[-1] if len(p) > 18 else None
        
        # ===============================
        # OYUNCU BİLGİSİ
        # ===============================
        injury_status = "🚑 SAKALI" if injured else "✅ Sağlam"
        
        summary_text += f"{'='*60}\n"
        summary_text += f"OYUNCU {idx}: {name}\n"
        summary_text += f"{'='*60}\n"
        summary_text += f"📍 Pozisyon: {position}\n"
        summary_text += f"📏 Boy/Kilo: {height}cm / {weight}kg\n"
        summary_text += f"💉 Durum: {injury_status}\n"
        summary_text += f"\n"
        if description:
            summary_text += f"- ⚠️ TEKNİK DİREKTÖR NOTU: {description}\n"
        
        # ===============================
        # GENEL PERFORMANS (games dict)
        # ===============================
        if isinstance(games, dict) and games:
            summary_text += f"📊 GENEL PERFORMANS:\n"
            appearences = games.get('appearences', 0) or 0
            lineups = games.get('lineups', 0) or 0
            minutes = games.get('minutes', 0) or 0
            rating = games.get('rating', 'N/A')
            captain = games.get('captain', False)
            
            summary_text += f"   • Toplam Maç: {appearences}\n"
            summary_text += f"   • İlk 11: {lineups}\n"
            summary_text += f"   • Süre: {minutes} dakika\n"
            summary_text += f"   • Ortalama Not: {rating}\n"
            if captain:
                summary_text += f"   • 👑 Kaptan\n"
            summary_text += f"\n"
        
        # ===============================
        # YEDEK KULÜBESI (substitutes dict)
        # ===============================
        if isinstance(substitutes, dict) and substitutes:
            sub_in = substitutes.get('in', 0) or 0
            sub_out = substitutes.get('out', 0) or 0
            bench = substitutes.get('bench', 0) or 0
            
            if sub_in > 0 or sub_out > 0 or bench > 0:
                summary_text += f"🔄 YEDEK KULÜBESI:\n"
                summary_text += f"   • Oyuna Giriş: {sub_in}\n"
                summary_text += f"   • Oyundan Çıkış: {sub_out}\n"
                summary_text += f"   • Yedek Bekleme: {bench}\n"
                summary_text += f"\n"
        
        # ===============================
        # POZİSYONA ÖZEL İSTATİSTİKLER
        # ===============================
        
        # --- SAVUNMA İSTATİSTİKLERİ ---
        if position == "Defender":
            summary_text += f"🛡️ SAVUNMA İSTATİSTİKLERİ:\n"
            
            # Tackles (Müdahaleler)
            if isinstance(tackles, dict):
                tackles_total = tackles.get('total', 'N/A')
                tackles_blocks = tackles.get('blocks', 'N/A')
                tackles_interceptions = tackles.get('interceptions', 'N/A')
                summary_text += f"   • Toplam Müdahale: {tackles_total}\n"
                summary_text += f"   • Blok: {tackles_blocks}\n"
                summary_text += f"   • Top Kesme: {tackles_interceptions}\n"
            
            # Duels (İkili Mücadeleler)
            if isinstance(duels, dict):
                duels_total = duels.get('total', 'N/A')
                duels_won = duels.get('won', 'N/A')
                summary_text += f"   • Toplam Düello: {duels_total}\n"
                summary_text += f"   • Kazanılan: {duels_won}\n"
            
            summary_text += f"\n"
        
        # --- ORTA SAHA İSTATİSTİKLERİ ---
        elif position == "Midfielder":
            summary_text += f"⚙️ ORTA SAHA İSTATİSTİKLERİ:\n"
            
            # Passing (Paslar)
            if isinstance(passing, dict):
                passes_total = passing.get('total', 'N/A')
                passes_key = passing.get('key', 'N/A')
                passes_accuracy = passing.get('accuracy', 'N/A')
                summary_text += f"   • Toplam Pas: {passes_total}\n"
                summary_text += f"   • Kilit Pas: {passes_key}\n"
                summary_text += f"   • İsabetlilik: {passes_accuracy}\n"
            
            # Goals (Goller ve Asistler)
            if isinstance(goals, dict):
                assists = goals.get('assists', 'N/A')
                summary_text += f"   • Asist: {assists}\n"
            
            # Duels (İkili Mücadeleler)
            if isinstance(duels, dict):
                duels_total = duels.get('total', 'N/A')
                duels_won = duels.get('won', 'N/A')
                summary_text += f"   • Düello (Toplam/Kazanılan): {duels_total}/{duels_won}\n"
            
            # Dribbles (Çalımlar)
            if isinstance(dribbles, dict):
                dribbles_attempts = dribbles.get('attempts', 'N/A')
                dribbles_success = dribbles.get('success', 'N/A')
                summary_text += f"   • Çalım (Deneme/Başarılı): {dribbles_attempts}/{dribbles_success}\n"
            
            summary_text += f"\n"
        
        # --- HÜCUM İSTATİSTİKLERİ ---
        elif position == "Attacker":
            summary_text += f"⚽ HÜCUM İSTATİSTİKLERİ:\n"
            
            # Goals (Goller)
            if isinstance(goals, dict):
                goals_total = goals.get('total', 'N/A')
                assists = goals.get('assists', 'N/A')
                summary_text += f"   • Gol: {goals_total}\n"
                summary_text += f"   • Asist: {assists}\n"
            
            # Shooting (Şutlar)
            if isinstance(shooting, dict):
                shots_total = shooting.get('total', 'N/A')
                shots_on = shooting.get('on', 'N/A')
                summary_text += f"   • Toplam Şut: {shots_total}\n"
                summary_text += f"   • İsabetli Şut: {shots_on}\n"
            
            # Dribbles (Çalımlar)
            if isinstance(dribbles, dict):
                dribbles_attempts = dribbles.get('attempts', 'N/A')
                dribbles_success = dribbles.get('success', 'N/A')
                dribbles_past = dribbles.get('past', 'N/A')
                summary_text += f"   • Çalım (Deneme/Başarılı): {dribbles_attempts}/{dribbles_success}\n"
                summary_text += f"   • Geçilen Oyuncu: {dribbles_past}\n"
            
            summary_text += f"\n"
        
        # ===============================
        # DİSİPLİN (cards dict)
        # ===============================
        if isinstance(cards, dict):
            yellow = cards.get('yellow', 0) or 0
            red = cards.get('red', 0) or 0
            yellowred = cards.get('yellowred', 0) or 0
            
            if yellow > 0 or red > 0 or yellowred > 0:
                summary_text += f"🟨🟥 DİSİPLİN:\n"
                summary_text += f"   • Sarı Kart: {yellow}\n"
                summary_text += f"   • Kırmızı Kart: {red}\n"
                summary_text += f"   • Sarı→Kırmızı: {yellowred}\n"
                summary_text += f"\n"
        
        # ===============================
        # PENALTI (penalty dict)
        # ===============================
        if isinstance(penalty, dict):
            pen_won = penalty.get('won', 0) or 0
            pen_scored = penalty.get('scored', 0) or 0
            pen_missed = penalty.get('missed', 0) or 0
            
            if pen_won > 0 or pen_scored > 0 or pen_missed > 0:
                summary_text += f"⚡ PENALTI:\n"
                summary_text += f"   • Kazandığı: {pen_won}\n"
                summary_text += f"   • Gol: {pen_scored}\n"
                summary_text += f"   • Kaçırdığı: {pen_missed}\n"
                summary_text += f"\n"
        
        summary_text += f"\n"
        # summary_text += f"\n"
    return summary_text
    

def json_safe(data):
    if not data: return "Veri Yok"
    try: return json.dumps(data, default=str, ensure_ascii=False)
    except: return str(data)


# --- DB pozisyon etiketleri (API-FOOTBALL / players.games.position ile uyumlu) ---
_POS_GK = "Goalkeeper"
_POS_DEF = "Defender"
_POS_MID = "Midfielder"
_POS_ATT = "Attacker"


def _tuple_position(row: tuple) -> str | None:
    if not isinstance(row, tuple) or len(row) < 18:
        return None
    return str(row[17] or "")


def _rows_over_height(rows: list, min_cm: int = 185) -> list:
    out = []
    for p in rows or []:
        if not isinstance(p, tuple) or len(p) < 3:
            continue
        h = p[2]
        if isinstance(h, (int, float)) and h and h > min_cm:
            out.append(p)
    return out


def _format_goalkeepers_and_defenders(db, team_id: int) -> str:
    """Savunma koçu: kaleci + savunma hattı (diğer hatlar gönderilmez)."""
    gks = db.fetch_player_statistics_by_positions(team_id, [_POS_GK])
    defs = db.fetch_player_statistics_by_positions(team_id, [_POS_DEF])
    parts = []
    if gks:
        parts.append("=== Kaleci ===\n" + format_stats_for_llm(gks))
    if defs:
        parts.append("=== Savunma Oyuncuları ===\n" + format_stats_for_llm(defs))
    return "\n\n".join(parts) if parts else "Veri Yok."


def _format_key_players_outfield(db, team_id: int) -> str:
    """Pozisyonlama: saha oyuncuları (kaleci hariç; rol kartları için yeterli bağlam)."""
    rows = db.fetch_player_statistics_by_positions(team_id, [_POS_DEF, _POS_MID, _POS_ATT])
    return format_stats_for_llm(rows) if rows else "Veri Yok."


def _set_piece_tall_and_mids(db, team_id: int) -> tuple[list, list]:
    """Duran top: tüm hatlardan uzunlar + orta saha pasçıları."""
    all_p = db.fetch_player_statistics_by_positions(
        team_id, [_POS_GK, _POS_DEF, _POS_MID, _POS_ATT]
    )
    tall = _rows_over_height(all_p)
    mids = [p for p in all_p if _tuple_position(p) == _POS_MID]
    return tall, mids


def run_coach_match_chat(user_message: str, history: list[dict], match_ctx: dict) -> str:
    """
    Maç oturumu: Redis'teki analiz özeti + son mesajlar. Oyuncu DB / tam RAG yok;
    gerekirse kullanıcıyı yeniden head-coach analizine yönlendirir.
    """
    lines = []
    for m in history or []:
        role = (m.get("role") or "user").lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        prefix = "Kullanıcı" if role == "user" else "Asistan"
        lines.append(f"{prefix}: {content}")
    block_hist = "\n".join(lines) if lines else "(henüz önceki mesaj yok)"

    ctx = match_ctx or {}
    snap = ctx.get("analysis_snapshot") or ""
    mid = ctx.get("match_id")
    hid = ctx.get("home_id")
    aid = ctx.get("away_id")
    mtid = ctx.get("my_team_id")
    mdate = ctx.get("match_date")

    prompt = f"""Sen Türkçe konuşan bir maç analizi asistanısın. Teknik direktör kısa sorular soruyor veya
analizde küçük taktik düzeltmeler istiyor.

KURALLAR:
- Sadece aşağıdaki MAÇ KİMLİĞİ ve SON ANALİZ metnine + önceki sohbete dayan.
- Canlı kadro veritabanına, yeniden tam analize veya otomatik RAG taramasına erişimin yok.
- Emin olmadığın bir oyuncu/kadro detayı için dürüstçe "bunu net söylemek için head-coach analizi veya kadro verisi gerekir" de.
- Yanıtı kısa ve uygulanabilir tut (madde işaretleri kullanabilirsin).

MAÇ: match_id={mid}, home_id={hid}, away_id={aid}, my_team_id={mtid}, match_date={mdate}

SON ANALİZ (referans metin):
{snap[:14000]}

ÖNCEKİ SOHBET:
{block_hist}

ŞİMDİKİ İSTEK:
{user_message.strip()}
"""
    llm = get_langchain_model(LLMModelType.GEMINI, temperature=0.35)
    _log_llm("Maç Sohbeti (Coach Match Chat)")
    out = llm.invoke(prompt)
    return getattr(out, "content", None) or str(out)


# 2. ALT BİRİM: ORTA SAHA KOORDİNATÖRÜ
class MidfielderLLMModel:
    def __init__(self, db_client):
        self.db = db_client
        self.llm = get_langchain_model(LLMModelType.GEMINI, temperature=0.35)
        self.prompt = PromptTemplate(
            input_variables=["opp_midfielders", "my_midfielders", "strategy_context", "tactical_knowledge"],
            template="""
            Sen UEFA Pro düzeyinde Orta Saha Koordinatörüsün.
            GÖREV: Tempo, alan kontrolü, ikinci top ve hücuma/savunmaya geçiş köprüsünü yönetmek.

            """ + _COACH_SHARED_RULES + """

            📚 TAKTİKSEL BİLGİ TABANI:
            {tactical_knowledge}

            VERİLER:
            Rakip Orta Saha: {opp_midfielders}
            Bizim Orta Saha: {my_midfielders}
            Maç bağlamı: {strategy_context}

            DERİNLEMESİNE ANALİZ:
            • Oyun modeli: topa sahip olma vs hızlı geçiş; rakip orta saha kalitesine göre karar.
            • Dikey/geometri: yarım alanlar, üçüncü adam koşusu, genişlik ve merkez dengelemesi.
            • İkinci top ve geçişler: kazanım sonrası ilk pas hattı; kayıpta kompaktlık.
            • Kilit oyuncu: pas, dripling veya mücadele verisine göre "motor" ve "oyun kurucu" rolleri.
            • Sayısal üstünlük: pres sonrası veya set durumunda orta sahada +1 yaratma fikirleri.

            ÇIKTI FORMATI:

            ## Orta Saha Özeti
            (2–4 cümle)

            ## Oyun Planı (Tempo + Alan)
            (Net cümleler: ne zaman yavaşlat, ne zaman hızlandır)

            ## Öncelikli Aksiyonlar
            1. ...
            2. ...
            3. ...

            ## Kilit Oyuncu ve Rol Dağılımı
            (İsim veya pozisyon; net görev tanımı)

            ## Riskler ve Tetikleyiciler
            (Örn. rakip çift pivot bastığında, kanat içe kattığında ne yapılır?)
            """
        )
        self.chain = self.prompt | self.llm | StrOutputParser()

    async def analyze(self, inputs):
        _log_llm("Orta Saha Koordinatörü Analizi")
        return await self.chain.ainvoke(inputs)



# 3. ALT BİRİM: HÜCUM KOORDİNATÖRÜ

class AttackerLLMModel:
    def __init__(self, db_client):
        self.db = db_client
        self.llm = get_langchain_model(LLMModelType.GEMINI, temperature=0.55)
        self.prompt = PromptTemplate(
            input_variables=["opp_defenders", "my_attackers", "opp_weakness", "tactical_knowledge"],
            template="""
            Sen UEFA Pro düzeyinde Hücum Koordinatörüsün.
            GÖREV: Gol beklentisi yüksek pozisyonlar, son pas kalitesi ve bitirici senaryolar üretmek.

            """ + _COACH_SHARED_RULES + """

            📚 TAKTİKSEL BİLGİ TABANI:
            {tactical_knowledge}

            VERİLER:
            Rakip Savunma: {opp_defenders}
            Bizim Hücumcular: {my_attackers}
            Rakip / bağlam notu: {opp_weakness}

            DERİNLEMESİNE ANALİZ:
            • Rakip savunma zaafları: merkez, bek arkası, duran top savunması, yavaş geri dönüş.
            • Bizim hücumcuların güçlü yönleri: şut, çalım, asist verisine dayalı rol.
            • Koridor seçimi: kanat iç/dış, merkez kombinasyon, cut-back bölgesi.
            • Net "gol senaryosu": en az 4–6 adımlık set (kim başlatır, kim bitirir).
            • Plan B: blok düşerse veya kanat kapanırsa alternatif hat.

            ÇIKTI FORMATI:

            ## Hücum Özeti
            (Ana tehdit ekseni: hangi koridor, neden)

            ## Hedef Bölge ve Senaryo A (birincil)
            (Adım adım kısa madde)

            ## Senaryo B (yedek)
            ...

            ## Öncelikli Aksiyonlar
            1. ...
            2. ...
            3. ...

            ## Bitiricilik ve Son Pas Talimatı
            (İsim veya pozisyon bazlı)

            ## Riskler
            (Örn. ofsayt tuzağı, geri üçlü hızlı çıkış)
            """
        )
        self.chain = self.prompt | self.llm | StrOutputParser()

    async def analyze(self, inputs):
        _log_llm("Hücum Koordinatörü Analizi")
        return await self.chain.ainvoke(inputs)



# 4. ALT BİRİM: DURAN TOP UZMANI

class SetPieceLLMModel:
    def __init__(self, db_client):
        self.db = db_client
        self.llm = get_langchain_model(LLMModelType.GEMINI, temperature=0.2)
        self.prompt = PromptTemplate(
            input_variables=["tallest_players", "best_passers", "situation", "tactical_knowledge"],
            template="""
            Sen UEFA Pro düzeyinde Duran Top ve Standart Faz Uzmanısın.
            GÖREV: Korner, frikik (hücum/savunma) ve ceza sahası içi duran toplarda net, tekrarlanabilir plan.

            """ + _COACH_SHARED_RULES + """

            📚 TAKTİKSEL BİLGİ TABANI:
            {tactical_knowledge}

            VERİLER:
            Hava + fizik avantajı: {tallest_players}
            Pas/kesici kalitesi: {best_passers}
            Maç anı / talimat: {situation}

            PLANLAMA:
            • Hücum korneri: birincil hedef (ön/arka direk, ceza yayı), ekran/kaçış, kısa korner ihtimali.
            • Savunma korneri: adam/bölge kararı, ön direk ve arka direk sorumluları, 2. top.
            • Frikik: direk şut adayı, orta, kısa kombinasyon; baraj sayısı ve koşu zamanlaması.
            • İletişim: sorumlu oyuncu ve "işaret" mantığı (tek kelime ile varyasyon).

            ÇIKTI FORMATI:

            ## Duran Top Özeti
            (1–3 cümle)

            ## Hücum Korneri — Set A
            (Kullanan, hedef bölge, koşu yapanlar)

            ## Hücum Korneri — Set B (alternatif)
            ...

            ## Savunma Korneri
            (Eşleşme veya bölge; 2. top)

            ## Frikik (25m içi / dışı ayrımı yap)
            ...

            ## Öncelikli Talimatlar (3 madde)
            """
        )
        self.chain = self.prompt | self.llm | StrOutputParser()

    async def analyze(self, inputs):
        _log_llm("Duran Top Uzmanı Analizi (Async)")
        return await self.chain.ainvoke(inputs)

    def analyze_sync(self, inputs):
        _log_llm("Duran Top Uzmanı Analizi (Sync)")
        return self.chain.invoke(inputs)
        """
        Senkron kullanım (örn. FastAPI BackgroundTasks içinden simülasyon üretimi).
        Not: `generate_all_simulations` senkron çalıştığı için burada invoke kullanılır.
        """
        return self.chain.invoke(inputs)



# 5. ALT BİRİM: POZİSYON VE ROL ANALİSTİ

class PlayerPositioningLLMModel:
    def __init__(self, db_client):
        self.db = db_client
        self.llm = get_langchain_model(LLMModelType.GEMINI, temperature=0.3)
        self.prompt = PromptTemplate(
            input_variables=["key_players", "formation", "tactical_knowledge"],
            template="""
            Sen UEFA Pro düzeyinde Pozisyon ve Rol Analistisin.
            GÖREV: Nominal formasyon + topa sahipken/top kaybedince şekil + oyuncu bazlı net rol kartları.

            """ + _COACH_SHARED_RULES + """

            📚 TAKTİKSEL BİLGİ TABANI:
            {tactical_knowledge}

            VERİLER:
            Formasyon / talimat: {formation}
            Kilit oyuncular: {key_players}

            ANALİZ:
            • Topa sahipken: genişlik, derinlik, iç koridor oyuncusu, false 9 / pivot ihtiyacı.
            • Top kaybedince: ilk baskı çizgisi, beklerin geri dönüşü, orta blok kompaktlığı.
            • 18 bölge: en az iki kilit oyuncu için "ağırlık bölgesi" (ör. sol iç koridor, ceza yayı).
            • Maç içi esneklik: kim kanada genişler, kim merkezi doldurur.
            • Sakatlık / düşük forma verisi varsa dikkat çek (oyuncu değişikliği tetikleyicisi olarak).

            ÇIKTI FORMATI:

            ## Şekil Özeti
            (Nominal + topa göre kısa tanım)

            ## Rol Kartları
            (Her satır: Oyuncu/pozisyon — topla — topsuz — uyarı)

            ## Bek / Kanat Direktifleri
            ...

            ## Öncelikli 3 Kural
            (Saha kenarından bağırılacak kadar net)

            ## Olası Oyuncu Değişikliği Tetikleyicileri
            (Veriye dayalı; spekülasyon değil)
            """
        )
        self.chain = self.prompt | self.llm | StrOutputParser()

    async def analyze(self, inputs):
        _log_llm("Pozisyon ve Rol Analiz")
        return await self.chain.ainvoke(inputs)



# BAĞIMSIZ BİRİMLER 

class MatchPreparationLLMModel:
    def __init__(self, db_client=None): 
        self.llm = get_langchain_model(LLMModelType.GEMINI, temperature=0.45)
        self.prompt = PromptTemplate(
            input_variables=["context", "tactical_knowledge"],
            template="""Sen UEFA Pro düzeyinde Maç Günü Hazırlık Koordinatörüsün.

""" + _COACH_SHARED_RULES + """

📚 TAKTİKSEL BİLGİ TABANI:
{tactical_knowledge}

BAĞLAM (takım, rol, TD notu): {context}

HEDEF: Oyuncuların zihinsel netlik, fiziksel hazır ve taktiksel odakla sahaya çıkması.

ÇIKTI FORMATI:

## Maç Günü Özeti
## Mental Hazırlık (brifing maddeleri, 5–7 dk konuşma iskeleti)
## Taktik Hatırlatıcılar (3 ana kural, tekrar yok)
## Isınma / Aktivasyon (dakika bazlı örnek akış: genel → dinamik → pas/rondo → hız)
## Kritik Uyarılar (disiplin, set parça, ilk 15 dk)
## Son Kontrol Listesi (kadro, forma, iletişim)
""",
        )
        self.chain = self.prompt | self.llm | StrOutputParser()

class TrainingDrillLLMModel:
    def __init__(self, db_client=None):
        self.llm = get_langchain_model(LLMModelType.GEMINI, temperature=0.45)
        self.prompt = PromptTemplate(
            input_variables=["context", "tactical_knowledge"],
            template="""Sen UEFA Pro düzeyinde Antrenman Planlama Uzmanısın.

""" + _COACH_SHARED_RULES + """

📚 TAKTİKSEL BİLGİ TABANI:
{tactical_knowledge}

BAĞLAM (odak, formasyon): {context}

Morfosiklus çerçevesi: MD+1 toparlanma → MD+2 analiz/aktivasyon → MD-3 ana yük → MD-2 form & set → MD-1 aktivasyon.

ÇIKTI FORMATI:

## Haftalık Özet (hedef ve yük felsefesi)
## Günlük Plan Tablosu
| Gün | Odak | Örnek drill (kısa) | Süre | Yoğunluk (düşük/orta/yüksek) |
## MD-3 Ana Seans (detay: alan, oyuncu sayısı, koçluk noktaları)
## MD-1 Aktivasyon (kısa, net)
## Regenerasyon / Sakatlık notu (varsa bağlamdan çıkar)
""",
        )
        self.chain = self.prompt | self.llm | StrOutputParser()



# ANA YÖNETİCİ: TEKNİK DİREKTÖR (HEAD COACH)

class HeadCoachAI:
    def __init__(self):
        # Redis Ayarları
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis_db = int(os.getenv("REDIS_DB", 0))
        self.queue_name = "head_coach_queue"
        
        # DB Bağlantısı (Tüm alt birimlere dağıtılacak)
        self.db = fetchDBdataClient()
        
        # TEKNİK EKİP
        self.defender_ai = DefenderLLMModel(self.db)
        self.midfielder_ai = MidfielderLLMModel(self.db)
        self.attacker_ai = AttackerLLMModel(self.db)
        self.set_piece_ai = SetPieceLLMModel(self.db)
        self.positioning_ai = PlayerPositioningLLMModel(self.db)
        
        # Head Coach Beyni
        self.master_llm = get_langchain_model(LLMModelType.GEMINI, temperature=0.4)
        
        # SENTEZ PROMPT'U
        self.master_prompt = PromptTemplate(
            input_variables=["def_report", "mid_report", "att_report", "set_report", "pos_report", "match_title", "tactical_knowledge"],
            template="""
            Sen {match_title} maçının TEKNİK DİREKTÖRÜSÜN.
            Teknik ekibin 5 uzman raporu + taktik dokümanından gelen bilgi tabanı elinde.

            """ + _MASTER_SYNTHESIS_RULES + """

            📚 TAKTİKSEL BİLGİ TABANI (özet referans):
            {tactical_knowledge}

            📥 [RAPOR 1 — SAVUNMA]: {def_report}
            📥 [RAPOR 2 — ORTA SAHA]: {mid_report}
            📥 [RAPOR 3 — HÜCUM]: {att_report}
            📥 [RAPOR 4 — DURAN TOP]: {set_report}
            📥 [RAPOR 5 — POZİSYON / ROL]: {pos_report}

            ÖNCE: Alt raporlar arasında çelişki var mı kontrol et (ör. çok yüksek hat vs derin blok).
            Varsa tek paragrafta nasıl dengelediğini yaz.

            -------------------------------------------------------------
            📋 NİHAİ MAÇ PLANI — ÇIKTI FORMATI (başlıkları aynen kullan):

            ## 1. Kırmızı Hat (Ana Fikir)
            (4–6 cümle: kazanmak için tek cümlelik oyun felsefesi + nasıl kazanırız)

            ## 2. Oyun Mentalitesi ve Tempo
            (Topa sahip olma / geçiş / blok; ne zaman hızlan, ne zaman yavaşlat)

            ## 3. Dört Evre — Taktiksel Kurgu
            ### 3.1 Hücum organizasyonu
            ### 3.2 Savunma organizasyonu
            ### 3.3 Hücuma geçiş (top kazanımı sonrası ilk 8 sn)
            ### 3.4 Savunmaya geçiş (top kaybı sonrası ilk 8 sn)

            ## 4. Metrik ve Gözlem Hedefleri
            (xG kalitesi, şut bölgeleri, PPDA/pressing yoğunluğu, alan hakimiyeti — sayı uydurma;
             "izleyeceğimiz sinyal" olarak ifade et: örn. "rakip kalecisine geri paslarda baskı")

            ## 5. Kritik Görevler ve Oyuncu Rolleri
            (İsimleri alt raporlardan al; 3–5 net madde)

            ## 6. Duran Top — Birincil Silahlar
            (Hücum + savunma; bir cümlede ana set)

            ## 7. Maç İçi Yönetim
            ### 7.1 Önde / Beraber / Geride — Plan B özeti
            ### 7.2 Oyuncu değişikliği tetikleyicileri (yorgunluk, sarı kart, taktik kilit)
            ### 7.3 Son 15 dakika özel notu

            ## 8. Teknik Direktörün Son Sözü
            (Kısa, net, takımı odaklayan 2–3 cümle)
            """
        )
        self.chain = self.master_prompt | self.master_llm | StrOutputParser()

    async def run_worker(self):
        """Sürekli çalışan dinleyici"""
        r = await redis.Redis(host=self.redis_host, port=self.redis_port, db=self.redis_db, decode_responses=True)
        print(f"👔 [HeadCoach] Sahaya İndi. Kuyruk: {self.queue_name}")

        while True:
            try:
                task_raw = await r.blpop(self.queue_name, timeout=0)
                if not task_raw: continue

                _, data_str = task_raw
                task_data = json.loads(data_str)
                task_id = task_data.get("task_id")
                
                print(f"📋 [HeadCoach] Dosya İnceleniyor ID: {task_id}")
                
                result = await self.process_holistic_strategy(task_data)

                # Yanıtı Redis'e Yaz
                result_key = f"response:{task_id}"
                response_payload = {
                    "task_id": task_id,
                    "worker": "HeadCoach_AI",
                    "result": result
                }
                
                await r.rpush(result_key, json.dumps(response_payload))
                await r.expire(result_key, 600)
                print(f"✅ [HeadCoach] Taktik Hazır ID: {task_id}")

            except Exception as e:
                print(f"❌ HeadCoach Hatası: {str(e)}")
                await asyncio.sleep(1)

    async def process_holistic_strategy(self, task_data):
        """
        TEK BİR LLM ÇAĞRISI ile tüm teknik ekip analizini ve ana planı üretir (Maksimum Verimlilik).
        Eski 6-isteklik (5 uzman + 1 sentez) yapıdan tek istekli yapıya geçildi.
        """
        params = task_data.get("params", {})
        home_id = params.get("home_id")
        away_id = params.get("away_id")
        my_team_id = params.get("my_team_id")
        coach_note = params.get("coach_instruction")
        coach_context_str = (
            f"\n⚠️ TEKNİK DİREKTÖR ÖZEL TALİMATI: {coach_note}" if coach_note else ""
        )

        home_form = self.db.fetch_team_formation(home_id) or "Bilinmiyor"
        away_form = self.db.fetch_team_formation(away_id) or "Bilinmiyor"

        if str(my_team_id) == str(home_id):
            my_role, opp_role = "Ev Sahibi", "Deplasman"
            my_tid, opp_tid = home_id, away_id
            my_form_str, opp_form_str = str(home_form), str(away_form)
        else:
            my_role, opp_role = "Deplasman", "Ev Sahibi"
            my_tid, opp_tid = away_id, home_id
            my_form_str, opp_form_str = str(away_form), str(home_form)

        # Veri Toplama (Tüm hatlar için tek seferde)
        str_my_gk_def = _format_goalkeepers_and_defenders(self.db, my_tid)
        opp_atts = self.db.fetch_player_statistics_by_positions(opp_tid, [_POS_ATT])
        str_opp_atts = format_stats_for_llm(opp_atts)

        my_mids = self.db.fetch_player_statistics_by_positions(my_tid, [_POS_MID])
        opp_mids = self.db.fetch_player_statistics_by_positions(opp_tid, [_POS_MID])
        str_my_mids = format_stats_for_llm(my_mids)
        str_opp_mids = format_stats_for_llm(opp_mids)

        my_atts = self.db.fetch_player_statistics_by_positions(my_tid, [_POS_ATT])
        opp_defs_only = self.db.fetch_player_statistics_by_positions(opp_tid, [_POS_DEF])
        str_my_atts = format_stats_for_llm(my_atts)
        str_opp_defs = format_stats_for_llm(opp_defs_only)

        tall_players, mids_for_set = _set_piece_tall_and_mids(self.db, my_tid)
        str_tall = format_stats_for_llm(tall_players) if tall_players else "Veri yok"
        str_set_mids = format_stats_for_llm(mids_for_set)

        str_key_outfield = _format_key_players_outfield(self.db, my_tid)

        print(f"👔 [HeadCoach] Bütünsel Analiz Başlatılıyor (Tek İstek Modu)...")
        rag_ctx = retrieve_context("taktiksel analiz derin blok pres hücum setleri", top_k=6) or "Veri yok."

        # BİRLEŞİK PROMPT
        unified_prompt = PromptTemplate(
            input_variables=["data"],
            template="""
            Sen UEFA Pro Lisanslı bir Teknik Direktör ve Taktik Dehasısın.
            Görevin: Elindeki oyuncu verilerini, formasyonları ve bilgi tabanını kullanarak 
            tek bir analiz ile eksiksiz bir maç planı hazırlamak.

            MAÇ BİLGİSİ: {match_title}
            BİZİM ROLÜMÜZ: {my_role} | DİZİLİŞ: {my_form}
            RAKİP ROLÜ: {opp_role} | DİZİLİŞ: {opp_form}
            {coach_note}

            --- OYUNCU VE TAKTIKSEL VERILER ---
            1. SAVUNMA & RAKİP HÜCUM:
               Bizim Gk+Def: {str_my_gk_def}
               Rakip Hücumlar: {str_opp_atts}

            2. ORTA SAHA GÜCÜ:
               Bizim Mids: {str_my_mids}
               Rakip Mids: {str_opp_mids}

            3. BİZİM HÜCUM & RAKİP SAVUNMA:
               Bizim Hücumlar: {str_my_atts}
               Rakip Savunma: {str_opp_defs}

            4. DURAN TOP VERİLERİ (Fiziksel Güç / Pasör):
               Uzunlar: {str_tall}
               Pasörler: {str_set_mids}

            5. KİLİT OYUNCULAR (Tüm Sahada):
               {str_key_outfield}

            📚 TAKTİKSEL REFERANSLAR:
            {tactical_knowledge}

            --- GÖREV ---
            Tek bir teknik direktör zihniyle (Savunma, Orta Saha, Hücum ve Duran Top uzmanlıklarını sentezleyerek) 
            aşağıdaki başlıklarla tam bir analiz metni üret:

            ## 1. Kırmızı Hat (Ana Fikir)
            ## 2. Oyun Mentalitesi ve Tempo
            ## 3. Dört Evre — Taktiksel Kurgu (Hücum, Savunma, Geçişler)
            ## 4. Metrik ve Gözlem Hedefleri
            ## 5. Kritik Görevler ve Oyuncu Rolleri
            ## 6. Duran Top Planı
            ## 7. Maç İçi Yönetim (Plan B, Değişiklikler)
            ## 8. Teknik Direktörün Son Sözü

            Açıklamaların net, futbol literatürüne uygun ve profesyonel olsun.
            """,
        )

        chain = unified_prompt | self.master_llm | StrOutputParser()
        
        _log_llm("Head Coach - Bütünsel Maç Planı Sentezi")
        final_output = await chain.ainvoke({
            "match_title": f"{my_role} ({my_tid}) vs {opp_role} ({opp_tid})",
            "my_role": my_role,
            "opp_role": opp_role,
            "my_form": my_form_str,
            "opp_form": opp_form_str,
            "coach_note": coach_context_str,
            "str_my_gk_def": str_my_gk_def,
            "str_opp_atts": str_opp_atts,
            "str_my_mids": str_my_mids,
            "str_opp_mids": str_opp_mids,
            "str_my_atts": str_my_atts,
            "str_opp_defs": str_opp_defs,
            "str_tall": str_tall,
            "str_set_mids": str_set_mids,
            "str_key_outfield": str_key_outfield,
            "tactical_knowledge": rag_ctx,
            "data": "input" # necessary as input_variables includes it
        })

        return final_output
        
class TacticalAIHub:
    def __init__(self):
        # Redis Ayarları
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis_db = int(os.getenv("REDIS_DB", 0))
        
        # Dinlenecek Kuyruklar (HeadCoach hariç diğerleri)
        self.queues = [
            "defense_tactic_queue",
            "offense_tactic_queue",
            "player_positioning_queue",
            "set_piece_queue",
            "match_preparation_queue",
            "training_drill_queue"
        ]
        
        # DB Bağlantısı
        self.db = fetchDBdataClient()
        
        # TEKNİK ALT BİRİMLER (Modeller)
        self.defender_ai = DefenderLLMModel(self.db)
        self.midfielder_ai = MidfielderLLMModel(self.db) 
        self.attacker_ai = AttackerLLMModel(self.db)
        self.set_piece_ai = SetPieceLLMModel(self.db)
        self.positioning_ai = PlayerPositioningLLMModel(self.db)
        self.match_prep_ai = MatchPreparationLLMModel(self.db)
        self.training_ai = TrainingDrillLLMModel(self.db)

    async def run_worker(self):
        """Birden fazla kuyruğu aynı anda dinler"""
        r = await redis.Redis(host=self.redis_host, port=self.redis_port, db=self.redis_db, decode_responses=True)
        print(f"📡 [TacticalHub] Özel Görevler İçin Dinlemede: {len(self.queues)} adet kuyruk.")

        while True:
            try:
                # blpop listeye verilen tüm kuyrukları sırayla kontrol eder
                # queue_name: Hangi kuyruktan geldiği
                # data_str: Gelen veri
                task_raw = await r.blpop(self.queues, timeout=0)
                if not task_raw: continue

                queue_name, data_str = task_raw
                task_data = json.loads(data_str)
                task_id = task_data.get("task_id")
                task_type = task_data.get("task_type") # Enum değeri buradan gelecek

                print(f"⚡ [TacticalHub] Yeni Görev: {task_type} (ID: {task_id})")
                
                # İşlemi yap
                result = await self.route_task(task_type, task_data)

                # Sonucu Redis'e Yaz
                result_key = f"response:{task_id}"
                response_payload = {
                    "task_id": task_id,
                    "worker": "TacticalAIHub",
                    "task_type": task_type,
                    "result": result
                }
                
                await r.rpush(result_key, json.dumps(response_payload))
                await r.expire(result_key, 600)
                print(f"✅ [TacticalHub] Görev Tamamlandı: {task_type}")

            except Exception as e:
                print(f"❌ Hub Hatası: {str(e)}")
                await asyncio.sleep(1)

# llm_models.py içindeki TacticalAIHub sınıfının route_task fonksiyonu

    async def route_task(self, task_type, task_data):
        """Gelen task_type'a göre ilgili LLM modelini çağırır + RAG bağlamını enjekte eder."""
        params = task_data.get('params', {})
        
        home_id = params.get('home_id')
        away_id = params.get('away_id')
        my_team_id = params.get('my_team_id')
        
        coach_note = params.get('coach_instruction')
        coach_context_str = f"\n⚠️ TEKNİK DİREKTÖR ÖZEL TALİMATI: {coach_note}" if coach_note else ""

        if str(my_team_id) == str(home_id):
            my_tid, opp_tid = home_id, away_id
            my_role, opp_role = "Ev Sahibi", "Deplasman"
        else:
            my_tid, opp_tid = away_id, home_id
            my_role, opp_role = "Deplasman", "Ev Sahibi"

        my_form_str = str(self.db.fetch_team_formation(my_tid) or "Bilinmiyor")
        opp_form_str = str(self.db.fetch_team_formation(opp_tid) or "Bilinmiyor")

        # --- RAG: görev tipine özel taktik bilgisi ---
        rag_search_map = {
            LLMAnswerStatus.DEFENSE_TACTIC_SUGGESTION.value:
                "savunma organizasyonu pressing hat savunma markaj PPDA geçiş",
            LLMAnswerStatus.OFFENSE_TACTIC_SUGGESTION.value:
                "hücum organizasyonu gol yolları kanat şut xG pozisyon",
            LLMAnswerStatus.SET_PIECE_SUGGESTION.value:
                "duran top korner frikik penaltı taç stratejisi",
            LLMAnswerStatus.PLAYER_POSITIONING_SUGGESTION.value:
                "formasyon pozisyonlama oyuncu rolleri alan kullanımı",
            LLMAnswerStatus.MATCH_PREPARATION_SUGGESTION.value:
                "maç hazırlığı mental hazırlık taktiksel brifing ısınma",
            LLMAnswerStatus.TRAINING_DRILL_SUGGESTION.value:
                "antrenman idman morfosiklus periyotlama haftalık yük",
        }
        rag_query = rag_search_map.get(task_type, "taktiksel analiz strateji")
        print(f"  📚 [TacticalHub] RAG aranıyor: '{rag_query[:50]}...'")
        rag_ctx = retrieve_context(rag_query, top_k=5)
        if not rag_ctx:
            rag_ctx = "Taktiksel bilgi tabanı henüz yüklenmemiş."

        # --- YÖNLENDİRME MANTIĞI ---
        
        if task_type == LLMAnswerStatus.DEFENSE_TACTIC_SUGGESTION.value:
            str_my_gk_def = _format_goalkeepers_and_defenders(self.db, my_tid)
            opp_atts = self.db.fetch_player_statistics_by_positions(opp_tid, [_POS_ATT])
            return await self.defender_ai.analyze({
                "opp_attackers": format_stats_for_llm(opp_atts),
                "my_defenders": str_my_gk_def,
                "opp_form": f"{opp_form_str} {coach_context_str}",
                "my_form": my_form_str,
                "tactical_knowledge": rag_ctx,
            })

        elif task_type == LLMAnswerStatus.OFFENSE_TACTIC_SUGGESTION.value:
            my_atts = self.db.fetch_player_statistics_by_positions(my_tid, [_POS_ATT])
            opp_defs = self.db.fetch_player_statistics_by_positions(opp_tid, [_POS_DEF])
            return await self.attacker_ai.analyze({
                "opp_defenders": format_stats_for_llm(opp_defs),
                "my_attackers": format_stats_for_llm(my_atts),
                "opp_weakness": f"Rakip Formasyonu: {opp_form_str}. {coach_context_str}",
                "tactical_knowledge": rag_ctx,
            })

        elif task_type == LLMAnswerStatus.SET_PIECE_SUGGESTION.value:
            tall_players, mids_for_set = _set_piece_tall_and_mids(self.db, my_tid)
            return await self.set_piece_ai.analyze({
                "tallest_players": format_stats_for_llm(tall_players)
                if tall_players
                else "Uzun oyuncu verisi yok",
                "best_passers": format_stats_for_llm(mids_for_set),
                "situation": f"Kritik Maç Anı. {coach_context_str}",
                "tactical_knowledge": rag_ctx,
            })

        elif task_type == LLMAnswerStatus.PLAYER_POSITIONING_SUGGESTION.value:
            str_key = _format_key_players_outfield(self.db, my_tid)
            return await self.positioning_ai.analyze({
                "key_players": str_key,
                "formation": f"{my_form_str} {coach_context_str}",
                "tactical_knowledge": rag_ctx,
            })

        elif task_type == LLMAnswerStatus.MATCH_PREPARATION_SUGGESTION.value:
            context = f"Biz: {my_role}, Rakip: {opp_role}. {coach_context_str}"
            _log_llm("Maç Hazırlık Uzmanı Analizi")
            return await self.match_prep_ai.chain.ainvoke({
                "context": context,
                "tactical_knowledge": rag_ctx,
            })

        elif task_type == LLMAnswerStatus.TRAINING_DRILL_SUGGESTION.value:
            focus_area = coach_note if coach_note else "Genel Taktik ve Kondisyon"
            _log_llm("Antrenman Drili Önerisi")
            return await self.training_ai.chain.ainvoke({
                "context": f"Odak Alanı: {focus_area}, Takım Formasyonu: {my_form_str}",
                "tactical_knowledge": rag_ctx,
            })

        else:
            return "❌ Tanımlanamayan görev türü."


# ─── STANDALONE TAKTİKSEL RAG SORGU ───────────────────────────────────────────
# Eski rag_query_engine.py'nin tüm işlevselliği burada tek fonksiyonda.
# Kullanım:
#   - API: POST /rag/query  →  tactical_rag_query("Pressing yoğunluğu nasıl ayarlanır?")
#   - CLI: python llm_models.py --rag-query "PPDA nedir?"

METRIC_GLOSSARY = {
    "xG":         "Expected Goals — Şutun gol olma istatistiksel olasılığı (0–1)",
    "PPDA":       "Passes Per Defensive Action — Düşük = yoğun pressing",
    "Field Tilt": "Rakip yarısındaki pas payı (%)",
    "BDP":        "Ball Dominant Period — Topla üstün geçilen süre",
    "xI":         "Expected Impact — Oyuncu kararlarının takım performansına beklenen katkısı",
}

MORFOCYCLE = {
    "MD+1": {"focus": "Aktif Toparlanma",              "intensity": "Çok Düşük"},
    "MD+2": {"focus": "Taktiksel Analiz & Aktivasyon",  "intensity": "Düşük-Orta"},
    "MD-3": {"focus": "Taktiksel Hazırlık (Ana Yük)",   "intensity": "Yüksek"},
    "MD-2": {"focus": "Form & Duran Top",               "intensity": "Orta"},
    "MD-1": {"focus": "Aktivasyon & Mental Hazırlık",    "intensity": "Çok Düşük"},
}

_STANDALONE_PROMPT = PromptTemplate(
    input_variables=["query", "context", "extras"],
    template="""Sen UEFA Pro düzeyinde taktik danışmansın; yanıtların bilgi tabanına dayanır.

SORU: {query}

📚 TAKTİKSEL BİLGİ TABANI:
{context}

📐 EK REFERANS (metrik / morfo günü):
{extras}

KURALLAR:
1. Önce bilgi tabanında geçen ifadelerle yanıtla; tabanda yoksa açıkça "Bu bilgi dokümanımda yer almıyor." de.
2. Metrikleri (xG, PPDA, Field Tilt, BDP, xI) yorumlarken tanım + pratik eşik/yorum birlikte ver; uydurma rakam kullanma.
3. Dört evre dilini kullan: Hücum Org., Savunma Org., Hücuma Geçiş, Savunmaya Geçiş.
4. Antrenman sorusunda MD+1 … MD-1 çerçevesini ve yük felsefesini bağla.
5. Çıktı formatı:

## Özet
## Analiz (bilgi tabanına atıf)
## Uygulanabilir Öneriler (numaralı 3+ madde)
## Dikkat / Sınırlar

Türkçe, net, koçluk dilinde yaz."""
)


def tactical_rag_query(question: str, verbose: bool = False) -> str:
    """
    Standalone taktiksel soru-cevap.
    Doğrudan bilgi tabanından (RAG) yanıt üretir.
    Oyuncu verisi gerektirmeyen genel taktik soruları için kullanılır.
    """
    print(f"\n🔍 RAG Sorgu: [{question[:60]}...]", flush=True)

    context = retrieve_context(question, top_k=6)

    if not context.strip():
        return (
            "⚠️ Bilgi tabanında ilgili içerik bulunamadı.\n"
            "Önce `python rag_ingest.py` komutuyla dokümanları indeksleyin."
        )

    extras_parts = []
    q_lower = question.lower()
    for name, desc in METRIC_GLOSSARY.items():
        if name.lower() in q_lower:
            extras_parts.append(f"• {name}: {desc}")
    for day, info in MORFOCYCLE.items():
        if day.lower().replace("+", "").replace("-", "") in q_lower.replace("+", "").replace("-", ""):
            extras_parts.append(f"• {day}: {info['focus']} (Yoğunluk: {info['intensity']})")
    if "antrenman" in q_lower or "idman" in q_lower or "morfosiklus" in q_lower:
        for day, info in MORFOCYCLE.items():
            extras_parts.append(f"• {day}: {info['focus']} | {info['intensity']}")

    extras = "\n".join(extras_parts) if extras_parts else "Ek bilgi yok."

    if verbose:
        print(f"  📚 RAG bağlamı: {len(context)} karakter")
        print(f"  📐 Ek bilgi: {len(extras_parts)} madde")

    llm   = get_langchain_model(LLMModelType.GEMINI, temperature=0.3)
    chain = _STANDALONE_PROMPT | llm | StrOutputParser()
    _log_llm(f"Standalone RAG Sorgusu: {question[:30]}...")
    answer = chain.invoke({"query": question, "context": context, "extras": extras})

    return answer


# ─── TAKTİK SİMÜLASYON JENERATÖRÜ ────────────────────────────────────────────

import re
import time as _time

_SIM_TYPES = [
    (
        "attack_organization",
        "Hücum Organizasyonu",
        "Takımın arka çizgiden başlayarak organize hücum kurgusu. "
        "Topu savunmadan orta sahaya, kanat değişikliği ve son pas aşamasına taşı.",
    ),
    (
        "defense_organization",
        "Savunma Organizasyonu",
        "Rakibin top taşımasına karşı blok savunma dizilişi. "
        "Takım kompakt kalır, oyuncular arası mesafe dar tutulur, pressing tetikleyicisi göster.",
    ),
    (
        "counter_attack",
        "Kontra Atak — Gol Pozisyonu",
        "Top kazanımı sonrası hızlı geçiş: topu kazanan oyuncu ileri pası atar, "
        "kanat oyuncuları derinlik oluşturur, orta forvet bitirici pozisyona gelir.",
    ),
    (
        "set_piece_attack",
        "Duran Top Hücum (Korner / Frikik)",
        "Korner veya frikik organizasyonu: kısa-uzun opsiyon, perdeleme hareketi, "
        "uzun oyuncular yakın direğe, ikinci direk ve penaltı noktasına konum al.",
    ),
    (
        "set_piece_defense",
        "Duran Top Savunma",
        "Rakip korneri / frikiki savunması: adam adam + bölge hibrit, "
        "yakın direk savunucusu, ikinci direk koruyucu, kontra atak çıkış oyuncusu.",
    ),
]

_SIM_SCENARIO_PROMPT = PromptTemplate(
    input_variables=["coach_report", "match_title", "tactical_knowledge", "match_descriptor"],
    template="""Sen UEFA Pro düzeyinde bir teknik direktör yardımcısısın.
Elindeki HEAD COACH maç planını ve taktik bilgi tabanını kullanarak simülasyon motoru için
her sim türüne özel, maç-özel "scenario" metinleri üret.

ÇIKTI: SADECE geçerli bir JSON obje döndür. Açıklama, markdown veya başka metin YAZMA.

Kurallar:
- Her alan 2–5 kısa cümle. Somut, uygulanabilir aksiyonlar.
- Senaryolarda takım adlarını ve "bizim / rakip" ayrımını açıkça kullan (aşağıdaki TAKIM/ROL satırına uy).
- defense_organization ve counter_attack'ta mümkünse hangi hattın kimi markajlayacağını veya bölgeyi yaz.
- Eğer raporda net bilgi yoksa genel geçer cümle yazma; mevcut rapordan çıkarım yap.

Girdi:
MAÇ: {match_title}
TAKIMLAR / ROL: {match_descriptor}
TAKTİKSEL BİLGİ TABANI (özet): {tactical_knowledge}
HEAD COACH RAPORU:
{coach_report}

JSON şeması (anahtarları aynen kullan):
{{
  "attack_organization": "...",
  "defense_organization": "...",
  "counter_attack": "...",
  "set_piece_attack": "...",
  "set_piece_defense": "..."
}}
""",
)

_SIM_PROMPT = PromptTemplate(
    input_variables=[
        "sim_type_tr",
        "sim_type_key",
        "count",
        "scenario",
        "my_formation",
        "opp_formation",
        "match_descriptor",
        "matchup_instructions",
        "coach_context",
    ],
    template="""Sen bir futbol taktik simülasyon motorusun.
Görev: "{sim_type_tr}" için tam {count} adet farklı taktiksel varyasyon üret.
Her varyasyon oyuncu hareketlerini zaman kareleri (frames) olarak içermeli.

ÇIKTI: SADECE geçerli bir JSON dizisi döndür. Açıklama, markdown veya başka metin YAZMA.

Format:
[
  {{
    "title": "Varyasyon Başlığı",
    "description": "Taktiksel mantığın kısa (1 cümle) açıklaması",
    "sim_type": "{sim_type_key}",
    "frames": [
      {{
        "timestamp": 0,
        "ball": [x, y],
        "ball_owner": "h7",
        "positions": {{
          "h1": [x, y], ..., "h11": [x, y],
          "a1": [x, y], ..., "a11": [x, y]
        }}
      }},
      ... (6-8 kare üret)
    ]
  }},
  ... (toplam {count} tane bu objeden)
]

KOORDİNAT KURALLARI:
- (0,0) = sol üst köşe, (1,1) = sağ alt köşe
- Bizim takım (h) sol yarı sahada başlar, sağa hücum eder (h1 kaleci ≈ [0.04, 0.5])
- Rakip takım (a) sağ yarı sahada başlar (a1 kaleci ≈ [0.96, 0.5])
- Her varyasyon birbirinden taktiksel olarak farklı olmalı (farklı pas koridorları, farklı markaj hataları vb.)
- Frames için timestamp: 0, 800, 1600, ... 5600ms arası.

MAÇ VE TAKIMLAR:
{match_descriptor}

EŞLEŞME / TAKTİKSEL ANALİZ (bu bağlamla tutarlı varyasyonlar üret):
{matchup_instructions}

FORMASYON: Biz {my_formation} — Rakip {opp_formation}

SENARYO / EK BAĞLAM:
{scenario}

ANALİZ RAPORU ÖZETİ:
{coach_context}

Şimdi sadece JSON dizisini döndür:""",
)

_BATCH_SIM_PROMPT = _SIM_PROMPT

def _extract_json_array(text: str):
    text = text.strip()
    if text.startswith("```"):
        m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
        if m:
            text = m.group(1)
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
        if isinstance(arr, list):
            return arr
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _validate_sim_frames(arr) -> list | None:
    if not isinstance(arr, list) or len(arr) < 2:
        return None
    valid = []
    for frame in arr:
        if not isinstance(frame, dict):
            continue
        ts = frame.get("timestamp")
        pos = frame.get("positions")
        ball = frame.get("ball")
        ball_owner = frame.get("ball_owner")
        if ts is None or not isinstance(pos, dict):
            continue
        if not (isinstance(ball, list) and len(ball) == 2):
            continue
        clean_pos = {}
        for k, v in pos.items():
            if isinstance(v, list) and len(v) == 2:
                try:
                    clean_pos[k] = [float(v[0]), float(v[1])]
                except (TypeError, ValueError):
                    continue
        try:
            clean_ball = [float(ball[0]), float(ball[1])]
        except (TypeError, ValueError):
            continue
        clean_owner = ball_owner if isinstance(ball_owner, str) else None
        if len(clean_pos) >= 10:
            valid.append(
                {"timestamp": int(ts), "positions": clean_pos, "ball": clean_ball, "ball_owner": clean_owner}
            )
    return valid if len(valid) >= 2 else None


def generate_batch_simulations(
    sim_type: str,
    count: int,
    my_formation: str,
    opp_formation: str,
    match_descriptor: str,
    matchup_instructions: str,
    coach_context: str,
    scenario_base: str = ""
) -> list[dict]:
    """Birden fazla simülasyonu TEK bir LLM çağrısı ile üretir (Rate limit dostu)."""
    titles = {
        "attack_organization": "Hücum Organizasyonu",
        "defense_organization": "Savunma Organizasyonu",
        "counter_attack": "Kontra Atak",
        "set_piece_attack": "Duran Top (Hücum)",
        "set_piece_defense": "Duran Top (Savunma)",
        "all": "Genel Taktik"
    }
    t_name = titles.get(sim_type, "Taktiksel Varyasyon")
    
    print(f"  🎬 [{sim_type}] {count} adet simülasyon BATCH üretiliyor...")
    llm = get_langchain_model(LLMModelType.GEMINI, temperature=0.3)
    chain = _BATCH_SIM_PROMPT | llm | StrOutputParser()
    
    _log_llm(f"Simülasyon Üretimi (Batch) - Tip: {sim_type}, Adet: {count}")
    try:
        raw = chain.invoke({
            "sim_type_tr": t_name,
            "sim_type_key": sim_type,
            "count": count,
            "scenario": scenario_base,
            "my_formation": my_formation or "4-4-2",
            "opp_formation": opp_formation or "4-4-2",
            "match_descriptor": match_descriptor or "",
            "matchup_instructions": (matchup_instructions or "")[:5200],
            "coach_context": (coach_context or "")[:2000],
        })
    except Exception as e:
        print(f"  ❌ [{sim_type}] BATCH LLM hatası: {e}")
        return []

    try:
        data = _extract_json_array(raw)
        if not isinstance(data, list):
            # Eğer doğrudan frames listesi döndüyse (hata/eski format)
            frames = _validate_sim_frames(data)
            if frames:
                return [{"title": t_name, "description": "", "sim_type": sim_type, "frames": frames}]
            return []
        
        results = []
        for item in data:
            if not isinstance(item, dict): continue
            f_frames = _validate_sim_frames(item.get("frames"))
            if f_frames:
                results.append({
                    "title": item.get("title") or t_name,
                    "description": item.get("description") or "",
                    "sim_type": item.get("sim_type") or sim_type,
                    "frames": f_frames
                })
        return results
    except Exception as e:
        print(f"  ⚠️ [{sim_type}] BATCH JSON işleme hatası: {e}")
        return []


def generate_single_simulation(
    sim_type: str,
    title: str,
    scenario: str,
    my_formation: str,
    opp_formation: str,
    match_descriptor: str,
    matchup_instructions: str,
    coach_context: str,
) -> dict | None:
    """Tekli simülasyon üretmek için batch fonksiyonunu 1 adet ile çağırır."""
    res = generate_batch_simulations(
        sim_type, 1, my_formation, opp_formation, 
        match_descriptor, matchup_instructions, coach_context, scenario
    )
    return res[0] if res else None


def generate_custom_simulations_task(sim_params: dict, coach_report: str = "") -> list[dict]:
    from api_client import fetchDBdataClient
    from database import SessionLocal
    from model import Team

    my_team_id = sim_params.get("my_team_id")
    home_id = sim_params.get("home_id")
    away_id = sim_params.get("away_id")
    opp_id = away_id if str(my_team_id) == str(home_id) else home_id
    sim_type = sim_params.get("sim_type", "attack_organization")
    count = sim_params.get("count", 1)

    def _team_label(tid):
        if tid is None: return "?"
        dbl = SessionLocal()
        try:
            tr = dbl.query(Team).filter(Team.id == tid).first()
            return (tr.name or "").strip() if tr and tr.name else f"Takım {tid}"
        finally:
            dbl.close()

    home_name = _team_label(home_id)
    away_name = _team_label(away_id)
    my_team_name = home_name if str(my_team_id) == str(home_id) else away_name
    opp_team_name = away_name if str(my_team_id) == str(home_id) else home_name

    match_descriptor = (
        f"Ev sahibi: {home_name} (home_id={home_id}) | "
        f"Deplasman: {away_name} (away_id={away_id}). "
        f"BİZİM TAKIM: {my_team_name} (my_team_id={my_team_id}) → h1–h11 bu takımdır (sol yarı, sağa hücum). "
        f"RAKİP: {opp_team_name} (opp_team_id={opp_id}) → a1–a11 bu takımdır (sağ yarı)."
    )

    db_client = fetchDBdataClient()
    my_form = db_client.fetch_team_formation(my_team_id) or "4-4-2"
    opp_form = db_client.fetch_team_formation(opp_id) or "4-4-2"

    delay = float(os.getenv("SIM_GEN_DELAY_SEC", "3"))

    titles = {
        "attack_organization": "Özel Hücum Organizasyonu",
        "defense_organization": "Özel Savunma Organizasyonu",
        "counter_attack": "Özel Kontra Atak",
        "set_piece_attack": "Özel Duran Top (Hücum)",
        "set_piece_defense": "Özel Duran Top (Savunma)",
        "all": "Genel Özel Simülasyon"
    }
    
    t_title = titles.get(sim_type, "Manuel Simülasyon")

    results = generate_batch_simulations(
        sim_type,
        count,
        my_form,
        opp_form,
        match_descriptor,
        f"Hedeflenen simülasyon türü: {sim_type}. Lütfen her varyasyonu farklı bir taktiksel çözümle (pas kanalı, topsuz koşu, pres vs.) planla."
        + (f"\n⚠️ TEKNİK DİREKTÖR ÖZEL TALİMATI: {sim_params.get('coach_instruction')}" if sim_params.get('coach_instruction') else ""),
        coach_report if coach_report else "Bu manuel bir direktiftir.",
        scenario_base=f"Kullanıcı Talebi: {t_title}"
    )

    return results

def generate_all_simulations(
    match_params: dict,
    coach_report: str,
) -> list[dict]:
    """Tüm simülasyon tiplerini sırayla üretir (rate-limit dostu)."""
    from api_client import fetchDBdataClient
    from database import SessionLocal
    from model import Team

    my_team_id = match_params.get("my_team_id")
    home_id = match_params.get("home_id")
    away_id = match_params.get("away_id")
    opp_id = away_id if str(my_team_id) == str(home_id) else home_id

    # Opsiyonel metadata (frontend -> /coach/head-coach request'inden gelebilir)
    match_date = match_params.get("match_date")  # str (ISO) veya None

    def _team_label(tid):
        if tid is None:
            return "?"
        dbl = SessionLocal()
        try:
            tr = dbl.query(Team).filter(Team.id == tid).first()
            return (tr.name or "").strip() if tr and tr.name else f"Takım {tid}"
        finally:
            dbl.close()

    home_name = _team_label(home_id)
    away_name = _team_label(away_id)
    my_team_name = home_name if str(my_team_id) == str(home_id) else away_name
    opp_team_name = away_name if str(my_team_id) == str(home_id) else home_name

    match_descriptor = (
        f"Ev sahibi: {home_name} (home_id={home_id}) | "
        f"Deplasman: {away_name} (away_id={away_id}). "
        f"BİZİM TAKIM: {my_team_name} (my_team_id={my_team_id}) → h1–h11 bu takımdır (sol yarı, sağa hücum). "
        f"RAKİP: {opp_team_name} (opp_team_id={opp_id}) → a1–a11 bu takımdır (sağ yarı)."
    )
    match_title_hint = (
        f"{home_name} (ev) vs {away_name} (dep) — Maç #{match_params.get('match_id')}"
        + (f" — {match_date}" if match_date else "")
    )

    matchup_instructions = (
        "Head coach raporuna göre bu iki takım arasındaki maçı canlandır. Genel animasyon üretme.\n"
        "- Savunma: kritik rakip hücumcusunu hangi bizim oyuncu (h*) yakın markaj/bölge ile karşılıyor; karelerde mesafeyi göster.\n"
        "- Hücum: hangi koridor/kanat ağırlıklı; top ve destek koşuları bu fikre uygun hareket etsin.\n"
        "- Kontra / duran top: raporda geçen organizasyonu sahaya yansıt.\n\n"
        f"--- Head Coach raporu (özet-kaynak) ---\n{(coach_report or '')[:4800]}"
    )
    coach_context_short = (coach_report or "")[:1000]

    db_client = fetchDBdataClient()
    my_form = db_client.fetch_team_formation(my_team_id) or "4-4-2"
    opp_form = db_client.fetch_team_formation(opp_id) or "4-4-2"

    delay = float(os.getenv("SIM_GEN_DELAY_SEC", "3"))

    # Maç-özel senaryoları HEAD COACH raporundan üret.
    # Head coach çıktısı zaten görev bazlı RAG içeriyor; burada ayrıca sim bağlamı için kısa bir RAG özet ekliyoruz.
    scenarios_by_type: dict[str, str] = {}
    try:
        rag_ctx = retrieve_context(
            "hücum organizasyonu savunma organizasyonu geçiş kontra atak duran top korner frikik",
            top_k=6,
        )
        if not rag_ctx:
            rag_ctx = "Taktiksel bilgi tabanı henüz yüklenmemiş."
        llm = get_langchain_model(LLMModelType.GEMINI, temperature=0.25)
        chain = _SIM_SCENARIO_PROMPT | llm | StrOutputParser()
        _log_llm("Maç-Özel Simülasyon Senaryosu Üretimi")
        raw = chain.invoke(
            {
                "coach_report": (coach_report or "")[:3500],
                "match_title": match_title_hint,
                "tactical_knowledge": rag_ctx[:2500],
                "match_descriptor": match_descriptor,
            }
        )
        obj = None
        try:
            obj = json.loads(raw.strip())
        except Exception:
            # bazen model JSON dışında bir şey ekler; obje yakalamayı dene
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                obj = json.loads(m.group(0))
        if isinstance(obj, dict):
            for k in ("attack_organization", "defense_organization", "counter_attack", "set_piece_attack", "set_piece_defense"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    scenarios_by_type[k] = v.strip()[:2000]
    except Exception as e:
        print(f"  ⚠️ [sim_scenarios] senaryo üretimi başarısız: {e}")

    # Duran top sim'leri için: gerçek raporu üretip "scenario" olarak kullan.
    # (Simülasyon motoru frame'leri bu senaryoya göre çıkarır.)
    set_piece_scenario = None
    try:
        tall_players, my_mids = _set_piece_tall_and_mids(db_client, my_team_id)

        rag_ctx = retrieve_context("duran top korner frikik penaltı taç stratejisi", top_k=5)
        if not rag_ctx:
            rag_ctx = "Taktiksel bilgi tabanı henüz yüklenmemiş."

        sp_ai = SetPieceLLMModel(db_client)
        set_piece_report = sp_ai.analyze_sync({
            "tallest_players": format_stats_for_llm(tall_players),
            "best_passers": format_stats_for_llm(my_mids or []),
            "situation": f"{match_title_hint}. Kritik maç anı / duran top odak. {(coach_context_short or '')[:800]}",
            "tactical_knowledge": rag_ctx,
        })
        if isinstance(set_piece_report, str) and set_piece_report.strip():
            # Sim prompt'una "scenario" olarak gidecek: kısa ve odaklı tut.
            set_piece_scenario = f"{match_title_hint}\n\n{set_piece_report.strip()}"[:2000]
    except Exception as e:
        print(f"  ⚠️ [set_piece] rapor üretilemedi: {e}")

    # Tüm simülasyonları BATCH olarak tek seferde üret (Rate limit dostu)
    print(f"🎬 Tüm taktiksel varyasyonlar ({len(_SIM_TYPES)} tip) BATCH olarak talep ediliyor...")
    
    # Her tip için senaryoyu belirle
    all_scenarios_combined = ""
    for stype, title, base_scenario in _SIM_TYPES:
        scen = scenarios_by_type.get(stype) or base_scenario
        if stype in ("set_piece_attack", "set_piece_defense") and set_piece_scenario:
            scen = set_piece_scenario
        all_scenarios_combined += f"### {title} ({stype}):\n{scen}\n\n"

    # Batch üretimi başlat
    results = generate_batch_simulations(
        sim_type="all",
        count=len(_SIM_TYPES),
        my_formation=my_form,
        opp_formation=opp_form,
        match_descriptor=match_descriptor,
        matchup_instructions=matchup_instructions,
        coach_context=coach_context_short,
        scenario_base=all_scenarios_combined
    )

    print(f"🎬 BATCH: {len(results)}/{len(_SIM_TYPES)} simülasyon tek istekte üretildi.")
    return results


# ─── WORKER BAŞLATICI ─────────────────────────────────────────────────────────

async def main():
    coach = HeadCoachAI()
    hub = TacticalAIHub()

    print("🚀 Futbol AI Sistemi Başlatılıyor...")

    await asyncio.gather(
        coach.run_worker(),
        hub.run_worker()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Workerlar durduruldu.")
