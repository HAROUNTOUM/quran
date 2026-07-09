from django.contrib import admin

from .models import Ayah, EvaluationCriterion, Hizb, Juz, Rub, Surah, Thumn


@admin.register(Thumn)
class ThumnAdmin(admin.ModelAdmin):
    list_display = ("number", "rub", "number_in_hizb", "page", "start_surah", "start_ayah_number")
    list_filter = ("rub__hizb__juz",)
    ordering = ("number",)
    list_select_related = ("rub", "start_surah")
    raw_id_fields = ("rub", "start_surah")


@admin.register(Surah)
class SurahAdmin(admin.ModelAdmin):
    list_display = ("id", "name_ar", "name_en", "ayah_count", "revelation_type")
    search_fields = ("name_ar", "name_en")
    list_filter = ("revelation_type",)


@admin.register(Juz)
class JuzAdmin(admin.ModelAdmin):
    list_display = ("number", "ayah_count")
    ordering = ("number",)


@admin.register(Hizb)
class HizbAdmin(admin.ModelAdmin):
    list_display = ("number", "juz", "number_in_juz")
    list_filter = ("juz",)
    ordering = ("number",)


@admin.register(Rub)
class RubAdmin(admin.ModelAdmin):
    list_display = ("number", "hizb", "number_in_hizb", "label")
    list_filter = ("hizb__juz",)
    ordering = ("number",)

    def label(self, obj):
        return obj.label()
    label.short_description = "النطاق"


@admin.register(Ayah)
class AyahAdmin(admin.ModelAdmin):
    list_display = ("verse_key", "surah", "number_in_surah", "page", "sajdah")
    list_filter = ("page", "sajdah", "rub__hizb__juz")
    search_fields = ("text_normalized", "text_uthmani")
    list_select_related = ("surah",)
    raw_id_fields = ("surah", "rub")


@admin.register(EvaluationCriterion)
class EvaluationCriterionAdmin(admin.ModelAdmin):
    list_display = ("name_ar", "weight", "is_active")
    list_editable = ("weight", "is_active")
