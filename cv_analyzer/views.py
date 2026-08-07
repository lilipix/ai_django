from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView

from cv_analyzer.forms import CVAnalysisForm
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


class CVAnalysisCreateView(LoginRequiredMixin, CreateView):
    model = CVAnalysis
    form_class = CVAnalysisForm
    template_name = "cv_analyzer/analysis_create.html"

    def form_valid(self, form):
        analysis: CVAnalysis = form.save(commit=False)
        analysis.user = self.request.user
        analysis.save()
        analysis_id = int(analysis.pk)
        try:
            enqueue_cv_analysis(analysis_id)
        except Exception:
            analysis.mark_failed("Le lancement de l'analyse en arriere-plan a echoue.")
            messages.error(self.request, "Impossible de lancer l'analyse pour le moment.")
        else:
            messages.success(self.request, "Analyse lancee en arriere-plan.")

        self.object = analysis
        return super().form_valid(form)

    def form_invalid(self, form):
        # Les erreurs de validation du formulaire sont affichees par le template.
        messages.error(self.request, "Veuillez corriger les erreurs du formulaire.")
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("cv-analysis-detail", kwargs={"pk": self.object.pk})
