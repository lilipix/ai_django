from django.contrib import admin

from .models import CVAnalysis


@admin.register(CVAnalysis)
class CVAnalysisAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "created_at", "completed_at")
    list_filter = ("status", "created_at", "completed_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at", "completed_at")
