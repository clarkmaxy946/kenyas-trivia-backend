from django.urls import path

from .views import (
    CreateMatchView, HistoryView, MatchStatusView, ResumeView, RetryView,
    StartTurnView, SubmitTurnView, TeamNamesView,
)

urlpatterns = [
    path("", CreateMatchView.as_view()),
    path("resume/", ResumeView.as_view()),
    path("history/", HistoryView.as_view()),
    path("<str:match_id>/", MatchStatusView.as_view()),
    path("<str:match_id>/teams/", TeamNamesView.as_view()),
    path("<str:match_id>/retry/", RetryView.as_view()),
    path("<str:match_id>/turns/start/", StartTurnView.as_view()),
    path("<str:match_id>/turns/<str:turn_id>/submit/", SubmitTurnView.as_view()),
]