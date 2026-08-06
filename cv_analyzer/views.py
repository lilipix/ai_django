from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from cv_analyzer.models import CVAnalysis
from cv_analyzer.tasks import enqueue_cv_analysis


class SignUpView(CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy("cv-analysis-list")
    template_name = "registration/signup.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class CVAnalysisListView(LoginRequiredMixin, ListView):
    model = CVAnalysis
    context_object_name = "analyses"
    template_name = "cv_analyzer/analysis_list.html"

    def get_queryset(self):
        # Chaque utilisateur ne voit que son propre historique.
        return CVAnalysis.objects.filter(user=self.request.user)


class CVAnalysisDetailView(LoginRequiredMixin, DetailView):
    model = CVAnalysis
    context_object_name = "analysis"
    template_name = "cv_analyzer/analysis_detail.html"

    def get_queryset(self):
        # Une analyse appartenant a un autre utilisateur renverra une 404.
        return CVAnalysis.objects.filter(user=self.request.user)


class CVAnalysisCreateView(LoginRequiredMixin, View):
    template_name = "cv_analyzer/analysis_create.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        cv_text = request.POST.get("cv_text", "").strip()
        if len(cv_text) < 100:
            # Evite d'envoyer une soumission vide dans la file Celery.
            messages.error(request, "Le texte du CV doit contenir au moins 100 caracteres.")
            return render(request, self.template_name, {"cv_text": cv_text}, status=400)

        analysis: CVAnalysis = CVAnalysis.objects.create(user=request.user, cv_text=cv_text)
        analysis_id = int(analysis.pk)
        try:
            enqueue_cv_analysis(analysis_id)
        except Exception:
            analysis.mark_failed("Le lancement de l'analyse en arriere-plan a echoue.")
            messages.error(request, "Impossible de lancer l'analyse pour le moment.")
        else:
            messages.success(request, "Analyse lancee en arriere-plan.")

        return redirect("cv-analysis-detail", pk=analysis.pk)
