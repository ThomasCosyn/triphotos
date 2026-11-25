"""Tests du module dates : parsing EXIF, ISO 8601 / RFC 3339, cascade de repli."""

import os
from datetime import datetime
from pathlib import Path

from PIL import Image

from photos_importer import dates
from photos_importer.dates import (
    date_exif,
    date_modtime_rfc3339,
    date_prise,
    parse_exif_date,
    parse_iso8601,
)


def _jpeg_avec_exif(chemin: Path, tags: dict[int, str]) -> None:
    img = Image.new("RGB", (8, 8), (200, 10, 10))
    exif = Image.Exif()
    for tag, valeur in tags.items():
        exif[tag] = valeur
    img.save(chemin, exif=exif)


def test_parse_exif_date_valide():
    assert parse_exif_date("2024:07:15 10:30:00") == datetime(2024, 7, 15, 10, 30, 0)


def test_parse_exif_date_avec_nul_final():
    assert parse_exif_date("2024:07:15 10:30:00\x00") == datetime(2024, 7, 15, 10, 30, 0)


def test_parse_exif_date_nulle_ou_corrompue():
    assert parse_exif_date("0000:00:00 00:00:00") is None
    assert parse_exif_date("0000:01:01 00:00:00") is None
    assert parse_exif_date("hier soir") is None
    assert parse_exif_date("") is None
    assert parse_exif_date(None) is None


def test_date_exif_datetime_original_prioritaire(tmp_path):
    p = tmp_path / "a.jpg"
    _jpeg_avec_exif(p, {36867: "2024:07:15 10:30:00", 306: "2020:01:01 00:00:00"})
    assert date_exif(p) == datetime(2024, 7, 15, 10, 30, 0)


def test_date_exif_repli_sur_tag_306(tmp_path):
    p = tmp_path / "b.jpg"
    _jpeg_avec_exif(p, {306: "2021:12:31 23:59:59"})
    assert date_exif(p) == datetime(2021, 12, 31, 23, 59, 59)


def test_date_exif_sans_exif(tmp_path):
    p = tmp_path / "c.jpg"
    Image.new("RGB", (8, 8)).save(p)
    assert date_exif(p) is None


def test_date_exif_fichier_illisible(tmp_path):
    p = tmp_path / "corrompu.jpg"
    p.write_bytes(b"ceci n'est pas une image")
    assert date_exif(p) is None
    assert date_exif(tmp_path / "absent.jpg") is None


def test_parse_iso8601():
    assert parse_iso8601("2024-07-15T10:30:00Z") == datetime(2024, 7, 15, 10, 30, 0)
    assert parse_iso8601("2024-07-15T10:30:00") == datetime(2024, 7, 15, 10, 30, 0)
    brut = "2024-07-15T10:30:00.123456789+02:00"
    assert parse_iso8601(brut) == datetime(2024, 7, 15, 10, 30, 0, 123456)
    assert parse_iso8601("2024-07-15T10:30:00.5Z") == datetime(2024, 7, 15, 10, 30, 0, 500000)
    assert parse_iso8601("bidon") is None
    assert parse_iso8601("") is None


def test_date_modtime_rfc3339_rclone():
    assert date_modtime_rfc3339("2024-07-15T10:30:00.000000000Z") == datetime(2024, 7, 15, 10, 30)
    assert date_modtime_rfc3339("garbage") is None


def test_date_prise_video_ffprobe_puis_modtime(tmp_path, monkeypatch):
    p = tmp_path / "video.mp4"
    p.write_bytes(b"x")
    monkeypatch.setattr(dates, "date_exif", lambda _: None)
    monkeypatch.setattr(dates, "date_video", lambda _: datetime(2022, 3, 4, 5, 6, 7))
    assert date_prise(p) == datetime(2022, 3, 4, 5, 6, 7)
    monkeypatch.setattr(dates, "date_video", lambda _: None)
    assert date_prise(p, modtime="2023-08-09T01:02:03Z") == datetime(2023, 8, 9, 1, 2, 3)


def test_date_prise_image_exif_puis_modtime(tmp_path, monkeypatch):
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"x")
    monkeypatch.setattr(dates, "date_exif", lambda _: datetime(2024, 1, 2, 3, 4, 5))
    assert date_prise(p, modtime="2023-08-09T01:02:03Z") == datetime(2024, 1, 2, 3, 4, 5)
    monkeypatch.setattr(dates, "date_exif", lambda _: None)
    assert date_prise(p, modtime="2023-08-09T01:02:03Z") == datetime(2023, 8, 9, 1, 2, 3)


def test_date_prise_son_wav_ffprobe(tmp_path, monkeypatch):
    from photos_importer import dates

    p = tmp_path / "son.wav"
    p.write_bytes(b"x")
    monkeypatch.setattr(dates, "date_video", lambda _: datetime(2008, 6, 1, 12, 0, 0))
    assert dates.date_prise(p) == datetime(2008, 6, 1, 12, 0, 0)


def test_date_prise_video_mts_ffprobe(tmp_path, monkeypatch):
    from photos_importer import dates

    p = tmp_path / "video.MTS"
    p.write_bytes(b"x")
    monkeypatch.setattr(dates, "date_video", lambda _: datetime(2008, 6, 1, 12, 0, 0))
    assert dates.date_prise(p) == datetime(2008, 6, 1, 12, 0, 0)


def test_date_prise_repli_mtime_puis_maintenant(tmp_path, monkeypatch):
    p = tmp_path / "f.bin"
    p.write_bytes(b"x")
    stamp = datetime(2020, 5, 6, 7, 8, 9).timestamp()
    os.utime(p, (stamp, stamp))
    assert date_prise(p) == datetime(2020, 5, 6, 7, 8, 9)


def test_chemin_yyyy_mm_zero_padded():
    assert dates.chemin_yyyy_mm(datetime(2024, 7, 1)) == "2024/07"
    assert dates.chemin_yyyy_mm(datetime(1999, 12, 31)) == "1999/12"
