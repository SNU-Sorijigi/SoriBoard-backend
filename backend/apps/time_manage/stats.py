"""통계 페이지용 집계 API.

play history = TimeMusic ⨝ TimeInfo. 모든 엔드포인트는 공통 필터(`build_timemusic_filter`)
로 TimeMusic 쿼리셋을 만든 뒤 집계한다. 공통 응답 봉투:

    {
        "filters": {...},          # 적용된 필터(디버깅/표시용)
        "total_plays": <int>,      # 필터 적용 후 전체 선곡 수
        "labels": [...],           # 차트 x축/범례 라벨
        "values": [...],           # labels 와 1:1 대응하는 수치
        "items":  [{id, name, count}, ...]  # drill-down 용 식별자 포함
    }

필터 파라미터 형식이 틀리면 400 과 DRF 필드별 오류(예: {"start": [...]})를 돌려준다.
composer_id/music_id/player_id/conductor_id/orchestra_id 를 주면 그 대상의 선곡만
센다(차트 items 의 id 로 drill-down).

stats/firsts/?kind=composer|work 는 클럽 전체에서 처음 튼 날(필터와 무관)이 필터
기간에 드는 작곡가·곡을 처음 튼 날, 이름 순으로 준다(학기 결산). items 는
{id, name, count, first_played}, count 는 필터에 드는 선곡 수.
"""

import datetime
import math
from collections import defaultdict

from django.db.models import (
    Case,
    CharField,
    Count,
    F,
    Max,
    Min,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Concat, TruncMonth, TruncWeek
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Composer, Semester, TimeMusic

# ---------------------------------------------------------------------------
# 시대 구분 (작곡가 출생년도 기준 휴리스틱 + era_override 수동 보정)
# ---------------------------------------------------------------------------
# (라벨, 상한) — birth_year < 상한 이면 해당 시대. 위에서부터 처음 매칭되는 구간.
# 5분류로 단순화(중세=르네상스 포함, 근현대=20세기 이후). 경계 사례는 era_override 로 보정.
ERA_BUCKETS = [
    ("중세", 1600),  # 르네상스 이전·다성음악 포함
    ("바로크", 1710),
    ("고전", 1770),
    ("낭만", 1880),
    ("근현대", None),  # 1880 이상
]
ERA_ORDER = [label for label, _ in ERA_BUCKETS] + ["미상"]


def era_for(birth_year, override=None):
    """출생년도(+보정)를 시대 라벨로 변환.

    보정값은 admin 에서 자유 입력이라, ERA_ORDER 에 없는 라벨(예: "20세기")은
    무시하고 출생년도로 분류한다. 그대로 쓰면 차트 어느 칸에도 들지 않았다.
    """
    if override in ERA_ORDER:
        return override
    if birth_year is None:
        return "미상"
    for label, upper in ERA_BUCKETS:
        if upper is None or birth_year < upper:
            return label
    return "미상"


def era_counts(qs):
    """필터된 TimeMusic 쿼리셋 → {시대: 선곡수}. 작곡가 없는 행은 '미상'."""
    rows = qs.values(
        "music__composer__birth_year",
        "music__composer__era_override",
    ).annotate(count=Count("id", distinct=True))
    buckets = {label: 0 for label in ERA_ORDER}
    for row in rows:
        era = era_for(
            row["music__composer__birth_year"],
            row["music__composer__era_override"],
        )
        buckets[era] = buckets.get(era, 0) + row["count"]
    return buckets


# ---------------------------------------------------------------------------
# 장르 구분 (제목 + 편성 휴리스틱)
# ---------------------------------------------------------------------------
# 데이터는 정확하지 않으므로 "대부분 맞는" 분류가 목표다. 위에서부터 처음
# 매칭되는 장르로 분류한다. 지휘자 표기는 누락이 잦아 오케스트라 유무를 기준으로
# 삼고, 성악(가곡/오페라/합창/종교음악)은 연주자 역할로 먼저 걸러낸다.
GENRE_ORDER = ["교향곡", "협주곡", "관현악곡", "실내악곡", "독주곡", "기타"]

# 성악으로 보는 연주자 역할(instrument 칸 값). 정확히 일치할 때만 성악으로 본다.
# 부분 문자열로 보면 "콘트라베이스"가 "베이스"에, "알토 리코더"가 "알토"에 걸려
# 기악이 성악으로 오분류되므로 집합 일치를 쓴다.
_VOCAL_ROLES = frozenset(
    {
        "성악",
        "성악가",
        "보컬",
        "소프라노",
        "메조소프라노",
        "메조 소프라노",
        "메조",
        "알토",
        "콘트랄토",
        "테너",
        "카운터테너",
        "카운터 테너",
        "바리톤",
        "베이스바리톤",
        "베이스 바리톤",
        "베이스",
        "낭독",
        "내레이션",
        "합창",
        "합창단",
    }
)
# 제목에 들어가면 성악/극/종교음악으로 보는 키워드.
_VOCAL_TITLE_TERMS = (
    "오페라",
    "미사",
    "레퀴엠",
    "오라토리오",
    "칸타타",
    "수난곡",
    "가곡",
    "모테트",
    "마드리갈",
    "합창",
    "아리아",
    "성가",
    "찬트",
    "떼데움",
    "테데움",
    "마니피카트",
    "스타바트",
)


def _is_vocal_role(instrument):
    return (instrument or "").strip() in _VOCAL_ROLES


def genre_for(title, has_orchestra, instruments):
    """제목·오케스트라 유무·연주자 instrument 목록 → 장르 라벨.

    instruments 는 성악을 포함한 연주자 역할 문자열 리스트(예: ["피아노"]).
    """
    title = title or ""
    instruments = instruments or []

    # 1) 성악/극/종교음악: 성악 연주자가 있거나 제목 키워드가 잡히면.
    if any(_is_vocal_role(i) for i in instruments) or any(
        term in title for term in _VOCAL_TITLE_TERMS
    ):
        return "기타"

    # 여기부터는 기악으로 본다.
    n_players = len(instruments)

    # 2) 교향곡: 제목에 "교향곡".
    if "교향곡" in title:
        return "교향곡"

    # 3) 협주곡: 제목이 협주곡/concerto 거나(단, "관현악을 위한 협주곡" 제외),
    #    오케스트라 + 협연자(1명 이상).
    is_concerto_title = (
        "협주곡" in title or "concerto" in title.lower()
    ) and "관현악" not in title
    if is_concerto_title or (has_orchestra and n_players >= 1):
        return "협주곡"

    # 4) 관현악곡: 오케스트라 편성(교향곡·협주곡이 아닌).
    if has_orchestra:
        return "관현악곡"

    # 5) 독주곡: 연주자 1명.
    if n_players == 1:
        return "독주곡"

    # 6) 실내악곡: 연주자 2~8명.
    if 2 <= n_players <= 8:
        return "실내악곡"

    # 7) 기타: 위에 해당 없음(편성 정보 부족 포함).
    return "기타"


# ---------------------------------------------------------------------------
# 다양성 지표 (엔트로피/고른정도)
# ---------------------------------------------------------------------------
def diversity_metrics(counts, n_possible):
    """버킷별 선곡수 → 다양성 지표.

    - entropy: 섀넌 엔트로피 H = -Σ p·ln(p) (nats).
    - evenness: H 를 ln(n_possible) 로 정규화한 [0,1] 값. 가능한 모든 버킷을
      고르게 쓸수록 1 에 가깝다(다양성 목표 지표).
    """
    vals = [v for v in counts.values() if v > 0]
    n = sum(vals)
    if n == 0:
        return {"entropy": 0.0, "evenness": 0.0}
    entropy = 0.0
    for v in vals:
        p = v / n
        entropy -= p * math.log(p)
    max_entropy = math.log(n_possible) if n_possible > 1 else 0.0
    evenness = entropy / max_entropy if max_entropy > 0 else 0.0
    return {
        "entropy": round(entropy, 4),
        "evenness": round(evenness, 4),
    }


def plays_with_instruments(qs, *fields):
    """필터된 TimeMusic 쿼리셋 → (선곡 dict 목록, {선곡 id: 연주자 instrument 목록}).

    선곡 dict 는 id, music_id, music__title, orchestra_id 와 fields 를 담는다.
    모델 인스턴스(+ players prefetch)로 읽으면 5,000곡에 0.5초가 넘게 걸려
    values() 로 읽는다. players(M2M)는 따로 한 번에 읽어 행을 부풀리지 않고,
    distinct 쿼리셋이라 필터 조인의 중복 행은 한 dict 로 접힌다.
    """
    plays = list(qs.values("id", "music_id", "music__title", "orchestra_id", *fields))
    instruments = defaultdict(list)
    if plays:
        rows = TimeMusic.players.through.objects.filter(
            timemusic_id__in=qs.values("id")
        ).values_list("timemusic_id", "player__instrument")
        for play_id, instrument in rows:
            instruments[play_id].append(instrument)
    return plays, instruments


def genre_of(play, instruments):
    """plays_with_instruments 의 선곡 dict 하나 → 장르 라벨."""
    return genre_for(
        play["music__title"],
        play["orchestra_id"] is not None,
        instruments[play["id"]],
    )


def genre_counts(qs):
    """필터된 TimeMusic 쿼리셋 → {장르: 선곡수}. 선곡마다 1회 센다."""
    buckets = {label: 0 for label in GENRE_ORDER}
    plays, instruments = plays_with_instruments(qs)
    for play in plays:
        buckets[genre_of(play, instruments)] += 1
    return buckets


# ---------------------------------------------------------------------------
# 공통 필터
# ---------------------------------------------------------------------------
def _semester_date_range(semester_id):
    """학기 id → (start_date, end_date).

    Semester 모델에 학기 시작/종료 날짜가 없어 관례적으로 매핑한다.
    1학기 = 해당 연도 3/1 ~ 8/31, 2학기 = 해당 연도 9/1 ~ 다음 연도 2/말일.
    (근사치이며, 정확한 학기 경계가 필요하면 Semester 에 날짜 필드 추가 필요.)
    """
    try:
        semester = Semester.objects.get(id=semester_id)
    except Semester.DoesNotExist:
        return None, None
    if semester.semester_num == 1:
        return (
            datetime.date(semester.year, 3, 1),
            datetime.date(semester.year, 8, 31),
        )
    # 2월 말일은 다음 해 3/1 의 전날(윤년이면 2/29).
    return (
        datetime.date(semester.year, 9, 1),
        datetime.date(semester.year + 1, 3, 1) - datetime.timedelta(days=1),
    )


# id 는 SQLite INTEGER(64비트) 범위여야 한다. 넘으면 DB 드라이버가 OverflowError(500).
_ID_RANGE = {"min_value": -(2**63), "max_value": 2**63 - 1}


class StatsFilterSerializer(serializers.Serializer):
    """공통 필터 파라미터 검증. 빈 값(?start=)은 지정하지 않은 것으로 본다."""

    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    semester_id = serializers.IntegerField(required=False, **_ID_RANGE)
    user_id = serializers.IntegerField(required=False, **_ID_RANGE)
    composer_id = serializers.IntegerField(required=False, **_ID_RANGE)
    music_id = serializers.IntegerField(required=False, **_ID_RANGE)
    player_id = serializers.IntegerField(required=False, **_ID_RANGE)
    conductor_id = serializers.IntegerField(required=False, **_ID_RANGE)
    orchestra_id = serializers.IntegerField(required=False, **_ID_RANGE)


# 대상 id 파라미터 → TimeMusic 필드. player_id 는 M2M 이라 따로 처리한다.
_ID_FILTERS = {
    "composer_id": "music__composer_id",
    "music_id": "music_id",
    "conductor_id": "conductor_id",
    "orchestra_id": "orchestra_id",
}


def build_timemusic_filter(params):
    """쿼리 파라미터를 TimeMusic 필터(Q 객체)로 변환.

    지원 파라미터: start, end (YYYY-MM-DD), semester_id, user_id, include_mentees,
    composer_id, music_id, player_id, conductor_id, orchestra_id (모두 AND).
    적용된 필터 정보를 함께 돌려준다(응답 봉투의 filters 필드).
    날짜/id 형식이 틀리면 ValidationError(400)를 던진다.
    """
    filters = StatsFilterSerializer(data=params)
    filters.is_valid(raise_exception=True)
    q = Q()
    applied = {"scope": "all"}

    start = filters.validated_data.get("start")
    end = filters.validated_data.get("end")
    semester_id = filters.validated_data.get("semester_id")

    if semester_id is not None:
        s_start, s_end = _semester_date_range(semester_id)
        if s_start:
            q &= Q(time__date__gte=s_start, time__date__lte=s_end)
            applied["semester_id"] = str(semester_id)
            applied["start"] = str(s_start)
            applied["end"] = str(s_end)
    else:
        if start:
            q &= Q(time__date__gte=start)
            applied["start"] = str(start)
        if end:
            q &= Q(time__date__lte=end)
            applied["end"] = str(end)

    user_id = filters.validated_data.get("user_id")
    if user_id is not None:
        include_mentees = str(params.get("include_mentees", "")).lower() in (
            "1",
            "true",
            "yes",
        )
        if include_mentees:
            q &= Q(time__users__id=user_id) | Q(time__mentees__id=user_id)
        else:
            q &= Q(time__users__id=user_id)
        applied["scope"] = "individual"
        applied["user_id"] = user_id
        applied["include_mentees"] = include_mentees

    for param, field in _ID_FILTERS.items():
        value = filters.validated_data.get(param)
        if value is not None:
            q &= Q(**{field: value})
            applied[param] = value

    player_id = filters.validated_data.get("player_id")
    if player_id is not None:
        # 조인 대신 서브쿼리: 한 곡이 여러 행이 되지 않고, soloists 집계의
        # players 조인도 이 필터에 묶이지 않아 함께 연주한 연주자까지 센다.
        through = TimeMusic.players.through.objects.filter(player_id=player_id)
        q &= Q(id__in=through.values("timemusic_id"))
        applied["player_id"] = player_id

    return q, applied


def base_queryset(request):
    """필터가 적용된 TimeMusic 쿼리셋과 filters 정보를 반환.

    M2M(time__users) 조인 시 중복 행이 생길 수 있어 distinct() 적용.
    distinct() 는 values().annotate() 그룹 안의 중복 행은 없애지 못하므로
    그룹별 선곡 수는 Count("id", distinct=True) 로 센다(include_mentees 의
    users·mentees 조인은 한 곡을 여러 행으로 만든다).
    """
    q, applied = build_timemusic_filter(request.query_params)
    qs = TimeMusic.objects.filter(q).distinct()
    return qs, applied


def _limit(request, default=15):
    try:
        return max(1, min(100, int(request.query_params.get("limit", default))))
    except (TypeError, ValueError):
        return default


def _label(blank, alone, *parts):
    """응답에 보이는 이름(라벨)과 같은 문자열의 SQL 식. 동점 정렬용.

    blank 필드가 비면 alone 필드만, 아니면 parts(필드 이름 또는 Value)를 잇는다.
    SQLite 는 문자열을 코드 포인트 순으로 비교하므로 파이썬의 정렬과 같다.
    """
    return Case(
        When(**{blank: ""}, then=F(alone)),
        default=Concat(*parts),
        output_field=CharField(),
    )


def _top_by(qs, group_field, name_field, limit, id_field=None):
    """공통 top-N 집계. labels/values/items 봉투 부분을 만든다.

    선곡 수가 같으면 이름, 그다음 id 순(limit 의 경계도 이 순서를 따른다).
    """
    id_field = id_field or group_field
    rows = (
        qs.values(id_field, name_field)
        .annotate(count=Count("id", distinct=True))
        .order_by("-count", name_field, id_field)[:limit]
    )
    labels, values, items = [], [], []
    for row in rows:
        name = row[name_field]
        labels.append(name)
        values.append(row["count"])
        items.append({"id": row[id_field], "name": name, "count": row["count"]})
    return labels, values, items


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------
class StatsSummaryView(APIView):
    """헤더 KPI 카드용 요약 수치.

    sessions 는 필터에 드는 곡이 있는 타임 수(곡 없는 타임은 세지 않는다),
    requested 는 필터에 드는 신청곡 수.
    """

    def get(self, request):
        qs, applied = base_queryset(request)
        agg = qs.aggregate(
            total_plays=Count("id"),
            sessions=Count("time", distinct=True),
            requested=Count("id", filter=Q(is_requested=True)),
            composers=Count("music__composer", distinct=True),
            works=Count("music", distinct=True),
            conductors=Count("conductor", distinct=True),
            orchestras=Count("orchestra", distinct=True),
        )
        dates = qs.aggregate(first=Min("time__date"), last=Max("time__date"))
        return Response(
            {
                "filters": applied,
                "total_plays": agg["total_plays"],
                "sessions": agg["sessions"],
                "requested": agg["requested"],
                "composers": agg["composers"],
                "works": agg["works"],
                "conductors": agg["conductors"],
                "orchestras": agg["orchestras"],
                "date_start": str(dates["first"]) if dates["first"] else None,
                "date_end": str(dates["last"]) if dates["last"] else None,
            }
        )


class TopComposersStatsView(APIView):
    def get(self, request):
        qs, applied = base_queryset(request)
        total = qs.count()
        labels, values, items = _top_by(
            qs.exclude(music__composer__isnull=True),
            "music__composer__id",
            "music__composer__name",
            _limit(request),
        )
        return Response(
            {
                "filters": applied,
                "total_plays": total,
                "labels": labels,
                "values": values,
                "items": items,
            }
        )


class TopWorksStatsView(APIView):
    """많이 선곡된 곡. items 에 작곡가 id 와 첫·마지막 선곡일을 더한다.

    first_played/last_played 는 필터와 상관없이 그 곡의 전체 선곡 중 첫·마지막
    날짜다(기간을 좁혀도 "처음 튼 날"이 바뀌지 않는다). 선곡 수가 같으면
    라벨("작곡가 - 곡"), 그다음 id 순.
    """

    def get(self, request):
        qs, applied = base_queryset(request)
        total = qs.count()
        limit = _limit(request)
        rows = list(
            qs.exclude(music__isnull=True)
            .values(
                "music__id",
                "music__title",
                "music__composer__id",
                "music__composer__name",
            )
            .annotate(count=Count("id", distinct=True))
            .order_by(
                "-count",
                _label(
                    "music__composer__name",
                    "music__title",
                    "music__composer__name",
                    Value(" - "),
                    "music__title",
                ),
                "music__id",
            )[:limit]
        )
        dates = {}
        if rows:
            dates = {
                span["music_id"]: span
                for span in TimeMusic.objects.filter(
                    music_id__in=[row["music__id"] for row in rows]
                )
                .values("music_id")
                .annotate(first=Min("time__date"), last=Max("time__date"))
            }
        labels, values, items = [], [], []
        for row in rows:
            composer = row["music__composer__name"] or ""
            title = row["music__title"]
            label = f"{composer} - {title}" if composer else title
            played = dates[row["music__id"]]
            labels.append(label)
            values.append(row["count"])
            items.append(
                {
                    "id": row["music__id"],
                    "name": label,
                    "count": row["count"],
                    "composer_id": row["music__composer__id"],
                    "first_played": str(played["first"]),
                    "last_played": str(played["last"]),
                }
            )
        return Response(
            {
                "filters": applied,
                "total_plays": total,
                "labels": labels,
                "values": values,
                "items": items,
            }
        )


class TopConductorsStatsView(APIView):
    def get(self, request):
        qs, applied = base_queryset(request)
        total = qs.count()
        labels, values, items = _top_by(
            qs.exclude(conductor__isnull=True),
            "conductor__id",
            "conductor__name",
            _limit(request),
        )
        return Response(
            {
                "filters": applied,
                "total_plays": total,
                "labels": labels,
                "values": values,
                "items": items,
            }
        )


class TopOrchestrasStatsView(APIView):
    def get(self, request):
        qs, applied = base_queryset(request)
        total = qs.count()
        labels, values, items = _top_by(
            qs.exclude(orchestra__isnull=True),
            "orchestra__id",
            "orchestra__name",
            _limit(request),
        )
        return Response(
            {
                "filters": applied,
                "total_plays": total,
                "labels": labels,
                "values": values,
                "items": items,
            }
        )


class TopSoloistsStatsView(APIView):
    """많이 등장한 연주자(독주자·협연자 등). players(M2M) 기준 집계.

    악기에 상관없이 모든 연주자를 한데 모아 등장 선곡 수로 순위를 매긴다.
    라벨은 "이름 (악기)" 형태. M2M 조인으로 한 곡이 부풀지 않도록 곡은
    distinct 로 센다. 선곡 수가 같으면 라벨, 그다음 id 순.
    """

    def get(self, request):
        qs, applied = base_queryset(request)
        total = qs.count()
        rows = (
            qs.exclude(players__isnull=True)
            .values("players__id", "players__name", "players__instrument")
            .annotate(count=Count("id", distinct=True))
            .order_by(
                "-count",
                _label(
                    "players__instrument",
                    "players__name",
                    "players__name",
                    Value(" ("),
                    "players__instrument",
                    Value(")"),
                ),
                "players__id",
            )[: _limit(request)]
        )
        labels, values, items = [], [], []
        for row in rows:
            name = row["players__name"]
            instrument = row["players__instrument"]
            label = f"{name} ({instrument})" if instrument else name
            labels.append(label)
            values.append(row["count"])
            items.append(
                {"id": row["players__id"], "name": label, "count": row["count"]}
            )
        return Response(
            {
                "filters": applied,
                "total_plays": total,
                "labels": labels,
                "values": values,
                "items": items,
            }
        )


def _next_period(period, bucket):
    """다음 주(월요일) 또는 다음 달(1일)."""
    if bucket == "week":
        return period + datetime.timedelta(days=7)
    if period.month == 12:
        return period.replace(year=period.year + 1, month=1)
    return period.replace(month=period.month + 1)


class PlaysOverTimeStatsView(APIView):
    """기간별 선곡 추이. ?bucket=week|month|semester (기본 month).

    week·month 는 첫 선곡과 마지막 선곡 사이의 빈 버킷도 0 으로 준다(필터의
    start/end 까지 늘리지는 않는다). semester 는 선곡이 있는 학기만 준다.
    """

    def get(self, request):
        qs, applied = base_queryset(request)
        total = qs.count()
        bucket = request.query_params.get("bucket", "month")
        if bucket not in ("week", "month", "semester"):
            bucket = "month"

        if bucket == "week":
            trunc = TruncWeek("time__date")
        else:
            trunc = TruncMonth("time__date")

        rows = (
            qs.annotate(period=trunc)
            .values("period")
            .annotate(count=Count("id", distinct=True))
            .order_by("period")
        )

        if bucket == "semester":
            # month 결과를 학기 버킷(YYYY-N)으로 접는다.
            buckets = {}
            for row in rows:
                period = row["period"]
                if period is None:
                    continue
                sem = 1 if 3 <= period.month <= 8 else 2
                year = period.year if period.month >= 3 else period.year - 1
                key = f"{year}-{sem}"
                buckets[key] = buckets.get(key, 0) + row["count"]
            labels = sorted(buckets.keys())
            values = [buckets[k] for k in labels]
        else:
            # 첫 선곡과 마지막 선곡 사이의 빈 주·월은 0 으로 채운다.
            counts = {
                row["period"]: row["count"] for row in rows if row["period"] is not None
            }
            labels, values = [], []
            period, last = (min(counts), max(counts)) if counts else (None, None)
            while period is not None:
                labels.append(
                    period.strftime("%Y-%m-%d" if bucket == "week" else "%Y-%m")
                )
                values.append(counts.get(period, 0))
                # 마지막 버킷 다음은 만들지 않는다(9999년 12월 다음은 없다).
                period = _next_period(period, bucket) if period < last else None

        return Response(
            {
                "filters": {**applied, "bucket": bucket},
                "total_plays": total,
                "labels": labels,
                "values": values,
                "items": [],
            }
        )


class EraDistributionStatsView(APIView):
    """시대(중세/바로크/고전/낭만/근현대) 분포. 작곡가 출생년도 휴리스틱 사용."""

    def get(self, request):
        qs, applied = base_queryset(request)
        total = qs.count()
        buckets = era_counts(qs)

        labels, values, items = [], [], []
        for label in ERA_ORDER:
            count = buckets.get(label, 0)
            if count == 0:
                continue
            labels.append(label)
            values.append(count)
            items.append({"id": label, "name": label, "count": count})

        unknown = buckets.get("미상", 0)
        unknown_share = round(unknown / total, 4) if total else 0

        return Response(
            {
                "filters": applied,
                "total_plays": total,
                "labels": labels,
                "values": values,
                "items": items,
                "unknown_share": unknown_share,
            }
        )


class GenreDistributionStatsView(APIView):
    """장르(교향곡/협주곡/관현악곡/실내악곡/독주곡/기타) 분포. 편성 휴리스틱 사용."""

    def get(self, request):
        qs, applied = base_queryset(request)
        total = qs.count()
        buckets = genre_counts(qs)

        labels, values, items = [], [], []
        for label in GENRE_ORDER:
            count = buckets.get(label, 0)
            if count == 0:
                continue
            labels.append(label)
            values.append(count)
            items.append({"id": label, "name": label, "count": count})

        return Response(
            {
                "filters": applied,
                "total_plays": total,
                "labels": labels,
                "values": values,
                "items": items,
            }
        )


# 다양성 정규화에 쓰는 "가능한 버킷 수": 시대는 미상 제외 5개, 장르는 6개.
_ERA_POSSIBLE = len(ERA_BUCKETS)
_GENRE_POSSIBLE = len(GENRE_ORDER)


class DiversityStatsView(APIView):
    """선곡 다양성 지표.

    한 번의 순회로 시대·장르를 분류해 (1) 기간 전체 요약(분포 + 엔트로피/
    고른정도), (2) 기간 버킷별(?bucket=week|month, 기본 week) 시계열
    (선곡수·고유 곡수·시대 고른정도·장르 고른정도)을 함께 돌려준다.

    주간은 표본이 적어 고른정도가 출렁이므로, 프런트는 보통 선곡수는 주간으로,
    다양성은 월간/학기 요약으로 함께 보여준다.
    """

    def get(self, request):
        qs, applied = base_queryset(request)
        bucket = request.query_params.get("bucket", "week")
        if bucket not in ("week", "month"):
            bucket = "week"

        plays, instruments = plays_with_instruments(
            qs,
            "time__date",
            "music__composer__id",
            "music__composer__birth_year",
            "music__composer__era_override",
        )

        era_all = defaultdict(int)
        genre_all = defaultdict(int)
        works = set()
        composers = set()
        per_era = defaultdict(lambda: defaultdict(int))
        per_genre = defaultdict(lambda: defaultdict(int))
        per_plays = defaultdict(int)
        per_works = defaultdict(set)

        total = len(plays)
        for play in plays:
            date = play["time__date"]
            if bucket == "week":
                start = date - datetime.timedelta(days=date.weekday())
                key = start.strftime("%Y-%m-%d")
            else:
                key = date.strftime("%Y-%m")

            composer_id = play["music__composer__id"]
            era = (
                era_for(
                    play["music__composer__birth_year"],
                    play["music__composer__era_override"],
                )
                if composer_id
                else "미상"
            )
            genre = genre_of(play, instruments)

            era_all[era] += 1
            genre_all[genre] += 1
            per_era[key][era] += 1
            per_genre[key][genre] += 1
            per_plays[key] += 1
            if play["music_id"]:
                works.add(play["music_id"])
                per_works[key].add(play["music_id"])
            if composer_id:
                composers.add(composer_id)

        # 기간 전체 요약 분포.
        era_known = {e: c for e, c in era_all.items() if e != "미상"}
        era_labels = [l for l in ERA_ORDER if l != "미상" and era_all.get(l)]
        era_values = [era_all[l] for l in era_labels]
        genre_labels = [l for l in GENRE_ORDER if genre_all.get(l)]
        genre_values = [genre_all[l] for l in genre_labels]
        unknown = era_all.get("미상", 0)

        summary = {
            "distinct_works": len(works),
            "distinct_composers": len(composers),
            "era": {
                "labels": era_labels,
                "values": era_values,
                "unknown_share": round(unknown / total, 4) if total else 0,
                **diversity_metrics(era_known, _ERA_POSSIBLE),
            },
            "genre": {
                "labels": genre_labels,
                "values": genre_values,
                **diversity_metrics(genre_all, _GENRE_POSSIBLE),
            },
        }

        # 버킷별 시계열.
        labels = sorted(per_plays.keys())
        timeline = {
            "bucket": bucket,
            "labels": labels,
            "plays": [per_plays[k] for k in labels],
            "distinct_works": [len(per_works[k]) for k in labels],
            "era_evenness": [
                diversity_metrics(
                    {e: c for e, c in per_era[k].items() if e != "미상"},
                    _ERA_POSSIBLE,
                )["evenness"]
                for k in labels
            ],
            "genre_evenness": [
                diversity_metrics(per_genre[k], _GENRE_POSSIBLE)["evenness"]
                for k in labels
            ],
        }

        return Response(
            {
                "filters": {**applied, "bucket": bucket},
                "total_plays": total,
                "summary": summary,
                "timeline": timeline,
            }
        )


class FirstsQuerySerializer(StatsFilterSerializer):
    """stats/firsts 파라미터. kind 가 비면 composer."""

    kind = serializers.ChoiceField(
        choices=["composer", "work"], required=False, allow_blank=True
    )


class FirstPlaysStatsView(APIView):
    """기간 안에 처음 선곡된 작곡가·곡(학기 결산). ?kind=composer|work (기본 composer).

    처음 튼 날(first_played)은 필터와 상관없이 클럽 전체 선곡 중 첫 날짜다.
    그 날짜가 필터 기간(start/end, 또는 학기)에 들고 필터에 드는 선곡이 있는
    대상만, 처음 튼 날·이름·id 순으로 모두 준다. count 는 필터에 드는 선곡 수.
    기간을 주지 않으면 필터에 드는 모든 대상이 해당한다.
    """

    def get(self, request):
        params = FirstsQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        kind = params.validated_data.get("kind") or "composer"
        qs, applied = base_queryset(request)
        total = qs.count()

        if kind == "composer":
            id_field, own_field = "music__composer__id", "music__composer_id"
            fields = [id_field, "music__composer__name"]
        else:
            id_field, own_field = "music__id", "music_id"
            fields = [id_field, "music__title", "music__composer__name"]
        first = (
            TimeMusic.objects.filter(**{own_field: OuterRef(id_field)})
            .order_by("time__date")
            .values("time__date")[:1]
        )
        rows = (
            qs.exclude(**{f"{id_field}__isnull": True})
            .values(*fields)
            .annotate(first_played=Subquery(first))
        )
        # 끝 날짜는 따로 볼 필요가 없다: 첫 선곡일은 필터에 드는 선곡일보다 늦지 않다.
        if "start" in applied:
            rows = rows.filter(
                first_played__gte=datetime.date.fromisoformat(applied["start"])
            )
        rows = rows.annotate(count=Count("id", distinct=True)).order_by()

        items = []
        for row in rows:
            if kind == "composer":
                name = row["music__composer__name"]
            else:
                composer = row["music__composer__name"] or ""
                title = row["music__title"]
                name = f"{composer} - {title}" if composer else title
            items.append(
                {
                    "id": row[id_field],
                    "name": name,
                    "count": row["count"],
                    "first_played": str(row["first_played"]),
                }
            )
        items.sort(key=lambda item: (item["first_played"], item["name"], item["id"]))
        return Response(
            {
                "filters": {**applied, "kind": kind},
                "total_plays": total,
                "labels": [item["name"] for item in items],
                "values": [item["count"] for item in items],
                "items": items,
            }
        )
