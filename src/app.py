from flask import request
from openai_test import run_images
from flask import jsonify
from werkzeug.exceptions import HTTPException
from image_utils import *
from run_image_service import *

app = Flask(__name__)
CORS(app)

@app.route('/')
def hello():

    return "Hello, Flask!"


@app.route('/analyze-images', methods=['POST'])
def analyze_images_route():
    """
    JSON:
    - {"url": "/static/uploads/a.png"}
    - {"urls": ["/static/uploads/a.png", "/static/uploads/b.jpg"]}
    """
    urls = extract_image_filenames(request)
    if not urls:
        raise ValueError("이미지 URL이 필요합니다. (url 또는 urls)")

    result = run_images(urls)
    return result
# ------- 이미지 업로드 -------

@app.route("/upload-image", methods=["POST"])
def upload_image():
    """
    단일 이미지 업로드
    - form-data: { image: <파일> }
    응답: {"url": "..."}
    """
    file = request.files.get("image")
    if not file or file.filename == "":
        return jsonify({"error": "image 필드로 파일을 전송하세요."}), 400

    try:
        file_name = save_file_and_get_name(file)  # 앞서 만든 공통 유틸 사용
        return jsonify({"name": file_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.errorhandler(Exception)
def handle_exception(e):
    # HTTPException (Flask/werkzeug 기본 예외: 404, 400 등)
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code

    # 나머지 일반 Exception → 500
    return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=8000)
