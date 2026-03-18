import json

from src.utils.llm_client import get_llm_client
from src.utils.prompts_loader import load_txt


class OlivarAgent:

    def __init__(self, model: str):
        self.client = get_llm_client(model)
        self.model = model

        # cargar archivos
        self.role = load_txt("roles/olivar_expert.txt")
        self.prompt_template = load_txt("prompts/analysis_prompt.txt")

    def build_prompt(self, data: dict) -> str:
        return self.prompt_template.replace(
            "{data}",
            json.dumps(data, indent=2)
        )

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