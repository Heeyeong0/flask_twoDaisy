
import pathlib
from flask import Flask, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename


app = Flask(__name__)
CORS(app)
# ------- 설정 -------
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent  # src의 상위 = 프로젝트 루트
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

def save_file_and_get_name(file_storage) -> str:
    """FileStorage 1개 저장 후 난수화된 파일명 반환"""
    if not file_storage or file_storage.filename == "":
        raise ValueError("파일이 비어있습니다.")
    if not is_allowed(file_storage.filename):
        raise ValueError(f"허용되지 않는 확장자: {file_storage.filename}")

    # 확장자 추출
    ext = Path(secure_filename(file_storage.filename)).suffix.lower()
    new_name = f"{uuid.uuid4().hex}{ext}"

    target = UPLOAD_DIR / new_name
    file_storage.save(target)

    # URL 대신 파일 이름만 반환
    return new_name