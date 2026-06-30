from rest_framework.exceptions import ValidationError as DRFValidationError


SURAH_AYAH_COUNTS = {
    1: 7, 2: 286, 3: 200, 4: 176, 5: 120, 6: 165, 7: 206, 8: 75, 9: 129,
    10: 109, 11: 123, 12: 111, 13: 43, 14: 52, 15: 99, 16: 128, 17: 111,
    18: 110, 19: 98, 20: 135, 21: 112, 22: 78, 23: 118, 24: 64, 25: 77,
    26: 227, 27: 93, 28: 88, 29: 69, 30: 60, 31: 34, 32: 30, 33: 73,
    34: 54, 35: 45, 36: 83, 37: 182, 38: 88, 39: 75, 40: 85, 41: 54,
    42: 53, 43: 89, 44: 59, 45: 37, 46: 35, 47: 38, 48: 29, 49: 18,
    50: 45, 51: 60, 52: 49, 53: 62, 54: 55, 55: 78, 56: 96, 57: 29,
    58: 22, 59: 24, 60: 13, 61: 14, 62: 11, 63: 11, 64: 18, 65: 12,
    66: 12, 67: 30, 68: 52, 69: 52, 70: 44, 71: 28, 72: 28, 73: 20,
    74: 56, 75: 40, 76: 31, 77: 50, 78: 40, 79: 46, 80: 42, 81: 29,
    82: 19, 83: 36, 84: 25, 85: 22, 86: 17, 87: 19, 88: 26, 89: 30,
    90: 20, 91: 15, 92: 21, 93: 11, 94: 8, 95: 8, 96: 19, 97: 5,
    98: 8, 99: 8, 100: 11, 101: 11, 102: 8, 103: 3, 104: 9, 105: 5,
    106: 4, 107: 7, 108: 3, 109: 6, 110: 3, 111: 5, 112: 4, 113: 5,
    114: 6,
}


def validate_ayah_range(surah_number, start_ayah, end_ayah):
    max_ayahs = SURAH_AYAH_COUNTS.get(surah_number)
    if max_ayahs is None:
        raise DRFValidationError(
            f"رقم السورة {surah_number} غير صالح. يجب أن يكون بين 1 و 114"
        )
    if start_ayah < 1:
        raise DRFValidationError("بداية الآية يجب أن تكون 1 أو أكثر")
    if end_ayah > max_ayahs:
        raise DRFValidationError(
            f"نهاية الآية {end_ayah} تتجاوز الحد الأقصى لآيات السورة ({max_ayahs}). "
            f"سورة رقم {surah_number} تحتوي على {max_ayahs} آية فقط"
        )
    if start_ayah > end_ayah:
        raise DRFValidationError("بداية الآية يجب أن تكون أقل من أو تساوي نهاية الآية")


def compute_completed_pages(start_ayah, end_ayah):
    ayat_count = end_ayah - start_ayah + 1
    pages = ayat_count / 20.0
    return round(pages, 2)
