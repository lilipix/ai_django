from django.urls import path

from . import views

urlpatterns = [
    path("", views.CVAnalysisListView.as_view(), name="cv-analysis-list"),
    path("analyses/new/", views.CVAnalysisCreateView.as_view(), name="cv-analysis-create"),
    path("analyses/<int:pk>/", views.CVAnalysisDetailView.as_view(), name="cv-analysis-detail"),
]
