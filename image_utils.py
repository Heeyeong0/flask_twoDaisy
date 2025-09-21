import os
import pathlib
from flask import Flask, request, jsonify, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# ------- 설정 -------
BASE_DIR = pathlib.Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB

# ------- 공통 유틸 -------

def is_allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def unique_path(upload_dir: pathlib.Path, filename: str) -> pathlib.Path:
    """중복 방지 파일 경로 생성"""
    filename = secure_filename(filename)
    stem = pathlib.Path(filename).stem
    suffix = pathlib.Path(filename).suffix
    target = upload_dir / filename
    counter = 1
    while target.exists():
        target = upload_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    return target

def save_file_and_get_url(file_storage) -> str:
    """FileStorage 1개 저장 후 외부 접근 URL 반환"""
    if not file_storage or file_storage.filename == "":
        raise ValueError("파일이 비어있습니다.")
    if not is_allowed(file_storage.filename):
        raise ValueError(f"허용되지 않는 확장자: {file_storage.filename}")
    target = unique_path(UPLOAD_DIR, file_storage.filename)
    file_storage.save(target)
    # Flask 기본 static 라우트 활용
    rel = target.relative_to(BASE_DIR / "static")
    return url_for("static", filename=str(rel).replace("\\", "/"), _external=True)

def save_files_and_get_urls(files) -> list:
    urls = []
    for f in files:
        try:
            urls.append(save_file_and_get_url(f))
        except Exception as e:
            # 일부 실패해도 나머지 진행: 필요 시 정책에 맞게 전체 실패 처리로 바꿔도 됨
            print(f"❌ 업로드 실패: {getattr(f, 'filename', '')} - {e}")
    return urls
