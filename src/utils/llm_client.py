from src.config.llms import OpenAI


def get_llm_client(model: str) -> OpenAI:
    return OpenAI()