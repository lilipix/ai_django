from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CVAnalysisValidationError(ValueError):
    pass


class SubScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    score: int
    maximum: int
    explication: str

    @field_validator("label", "explication")
    @classmethod
    def validate_non_empty_string(cls, value):
        if not value.strip():
            raise ValueError("La valeur ne peut pas etre vide.")
        return value.strip()


class WeakPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titre: str
    explication: str

    @field_validator("titre", "explication")
    @classmethod
    def validate_non_empty_string(cls, value):
        if not value.strip():
            raise ValueError("La valeur ne peut pas etre vide.")
        return value.strip()


class CVSubScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structure_lisibilite: SubScore
    clarte_experiences: SubScore
    mise_en_valeur_impact: SubScore
    pertinence_competences: SubScore
    qualite_redactionnelle: SubScore
    completude_rubriques: SubScore

    @model_validator(mode="after")
    def validate_score_limits(self):
        expected_maximums = {
            "structure_lisibilite": 20,
            "clarte_experiences": 20,
            "mise_en_valeur_impact": 20,
            "pertinence_competences": 15,
            "qualite_redactionnelle": 15,
            "completude_rubriques": 10,
        }
        for field_name, maximum in expected_maximums.items():
            sub_score = getattr(self, field_name)
            if sub_score.maximum != maximum:
                raise ValueError(f"{field_name}.maximum doit valoir {maximum}.")
            if not 0 <= sub_score.score <= maximum:
                raise ValueError(f"{field_name}.score doit etre entre 0 et {maximum}.")
        return self

    def total(self):
        return sum(getattr(self, field_name).score for field_name in self.model_fields)


class CVAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score_total: Annotated[int, Field(ge=0, le=100)]
    sous_scores: CVSubScores
    points_forts: list[str]
    points_faibles: list[WeakPoint]
    recommandations: list[str]
    sections_ameliorees: dict[str, str]

    @field_validator("points_forts", "recommandations")
    @classmethod
    def validate_string_list(cls, value):
        cleaned = []
        for item in value:
            if not item.strip():
                raise ValueError("Les listes ne doivent pas contenir de chaine vide.")
            cleaned.append(item.strip())
        return cleaned

    @field_validator("sections_ameliorees")
    @classmethod
    def validate_sections(cls, value):
        cleaned = {}
        for key, section in value.items():
            if not key.strip() or not section.strip():
                raise ValueError("Les sections ameliorees ne doivent pas etre vides.")
            cleaned[key.strip()] = section.strip()
        return cleaned

    @model_validator(mode="after")
    def validate_total_score(self):
        if self.score_total != self.sous_scores.total():
            raise ValueError("Le score total doit correspondre a la somme des sous-scores.")
        return self


def validate_cv_analysis_result(data):
    try:
        return CVAnalysisResult.model_validate(data).model_dump()
    except ValueError as exc:
        raise CVAnalysisValidationError("La reponse IA ne respecte pas le schema attendu.") from exc
