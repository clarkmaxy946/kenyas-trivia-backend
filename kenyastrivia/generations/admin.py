from django.contrib import admin

from .models import GenerationJob, GenerationLog

admin.site.register(GenerationJob)
admin.site.register(GenerationLog)