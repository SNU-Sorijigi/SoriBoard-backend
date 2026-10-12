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
"""

import datetime
import math
from collections import defaultdict

from django.db.models import Count, Max, Min, Q
from django.db.models.functions import TruncMonth, TruncWeek
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
    """출생년도(+보정)를 시대 라벨로 변환."""
    if override:
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


def genre_counts(qs):
    """필터된 TimeMusic 쿼리셋 → {장르: 선곡수}.

    players(M2M) 조인이 행을 부풀리지 않도록 prefetch 후 파이썬에서 집계하며,
    필터 조인으로 생길 수 있는 중복 행은 id 로 1회만 센다.
    """
    buckets = {label: 0 for label in GENRE_ORDER}
    seen = set()
    plays = qs.select_related("music", "orchestra").prefetch_related("players")
    for tm in plays:
        if tm.id in seen:
            continue
        seen.add(tm.id)
        instruments = [p.instrument for p in tm.players.all()]
        title = tm.music.title if tm.music_id else ""
        genre = genre_for(title, tm.orchestra_id is not None, instruments)
        buckets[genre] += 1
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


def build_timemusic_filter(params):
    """쿼리 파라미터를 TimeMusic 필터(Q 객체)로 변환.

    지원 파라미터: start, end (YYYY-MM-DD), semester_id, user_id, include_mentees.
    적용된 필터 정보를 함께 돌려준다(응답 봉투의 filters 필드).
    start/end/semester_id/user_id 형식이 틀리면 ValidationError(400)를 던진다.
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


def _top_by(qs, group_field, name_field, limit, id_field=None):
    """공통 top-N 집계. labels/values/items 봉투 부분을 만든다."""
    id_field = id_field or group_field
    rows = (
        qs.values(id_field, name_field)
        .annotate(count=Count("id", distinct=True))
        .order_by("-count")[:limit]
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
    """헤더 KPI 카드용 요약 수치."""

    def get(self, request):
        qs, applied = base_queryset(request)
        agg = qs.aggregate(
            total_plays=Count("id"),
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
    def get(self, request):
        qs, applied = base_queryset(request)
        total = qs.count()
        limit = _limit(request)
        rows = (
            qs.exclude(music__isnull=True)
            .values("music__id", "music__title", "music__composer__name")
            .annotate(count=Count("id", distinct=True))
            .order_by("-count")[:limit]
        )
        labels, values, items = [], [], []
        for row in rows:
            composer = row["music__composer__name"] or ""
            title = row["music__title"]
            label = f"{composer} - {title}" if composer else title
            labels.append(label)
            values.append(row["count"])
            items.append({"id": row["music__id"], "name": label, "count": row["count"]})
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
    distinct 로 센다.
    """

    def get(self, request):
        qs, applied = base_queryset(request)
        total = qs.count()
        rows = (
            qs.exclude(players__isnull=True)
            .values("players__id", "players__name", "players__instrument")
            .annotate(count=Count("id", distinct=True))
            .order_by("-count")[: _limit(request)]
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


class PlaysOverTimeStatsView(APIView):
    """기간별 선곡 추이. ?bucket=week|month|semester (기본 month)."""

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
            labels, values = [], []
            for row in rows:
                period = row["period"]
                if period is None:
                    continue
                labels.append(
                    period.strftime("%Y-%m-%d" if bucket == "week" else "%Y-%m")
                )
                values.append(row["count"])

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

        plays = qs.select_related(
            "time", "music", "music__composer", "orchestra"
        ).prefetch_related("players")

        era_all = defaultdict(int)
        genre_all = defaultdict(int)
        works = set()
        composers = set()
        per_era = defaultdict(lambda: defaultdict(int))
        per_genre = defaultdict(lambda: defaultdict(int))
        per_plays = defaultdict(int)
        per_works = defaultdict(set)

        seen = set()
        total = 0
        for tm in plays:
            if tm.id in seen:
                continue
            seen.add(tm.id)
            total += 1

            date = tm.time.date
            if bucket == "week":
                start = date - datetime.timedelta(days=date.weekday())
                key = start.strftime("%Y-%m-%d")
            else:
                key = date.strftime("%Y-%m")

            composer = (
                tm.music.composer if (tm.music_id and tm.music.composer_id) else None
            )
            era = (
                era_for(composer.birth_year, composer.era_override)
                if composer
                else "미상"
            )

            instruments = [p.instrument for p in tm.players.all()]
            title = tm.music.title if tm.music_id else ""
            genre = genre_for(title, tm.orchestra_id is not None, instruments)

            era_all[era] += 1
            genre_all[genre] += 1
            per_era[key][era] += 1
            per_genre[key][genre] += 1
            per_plays[key] += 1
            if tm.music_id:
                works.add(tm.music_id)
                per_works[key].add(tm.music_id)
            if composer:
                composers.add(composer.id)

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
