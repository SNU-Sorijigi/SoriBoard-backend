"""Catalog quality: spelling variants that split the counts.

GET catalog/duplicates/?kind=composer|player|conductor|orchestra|music (default
composer) groups the rows whose normalized names match, so "J. S. Bach" and
"J.S. Bach" show up as one group. Works are grouped by composer row plus
catalog number (extract_catalog_ids), so "Op. 67" and "op.67" of one composer
match. Read-only: nothing is merged.

    {
        "kind": "composer",
        "groups": [
            {"key": "jsbach", "count": 4, "rows": [{id, name, count}, ...]},
        ],
    }

count is the number of plays: per row, and the sum per group. Groups come
most played first, then by key; rows most played first, then by name, then id.
Player rows add instrument; music rows (name = title) add composer_id and
composer_name.
"""

import unicodedata
from collections import defaultdict

from django.db.models import Count
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Composer, Conductor, Music, Orchestra, Player
from .views import extract_catalog_ids


def normalize_name(name):
    """The form names are compared in: NFKC (decomposed Hangul and full-width
    letters read as typed ones), casefolded, without whitespace, dots or
    dashes (any Unicode dash: "-", "‐", "–", ...)."""
    name = unicodedata.normalize("NFKC", name).casefold()
    return "".join(
        char
        for char in name
        if not (char.isspace() or char == "." or unicodedata.category(char) == "Pd")
    )


def _rows(kind):
    """Each catalog row of the kind with its play count, in one query."""
    if kind == "composer":
        return Composer.objects.values("id", "name").annotate(
            count=Count("musics__timemusic")
        )
    if kind == "player":
        return Player.objects.values("id", "name", "instrument").annotate(
            count=Count("timemusic")
        )
    if kind == "music":
        return Music.objects.values(
            "id", "title", "composer_id", "composer__name"
        ).annotate(count=Count("timemusic"))
    model = Conductor if kind == "conductor" else Orchestra
    return model.objects.values("id", "name").annotate(count=Count("timemusic"))


def _row(kind, values):
    if kind == "music":
        return {
            "id": values["id"],
            "name": values["title"],
            "count": values["count"],
            "composer_id": values["composer_id"],
            "composer_name": values["composer__name"],
        }
    row = {"id": values["id"], "name": values["name"], "count": values["count"]}
    if kind == "player":
        row["instrument"] = values["instrument"]
    return row


def duplicate_groups(kind):
    """The groups of two or more rows of the kind that share a key."""
    groups = defaultdict(list)
    for values in _rows(kind):
        row = _row(kind, values)
        if kind == "music":
            # A title with two catalog numbers can be in two groups.
            for key in extract_catalog_ids(row["name"]):
                groups[(row["composer_id"], key)].append(row)
        else:
            groups[normalize_name(row["name"])].append(row)

    result = []
    for group_key, rows in groups.items():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda row: (-row["count"], row["name"], row["id"]))
        key = group_key[1] if kind == "music" else group_key
        result.append(
            {"key": key, "count": sum(row["count"] for row in rows), "rows": rows}
        )
    result.sort(
        key=lambda group: (-group["count"], group["key"], group["rows"][0]["id"])
    )
    return result


class DuplicatesQuerySerializer(serializers.Serializer):
    """catalog/duplicates parameters. A blank kind is composer."""

    kind = serializers.ChoiceField(
        choices=["composer", "player", "conductor", "orchestra", "music"],
        required=False,
        allow_blank=True,
    )


class CatalogDuplicatesView(APIView):
    """Groups of catalog rows that are probably one composer, player,
    conductor, orchestra or work spelled in different ways."""

    def get(self, request):
        params = DuplicatesQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        kind = params.validated_data.get("kind") or "composer"
        return Response({"kind": kind, "groups": duplicate_groups(kind)})
