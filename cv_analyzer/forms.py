from django import forms

from cv_analyzer.models import CVAnalysis


class CVAnalysisForm(forms.ModelForm):
    class Meta:
        model = CVAnalysis
        fields = ["cv_text"]
        widgets = {
            "cv_text": forms.Textarea(
                attrs={
                    "rows": 15,
                    "placeholder": "Collez ici le texte de votre CV…",
                }
            )
        }

    def clean_cv_text(self):
        cv_text = self.cleaned_data["cv_text"].strip()

        if len(cv_text) < 100:
            raise forms.ValidationError(
                "Le texte du CV doit contenir au moins 100 caractères."
            )

        return cv_text