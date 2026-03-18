from dotenv import load_dotenv
load_dotenv()

import os
print(os.getenv("OPENAI_API_KEY"))

from src.orquestador.olivar_agent import OlivarAgent
from src.config.models_config import DEFAULT_OLIVAR_MODEL
from src.utils.data_loader import load_json


def main():

    data = load_json("data/escenarios/test_1.json")

    agent = OlivarAgent(model=DEFAULT_OLIVAR_MODEL)

    result = agent.analyze(data)

    print("\n--- RESULTADO ---\n")
    print(result)


if __name__ == "__main__":
    main()