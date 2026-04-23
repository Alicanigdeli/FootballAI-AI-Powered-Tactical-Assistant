import redis.asyncio as redis
import json
import os
from uuid import uuid4
from enum import Enum
from typing import Optional

# Enumlar aynı kalıyor
class LLMAnswerStatus(Enum):
    DEFENSE_TACTIC_SUGGESTION="defense_tactic_suggestion"
    OFFENSE_TACTIC_SUGGESTION="offense_tactic_suggestion"
    PLAYER_POSITIONING_SUGGESTION="player_positioning_suggestion"
    SET_PIECE_SUGGESTION="set_piece_suggestion"
    MATCH_PREPARATION_SUGGESTION="match_preparation_suggestion"
    TRAINING_DRILL_SUGGESTION="training_drill_suggestion"
    HOLISTIC_MATCH_STRATEGY="holistic_match_strategy"

class FootballLLMOrchestrator:
    def __init__(self):
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis_db = int(os.getenv("REDIS_DB", 0))
        self.redis_client = None

        self.queues = {
            LLMAnswerStatus.DEFENSE_TACTIC_SUGGESTION: "defense_tactic_queue",
            LLMAnswerStatus.OFFENSE_TACTIC_SUGGESTION: "offense_tactic_queue",
            LLMAnswerStatus.PLAYER_POSITIONING_SUGGESTION: "player_positioning_queue",
            LLMAnswerStatus.SET_PIECE_SUGGESTION: "set_piece_queue",
            LLMAnswerStatus.MATCH_PREPARATION_SUGGESTION: "match_preparation_queue",
            LLMAnswerStatus.TRAINING_DRILL_SUGGESTION: "training_drill_queue",
            LLMAnswerStatus.HOLISTIC_MATCH_STRATEGY: "head_coach_queue"
        }

    async def connect(self):
        self.redis_client = await redis.Redis(
            host=self.redis_host, 
            port=self.redis_port, 
            db=self.redis_db, 
            decode_responses=True
        )
        print("✅ Redis bağlantısı başarılı.")

    async def disconnect(self):
        if self.redis_client:
            await self.redis_client.close()

    # DEĞİŞİKLİK BURADA: prompt yok, context yerine params var
    async def submit_task(self, expertise: LLMAnswerStatus, params: dict) -> str:
        try:
            if not self.redis_client:
                await self.connect()

            task_id = str(uuid4())
            queue_name = self.queues[expertise]
            
            task_payload = {
                "task_id": task_id,
                "task_type": expertise.value, # Worker ne yapacağını bilsin
                "params": params,             # Worker hangi veriyi çekeceğini bilsin
                "status": "pending",
                "timestamp": str(os.getenv("TIMESTAMP", "")) # Opsiyonel zaman damgası
            }
            
            # Kuyruğa JSON olarak atıyoruz
            await self.redis_client.lpush(queue_name, json.dumps(task_payload))
            
            print(f"🚀 Görev {task_id} -> {queue_name} kuyruğuna gönderildi.")
            print(f"📦 Payload: {json.dumps(task_payload, indent=2)}")
            
            return task_id

        except Exception as e:
            print(f"❌ Görev gönderilirken hata oluştu: {e}")
            return None
        

