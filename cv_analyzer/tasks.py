import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from cv_analyzer.models import CVAnalysis
from cv_analyzer.services.mistral_service import MistralServiceError, analyze_cv_with_mistral
from cv_analyzer.validation import CVAnalysisValidationError

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(), max_retries=0)
def analyze_cv(self, analysis_id):
    try:
        with transaction.atomic():
            analysis = CVAnalysis.objects.select_for_update().get(pk=analysis_id)
            if analysis.status != CVAnalysis.Status.PENDING:
                return
            analysis.mark_processing()

        result = analyze_cv_with_mistral(analysis.cv_text)
        analysis.mark_completed(result)
    except CVAnalysis.DoesNotExist:
        logger.warning("CV analysis task received an unknown analysis id.")
    except (MistralServiceError, CVAnalysisValidationError) as exc:
        _mark_failed(analysis_id, str(exc))
    except Exception as exc:
        logger.exception("Unexpected CV analysis task failure for analysis id %s.", analysis_id)
        _mark_failed(analysis_id, "Une erreur inattendue est survenue pendant l'analyse.")
        raise exc


def _mark_failed(analysis_id, message):
    now = timezone.now()
    CVAnalysis.objects.filter(pk=analysis_id).update(
        status=CVAnalysis.Status.FAILED,
        error_message=message,
        completed_at=now,
        updated_at=now,
    )
