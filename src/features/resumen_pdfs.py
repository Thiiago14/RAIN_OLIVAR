"""
resumen_pdfs.py
---------------
Lee todos los PDFs de una carpeta, extrae su texto, lo envía a la API de
OpenAI y guarda un resumen agronómico estructurado en TXT por cada documento.

Uso:
    python scripts/resumen_pdfs.py
    python scripts/resumen_pdfs.py --input data/pdfs --output data/resumenes
    python scripts/resumen_pdfs.py --model gpt-4o --api-key sk-...
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependencias externas (pypdf, openai, python-dotenv, tqdm)
# ---------------------------------------------------------------------------
try:
    import pypdf
except ImportError:
    sys.exit("ERROR: Instala pypdf → pip install pypdf")

try:
    from openai import OpenAI
except ImportError:
    sys.exit("ERROR: Instala openai → pip install openai")

try:
    from tqdm import tqdm as _tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_INPUT = "Base documental"
DEFAULT_OUTPUT = "Base documental/resumenes"

# Caracteres máximos enviados en una sola llamada (≈ 12 k tokens / 4 chars/token)
CHUNK_SIZE = 12_000
CHUNK_OVERLAP = 500          # Overlap entre chunks para no perder contexto
MAX_RETRIES = 3
RETRY_DELAY = 5              # segundos entre reintentos

SYSTEM_PROMPT = textwrap.dedent("""\
    Eres un ingeniero agrónomo especialista en olivicultura mediterránea e hidrología
    agrícola. Tu misión es analizar documentos técnicos o científicos y extraer toda
    la información relevante para elaborar un INFORME AGRONÓMICO DE EVALUACIÓN DE
    DAÑOS POR LLUVIAS EXTREMAS EN OLIVAR.

    El resumen que generes será consumido por un modelo predictivo que redactará el
    informe final. Por eso es CRÍTICO que:
      - Toda cifra, rango o umbral numérico quede recogido con su unidad.
      - Cada variable aparezca en su sección correspondiente, sin omisiones.
      - No inventes datos; si algo no aparece en el texto escribe exactamente:
        [NO DISPONIBLE EN EL DOCUMENTO]

    RESPONDE SIEMPRE en español y sigue EXACTAMENTE esta estructura:

    ================================================================
    1. CARACTERIZACIÓN DE LA PARCELA / ZONA DE ESTUDIO
    ================================================================
    - Localización geográfica (provincia, comarca, coordenadas si se citan).
    - Variedad/es de olivar mencionadas (ej. Picual, Hojiblanca, Arbequina…).
    - Marco de plantación y densidad (pies/ha si se indica).
    - Tipo y textura de suelo (arcilloso, franco, limoso, pedregoso, etc.).
    - Pendiente media o rango de pendiente (%; clasificación si la hay).
    - Sistema de manejo del suelo (laboreo, cubierta vegetal, mínimo laboreo…).
    - Estadio fenológico del olivar en el momento del evento.

    ================================================================
    2. CARACTERIZACIÓN DEL EVENTO DE LLUVIA EXTREMA
    ================================================================
    - Fecha o periodo del evento.
    - Precipitación total acumulada (mm) y periodo de retorno (años) si se cita.
    - Intensidad máxima (mm/h o mm/día).
    - Duración total del episodio (horas/días).
    - Duración del encharcamiento o saturación hídrica del suelo (horas/días).
    - Caudal de escorrentía generado (m³/ha o l/s) si se indica.
    - Comparativa con precipitación media de la zona (si se menciona).

    ================================================================
    3. EVALUACIÓN AGRONÓMICA DEL IMPACTO
    ================================================================
    3.1 A NIVEL GENERAL (zona/comarca):
    - Descripción del impacto observado en el cultivo.
    - Superficie afectada (ha o %) si se cuantifica.
    - Síntomas en el árbol: asfixia radicular, defoliación, muerte de ramas, etc.

    3.2 A NIVEL DE PARCELA:
    - Daños específicos documentados por parcela o tipo de parcela.
    - Relación entre pendiente/suelo y nivel de daño observado.
    - Erosión, arrastre de suelo o cárcavas generadas (t/ha si se cita).

    ================================================================
    4. RIESGOS DETECTADOS
    ================================================================
    Para cada riesgo identificado indica:
    - Tipo de riesgo (escorrentía, erosión, encharcamiento, asfixia radicular,
      deslizamiento, contaminación difusa, pérdida de fertilizante, etc.).
    - Nivel de riesgo (bajo / medio / alto / muy alto) y criterio utilizado.
    - Condiciones de suelo/pendiente/manejo que lo agravan.
    - Enfermedades oportunistas favorecidas (Verticillium, Phytophthora, etc.)
      con agente causal y condiciones de desarrollo.

    ================================================================
    5. ESTIMACIÓN DE PÉRDIDA DE RENDIMIENTO
    ================================================================
    - Porcentaje de pérdida de cosecha estimado (% sobre producción esperada).
    - Producción esperada sin daño (kg/ha o t/ha) si se menciona.
    - Producción estimada tras el evento (kg/ha o t/ha).
    - Método o modelo de estimación utilizado en el documento.
    - Factores que modulan la pérdida (variedad, pendiente, suelo, fenología…).
    - Rangos o escenarios de pérdida si el documento los contempla
      (ej. pérdida mínima / media / máxima).

    ================================================================
    6. IMPACTO ECONÓMICO ESTIMADO
    ================================================================
    - Precio de mercado del aceite o aceituna citado (€/kg o €/t).
    - Pérdida económica estimada (€/ha) por parcela o tipo de parcela.
    - Pérdida económica media en el conjunto de parcelas evaluadas (€/ha).
    - Costes adicionales de restauración/rehabilitación si se indican (€/ha).
    - Otros costes asociados (replantación, tratamientos fitosanitarios, etc.).

    ================================================================
    7. VARIABLES Y PARÁMETROS CUANTITATIVOS CLAVE
    ================================================================
    Tabla con TODOS los valores numéricos relevantes extraídos del documento:
    | Variable | Valor | Unidad | Fuente/Contexto |
    (Incluir: precipitación, pendiente, textura, encharcamiento, escorrentía,
    erosión, rendimiento, pérdida %, precio €, CN, Kc, ETP, NDVI u otros índices)

    ================================================================
    8. RECOMENDACIONES TÉCNICAS
    ================================================================
    Para cada recomendación indica:
    - Medida técnica propuesta.
    - Objetivo agronómico (reducir escorrentía, mejorar drenaje, rehabilitar
      suelo, proteger raíces, recuperar producción, etc.).
    - Plazo de aplicación (inmediato / corto / medio / largo plazo).
    - Coste orientativo (€/ha) si se menciona.

    ================================================================
    9. CONCEPTOS Y MODELOS TÉCNICOS CITADOS
    ================================================================
    Lista de términos, índices, ecuaciones o modelos mencionados en el documento
    que el modelo predictivo debe conocer para generar el informe:
    (ej. CN curve number, RUSLE, USLE, Penman-Monteith, SCS, período de retorno,
    escorrentía superficial, capacidad de campo, punto de marchitez, etc.)

    ================================================================
    10. SÍNTESIS PARA EL MODELO PREDICTIVO
    ================================================================
    Párrafo de 5-8 líneas que resuma los hallazgos más importantes del documento
    en términos de: severidad del evento, nivel de daño al olivar, estimación de
    pérdidas y las medidas más urgentes. Este párrafo es el contexto principal
    que recibirá el modelo generador del informe.
    ================================================================

    REGLAS FINALES:
    - No inventes ningún dato. Usa [NO DISPONIBLE EN EL DOCUMENTO] cuando falte info.
    - Mantén todas las unidades originales del documento.
    - Si el documento no trata de olivar ni de lluvias, indícalo al inicio y extrae
      igualmente lo que sea transferible a ese contexto.
    - Usa lenguaje técnico agronómico preciso.
""")

CHUNK_SUMMARY_PROMPT = textwrap.dedent("""\
    El siguiente texto es un FRAGMENTO de un documento técnico sobre olivar y/o
    eventos de lluvia extrema. Extrae y lista de forma concisa SOLO lo que aparezca
    en el texto, agrupado en estos bloques:

    [PARCELA/ZONA]
    - Localización, variedad de olivar, pendiente (%), tipo de suelo, densidad.

    [EVENTO DE LLUVIA]
    - Precipitación (mm), intensidad (mm/h), duración (h/días), encharcamiento (h/días),
      período de retorno (años), escorrentía (m³/ha).

    [DAÑOS AGRONÓMICOS]
    - Síntomas en el árbol, superficie afectada (ha o %), erosión (t/ha).

    [RIESGOS]
    - Tipo de riesgo, nivel (bajo/medio/alto/muy alto), enfermedades favorecidas.

    [PÉRDIDAS Y ECONOMÍA]
    - % pérdida de cosecha, producción esperada vs. real (kg/ha), impacto económico (€/ha).

    [RECOMENDACIONES]
    - Medida técnica, objetivo, plazo, coste (€/ha) si se indica.

    [MODELOS Y PARÁMETROS]
    - Índices, ecuaciones, modelos o valores numéricos clave (CN, NDVI, ETP, etc.).

    Responde en español. Usa [NO DISPONIBLE] si algo no aparece. No añadas datos externos.
""")

CONSOLIDATION_PROMPT = textwrap.dedent("""\
    Los siguientes son RESÚMENES PARCIALES de distintos fragmentos de un mismo
    documento técnico sobre olivar y lluvias extremas. Consolídalos en un único
    resumen estructurado siguiendo EXACTAMENTE las 10 secciones del informe agronómico:

    ================================================================
    1. CARACTERIZACIÓN DE LA PARCELA / ZONA DE ESTUDIO
    2. CARACTERIZACIÓN DEL EVENTO DE LLUVIA EXTREMA
    3. EVALUACIÓN AGRONÓMICA DEL IMPACTO
       3.1 A NIVEL GENERAL  |  3.2 A NIVEL DE PARCELA
    4. RIESGOS DETECTADOS
    5. ESTIMACIÓN DE PÉRDIDA DE RENDIMIENTO
    6. IMPACTO ECONÓMICO ESTIMADO
    7. VARIABLES Y PARÁMETROS CUANTITATIVOS CLAVE  (tabla)
    8. RECOMENDACIONES TÉCNICAS
    9. CONCEPTOS Y MODELOS TÉCNICOS CITADOS
    10. SÍNTESIS PARA EL MODELO PREDICTIVO
    ================================================================

    Instrucciones:
    - Elimina duplicados e integra la información complementaria de cada fragmento.
    - Mantén TODOS los valores numéricos con sus unidades.
    - Usa [NO DISPONIBLE EN EL DOCUMENTO] si algo no aparece en ningún fragmento.
    - Responde en español con lenguaje técnico agronómico preciso.
    - No añadas información que no provenga de los fragmentos.
""")


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------

def _load_env() -> None:
    """
    Carga variables de entorno desde el primer .env encontrado.
    Usa python-dotenv si está disponible; si no, lo parsea manualmente.
    """
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / ".env",
        script_dir.parent / ".env",
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",
    ]

    env_file: Path | None = None
    for candidate in candidates:
        if candidate.exists():
            env_file = candidate
            break

    if env_file is None:
        return

    # Intentar con python-dotenv primero
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
        return
    except ImportError:
        pass

    # Fallback: parsear el .env manualmente
    with open(env_file, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _extract_text_from_pdf(pdf_path: Path) -> str:
    """Extrae todo el texto de un PDF página a página."""
    reader = pypdf.PdfReader(str(pdf_path))
    pages_text: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages_text.append(text)
    return "\n".join(pages_text)


def _split_into_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Divide el texto en chunks con overlap para no perder contexto."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def _call_openai(
    client: OpenAI,
    model: str,
    system: str,
    user_content: str,
    retries: int = MAX_RETRIES,
) -> tuple[str, int]:
    """Llama a la API de OpenAI y devuelve (respuesta, tokens_totales)."""
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            return content, tokens
        except Exception as exc:  # noqa: BLE001
            if attempt == retries:
                raise
            print(f"  [Reintento {attempt}/{retries}] Error: {exc}. Esperando {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
    return "", 0  # nunca se alcanza


def _summarize_pdf(client: OpenAI, model: str, text: str) -> tuple[str, int]:
    """
    Genera el resumen agronómico estructurado de un PDF.
    Si el texto es largo, primero resume por chunks y luego consolida.
    """
    total_tokens = 0

    if len(text) <= CHUNK_SIZE:
        summary, tokens = _call_openai(client, model, SYSTEM_PROMPT, text)
        return summary, tokens

    # --- Texto largo: resumir por chunks y consolidar ---
    chunks = _split_into_chunks(text, CHUNK_SIZE, CHUNK_OVERLAP)
    chunk_summaries: list[str] = []

    for i, chunk in enumerate(chunks, 1):
        print(f"    Procesando fragmento {i}/{len(chunks)}...")
        partial, tokens = _call_openai(
            client, model, CHUNK_SUMMARY_PROMPT,
            f"FRAGMENTO {i}/{len(chunks)}:\n\n{chunk}"
        )
        chunk_summaries.append(f"--- Fragmento {i} ---\n{partial}")
        total_tokens += tokens

    # Consolidación final
    print(f"    Consolidando {len(chunks)} fragmentos en resumen final...")
    combined = "\n\n".join(chunk_summaries)
    final_summary, tokens = _call_openai(
        client, model, CONSOLIDATION_PROMPT,
        f"RESÚMENES PARCIALES:\n\n{combined}"
    )
    total_tokens += tokens
    return final_summary, total_tokens


def _wrap_output(pdf_name: str, summary: str, tokens: int, model: str) -> str:
    """Formatea el archivo TXT de salida con cabecera informativa."""
    separator = "=" * 62
    header = (
        f"{separator}\n"
        f"RESUMEN AGRONÓMICO\n"
        f"Documento : {pdf_name}\n"
        f"Modelo    : {model}\n"
        f"Tokens    : {tokens}\n"
        f"{separator}\n\n"
    )
    return header + summary + "\n"


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resume PDFs agronómicos usando la API de OpenAI."
    )
    parser.add_argument(
        "--input", "-i",
        default=DEFAULT_INPUT,
        help=f"Carpeta con los PDFs de entrada (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output", "-o",
        default=DEFAULT_OUTPUT,
        help=f"Carpeta donde guardar los TXTs (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help=f"Modelo de OpenAI a usar (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--api-key", "-k",
        default=None,
        help="API key de OpenAI (si no se pasa, se lee de OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Reprocesar PDFs aunque ya exista el TXT de salida",
    )
    args = parser.parse_args()

    # Cargar .env antes de leer variables de entorno
    _load_env()

    # --- Validar API key ---
    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        sys.exit(
            "ERROR: No se encontró la API key de OpenAI.\n"
            "  Opción 1 → export OPENAI_API_KEY=sk-...\n"
            "  Opción 2 → crea un archivo .env con OPENAI_API_KEY=sk-...\n"
            "  Opción 3 → usa --api-key sk-..."
        )

    client = OpenAI(api_key=api_key)

    # --- Preparar carpetas ---
    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.exists():
        sys.exit(f"ERROR: La carpeta de entrada no existe: {input_dir.resolve()}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Listar PDFs ---
    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No se encontraron archivos PDF en: {input_dir.resolve()}")
        return

    print(f"\nEncontrados {len(pdf_files)} PDF(s) en '{input_dir.resolve()}'")
    print(f"Modelo      : {args.model}")
    print(f"Salida en   : {output_dir.resolve()}\n")

    iterator = _tqdm(pdf_files, desc="Procesando PDFs") if _HAS_TQDM else pdf_files
    total_tokens_all = 0

    for pdf_path in iterator:
        pdf_name = pdf_path.stem
        output_path = output_dir / f"{pdf_name}_resumen.txt"

        if output_path.exists() and not args.force:
            print(f"  [SKIP] '{pdf_path.name}' → ya existe '{output_path.name}' (usa --force para reprocesar)")
            continue

        print(f"\n  Procesando: {pdf_path.name}")

        # 1. Extraer texto
        try:
            text = _extract_text_from_pdf(pdf_path)
        except Exception as exc:  # noqa: BLE001
            print(f"  [ERROR] No se pudo leer el PDF: {exc}")
            continue

        if not text.strip():
            print(f"  [WARN] El PDF '{pdf_path.name}' no contiene texto extraíble (puede ser escaneado).")
            continue

        print(f"  Texto extraído: {len(text):,} caracteres")

        # 2. Enviar a OpenAI y obtener resumen
        try:
            summary, tokens = _summarize_pdf(client, args.model, text)
        except Exception as exc:  # noqa: BLE001
            print(f"  [ERROR] Fallo en la API de OpenAI: {exc}")
            continue

        total_tokens_all += tokens

        # 3. Guardar TXT
        output_content = _wrap_output(pdf_path.name, summary, tokens, args.model)
        output_path.write_text(output_content, encoding="utf-8")
        print(f"  [OK] Guardado en '{output_path}' ({tokens} tokens usados)")

    print(f"\nProceso completado. Tokens totales consumidos: {total_tokens_all:,}")


if __name__ == "__main__":
    main()
