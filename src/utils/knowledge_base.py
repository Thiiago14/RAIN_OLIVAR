import os


def load_knowledge(base_path="data/Base documental/resumenes"):
    texts = []

    for file in os.listdir(base_path):
        if file.endswith(".txt"):
            with open(os.path.join(base_path, file), "r", encoding="utf-8") as f:
                content = f.read()

                # dividir en bloques
                chunks = content.split("\n\n")
                texts.extend(chunks)

    return texts


def get_relevant_knowledge(data: dict, texts: list, top_k=3):

    keywords = [
        str(data.get("tipo_suelo", "")),
        str(data.get("estado_fenologico", "")),
        str(data.get("encharcamiento", "")),
        str(data.get("erosion", "")),
        str(data.get("escorrentia", "")),
        str(data.get("inundacion", "")),
        str(data.get("drenaje", "")),
        str(data.get("suelo", "")), 
        str(data.get("olivar", "")),
        str(data.get("raices", "")),
        str(data.get("estres_hidrico", "")),
        str(data.get("manejo", "")),
        str(data.get("cubiertas_vegetales", "")),
        str(data.get("precipitaciones", "")),
        str(data.get("recomendaciones", ""))
    ]

    scored = []

    for t in texts:
        score = 0
        t_lower = t.lower()

        for k in keywords:
            if k and k.lower() in t_lower:
                score += 1

        # bonus por términos críticos
        if "recomendación" in t_lower:
            score += 2
        if "manejo" in t_lower:
            score += 2

        scored.append((score, t))

    scored.sort(reverse=True, key=lambda x: x[0])

    return [t for _, t in scored[:top_k]]