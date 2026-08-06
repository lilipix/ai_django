import json
import logging

from django.conf import settings
from mistralai.client import Mistral

from cv_analyzer.validation import CVAnalysisResult, validate_cv_analysis_result

logger = logging.getLogger(__name__)


class MistralServiceError(RuntimeError):
    pass


SYSTEM_PROMPT = """
Tu es un expert en recrutement et amelioration de CV.
Analyse uniquement le contenu fourni par l'utilisateur.
Tu ne dois jamais inventer d'experience, diplome, competence, resultat chiffre
ou information personnelle absente du CV.
Si une information manque, signale le manque dans les points faibles ou recommandations.
Retourne exclusivement un JSON conforme au schema demande.
"""


USER_PROMPT_TEMPLATE = """
Analyse le CV ci-dessous selon cette grille sur 100 points :
- structure et lisibilite : 20 points ;
- clarte des experiences : 20 points ;
- mise en valeur de l'impact : 20 points ;
- pertinence des competences : 15 points ;
- qualite redactionnelle : 15 points ;
- completude des rubriques : 10 points.

Le score_total doit etre exactement la somme des sous-scores.
Pour chaque sous-score, fournis un score, le maximum attendu et une explication concrete.
Les recommandations doivent etre actionnables.
Les sections ameliorees doivent proposer des reformulations sans ajouter de faits absents du CV.

CV a analyser :
{cv_text}
"""


def analyze_cv_with_mistral(cv_text):
    api_key = settings.MISTRAL_API_KEY
    if not api_key:
        raise MistralServiceError("La cle API Mistral n'est pas configuree.")

    client = Mistral(api_key=api_key)
    try:
        response = client.chat.complete(
            model=settings.MISTRAL_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(cv_text=cv_text)},
            ],
            temperature=0.2,
            max_tokens=2500,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "cv_analysis_result",
                    "schema": CVAnalysisResult.model_json_schema(),
                    "strict": True,
                },
            },
            timeout_ms=settings.MISTRAL_TIMEOUT_MS,
        )
    except Exception as exc:
        logger.warning("Mistral CV analysis request failed: %s", exc.__class__.__name__)
        raise MistralServiceError("L'analyse IA a echoue. Veuillez reessayer plus tard.") from exc

    content = _extract_response_content(response)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise MistralServiceError("La reponse IA n'est pas un JSON valide.") from exc

    return validate_cv_analysis_result(payload)


def _extract_response_content(response):
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise MistralServiceError("La reponse IA est vide ou invalide.") from exc

    if isinstance(content, str) and content.strip():
        return content

    if isinstance(content, list):
        text_parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        text = "".join(text_parts).strip()
        if text:
            return text

    raise MistralServiceError("La reponse IA ne contient pas de texte exploitable.")
