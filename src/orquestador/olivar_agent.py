import json

from src.utils.llm_client import get_llm_client
from src.utils.prompts_loader import load_txt
from src.utils.knowledge_base import get_relevant_knowledge
from src.utils.knowledge_base import load_knowledge, get_relevant_knowledge      

class OlivarAgent:
    def __init__(self, model: str):
        self.client = get_llm_client(model)
        self.model = model

        self.role = load_txt("roles/olivar_expert.txt")
        self.prompt_template = load_txt("prompts/analysis_prompt.txt")

        self.knowledge = load_knowledge()

    def build_prompt(self, data: dict) -> str:
        prompt = self.prompt_template

        relevant_docs = get_relevant_knowledge(data, self.knowledge)
        knowledge_text = "\n\n".join(relevant_docs)
        # Reemplazo del bloque de datos
        prompt = prompt.replace("{data}", json.dumps(data, indent=2))

        # Reemplazos explícitos
        prompt = prompt.replace("{pct_perdida_pred}", str(data.get("pct_perdida_pred", "")))
        prompt = prompt.replace("{impacto_eur_ha_pred}", str(data.get("impacto_eur_ha_pred", "")))
        prompt = prompt.replace("{knowledge}", knowledge_text)

        return prompt

    def analyze(self, data: dict) -> str:
        prompt = self.build_prompt(data)

        messages = [
            {"role": "system", "content": self.role},
            {"role": "user", "content": prompt},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
        )

        return response.choices[0].message.content