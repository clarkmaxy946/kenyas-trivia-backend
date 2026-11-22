from django.contrib import admin

from .models import Match, Team, Turn

admin.site.register(Match)
admin.site.register(Team)
admin.site.register(Turn)