from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsAccount

from . import services


def _body(request):
    return request.data if isinstance(request.data, dict) else {}


class CreateMatchView(APIView):
    def post(self, request):
        return Response(services.create_match(request.user), status=status.HTTP_201_CREATED)


class MatchStatusView(APIView):
    def get(self, request, match_id):
        return Response(services.get_status(request.user, match_id))


class TeamNamesView(APIView):
    def post(self, request, match_id):
        return Response(services.submit_team_names(request.user, match_id, _body(request).get("names")))


class RetryView(APIView):
    def post(self, request, match_id):
        return Response(services.retry(request.user, match_id))


class StartTurnView(APIView):
    def post(self, request, match_id):
        return Response(services.start_turn(request.user, match_id), status=status.HTTP_201_CREATED)


class SubmitTurnView(APIView):
    def post(self, request, match_id, turn_id):
        return Response(services.submit_turn(request.user, match_id, turn_id, request.data))


class ResumeView(APIView):
    def get(self, request):
        return Response(services.resume(request.user))


class HistoryView(APIView):
    permission_classes = [IsAccount]

    def get(self, request):
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            page = 1
        return Response(services.history(request.user, page))