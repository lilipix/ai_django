from typing import Any, cast
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cv_analyzer.forms import CVAnalysisForm
from cv_analyzer.models import CVAnalysis
from cv_analyzer.services.mistral_service import MistralServiceError
from cv_analyzer.tasks import analyze_cv, enqueue_cv_analysis


User = get_user_model()


def build_valid_cv_text() -> str:
	# Texte de CV volontairement suffisant pour passer la validation du formulaire.
	return (
		"Expérience en gestion de projet et coordination d'équipe sur plusieurs "
		"missions longues. "
		"Compétences en communication, organisation et suivi de production. "
		"Objectif professionnel clairement défini avec résultats mesurables."
	)


class CVAnalysisFormTests(TestCase):
	def test_clean_cv_text_trims_and_accepts_valid_input(self):
		form = CVAnalysisForm(data={"cv_text": f"  {build_valid_cv_text()}  "})

		self.assertTrue(form.is_valid())
		self.assertEqual(form.cleaned_data["cv_text"], build_valid_cv_text())

	def test_clean_cv_text_rejects_short_input(self):
		form = CVAnalysisForm(data={"cv_text": "CV trop court"})

		self.assertFalse(form.is_valid())
		self.assertIn("au moins 100 caractères", form.errors["cv_text"][0])


class CVAnalysisModelTests(TestCase):
	# Ces tests vérifient les transitions d'état et le stockage des résultats sur le modèle.
	def setUp(self):
		self.user = User.objects.create_user(username="alice", password="password123")

	def test_str_includes_pk_user_and_status(self):
		analysis = CVAnalysis.objects.create(
			user=self.user,
			cv_text=build_valid_cv_text(),
		)

		self.assertEqual(
			str(analysis),
			f"Analyse CV #{analysis.pk} - {self.user} - {CVAnalysis.Status.PENDING}",
		)

	def test_mark_processing_clears_previous_error(self):
		analysis = CVAnalysis.objects.create(
			user=self.user,
			cv_text=build_valid_cv_text(),
			status=CVAnalysis.Status.FAILED,
			error_message="Ancienne erreur",
		)

		analysis.mark_processing()
		analysis.refresh_from_db()

		self.assertEqual(analysis.status, CVAnalysis.Status.PROCESSING)
		self.assertEqual(analysis.error_message, "")

	def test_mark_completed_sets_result_and_timestamp(self):
		analysis = CVAnalysis.objects.create(
			user=self.user,
			cv_text=build_valid_cv_text(),
		)

		result = {"score": 82, "summary": "Bon CV"}
		analysis.mark_completed(result)
		analysis.refresh_from_db()

		self.assertEqual(analysis.status, CVAnalysis.Status.COMPLETED)
		self.assertEqual(analysis.result, result)
		self.assertEqual(analysis.error_message, "")
		self.assertIsNotNone(analysis.completed_at)

	def test_mark_failed_sets_error_and_timestamp(self):
		analysis = CVAnalysis.objects.create(
			user=self.user,
			cv_text=build_valid_cv_text(),
		)

		analysis.mark_failed("Erreur de traitement")
		analysis.refresh_from_db()

		self.assertEqual(analysis.status, CVAnalysis.Status.FAILED)
		self.assertEqual(analysis.error_message, "Erreur de traitement")
		self.assertIsNotNone(analysis.completed_at)


class CVAnalysisViewTests(TestCase):
	# Ces tests couvrent les vues publiques et protégées, ainsi que le lancement d'analyse.
	def setUp(self):
		self.user = User.objects.create_user(username="alice", password="password123")
		self.other_user = User.objects.create_user(username="bob", password="password123")

	def test_signup_view_get_returns_form(self):
		# La page d'inscription doit exposer le formulaire d'enregistrement.
		response = self.client.get(reverse("signup"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "username")

	def test_signup_view_creates_user_and_logs_in(self):
		# Une inscription valide doit créer l'utilisateur puis le connecter.
		response = self.client.post(
			reverse("signup"),
			data={
				"username": "charlie",
				"password1": "StrongPassword123!",
				"password2": "StrongPassword123!",
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("cv-analysis-list"))
		self.assertTrue(User.objects.filter(username="charlie").exists())
		self.assertIn("_auth_user_id", self.client.session)

	def test_list_view_requires_authentication(self):
		# L'historique reste inaccessible tant que l'utilisateur n'est pas authentifié.
		response = self.client.get(reverse("cv-analysis-list"))

		self.assertEqual(response.status_code, 302)

	def test_list_view_shows_only_authenticated_user_analyses(self):
		own_analysis = CVAnalysis.objects.create(
			user=self.user,
			cv_text=build_valid_cv_text(),
		)
		other_analysis = CVAnalysis.objects.create(
			user=self.other_user,
			cv_text=build_valid_cv_text(),
		)

		self.client.force_login(self.user)
		response = self.client.get(reverse("cv-analysis-list"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, f"#{own_analysis.pk}")
		self.assertNotContains(response, f"#{other_analysis.pk}")

	def test_detail_view_returns_404_for_other_users_analysis(self):
		# Une analyse appartenant à un autre compte doit rester invisible.
		analysis = CVAnalysis.objects.create(
			user=self.other_user,
			cv_text=build_valid_cv_text(),
		)

		self.client.force_login(self.user)
		response = self.client.get(reverse("cv-analysis-detail", args=[analysis.pk]))

		self.assertEqual(response.status_code, 404)

	@patch("cv_analyzer.views.enqueue_cv_analysis")
	def test_create_view_creates_analysis_and_redirects(self, mock_enqueue):
		# On mocke Celery pour vérifier seulement la logique de vue et la redirection.
		self.client.force_login(self.user)
		response = self.client.post(
			reverse("cv-analysis-create"),
			data={"cv_text": build_valid_cv_text()},
		)

		analysis = CVAnalysis.objects.get(user=self.user)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(
			response["Location"],
			reverse("cv-analysis-detail", args=[analysis.pk]),
		)
		self.assertEqual(analysis.status, CVAnalysis.Status.PENDING)
		self.assertEqual(analysis.cv_text, build_valid_cv_text())
		mock_enqueue.assert_called_once_with(analysis.pk)

	@patch("cv_analyzer.views.enqueue_cv_analysis")
	def test_create_view_rejects_short_cv(self, mock_enqueue):
		# Un CV trop court doit être rejeté avant toute création en base.
		self.client.force_login(self.user)
		response = self.client.post(
			reverse("cv-analysis-create"),
			data={"cv_text": "CV trop court"},
		)

		self.assertEqual(response.status_code, 400)
		self.assertEqual(CVAnalysis.objects.count(), 0)
		mock_enqueue.assert_not_called()

	@patch("cv_analyzer.views.enqueue_cv_analysis", side_effect=Exception("Celery indisponible"))
	def test_create_view_marks_analysis_failed_if_enqueue_fails(self, mock_enqueue):
		# Si la file d'attente échoue, l'analyse doit être marquée comme échouée.
		self.client.force_login(self.user)
		response = self.client.post(
			reverse("cv-analysis-create"),
			data={"cv_text": build_valid_cv_text()},
		)

		analysis = CVAnalysis.objects.get(user=self.user)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response["Location"], reverse("cv-analysis-detail", args=[analysis.pk]))
		self.assertEqual(analysis.status, CVAnalysis.Status.FAILED)
		self.assertEqual(
			analysis.error_message,
			"Le lancement de l'analyse en arriere-plan a echoue.",
		)
		mock_enqueue.assert_called_once_with(analysis.pk)


class CVAnalysisTaskTests(TestCase):
	# Ces tests valident le wrapper Celery et le traitement asynchrone avec l'appel IA mocké.
	def setUp(self):
		self.user = User.objects.create_user(username="alice", password="password123")

	def test_enqueue_cv_analysis_calls_celery_delay(self):
		# Le wrapper ne doit faire qu'un appel delay vers la tâche Celery.
		with patch("cv_analyzer.tasks.analyze_cv.delay") as mock_delay:
			enqueue_cv_analysis(42)

		mock_delay.assert_called_once_with(42)

	@patch("cv_analyzer.tasks.analyze_cv_with_mistral")
	def test_analyze_cv_marks_analysis_completed(self, mock_analyze):
		# L'appel IA est mocké pour éviter tout accès réseau et simuler un succès.
		mock_analyze.return_value = {"score_total": 82, "summary": "Bon CV"}
		analysis = CVAnalysis.objects.create(user=self.user, cv_text=build_valid_cv_text())

		cast(Any, analyze_cv).run(analysis.pk)
		analysis.refresh_from_db()

		self.assertEqual(analysis.status, CVAnalysis.Status.COMPLETED)
		self.assertEqual(analysis.result, {"score_total": 82, "summary": "Bon CV"})
		self.assertEqual(analysis.error_message, "")
		self.assertIsNotNone(analysis.completed_at)
		mock_analyze.assert_called_once_with(analysis.cv_text)

	@patch("cv_analyzer.tasks.analyze_cv_with_mistral", side_effect=MistralServiceError("API indisponible"))
	def test_analyze_cv_marks_analysis_failed_when_api_errors(self, mock_analyze):
		# En cas d'erreur IA, le worker doit enregistrer un statut FAILED lisible.
		analysis = CVAnalysis.objects.create(user=self.user, cv_text=build_valid_cv_text())

		cast(Any, analyze_cv).run(analysis.pk)
		analysis.refresh_from_db()

		self.assertEqual(analysis.status, CVAnalysis.Status.FAILED)
		self.assertEqual(analysis.error_message, "API indisponible")
		self.assertIsNotNone(analysis.completed_at)
		mock_analyze.assert_called_once_with(analysis.cv_text)
