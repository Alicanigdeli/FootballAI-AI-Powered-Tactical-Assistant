import os
from enum import Enum
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI


load_dotenv()

class LLMModelType(Enum):
    GEMINI = "gemini"
    GPT4 = "gpt4"

def get_langchain_model(model_type: LLMModelType = LLMModelType.GEMINI, temperature: float = 0.7):
    """Belirtilen LLM modelini LangChain üzerinden başlatır ve döner."""    
    if model_type == LLMModelType.GEMINI:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY .env dosyasında bulunamadı!")
            
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",  
            google_api_key=api_key,
            temperature=temperature,
            convert_system_message_to_human=True 
        )
        
    elif model_type == LLMModelType.GPT4:
        # Örnek GPT yapısı (kütüphane yüklüyse çalışır)
        # api_key = os.getenv("OPENAI_API_KEY")
        # return ChatOpenAI(model="gpt-4", api_key=api_key, temperature=temperature)
        raise NotImplementedError("GPT-4 henüz aktif edilmedi.")
        
    else:
        raise ValueError(f"Desteklenmeyen LLM Modeli: {model_type}")