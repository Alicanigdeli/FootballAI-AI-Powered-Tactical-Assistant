"""
Hiyerarşik RAG İndeksleme Sistemi (HRAG)
=========================================
Dokümanları 3 katmanda işler:
  Seviye 1 → Belge  (Document) : Bütünsel özet + kaynak meta
  Seviye 2 → Bölüm  (Section)  : Başlık bazlı segmentler
  Seviye 3 → Olgu   (Fact)     : Küçük chunk'lar (overlap %15)

Embedding : Google Gemini API (varsayılan: gemini-embedding-001 — embedContent uyumlu)
Vector DB : ChromaDB (PersistentClient)
Etiketleme: TacticalGPT stili XML (<team>, <position>, <player>, <location>)
"""

import os
import re
import time
import random
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import chromadb

load_dotenv()

# ─── ORTAM DEĞİŞKENLERİ ───────────────────────────────────────────────────────

RAG_DOCUMENTS_PATH = os.getenv("RAG_DOCUMENTS_PATH", "./rag_docs")
CHROMA_PERSIST_DIR  = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
CHUNK_SIZE          = int(os.getenv("RAG_CHUNK_SIZE", "800"))
CHUNK_OVERLAP       = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))   # ~%15
TOP_K               = int(os.getenv("RAG_TOP_K", "6"))
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
# text-embedding-004 çoğu Gemini API anahtarında embedContent ile 404 verir; bkz. https://ai.google.dev/gemini-api/docs/embeddings
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")

# Ücretsiz kotada 429 azaltmak: küçük batch + bekleme + 429’da üstel geri deneme
RAG_EMBED_BATCH_SIZE     = max(1, int(os.getenv("RAG_EMBED_BATCH_SIZE", "4")))
RAG_EMBED_DELAY_SEC      = float(os.getenv("RAG_EMBED_DELAY_SEC", "3.0"))
RAG_EMBED_MAX_RETRIES    = int(os.getenv("RAG_EMBED_MAX_RETRIES", "12"))
RAG_EMBED_RETRY_BASE_SEC = float(os.getenv("RAG_EMBED_RETRY_BASE_SEC", "10.0"))
RAG_EMBED_RETRY_MAX_SEC  = float(os.getenv("RAG_EMBED_RETRY_MAX_SEC", "180.0"))

# ChromaDB koleksiyon isimleri (her hiyerarşi katmanı için ayrı)
COL_DOCUMENT = "tactical_documents"
COL_SECTION  = "tactical_sections"
COL_FACT     = "tactical_facts"

# ─── 18 BÖLGELİ SAHA SİSTEMİ ─────────────────────────────────────────────────
# 3 dikey üçte (Savunma / Orta / Hücum) × 6 yatay kanal = 18 bölge

FIELD_ZONES: Dict[int, str] = {
    1: "Savunma Sol Kanat",          2: "Savunma Sol İç Koridor",
    3: "Savunma Merkez Sol",         4: "Savunma Merkez Sağ",
    5: "Savunma Sağ İç Koridor",     6: "Savunma Sağ Kanat",
    7: "Orta Saha Sol Kanat",        8: "Orta Saha Sol İç",
    9: "Orta Saha Merkez Sol",       10: "Orta Saha Merkez Sağ",
    11: "Orta Saha Sağ İç",          12: "Orta Saha Sağ Kanat",
    13: "Hücum Sol Kanat",           14: "Hücum Sol Yarı-Merkez",
    15: "Hücum Merkez (Ceza Sahası)", 16: "Hücum Sağ Yarı-Merkez",
    17: "Hücum Sağ Kanat",           18: "Hücum Geniş Bölge",
}

ZONE_KEYWORDS: Dict[str, List[int]] = {
    "savunma":      [1, 2, 3, 4, 5, 6],
    "kaleci":       [3, 4],
    "orta saha":    [7, 8, 9, 10, 11, 12],
    "hücum":        [13, 14, 15, 16, 17, 18],
    "ceza sahası":  [15],
    "sol kanat":    [1, 7, 13],
    "sağ kanat":    [6, 12, 17],
    "merkez":       [3, 4, 9, 10, 15],
    "yarı alan":    [7, 8, 9, 10, 11, 12],
    "kanat":        [1, 6, 7, 12, 13, 17],
}

# ─── OYUN EVRELERİ ─────────────────────────────────────────────────────────────

class GamePhase(Enum):
    ATTACK_ORG        = "Hücum Organizasyonu"
    DEFENSE_ORG       = "Savunma Organizasyonu"
    TRANS_TO_ATTACK   = "Hücuma Geçiş"
    TRANS_TO_DEFENSE  = "Savunmaya Geçiş"
    SET_PIECE         = "Duran Top"
    TRAINING          = "Antrenman"
    GENERAL           = "Genel"

PHASE_KEYWORDS: Dict[GamePhase, List[str]] = {
    GamePhase.ATTACK_ORG:       ["hücum organi", "atak", "birleşim", "pas kombinasyonu", "kanat hücumu", "xg", "şut"],
    GamePhase.DEFENSE_ORG:      ["savunma organi", "blok", "pressing", "ppda", "kapma", "hat savunma", "baskı"],
    GamePhase.TRANS_TO_ATTACK:  ["hücuma geçiş", "kontra", "top kazanma", "dikey pas", "hızlı çıkış"],
    GamePhase.TRANS_TO_DEFENSE: ["savunmaya geçiş", "top kaybı", "geriye dönüş", "pressing tetik"],
    GamePhase.SET_PIECE:        ["duran top", "korner", "frikik", "penaltı", "taç atışı"],
    GamePhase.TRAINING:         ["antrenman", "idman", "morfosiklus", "periyotlama", "md+", "md-", "haftalık"],
}

METRIC_KEYWORDS = ["xg", "ppda", "field tilt", "bdp", "xi", "expected impact",
                   "pressing intensity", "build-up", "bölge kontrolü"]


# ─── YARDIMCI FONKSİYONLAR ────────────────────────────────────────────────────

def _hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def detect_game_phase(text: str) -> GamePhase:
    lower = text.lower()
    scores = {p: sum(1 for kw in kws if kw in lower)
              for p, kws in PHASE_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else GamePhase.GENERAL


def detect_field_zones(text: str) -> List[int]:
    lower = text.lower()
    zones: set = set()
    for kw, zone_list in ZONE_KEYWORDS.items():
        if kw in lower:
            zones.update(zone_list)
    for m in re.finditer(r"bölge\s*(\d+)", lower):
        z = int(m.group(1))
        if 1 <= z <= 18:
            zones.add(z)
    return sorted(zones)


def detect_metrics(text: str) -> List[str]:
    lower = text.lower()
    return [m for m in METRIC_KEYWORDS if m in lower]


def xml_wrap(tag: str, content: str, attrs: Dict[str, str] = None) -> str:
    if not content:
        return ""
    attr_str = (" " + " ".join(f'{k}="{v}"' for k, v in attrs.items())) if attrs else ""
    return f"<{tag}{attr_str}>{content.strip()}</{tag}>"


def build_tactical_xml(
    text: str,
    team: str = "",
    phase: GamePhase = GamePhase.GENERAL,
    zones: List[int] = None,
    players: List[str] = None,
) -> str:
    """
    Metni TacticalGPT tarzı XML etiketleriyle zenginleştirir.
    Hem embedding kalitesini hem de LLM bağlamını artırır.
    """
    parts = []
    if team:
        parts.append(xml_wrap("team", team))
    if phase != GamePhase.GENERAL:
        parts.append(xml_wrap("phase", phase.value))
    if players:
        for p in players[:5]:
            parts.append(xml_wrap("player", p))
    if zones:
        for z in zones[:4]:
            parts.append(xml_wrap("location", FIELD_ZONES.get(z, f"Bölge {z}"),
                                  {"zone_id": str(z)}))
    parts.append(xml_wrap("content", text))
    return "\n".join(filter(None, parts))


# ─── DOKÜMAN YÜKLEYİCİ ────────────────────────────────────────────────────────

def load_document(file_path: str):
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        loader = PyPDFLoader(file_path)
    elif ext in (".txt", ".md"):
        loader = TextLoader(file_path, encoding="utf-8")
    else:
        raise ValueError(f"Desteklenmeyen format: {ext}  (pdf / txt / md kabul edilir)")
    return loader.load()


# ─── HİYERARŞİK BÖLÜMLEME ─────────────────────────────────────────────────────

def split_into_sections(pages) -> List[Dict[str, Any]]:
    """
    Sayfaları büyük harf satırları veya markdown başlıklarına göre bölümlere ayırır.
    Her bölüm: {title, text, source, section_index}
    """
    full_text = "\n".join(p.page_content for p in pages)
    source    = pages[0].metadata.get("source", "unknown") if pages else "unknown"

    # Bölüm ayırıcı: tümü büyük harf satır (min 4 karakter) veya # başlıklı satır
    pattern = re.compile(
        r"(?:^|\n)(?=[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9\s\-]{3,}$|#{1,3}\s)",
        re.MULTILINE,
    )
    raw = pattern.split(full_text)

    sections = []
    for i, sec in enumerate(raw):
        sec = sec.strip()
        if len(sec) < 80:
            continue
        title = sec.split("\n")[0].lstrip("#").strip() or f"Bölüm {i + 1}"
        sections.append({
            "title":         title,
            "text":          sec,
            "source":        source,
            "section_index": i,
        })
    # Hiç bölüm bulunamazsa tüm metni tek bölüm olarak kabul et
    if not sections:
        sections = [{
            "title":         "Genel İçerik",
            "text":          full_text,
            "source":        source,
            "section_index": 0,
        }]
    return sections


def split_facts(section_text: str) -> List[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " "],
        length_function=len,
    )
    return splitter.split_text(section_text)


# ─── CHROMA & EMBEDDING ───────────────────────────────────────────────────────

def get_chroma() -> chromadb.PersistentClient:
    Path(CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)


def get_collection(client: chromadb.PersistentClient, name: str):
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def get_embedder() -> GoogleGenerativeAIEmbeddings:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY .env dosyasında tanımlı değil!")
    return GoogleGenerativeAIEmbeddings(
        model=GEMINI_EMBEDDING_MODEL,
        google_api_key=GEMINI_API_KEY,
    )


def _is_quota_or_rate_limit(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "429" in msg
        or "resource_exhausted" in msg
        or "quota" in msg
        or "rate limit" in msg
    )


def _embed_batch_with_retry(embedder: GoogleGenerativeAIEmbeddings, batch: List[str]) -> List[List[float]]:
    """Tek bir embedding batch’i; 429/kota hatalarında üstel bekleme ile yeniden dener."""
    last: Optional[BaseException] = None
    for attempt in range(RAG_EMBED_MAX_RETRIES):
        try:
            return embedder.embed_documents(batch)
        except Exception as e:
            last = e
            if not _is_quota_or_rate_limit(e):
                raise
            wait = min(
                RAG_EMBED_RETRY_MAX_SEC,
                RAG_EMBED_RETRY_BASE_SEC * (2**attempt),
            )
            wait += random.uniform(0.0, 2.0)
            print(
                f"  ⏳ Kota / hız sınırı — {wait:.1f}s bekleniyor "
                f"(deneme {attempt + 1}/{RAG_EMBED_MAX_RETRIES})"
            )
            time.sleep(wait)
    assert last is not None
    raise last


def embed_documents_throttled(
    embedder: GoogleGenerativeAIEmbeddings,
    texts: List[str],
    step_label: str = "",
) -> List[List[float]]:
    """
    Metinleri küçük gruplar halinde embed eder; gruplar arasında RAG_EMBED_DELAY_SEC bekler.
    Ücretsiz Gemini kotasında tek seferde çok istek atmamak için.
    """
    if not texts:
        return []
    out: List[List[float]] = []
    n = len(texts)
    for start in range(0, n, RAG_EMBED_BATCH_SIZE):
        end = min(start + RAG_EMBED_BATCH_SIZE, n)
        batch = texts[start:end]
        embs = _embed_batch_with_retry(embedder, batch)
        out.extend(embs)
        if step_label:
            print(f"  📦 {step_label} embed: {end}/{n}")
        if end < n and RAG_EMBED_DELAY_SEC > 0:
            time.sleep(RAG_EMBED_DELAY_SEC)
    return out


def _upsert_batch(collection, ids, embeddings, documents, metadatas):
    """ChromaDB'ye toplu kayıt atar."""
    BATCH = 50
    for start in range(0, len(ids), BATCH):
        end = start + BATCH
        collection.upsert(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )


# ─── ANA İNDEKSLEME ───────────────────────────────────────────────────────────

def ingest_file(file_path: str, team_name: str = ""):
    """
    Tek bir dosyayı 3 seviyeli hiyerarşide ChromaDB'ye indeksler.
    """
    print(f"\n📄 İndeksleniyor → {Path(file_path).name}")
    print(
        f"  ⚙️  Embedding: batch={RAG_EMBED_BATCH_SIZE}, "
        f"gruplar arası={RAG_EMBED_DELAY_SEC}s, "
        f"429 için en fazla {RAG_EMBED_MAX_RETRIES} deneme (üstel bekleme)"
    )

    embedder = get_embedder()
    chroma   = get_chroma()
    col_doc  = get_collection(chroma, COL_DOCUMENT)
    col_sec  = get_collection(chroma, COL_SECTION)
    col_fact = get_collection(chroma, COL_FACT)

    # ── SEVİYE 1: BELGE ──────────────────────────────────────────────────────
    pages    = load_document(file_path)
    doc_text = "\n".join(p.page_content for p in pages)
    doc_id   = f"doc_{_hash(doc_text)}"

    doc_xml = build_tactical_xml(
        doc_text[:2500],
        team=team_name,
        phase=GamePhase.GENERAL,
    )
    doc_emb = embed_documents_throttled(embedder, [doc_xml], "Belge")[0]
    col_doc.upsert(
        ids=[doc_id],
        embeddings=[doc_emb],
        documents=[doc_xml],
        metadatas=[{
            "level":       "document",
            "source":      file_path,
            "team":        team_name,
            "total_pages": len(pages),
            "char_count":  len(doc_text),
        }],
    )
    print(f"  ✅ Belge seviyesi : {doc_id}")

    # ── SEVİYE 2: BÖLÜM ──────────────────────────────────────────────────────
    sections = split_into_sections(pages)
    print(f"  📑 {len(sections)} bölüm tespit edildi")

    sec_ids, sec_embs, sec_docs, sec_metas = [], [], [], []
    for sec in sections:
        phase   = detect_game_phase(sec["text"])
        zones   = detect_field_zones(sec["text"])
        metrics = detect_metrics(sec["text"])

        sec_xml = build_tactical_xml(
            sec["text"][:1800],
            team=team_name,
            phase=phase,
            zones=zones[:4],
        )
        sec_id = f"sec_{_hash(sec['text'])}_{sec['section_index']}"
        sec_ids.append(sec_id)
        sec_docs.append(sec_xml)
        sec_metas.append({
            "level":         "section",
            "source":        sec["source"],
            "section_title": sec["title"],
            "team":          team_name,
            "game_phase":    phase.value,
            "field_zones":   ",".join(map(str, zones[:6])),
            "metrics":       ",".join(metrics),
            "parent_doc":    doc_id,
        })

    sec_embs = embed_documents_throttled(embedder, sec_docs, "Bölüm")
    _upsert_batch(col_sec, sec_ids, sec_embs, sec_docs, sec_metas)
    print(f"  ✅ Bölüm seviyesi : {len(sec_ids)} kayıt")

    # ── SEVİYE 3: OLGU ───────────────────────────────────────────────────────
    fact_ids, fact_docs, fact_metas = [], [], []

    for sec in sections:
        parent_phase = detect_game_phase(sec["text"])
        parent_zones = detect_field_zones(sec["text"])
        chunks       = split_facts(sec["text"])

        for i, chunk in enumerate(chunks):
            chunk_phase   = detect_game_phase(chunk)
            chunk_zones   = detect_field_zones(chunk)
            final_phase   = chunk_phase if chunk_phase != GamePhase.GENERAL else parent_phase
            final_zones   = chunk_zones if chunk_zones else parent_zones

            fact_xml = build_tactical_xml(
                chunk,
                team=team_name,
                phase=final_phase,
                zones=final_zones[:4],
            )
            fact_id = f"fact_{_hash(chunk)}_{sec['section_index']}_{i}"
            fact_ids.append(fact_id)
            fact_docs.append(fact_xml)
            fact_metas.append({
                "level":         "fact",
                "source":        sec["source"],
                "section_title": sec["title"],
                "chunk_index":   i,
                "team":          team_name,
                "game_phase":    final_phase.value,
                "field_zones":   ",".join(map(str, final_zones[:6])),
                "metrics":       ",".join(detect_metrics(chunk)),
                "parent_doc":    doc_id,
            })

    if fact_docs and RAG_EMBED_DELAY_SEC > 0:
        print(f"  ⏸  Bölümler bitti; olgu embedding öncesi {RAG_EMBED_DELAY_SEC:.1f}s bekleniyor…")
        time.sleep(RAG_EMBED_DELAY_SEC)

    all_fact_embs = embed_documents_throttled(embedder, fact_docs, "Olgu")

    _upsert_batch(col_fact, fact_ids, all_fact_embs, fact_docs, fact_metas)
    print(f"  ✅ Olgu seviyesi  : {len(fact_ids)} chunk")
    print(f"\n🏁 Tamamlandı → {CHROMA_PERSIST_DIR}")


def ingest_directory(directory: str = None, team_name: str = ""):
    """
    RAG_DOCUMENTS_PATH altındaki tüm desteklenen dosyaları indeksler.
    Desteklenen: .pdf, .txt, .md
    """
    path = Path(directory or RAG_DOCUMENTS_PATH)
    if not path.exists():
        print(f"⚠️  Klasör bulunamadı: {path}")
        print("   RAG_DOCUMENTS_PATH değişkenini .env dosyasında ayarlayın.")
        return

    files = [f for f in path.rglob("*") if f.suffix.lower() in {".pdf", ".txt", ".md"}]
    if not files:
        print(f"⚠️  {path} altında desteklenen dosya bulunamadı (.pdf / .txt / .md)")
        return

    print(f"🔍 {len(files)} dosya bulundu → İndeksleme başlıyor...")
    ok, fail = 0, 0
    for f in files:
        try:
            ingest_file(str(f), team_name=team_name)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ❌ [{f.name}] Hata: {e}")

    if fail == 0:
        print(f"\n✅ İndeksleme tamam: {ok} dosya.")
    else:
        print(f"\n⚠️  Bitti: {ok} başarılı, {fail} hata. Chroma'da eksik veri olabilir; `python rag_ingest.py --stats` ile kontrol edin.")


# ─── RETRIEVAL (Koç modelleri tarafından çağrılır) ─────────────────────────

def retrieve_context(
    search_text: str,
    game_phase: str = None,
    top_k: int = None,
) -> str:
    """
    ChromaDB'den taktiksel bilgi çeker.  Her koç modülü bu fonksiyonu çağırarak
    kendi raporuna doküman bilgisini ekler.

    Parametreler
    ------------
    search_text : Arama metni (Türkçe, ne kadar alan-spesifik olursa o kadar iyi)
    game_phase  : Oyun evresi filtresi — "Hücum Organizasyonu", "Savunma Organizasyonu",
                  "Hücuma Geçiş", "Savunmaya Geçiş", "Duran Top", "Antrenman", "Genel"
    top_k       : Döndürülecek chunk sayısı (varsayılan .env'deki RAG_TOP_K)

    Döndürür
    --------
    str — Formatlanmış RAG bağlamı; ChromaDB boşsa veya hata olursa boş string
    """
    top_k = top_k or TOP_K

    if not GEMINI_API_KEY:
        return ""

    try:
        embedder  = get_embedder()
        query_emb = embedder.embed_query(search_text)
    except Exception as exc:
        print(f"⚠️  [RAG] Embedding hatası: {exc}")
        return ""

    try:
        client   = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        col_fact = client.get_or_create_collection(COL_FACT)
        col_sec  = client.get_or_create_collection(COL_SECTION)
    except Exception:
        return ""

    where = {"game_phase": {"$eq": game_phase}} if game_phase else None

    def _query(collection, n):
        kwargs = dict(
            query_embeddings=[query_emb],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        if where:
            kwargs["where"] = where
        try:
            return collection.query(**kwargs)
        except Exception:
            kwargs.pop("where", None)
            return collection.query(**kwargs)

    facts = _query(col_fact, top_k)
    secs  = _query(col_sec, max(2, top_k // 3))

    parts: List[str] = []

    if facts and facts["documents"] and facts["documents"][0]:
        for doc, meta, dist in zip(
            facts["documents"][0],
            facts["metadatas"][0],
            facts["distances"][0],
        ):
            relevance = round(1.0 - float(dist), 3)
            parts.append(
                f"[{meta.get('section_title','?')} | "
                f"Evre: {meta.get('game_phase','?')} | "
                f"Uygunluk: {relevance}]\n{doc}"
            )

    if secs and secs["documents"] and secs["documents"][0]:
        for doc, meta in zip(secs["documents"][0], secs["metadatas"][0]):
            parts.append(
                f"[BÖLÜM: {meta.get('section_title','?')}]\n{doc[:800]}"
            )

    return "\n\n".join(parts)


def get_chroma_stats() -> Dict[str, Any]:
    """
    ChromaDB özetini döndürür (API ve CLI için).
    persist_dir yoksa veya koleksiyon yoksa sayılar 0 olur.
    """
    p = Path(CHROMA_PERSIST_DIR).resolve()
    out: Dict[str, Any] = {
        "persist_dir": str(p),
        "persist_dir_exists": p.exists(),
        "collections": {},
        "total_documents": 0,
    }
    if not p.exists():
        return out
    client = get_chroma()
    names = [COL_DOCUMENT, COL_SECTION, COL_FACT]
    total = 0
    for name in names:
        try:
            col = client.get_collection(name)
            n = col.count()
            out["collections"][name] = n
            total += n
        except Exception:
            out["collections"][name] = 0
    out["total_documents"] = total
    return out


def print_chroma_stats() -> None:
    """ChromaDB koleksiyonlarındaki kayıt sayılarını terminale yazar."""
    s = get_chroma_stats()
    p = Path(s["persist_dir"])
    if not s["persist_dir_exists"]:
        print(f"⚠️  Chroma klasörü yok: {p}\n   Henüz ingest çalışmamış veya CHROMA_PERSIST_DIR yanlış.")
        return
    print(f"📂 Chroma dizini: {p}\n")
    for name, n in s["collections"].items():
        print(f"  • {name}: {n} kayıt")
    print(f"\n  Toplam vektörlü kayıt: {s['total_documents']}")
    if s["total_documents"] == 0:
        print("\n  → Veri yok. Önce: python rag_ingest.py  (veya POST /rag/ingest)")


# ─── CLI KULLANIMI ────────────────────────────────────────────────────────────
# python rag_ingest.py
# python rag_ingest.py --stats
# python rag_ingest.py --team "Galatasaray"
# python rag_ingest.py --file /path/to/doc.pdf --team "Fenerbahçe"

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Taktiksel RAG İndeksleme Aracı")
    parser.add_argument("--file",  type=str, default=None, help="Tek dosya yolu")
    parser.add_argument("--dir",   type=str, default=None, help="Klasör yolu (varsayılan: RAG_DOCUMENTS_PATH)")
    parser.add_argument("--team",  type=str, default="",   help="Takım adı (metadata için)")
    parser.add_argument("--stats", action="store_true",     help="ChromaDB kayıt sayılarını göster")
    args = parser.parse_args()

    if args.stats:
        print_chroma_stats()
    elif args.file:
        ingest_file(args.file, team_name=args.team)
    else:
        ingest_directory(args.dir, team_name=args.team)
